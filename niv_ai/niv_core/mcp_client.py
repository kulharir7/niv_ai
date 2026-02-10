"""
MCP (Model Context Protocol) Client for Niv AI

High-performance, cached MCP client.
- Tool-to-server index for instant lookup
- Session reuse (no re-initialize per call)
- Supports stdio, SSE, and streamable-http transports
- JSON-RPC 2.0 protocol — no mcp pip package needed
"""

import json
import os
import subprocess
import threading
import time
import frappe
from typing import Dict, Any, List, Optional


# ─── Global Caches ─────────────────────────────────────────────────

_cache_lock = threading.Lock()

# Tool discovery cache: server_name → {"tools": [...], "expires": ts}
_tools_cache = {}

# Tool-to-server index: tool_name → server_name (instant lookup)
_tool_index = {}
_tool_index_expires = 0

# OpenAI format cache for get_available_tools
_openai_tools_cache = {"tools": [], "expires": 0}

# HTTP session reuse
_http_sessions = {}

CACHE_TTL = 300  # 5 minutes


class MCPError(Exception):
    pass


def _next_id():
    """Thread-safe incrementing ID."""
    if not hasattr(_next_id, "_counter"):
        _next_id._counter = 0
        _next_id._lock = threading.Lock()
    with _next_id._lock:
        _next_id._counter += 1
        return _next_id._counter


def _jsonrpc(method, params=None, req_id=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if req_id is not None:
        msg["id"] = req_id
    return msg


def _get_http_session(url):
    """Reuse HTTP session per server URL for connection pooling."""
    import requests
    base = url.split("/api/")[0] if "/api/" in url else url
    if base not in _http_sessions:
        _http_sessions[base] = requests.Session()
    return _http_sessions[base]


# ─── Stdio Transport ───────────────────────────────────────────────

def _stdio_session(command, args_str, env_vars_str):
    cmd = command.strip()
    args = args_str.strip().split() if args_str else []
    env_extra = json.loads(env_vars_str or "{}") if env_vars_str else {}
    env = {**os.environ, **env_extra}

    proc = subprocess.Popen(
        [cmd] + args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    def send(msg):
        data = json.dumps(msg) + "\n"
        proc.stdin.write(data.encode())
        proc.stdin.flush()

    def recv(timeout=15):
        start = time.time()
        while time.time() - start < timeout:
            line = proc.stdout.readline()
            if line:
                text = line.decode().strip()
                if text:
                    return json.loads(text)
            time.sleep(0.05)
        raise MCPError("Timeout waiting for stdio MCP response")

    return proc, send, recv


def _stdio_initialize(command, args_str, env_vars_str):
    proc, send, recv = _stdio_session(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "niv-ai", "version": "0.2.0"},
        }, req_id=_next_id()))
        recv()
        send(_jsonrpc("notifications/initialized"))
        return proc, send, recv
    except Exception:
        proc.terminate()
        raise


def stdio_list_tools(command, args_str, env_vars_str) -> List[Dict]:
    proc, send, recv = _stdio_initialize(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("tools/list", {}, req_id=_next_id()))
        resp = recv()
        return resp.get("result", {}).get("tools", [])
    finally:
        proc.terminate()


def stdio_call_tool(command, args_str, env_vars_str, tool_name, arguments) -> Any:
    proc, send, recv = _stdio_initialize(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, req_id=_next_id()))
        resp = recv(timeout=30)
        if "error" in resp:
            raise MCPError(resp["error"].get("message", str(resp["error"])))
        return resp.get("result", {})
    finally:
        proc.terminate()


# ─── HTTP Transport (streamable-http) ──────────────────────────────

def _build_headers(api_key=None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        if ":" in api_key:
            headers["Authorization"] = f"token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    # Frappe multi-site Host header
    try:
        site = frappe.local.site if hasattr(frappe.local, "site") else None
        if site:
            headers["Host"] = site
    except Exception:
        pass
    return headers


def _http_post(url, payload, api_key=None, timeout=15):
    session = _get_http_session(url)
    headers = _build_headers(api_key)
    resp = session.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# MCP session init cache: url → {"initialized": True, "expires": ts}
_mcp_init_cache = {}
_MCP_INIT_TTL = 600  # 10 min — sessions usually persist


def _ensure_initialized(url, api_key=None):
    """Initialize MCP session only if not already done (cached)."""
    cache_key = url
    cached = _mcp_init_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return  # Already initialized

    try:
        _http_post(url, _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "niv-ai", "version": "0.2.0"},
        }, req_id=_next_id()), api_key)
        try:
            _http_post(url, _jsonrpc("notifications/initialized"), api_key, timeout=5)
        except Exception:
            pass
        _mcp_init_cache[cache_key] = {"initialized": True, "expires": time.time() + _MCP_INIT_TTL}
    except Exception:
        # Init failed — remove stale cache, let caller handle
        _mcp_init_cache.pop(cache_key, None)
        raise


def http_list_tools(url, api_key=None) -> List[Dict]:
    _ensure_initialized(url, api_key)
    resp = _http_post(url, _jsonrpc("tools/list", {}, req_id=_next_id()), api_key)
    return resp.get("result", {}).get("tools", [])


def http_call_tool(url, api_key, tool_name, arguments) -> Any:
    _ensure_initialized(url, api_key)
    resp = _http_post(url, _jsonrpc("tools/call", {
        "name": tool_name, "arguments": arguments
    }, req_id=_next_id()), api_key, timeout=30)
    if "error" in resp:
        raise MCPError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result", {})


# ─── SSE Transport ─────────────────────────────────────────────────

def _sse_request(url, payload, api_key=None, timeout=30):
    import requests
    headers = _build_headers(api_key)
    headers["Accept"] = "text/event-stream"
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        return resp.json()

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if not data_str:
            continue
        try:
            data = json.loads(data_str)
            if isinstance(data, dict) and ("result" in data or "error" in data):
                return data
        except json.JSONDecodeError:
            continue

    raise MCPError("No valid response from SSE stream")


def _ensure_sse_initialized(url, api_key=None):
    """Initialize MCP SSE session (cached like HTTP)."""
    cache_key = f"sse_{url}"
    cached = _mcp_init_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return

    try:
        _sse_request(url, _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "niv-ai", "version": "0.2.0"},
        }, req_id=_next_id()), api_key)
        try:
            _sse_request(url, _jsonrpc("notifications/initialized"), api_key, timeout=5)
        except Exception:
            pass
        _mcp_init_cache[cache_key] = {"initialized": True, "expires": time.time() + _MCP_INIT_TTL}
    except Exception:
        _mcp_init_cache.pop(cache_key, None)
        raise


def sse_list_tools(url, api_key=None) -> List[Dict]:
    _ensure_sse_initialized(url, api_key)
    resp = _sse_request(url, _jsonrpc("tools/list", {}, req_id=_next_id()), api_key)
    return resp.get("result", {}).get("tools", [])


def sse_call_tool(url, api_key, tool_name, arguments) -> Any:
    _ensure_sse_initialized(url, api_key)
    resp = _sse_request(url, _jsonrpc("tools/call", {
        "name": tool_name, "arguments": arguments
    }, req_id=_next_id()), api_key, timeout=30)
    if "error" in resp:
        raise MCPError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result", {})


# ─── Server Config Helpers ─────────────────────────────────────────

def _get_api_key(doc):
    try:
        return doc.get_password("api_key") if doc.api_key else None
    except Exception:
        return None


def _get_server_config(server_name):
    """Get server doc with basic info. Cached per-request via frappe.local."""
    cache_key = f"mcp_server_{server_name}"
    if hasattr(frappe.local, cache_key):
        return getattr(frappe.local, cache_key)
    doc = frappe.get_doc("Niv MCP Server", server_name)
    setattr(frappe.local, cache_key, doc)
    return doc


# ─── High-Level API ────────────────────────────────────────────────

def get_all_active_servers() -> List[str]:
    """Get names of all active MCP servers."""
    return [d.name for d in frappe.get_all("Niv MCP Server", filters={"is_active": 1}, fields=["name"])]


def discover_tools(server_name: str, use_cache: bool = True) -> List[Dict]:
    """Discover tools from an MCP server. Returns list of MCP tool dicts."""
    if use_cache:
        with _cache_lock:
            cached = _tools_cache.get(server_name)
            if cached and cached["expires"] > time.time():
                return cached["tools"]

    doc = _get_server_config(server_name)
    if not doc.is_active:
        return []

    tools = []
    try:
        if doc.transport_type == "stdio":
            tools = stdio_list_tools(doc.command, doc.args, doc.env_vars)
        elif doc.transport_type == "streamable-http":
            tools = http_list_tools(doc.server_url, _get_api_key(doc))
        elif doc.transport_type == "sse":
            tools = sse_list_tools(doc.server_url, _get_api_key(doc))
        else:
            frappe.logger().warning(f"Niv MCP: Unknown transport '{doc.transport_type}' for '{server_name}'")
            return []
    except Exception as e:
        frappe.logger().error(f"Niv MCP: Failed to discover tools from '{server_name}': {e}")
        return []

    with _cache_lock:
        _tools_cache[server_name] = {"tools": tools, "expires": time.time() + CACHE_TTL}

    return tools


def _rebuild_tool_index():
    """Rebuild the tool_name → server_name index from all active servers."""
    global _tool_index, _tool_index_expires
    new_index = {}
    for server_name in get_all_active_servers():
        try:
            tools = discover_tools(server_name)
            for tool in tools:
                name = tool.get("name", "")
                if name and name not in new_index:
                    new_index[name] = server_name
        except Exception:
            continue

    with _cache_lock:
        _tool_index = new_index
        _tool_index_expires = time.time() + CACHE_TTL


def find_tool_server(tool_name: str) -> Optional[str]:
    """Find which MCP server has this tool. Uses cached index — instant lookup."""
    global _tool_index_expires

    with _cache_lock:
        if _tool_index_expires > time.time() and tool_name in _tool_index:
            return _tool_index[tool_name]

    # Cache miss or expired — rebuild
    _rebuild_tool_index()

    with _cache_lock:
        return _tool_index.get(tool_name)


def call_tool_fast(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool on an MCP server. Uses session reuse."""
    doc = _get_server_config(server_name)

    if doc.transport_type == "stdio":
        return stdio_call_tool(doc.command, doc.args, doc.env_vars, tool_name, arguments)
    elif doc.transport_type == "streamable-http":
        return http_call_tool(doc.server_url, _get_api_key(doc), tool_name, arguments)
    elif doc.transport_type == "sse":
        return sse_call_tool(doc.server_url, _get_api_key(doc), tool_name, arguments)
    else:
        raise MCPError(f"Unknown transport: {doc.transport_type}")


def get_all_mcp_tools_cached() -> List[Dict]:
    """
    Get all MCP tools in OpenAI function calling format.
    Cached for performance — no repeated HTTP calls.
    """
    global _openai_tools_cache

    with _cache_lock:
        if _openai_tools_cache["expires"] > time.time() and _openai_tools_cache["tools"]:
            return _openai_tools_cache["tools"]

    result = []
    seen_names = set()

    for server_name in get_all_active_servers():
        try:
            tools = discover_tools(server_name)
            for tool in tools:
                name = tool.get("name", "")
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                params = tool.get("inputSchema", {"type": "object", "properties": {}})
                result.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", name),
                        "parameters": params,
                    },
                })
        except Exception as e:
            frappe.logger().error(f"Niv MCP: Error getting tools from '{server_name}': {e}")

    # Also rebuild tool index while we're at it
    global _tool_index, _tool_index_expires
    with _cache_lock:
        _openai_tools_cache = {"tools": result, "expires": time.time() + CACHE_TTL}

    _rebuild_tool_index()

    return result


# ─── Legacy API compatibility ──────────────────────────────────────

def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy wrapper — use call_tool_fast instead."""
    server_name = find_tool_server(tool_name)
    if not server_name:
        return {"error": f"MCP tool '{tool_name}' not found on any active server"}
    try:
        result = call_tool_fast(server_name, tool_name, arguments)
        if isinstance(result, dict) and "content" in result:
            contents = result["content"]
            if isinstance(contents, list):
                text_parts = []
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                    elif isinstance(c, dict):
                        text_parts.append(json.dumps(c))
                    else:
                        text_parts.append(str(c))
                return {"success": True, "result": "\n".join(text_parts)}
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"MCP tool execution failed: {e}"}


def get_all_mcp_tools() -> List[Dict]:
    """Legacy wrapper."""
    return get_all_mcp_tools_cached()


def call_tool(server_name, tool_name, arguments):
    """Legacy wrapper."""
    return call_tool_fast(server_name, tool_name, arguments)


def clear_cache(server_name: str = None):
    """Clear all caches."""
    global _tool_index_expires, _openai_tools_cache
    with _cache_lock:
        if server_name:
            _tools_cache.pop(server_name, None)
        else:
            _tools_cache.clear()
        _tool_index.clear()
        _tool_index_expires = 0
        _openai_tools_cache = {"tools": [], "expires": 0}
        _mcp_init_cache.clear()
