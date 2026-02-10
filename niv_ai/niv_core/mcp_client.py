"""
MCP (Model Context Protocol) Client for Niv AI

Synchronous, thread-safe MCP client supporting stdio, SSE, and streamable-http transports.
Implements JSON-RPC 2.0 protocol directly — no mcp pip package needed.
"""

import json
import os
import subprocess
import threading
import time
import frappe
from typing import Dict, Any, List, Optional


# Global cache: server_name -> {"tools": [...], "expires": timestamp}
_tools_cache = {}
_cache_lock = threading.Lock()
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


def _jsonrpc(method, params=None, id=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if id is not None:
        msg["id"] = id
    return msg


# ─── Stdio Transport ───────────────────────────────────────────────

def _stdio_session(command, args_str, env_vars_str):
    """Run a stdio MCP session. Returns (initialize_result, process) after handshake."""
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
        import select
        start = time.time()
        while time.time() - start < timeout:
            line = proc.stdout.readline()
            if line:
                text = line.decode().strip()
                if text:
                    return json.loads(text)
            time.sleep(0.05)
        raise MCPError("Timeout waiting for MCP server response")

    return proc, send, recv


def _stdio_initialize(command, args_str, env_vars_str):
    """Full initialize handshake over stdio. Returns (proc, send, recv, init_result)."""
    proc, send, recv = _stdio_session(command, args_str, env_vars_str)
    try:
        # Initialize
        send(_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "niv-ai", "version": "0.1.0"},
        }, id=_next_id()))
        init_resp = recv()

        # Send initialized notification
        send(_jsonrpc("notifications/initialized"))

        return proc, send, recv, init_resp
    except Exception:
        proc.terminate()
        raise


def stdio_list_tools(command, args_str, env_vars_str) -> List[Dict]:
    """Connect via stdio, initialize, list tools, disconnect."""
    proc, send, recv, _ = _stdio_initialize(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("tools/list", {}, id=_next_id()))
        resp = recv()
        return resp.get("result", {}).get("tools", [])
    finally:
        proc.terminate()


def stdio_call_tool(command, args_str, env_vars_str, tool_name, arguments) -> Any:
    """Connect via stdio, initialize, call tool, disconnect."""
    proc, send, recv, _ = _stdio_initialize(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, id=_next_id()))
        resp = recv(timeout=30)
        if "error" in resp:
            raise MCPError(resp["error"].get("message", str(resp["error"])))
        return resp.get("result", {})
    finally:
        proc.terminate()


# ─── HTTP Transport (streamable-http) ──────────────────────────────

def _http_post(url, payload, api_key=None, timeout=15):
    import requests
    headers = {"Content-Type": "application/json"}
    if api_key:
        # Frappe/ERPNext uses "token key:secret" format
        if ":" in api_key:
            headers["Authorization"] = f"token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    # For Frappe multi-site, add Host header with site name
    if "localhost" in url or "127.0.0.1" in url:
        try:
            import frappe
            site = frappe.local.site if hasattr(frappe.local, "site") else None
            if site:
                headers["Host"] = site
        except Exception:
            pass
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _http_initialize(url, api_key=None):
    return _http_post(url, _jsonrpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "niv-ai", "version": "0.1.0"},
    }, id=_next_id()), api_key)


def http_list_tools(url, api_key=None) -> List[Dict]:
    _http_initialize(url, api_key)
    # Send initialized notification (fire-and-forget)
    try:
        _http_post(url, _jsonrpc("notifications/initialized"), api_key, timeout=5)
    except Exception:
        pass
    resp = _http_post(url, _jsonrpc("tools/list", {}, id=_next_id()), api_key)
    return resp.get("result", {}).get("tools", [])


def http_call_tool(url, api_key, tool_name, arguments) -> Any:
    _http_initialize(url, api_key)
    try:
        _http_post(url, _jsonrpc("notifications/initialized"), api_key, timeout=5)
    except Exception:
        pass
    resp = _http_post(url, _jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, id=_next_id()), api_key, timeout=30)
    if "error" in resp:
        raise MCPError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result", {})


# ─── SSE Transport ─────────────────────────────────────────────────

def _sse_request(url, payload, api_key=None, timeout=30):
    """POST JSON-RPC to SSE endpoint and parse SSE response for the result."""
    import requests
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        if ":" in api_key:
            headers["Authorization"] = f"token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    if "localhost" in url or "127.0.0.1" in url:
        try:
            import frappe
            site = frappe.local.site if hasattr(frappe.local, "site") else None
            if site:
                headers["Host"] = site
        except Exception:
            pass

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
    resp.raise_for_status()

    # If response is JSON directly (some servers)
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        return resp.json()

    # Parse SSE stream for first data message with matching id
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

    raise MCPError("No valid response received from SSE stream")


def sse_list_tools(url, api_key=None) -> List[Dict]:
    _sse_request(url, _jsonrpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "niv-ai", "version": "0.1.0"},
    }, id=_next_id()), api_key)
    try:
        _sse_request(url, _jsonrpc("notifications/initialized"), api_key, timeout=5)
    except Exception:
        pass
    resp = _sse_request(url, _jsonrpc("tools/list", {}, id=_next_id()), api_key)
    return resp.get("result", {}).get("tools", [])


def sse_call_tool(url, api_key, tool_name, arguments) -> Any:
    _sse_request(url, _jsonrpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "niv-ai", "version": "0.1.0"},
    }, id=_next_id()), api_key)
    try:
        _sse_request(url, _jsonrpc("notifications/initialized"), api_key, timeout=5)
    except Exception:
        pass
    resp = _sse_request(url, _jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, id=_next_id()), api_key, timeout=30)
    if "error" in resp:
        raise MCPError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result", {})


# ─── High-Level API ────────────────────────────────────────────────

def _get_api_key(doc):
    """Safely get decrypted API key from doc."""
    try:
        return doc.get_password("api_key") if doc.api_key else None
    except Exception:
        return None


def discover_tools(server_name: str, use_cache: bool = True) -> List[Dict]:
    """
    Discover tools from an MCP server. Returns list of MCP tool dicts.
    Each tool has: name, description, inputSchema.
    """
    # Check cache
    if use_cache:
        with _cache_lock:
            cached = _tools_cache.get(server_name)
            if cached and cached["expires"] > time.time():
                return cached["tools"]

    doc = frappe.get_doc("Niv MCP Server", server_name)
    if not doc.is_active:
        return []

    tools = []
    transport = doc.transport_type

    try:
        if transport == "stdio":
            tools = stdio_list_tools(doc.command, doc.args, doc.env_vars)
        elif transport == "streamable-http":
            tools = http_list_tools(doc.server_url, _get_api_key(doc))
        elif transport == "sse":
            tools = sse_list_tools(doc.server_url, _get_api_key(doc))
        else:
            frappe.logger().warning(f"Niv AI MCP: Unknown transport '{transport}' for server '{server_name}'")
            return []
    except Exception as e:
        frappe.logger().error(f"Niv AI MCP: Failed to discover tools from '{server_name}': {e}")
        return []

    # Cache
    with _cache_lock:
        _tools_cache[server_name] = {"tools": tools, "expires": time.time() + CACHE_TTL}

    return tools


def call_tool(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool on an MCP server."""
    doc = frappe.get_doc("Niv MCP Server", server_name)
    transport = doc.transport_type

    if transport == "stdio":
        return stdio_call_tool(doc.command, doc.args, doc.env_vars, tool_name, arguments)
    elif transport == "streamable-http":
        return http_call_tool(doc.server_url, _get_api_key(doc), tool_name, arguments)
    elif transport == "sse":
        return sse_call_tool(doc.server_url, _get_api_key(doc), tool_name, arguments)
    else:
        raise MCPError(f"Unknown transport: {transport}")


def get_all_active_servers() -> List[str]:
    """Get names of all active MCP servers."""
    return [d.name for d in frappe.get_all("Niv MCP Server", filters={"is_active": 1}, fields=["name"])]


def get_all_mcp_tools() -> List[Dict]:
    """
    Get all tools from all active MCP servers in OpenAI function calling format.
    Gracefully skips servers that are down.
    """
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
            frappe.logger().error(f"Niv AI MCP: Error getting tools from '{server_name}': {e}")

    return result


def find_tool_server(tool_name: str) -> Optional[str]:
    """Find which MCP server provides a given tool. Returns server_name or None."""
    for server_name in get_all_active_servers():
        try:
            tools = discover_tools(server_name)
            for tool in tools:
                if tool.get("name") == tool_name:
                    return server_name
        except Exception:
            continue
    return None


def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find the MCP server that has this tool and execute it.
    Returns the result dict or {"error": "..."}.
    """
    server_name = find_tool_server(tool_name)
    if not server_name:
        return {"error": f"MCP tool '{tool_name}' not found on any active server"}

    try:
        result = call_tool(server_name, tool_name, arguments)
        # MCP tools/call returns {"content": [...]} — extract text
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
            return {"success": True, "result": str(contents)}
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"MCP tool execution failed: {e}"}


def clear_cache(server_name: str = None):
    """Clear tool cache for a server or all servers."""
    with _cache_lock:
        if server_name:
            _tools_cache.pop(server_name, None)
        else:
            _tools_cache.clear()
