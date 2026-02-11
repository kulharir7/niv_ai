"""
MCP Client for Niv AI — Official SDK Implementation

Uses `mcp` (official MCP Python SDK) + `langchain-mcp-adapters` for:
- Proper MCP protocol handling (session IDs, handshakes, transport)
- Automatic LangChain tool conversion
- Correct error handling and connection lifecycle

Sync wrapper around async SDK for Frappe/Gunicorn (WSGI) compatibility.
Redis caching + DB fallback for reliability.
Same-server deadlock protection retained.
"""

import asyncio
import json
import threading
import time
import frappe
from typing import Dict, Any, List, Optional


# ─── Async-to-Sync Bridge ─────────────────────────────────────────
# Frappe is WSGI (sync). MCP SDK is async. We bridge with a dedicated
# event loop running in a background thread.

_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _get_event_loop():
    """Get or create a persistent event loop in a background thread."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
        return _loop


def _run_async(coro):
    """Run an async coroutine from sync Frappe code. Thread-safe."""
    loop = _get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


# ─── Cache Layer (Redis + Worker Memory) ──────────────────────────

_cache_lock = threading.Lock()
_tools_cache = {}  # server_name -> {"tools": [...], "expires": ts}
_tool_index = {}  # tool_name -> server_name
_tool_index_expires = 0
_openai_tools_cache = {"tools": [], "expires": 0}

CACHE_TTL = 300  # 5 min
REDIS_CACHE_TTL = 600  # 10 min
REDIS_KEY_PREFIX = "niv_mcp_tools:"


class MCPError(Exception):
    pass


def _redis_set(key, value, ttl=REDIS_CACHE_TTL):
    """Set in Redis cache. v14+v15 compatible."""
    try:
        data = json.dumps(value) if not isinstance(value, str) else value
        try:
            frappe.cache().set_value(f"{REDIS_KEY_PREFIX}{key}", data, expires_in_sec=ttl)
        except TypeError:
            # v14 fallback
            frappe.cache().set_value(f"{REDIS_KEY_PREFIX}{key}", data)
    except Exception:
        pass


def _redis_get(key):
    """Get from Redis cache. Handles bytes (v14) and str (v15)."""
    try:
        data = frappe.cache().get_value(f"{REDIS_KEY_PREFIX}{key}")
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        if isinstance(data, str):
            return json.loads(data)
        return data
    except Exception:
        return None


def _redis_get_tools(server_name):
    return _redis_get(f"tools:{server_name}")


def _redis_set_tools(server_name, tools):
    _redis_set(f"tools:{server_name}", tools)


def _redis_get_openai_tools():
    return _redis_get("openai_tools")


def _redis_set_openai_tools(tools):
    _redis_set("openai_tools", tools)


def _redis_get_tool_index():
    return _redis_get("tool_index")


def _redis_set_tool_index(index):
    _redis_set("tool_index", index)


# ─── DB Fallback ──────────────────────────────────────────────────

def _db_get_tools(server_name):
    """Get tools from Niv MCP Server doc (always works, no network)."""
    try:
        doc = frappe.get_doc("Niv MCP Server", server_name)
        raw = doc.get("tools_discovered")
        if raw:
            return json.loads(raw)
        tools = []
        for row in (doc.get("tools") or []):
            tool = {"name": row.tool_name}
            if hasattr(row, "description") and row.description:
                tool["description"] = row.description
            schema = {"type": "object", "properties": {}}
            if hasattr(row, "input_schema") and row.input_schema:
                try:
                    schema = json.loads(row.input_schema)
                except Exception:
                    pass
            tool["inputSchema"] = schema
            tools.append(tool)
        return tools if tools else None
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: DB fallback failed for '{server_name}': {e}")
        return None


# ─── Same-Server Detection ────────────────────────────────────────

def _is_same_server(url):
    """Detect if MCP server URL points to this Frappe instance (deadlock risk)."""
    if not url:
        return False
    try:
        site = frappe.local.site if hasattr(frappe.local, "site") else None
        if not site:
            return False
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return True
        if site in host or host in site:
            return True
        try:
            site_host = frappe.get_conf().get("host_name", "")
            if site_host and site_host.replace("https://", "").replace("http://", "").split("/")[0] == host:
                return True
        except Exception:
            pass
    except Exception:
        pass
    return False


def _direct_fac_list_tools():
    """List tools via direct Python import (no HTTP, no deadlock)."""
    try:
        from frappe_assistant_core.api.fac_endpoint import handle_mcp
        payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}
        old_request_data = getattr(frappe.local, 'request_data', None)
        frappe.local.request_data = json.dumps(payload).encode("utf-8")
        response = handle_mcp()
        frappe.local.request_data = old_request_data
        if hasattr(response, 'data'):
            data = json.loads(response.data)
        elif isinstance(response, dict):
            data = response
        else:
            data = json.loads(str(response))
        return data.get("result", {}).get("tools", [])
    except ImportError:
        return None
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: Direct FAC list failed: {e}")
        return None


def _direct_fac_call_tool(tool_name, arguments):
    """Call a tool via direct Python import (no HTTP, no deadlock)."""
    try:
        from frappe_assistant_core.api.fac_endpoint import handle_mcp
        payload = {"jsonrpc": "2.0", "method": "tools/call",
                   "params": {"name": tool_name, "arguments": arguments}, "id": 1}
        old_request_data = getattr(frappe.local, 'request_data', None)
        frappe.local.request_data = json.dumps(payload).encode("utf-8")
        response = handle_mcp()
        frappe.local.request_data = old_request_data
        if hasattr(response, 'data'):
            data = json.loads(response.data)
        elif isinstance(response, dict):
            data = response
        else:
            data = json.loads(str(response))
        if "error" in data:
            raise MCPError(data["error"].get("message", str(data["error"])))
        return data.get("result", {})
    except ImportError:
        return None
    except MCPError:
        raise
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: Direct FAC call failed: {e}")
        return None


# ─── Official SDK: Async Discovery & Tool Calling ─────────────────

def _build_connection_config(doc):
    """Build langchain-mcp-adapters Connection dict from Niv MCP Server doc."""
    api_key = None
    try:
        api_key = doc.get_password("api_key") if doc.api_key else None
    except Exception:
        pass

    headers = {}
    try:
        site = frappe.local.site if hasattr(frappe.local, "site") else None
        if site:
            headers["Host"] = site
            headers["X-Frappe-Site-Name"] = site
    except Exception:
        pass
    if api_key:
        if ":" in api_key:
            headers["Authorization"] = f"token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    transport = doc.transport_type
    if transport == "streamable-http":
        return {
            "transport": "streamable_http",
            "url": doc.server_url,
            "headers": headers if headers else None,
        }
    elif transport == "sse":
        return {
            "transport": "sse",
            "url": doc.server_url,
            "headers": headers if headers else None,
        }
    elif transport == "stdio":
        args = doc.args.strip().split() if doc.args else []
        env = json.loads(doc.env_vars or "{}") if doc.env_vars else None
        return {
            "transport": "stdio",
            "command": doc.command.strip(),
            "args": args,
            "env": env,
        }
    else:
        raise MCPError(f"Unknown transport: {transport}")


async def _sdk_list_tools(connection_config):
    """Discover tools from MCP server using official SDK."""
    from langchain_mcp_adapters.sessions import create_session
    async with create_session(connection_config) as session:
        await session.initialize()
        result = await session.list_tools()
        # Convert to plain dict format for caching
        tools = []
        for tool in result.tools:
            t = {"name": tool.name}
            if tool.description:
                t["description"] = tool.description
            if tool.inputSchema:
                t["inputSchema"] = tool.inputSchema
            else:
                t["inputSchema"] = {"type": "object", "properties": {}}
            tools.append(t)
        return tools


async def _sdk_call_tool(connection_config, tool_name, arguments):
    """Execute a tool on MCP server using official SDK."""
    from langchain_mcp_adapters.sessions import create_session
    async with create_session(connection_config) as session:
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)
        return {"content": [{"type": c.type, "text": getattr(c, "text", str(c))} for c in result.content]}


# ─── Server Config Helper ─────────────────────────────────────────

def _get_server_config(server_name):
    cache_key = f"mcp_server_{server_name}"
    if hasattr(frappe.local, cache_key):
        return getattr(frappe.local, cache_key)
    doc = frappe.get_doc("Niv MCP Server", server_name)
    setattr(frappe.local, cache_key, doc)
    return doc


def _get_api_key(doc):
    try:
        return doc.get_password("api_key") if doc.api_key else None
    except Exception:
        return None


# ─── High-Level API ────────────────────────────────────────────────

def get_all_active_servers():
    """Get names of all active MCP servers."""
    return [d.name for d in frappe.get_all("Niv MCP Server", filters={"is_active": 1}, fields=["name"])]


def discover_tools(server_name, use_cache=True):
    """Discover tools from an MCP server.

    Resolution order:
    1. Worker memory cache
    2. Redis shared cache
    3. Same-server direct Python import (deadlock-safe)
    4. Official MCP SDK (HTTP/SSE/stdio)
    5. DB fallback (tools_discovered JSON)
    """
    # 1. Worker cache
    if use_cache:
        with _cache_lock:
            cached = _tools_cache.get(server_name)
            if cached and cached["expires"] > time.time():
                return cached["tools"]

    # 2. Redis cache
    redis_tools = _redis_get_tools(server_name)
    if redis_tools:
        with _cache_lock:
            _tools_cache[server_name] = {"tools": redis_tools, "expires": time.time() + CACHE_TTL}
        return redis_tools

    doc = _get_server_config(server_name)
    if not doc.is_active:
        return []

    tools = []
    same_server = _is_same_server(doc.server_url) if doc.transport_type != "stdio" else False

    # 3. Direct Python for same-server
    if same_server:
        tools = _direct_fac_list_tools() or []

    # 4. Official SDK
    if not tools:
        try:
            conn = _build_connection_config(doc)
            tools = _run_async(_sdk_list_tools(conn))
        except Exception as e:
            frappe.logger().error(f"Niv MCP: SDK discovery failed for '{server_name}': {e}")

    # 5. DB fallback
    if not tools:
        frappe.logger().warning(f"Niv MCP: All methods failed for '{server_name}', using DB fallback")
        tools = _db_get_tools(server_name) or []

    # Cache
    if tools:
        with _cache_lock:
            _tools_cache[server_name] = {"tools": tools, "expires": time.time() + CACHE_TTL}
        _redis_set_tools(server_name, tools)

    return tools


def _rebuild_tool_index():
    """Rebuild tool_name -> server_name index."""
    global _tool_index, _tool_index_expires

    redis_index = _redis_get_tool_index()
    if redis_index:
        with _cache_lock:
            _tool_index = redis_index
            _tool_index_expires = time.time() + CACHE_TTL
        return

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

    if new_index:
        _redis_set_tool_index(new_index)


def find_tool_server(tool_name):
    """Find which MCP server has this tool."""
    global _tool_index_expires

    with _cache_lock:
        if _tool_index_expires > time.time() and tool_name in _tool_index:
            return _tool_index[tool_name]

    _rebuild_tool_index()

    with _cache_lock:
        return _tool_index.get(tool_name)


def call_tool_fast(server_name, tool_name, arguments, user_api_key=None):
    """Execute a tool on an MCP server.

    Same-server: direct Python import first (no deadlock).
    Remote: official MCP SDK.
    """
    doc = _get_server_config(server_name)

    # Same-server optimization
    if doc.transport_type != "stdio" and _is_same_server(doc.server_url):
        result = _direct_fac_call_tool(tool_name, arguments)
        if result is not None:
            return result

    # Official SDK
    try:
        conn = _build_connection_config(doc)
        # Override auth with user key if provided
        if user_api_key:
            headers = conn.get("headers") or {}
            if ":" in user_api_key:
                headers["Authorization"] = f"token {user_api_key}"
            else:
                headers["Authorization"] = f"Bearer {user_api_key}"
            conn["headers"] = headers
        return _run_async(_sdk_call_tool(conn, tool_name, arguments))
    except Exception as e:
        raise MCPError(f"Tool '{tool_name}' failed: {e}")


def get_all_mcp_tools_cached():
    """Get all MCP tools in OpenAI function calling format. Cached."""
    global _openai_tools_cache

    with _cache_lock:
        if _openai_tools_cache["expires"] > time.time() and _openai_tools_cache["tools"]:
            return _openai_tools_cache["tools"]

    redis_tools = _redis_get_openai_tools()
    if redis_tools:
        with _cache_lock:
            _openai_tools_cache = {"tools": redis_tools, "expires": time.time() + CACHE_TTL}
        return redis_tools

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
                if not isinstance(params, dict) or "type" not in params:
                    params = {"type": "object", "properties": {}}
                result.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", name),
                        "parameters": params,
                    },
                })
        except Exception as e:
            frappe.logger().error(f"Niv MCP: Error from '{server_name}': {e}")

    if result:
        with _cache_lock:
            _openai_tools_cache = {"tools": result, "expires": time.time() + CACHE_TTL}
        _redis_set_openai_tools(result)
        _rebuild_tool_index()

    return result


# ─── Legacy API ────────────────────────────────────────────────────

def execute_mcp_tool(tool_name, arguments):
    server_name = find_tool_server(tool_name)
    if not server_name:
        return {"error": f"MCP tool '{tool_name}' not found"}
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
        return {"error": f"Tool execution failed: {e}"}


def get_all_mcp_tools():
    return get_all_mcp_tools_cached()


def call_tool(server_name, tool_name, arguments):
    return call_tool_fast(server_name, tool_name, arguments)


def clear_cache(server_name=None):
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
    try:
        if server_name:
            frappe.cache().delete_value(f"{REDIS_KEY_PREFIX}tools:{server_name}")
        else:
            for key in ("openai_tools", "tool_index"):
                frappe.cache().delete_value(f"{REDIS_KEY_PREFIX}{key}")
            for sn in get_all_active_servers():
                frappe.cache().delete_value(f"{REDIS_KEY_PREFIX}tools:{sn}")
    except Exception:
        pass
