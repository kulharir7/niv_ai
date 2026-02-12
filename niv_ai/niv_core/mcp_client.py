"""
MCP Client for Niv AI — Bulletproof Implementation

Architecture:
  SAME-SERVER (FAC on localhost): Direct Python import ONLY.
    - Zero external dependencies. No SDK, no HTTP, no pip packages needed.
    - Cannot fail unless FAC itself is broken.
    - This is 99% of real usage (FAC runs on same Frappe instance).

  REMOTE SERVER: Official MCP SDK (langchain-mcp-adapters).
    - Only used when server_url points to a different host.
    - SDK is an OPTIONAL dependency — gracefully degrades to DB fallback.
    - Async SDK bridged to sync via background thread event loop.

Caching: Worker memory → Redis → Live discovery → DB fallback.
v14 + v15 compatible.
"""

import json
import threading
import time
import frappe
from typing import Any, Dict, List, Optional


# ─── Constants ────────────────────────────────────────────────────

CACHE_TTL = 300  # 5 min worker memory
REDIS_CACHE_TTL = 600  # 10 min Redis
REDIS_KEY_PREFIX = "niv_mcp_tools:"


class MCPError(Exception):
    pass


# ─── Cache Layer (Redis + Worker Memory) ──────────────────────────

_cache_lock = threading.Lock()
_tools_cache = {}  # server_name -> {"tools": [...], "expires": ts}
_tool_index = {}  # tool_name -> server_name
_tool_index_expires = 0
_openai_tools_cache = {"tools": [], "expires": 0}
# Track which servers are same-server (avoid re-detecting every call)
_same_server_cache = {}  # server_name -> bool


def _redis_set(key, value, ttl=REDIS_CACHE_TTL):
    """Set in Redis cache. v14+v15 compatible."""
    try:
        data = json.dumps(value) if not isinstance(value, str) else value
        try:
            frappe.cache().set_value(f"{REDIS_KEY_PREFIX}{key}", data, expires_in_sec=ttl)
        except TypeError:
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


# ─── Same-Server Detection ────────────────────────────────────────

def _is_same_server(server_name, url):
    """Detect if MCP server URL points to this Frappe instance.
    Result is cached per server_name for the worker's lifetime."""
    if server_name in _same_server_cache:
        return _same_server_cache[server_name]

    result = False
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if host in ("localhost", "127.0.0.1", "0.0.0.0"):
                result = True
            else:
                site = getattr(frappe.local, "site", None) or ""
                if site and (site in host or host in site):
                    result = True
                else:
                    host_name = frappe.get_conf().get("host_name", "")
                    if host_name:
                        conf_host = host_name.replace("https://", "").replace("http://", "").split("/")[0]
                        if conf_host == host:
                            result = True
        except Exception:
            pass

    _same_server_cache[server_name] = result
    return result


# ─── Direct Python Call (Same-Server) ─────────────────────────────
# This is the PRIMARY path. No HTTP, no SDK, no external deps.
# Calls FAC's MCPServer internals directly — bypasses HTTP auth layer.

_fac_mcp_server = None  # Cached FAC MCP server instance


def _get_fac_server():
    """Get the FAC MCPServer instance with tools registered. Cached.
    Works on any FAC version that has mcp.server.MCPServer."""
    global _fac_mcp_server
    if _fac_mcp_server is not None:
        return _fac_mcp_server

    from frappe_assistant_core.api.fac_endpoint import mcp, _import_tools
    _import_tools()  # Register all enabled tools

    # Verify MCPServer has the methods we need (future-proofing)
    if not hasattr(mcp, "_handle_tools_list") or not hasattr(mcp, "_handle_tools_call"):
        raise MCPError(
            "FAC version too old — MCPServer missing _handle_tools_list/_handle_tools_call. "
            "Please update frappe_assistant_core."
        )

    _fac_mcp_server = mcp
    return _fac_mcp_server


def _direct_call(method, params):
    """Call FAC MCP server directly via Python — NO HTTP, NO auth headers.

    Bypasses handle_mcp() entirely. Calls _handle_tools_list / _handle_tools_call
    on the MCPServer instance. Runs as current frappe.session.user.

    Returns the MCP result dict, or raises MCPError on failure.
    NEVER returns None silently.
    """
    # Reconnect DB if connection was lost (gthread workers drop connections during long streams)
    try:
        frappe.db.sql("SELECT 1")
    except Exception:
        frappe.db.connect()

    server = _get_fac_server()

    if method == "tools/list":
        return server._handle_tools_list(params)
    elif method == "tools/call":
        result = server._handle_tools_call(params)
        # Check if tool returned an error
        if result.get("isError"):
            contents = result.get("content", [])
            error_text = contents[0].get("text", "Unknown error") if contents else "Unknown error"
            raise MCPError(error_text)
        return result
    else:
        raise MCPError(f"Unknown MCP method: {method}")


def _direct_list_tools():
    """List tools via direct Python call. Raises on failure."""
    result = _direct_call("tools/list", {})
    tools = result.get("tools", [])
    if not tools:
        frappe.logger().warning("Niv MCP: Direct FAC returned 0 tools")
    return tools


def _direct_call_tool(tool_name, arguments):
    """Call a single tool via direct Python call. Raises on failure."""
    return _direct_call("tools/call", {"name": tool_name, "arguments": arguments})


# ─── SDK Path (Remote Servers Only) ───────────────────────────────
# Only imported/used when connecting to a non-localhost MCP server.
# If SDK is not installed, falls back to DB.

_sdk_available = None  # None = not checked, True/False after first check
_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _check_sdk():
    """Check if MCP SDK is importable. Cached result."""
    global _sdk_available
    if _sdk_available is not None:
        return _sdk_available
    try:
        import langchain_mcp_adapters.sessions  # noqa: F401
        _sdk_available = True
    except ImportError:
        _sdk_available = False
        frappe.logger().info("Niv MCP: SDK (langchain-mcp-adapters) not installed. Remote MCP servers won't work.")
    return _sdk_available


def _get_event_loop():
    """Get or create a persistent event loop in a background thread."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop
        import asyncio
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
        return _loop


def _run_async(coro):
    """Run an async coroutine from sync code. Thread-safe."""
    import asyncio
    loop = _get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


def _build_connection_config(doc):
    """Build SDK connection config from Niv MCP Server doc."""
    api_key = None
    try:
        api_key = doc.get_password("api_key") if doc.api_key else None
    except Exception:
        pass

    headers = {}
    site = getattr(frappe.local, "site", None)
    if site:
        headers["Host"] = site
        headers["X-Frappe-Site-Name"] = site
    if api_key:
        headers["Authorization"] = f"token {api_key}" if ":" in api_key else f"Bearer {api_key}"

    transport = doc.transport_type
    if transport in ("streamable-http", "sse"):
        return {
            "transport": "streamable_http" if transport == "streamable-http" else "sse",
            "url": doc.server_url,
            "headers": headers or None,
        }
    elif transport == "stdio":
        args = doc.args.strip().split() if doc.args else []
        env = json.loads(doc.env_vars or "{}") if doc.env_vars else None
        return {"transport": "stdio", "command": doc.command.strip(), "args": args, "env": env}
    else:
        raise MCPError(f"Unknown transport: {transport}")


async def _sdk_list_tools_async(connection_config):
    """Discover tools using official SDK. With retry."""
    import asyncio
    from langchain_mcp_adapters.sessions import create_session

    last_err = None
    for attempt in range(3):
        try:
            async with create_session(connection_config) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    t = {"name": tool.name}
                    if tool.description:
                        t["description"] = tool.description
                    t["inputSchema"] = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}
                    tools.append(t)
                return tools
        except Exception as e:
            last_err = e
            if any(code in str(e).lower() for code in ("401", "403", "404")):
                raise
            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))
    raise last_err


async def _sdk_call_tool_async(connection_config, tool_name, arguments):
    """Execute a tool using official SDK. With retry."""
    import asyncio
    from langchain_mcp_adapters.sessions import create_session

    last_err = None
    for attempt in range(3):
        try:
            async with create_session(connection_config) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return {"content": [{"type": c.type, "text": getattr(c, "text", str(c))} for c in result.content]}
        except Exception as e:
            last_err = e
            if any(code in str(e).lower() for code in ("401", "403", "404")):
                raise
            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))
    raise last_err


def _sdk_list_tools(doc):
    """Sync wrapper for SDK tool discovery."""
    conn = _build_connection_config(doc)
    return _run_async(_sdk_list_tools_async(conn))


def _sdk_call_tool(doc, tool_name, arguments, user_api_key=None):
    """Sync wrapper for SDK tool call."""
    conn = _build_connection_config(doc)
    if user_api_key:
        headers = conn.get("headers") or {}
        headers["Authorization"] = f"token {user_api_key}" if ":" in user_api_key else f"Bearer {user_api_key}"
        conn["headers"] = headers
    return _run_async(_sdk_call_tool_async(conn, tool_name, arguments))


# ─── DB Fallback ──────────────────────────────────────────────────

def _db_get_tools(server_name):
    """Get tools from Niv MCP Server doc. Last resort, always works."""
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


# ─── Server Config Helper ─────────────────────────────────────────

def _get_server_config(server_name):
    cache_key = f"mcp_server_{server_name}"
    if hasattr(frappe.local, cache_key):
        return getattr(frappe.local, cache_key)
    doc = frappe.get_doc("Niv MCP Server", server_name)
    setattr(frappe.local, cache_key, doc)
    return doc


# ─── High-Level API ────────────────────────────────────────────────

def get_all_active_servers():
    return [d.name for d in frappe.get_all("Niv MCP Server", filters={"is_active": 1}, fields=["name"])]


def discover_tools(server_name, use_cache=True):
    """Discover tools from an MCP server.

    Resolution:
    1. Worker memory cache
    2. Redis shared cache
    3. SAME-SERVER → Direct Python import (no deps, no network)
       REMOTE → Official SDK (optional dep)
    4. DB fallback (tools_discovered JSON field)
    """
    # 1. Worker cache
    if use_cache:
        with _cache_lock:
            cached = _tools_cache.get(server_name)
            if cached and cached["expires"] > time.time():
                return cached["tools"]

    # 2. Redis cache
    redis_tools = _redis_get(f"tools:{server_name}")
    if redis_tools:
        with _cache_lock:
            _tools_cache[server_name] = {"tools": redis_tools, "expires": time.time() + CACHE_TTL}
        return redis_tools

    # 3. Live discovery
    doc = _get_server_config(server_name)
    if not doc.is_active:
        return []

    tools = None
    same_server = doc.transport_type != "stdio" and _is_same_server(server_name, doc.server_url)

    if same_server:
        # ── SAME-SERVER: Direct Python ──
        try:
            tools = _direct_list_tools()
        except ImportError:
            frappe.logger().error(f"Niv MCP: FAC not installed! Cannot discover tools for '{server_name}'")
        except Exception as e:
            frappe.logger().error(f"Niv MCP: Direct discovery failed for '{server_name}': {e}")
        # DO NOT fall through to SDK for same-server. Go straight to DB fallback.
    else:
        # ── REMOTE: SDK (if available) ──
        if _check_sdk():
            try:
                tools = _sdk_list_tools(doc)
            except Exception as e:
                frappe.logger().error(f"Niv MCP: SDK discovery failed for '{server_name}': {e}")

    # 4. DB fallback
    if not tools:
        frappe.logger().warning(f"Niv MCP: Live discovery failed for '{server_name}', using DB fallback")
        tools = _db_get_tools(server_name) or []

    # Cache results
    if tools:
        with _cache_lock:
            _tools_cache[server_name] = {"tools": tools, "expires": time.time() + CACHE_TTL}
        _redis_set(f"tools:{server_name}", tools)

    return tools


def _rebuild_tool_index():
    """Rebuild tool_name → server_name index."""
    global _tool_index, _tool_index_expires

    redis_index = _redis_get("tool_index")
    if redis_index:
        with _cache_lock:
            _tool_index = redis_index
            _tool_index_expires = time.time() + CACHE_TTL
        return

    new_index = {}
    for server_name in get_all_active_servers():
        try:
            for tool in discover_tools(server_name):
                name = tool.get("name", "")
                if name and name not in new_index:
                    new_index[name] = server_name
        except Exception:
            continue

    with _cache_lock:
        _tool_index = new_index
        _tool_index_expires = time.time() + CACHE_TTL

    if new_index:
        _redis_set("tool_index", new_index)


def find_tool_server(tool_name):
    """Find which MCP server hosts this tool."""
    global _tool_index_expires
    with _cache_lock:
        if _tool_index_expires > time.time() and tool_name in _tool_index:
            return _tool_index[tool_name]
    _rebuild_tool_index()
    with _cache_lock:
        return _tool_index.get(tool_name)


def call_tool_fast(server_name, tool_name, arguments, user_api_key=None):
    """Execute a tool. Same-server uses direct Python. Remote uses SDK.

    GUARANTEE: Same-server calls NEVER touch SDK/pip packages.
    """
    doc = _get_server_config(server_name)
    same_server = doc.transport_type != "stdio" and _is_same_server(server_name, doc.server_url)

    if same_server:
        # ── SAME-SERVER: Direct Python call. Period. ──
        try:
            return _direct_call_tool(tool_name, arguments)
        except ImportError:
            raise MCPError(f"FAC app not installed — cannot call tool '{tool_name}'")
        except MCPError:
            raise
        except Exception as e:
            raise MCPError(f"Tool '{tool_name}' failed (direct): {e}")
    else:
        # ── REMOTE: SDK ──
        if not _check_sdk():
            raise MCPError(
                f"Tool '{tool_name}' is on remote server '{server_name}' "
                "but MCP SDK is not installed. Run: pip install mcp langchain-mcp-adapters"
            )
        try:
            return _sdk_call_tool(doc, tool_name, arguments, user_api_key)
        except Exception as e:
            raise MCPError(f"Tool '{tool_name}' failed (SDK): {e}")


def get_all_mcp_tools_cached():
    """Get all MCP tools in OpenAI function format. Cached."""
    global _openai_tools_cache

    with _cache_lock:
        if _openai_tools_cache["expires"] > time.time() and _openai_tools_cache["tools"]:
            return _openai_tools_cache["tools"]

    redis_tools = _redis_get("openai_tools")
    if redis_tools:
        with _cache_lock:
            _openai_tools_cache = {"tools": redis_tools, "expires": time.time() + CACHE_TTL}
        return redis_tools

    result = []
    seen_names = set()

    for server_name in get_all_active_servers():
        try:
            for tool in discover_tools(server_name):
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
        _redis_set("openai_tools", result)
        _rebuild_tool_index()

    return result


# ─── Legacy API (backward compat) ─────────────────────────────────

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
