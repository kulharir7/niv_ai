"""
MCP Client for Niv AI — SDK-Only Implementation

Architecture:
  ALL SERVERS: Official MCP SDK (mcp + langchain-mcp-adapters).
    - Standard MCP protocol over Streamable HTTP.
    - No hardcoded imports — server URL from Niv MCP Server DocType.
    - Async SDK bridged to sync via background thread event loop.
    - Works with any MCP-compatible server (FAC, custom, remote).

  Caching: Worker memory → Redis → Live SDK discovery.
  Config: Niv MCP Server DocType (UI-managed).
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


# ─── Circuit Breaker ──────────────────────────────────────────────
# After 3 consecutive failures, skip server for 60s. Auto-recover.

CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN = 60  # seconds
CIRCUIT_BREAKER_PREFIX = "niv_mcp_cb:"


def _check_circuit_breaker(server_name):
    """Return True if server is healthy (circuit closed). False if tripped (open)."""
    try:
        data = _redis_get(f"cb:{server_name}")
        if not data or not isinstance(data, dict):
            return True
        if data.get("failures", 0) >= CIRCUIT_BREAKER_THRESHOLD:
            tripped_at = data.get("tripped_at", 0)
            if time.time() - tripped_at < CIRCUIT_BREAKER_COOLDOWN:
                return False  # circuit open — skip server
            # Cooldown expired — allow one attempt (half-open)
        return True
    except Exception:
        return True


def _record_failure(server_name):
    """Record a failure. Trip circuit after threshold."""
    try:
        data = _redis_get(f"cb:{server_name}") or {}
        if not isinstance(data, dict):
            data = {}
        failures = data.get("failures", 0) + 1
        data["failures"] = failures
        if failures >= CIRCUIT_BREAKER_THRESHOLD:
            data["tripped_at"] = time.time()
            frappe.logger().warning(f"Niv MCP: Circuit breaker OPEN for '{server_name}' after {failures} failures")
        _redis_set(f"cb:{server_name}", data, ttl=CIRCUIT_BREAKER_COOLDOWN * 2)
    except Exception:
        pass


def _record_success(server_name):
    """Reset failure count on success."""
    try:
        _redis_set(f"cb:{server_name}", {"failures": 0}, ttl=CIRCUIT_BREAKER_COOLDOWN * 2)
    except Exception:
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


# ─── MCP SDK Tool Discovery & Execution ──────────────────────────
# Uses official MCP SDK — standard protocol, no hardcoded imports.


def _ensure_db_alive():
    """Ensure DB connection is alive. Reconnect if dead."""
    try:
        frappe.db.sql("SELECT 1")
    except Exception:
        try:
            frappe.db.connect()
        except Exception:
            pass


def _direct_list_tools():
    """List tools via MCP SDK — standard protocol, no hardcoded imports.
    Config from Niv MCP Server DocType."""
    
    servers = get_all_active_servers()
    if not servers:
        return []
    
    config = _get_server_config(servers[0])
    url = config.get("server_url", "")
    if not url:
        frappe.logger().warning("Niv MCP: No server URL configured")
        return []
    
    site = getattr(frappe.local, "site", None) or ""
    headers = {}
    if site:
        headers["Host"] = site
        headers["X-Frappe-Site-Name"] = site
    
    try:
        admin = frappe.get_doc("User", "Administrator")
        api_key = admin.api_key
        if api_key:
            api_secret = frappe.utils.password.get_decrypted_password("User", "Administrator", "api_secret")
            if api_secret:
                headers["Authorization"] = f"token {api_key}:{api_secret}"
    except Exception:
        pass
    
    # Capture URL and headers NOW (frappe context available here)
    _url = url
    _headers = dict(headers)
    
    async def _discover():
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession
        import asyncio
        
        async with streamablehttp_client(_url, headers=_headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=15)
                result = await asyncio.wait_for(session.list_tools(), timeout=30)
                tools = []
                for t in result.tools:
                    tools.append({
                        "name": t.name,
                        "description": t.description or t.name,
                        "inputSchema": t.inputSchema if t.inputSchema else {"type": "object", "properties": {}},
                    })
                return tools
    
    try:
        tools = _run_async(_discover())
        if tools:
            frappe.logger().info(f"Niv MCP: SDK discovered {len(tools)} tools")
            return tools
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: SDK discovery failed: {e}")
    
    return []


def _direct_call_tool(tool_name, arguments):
    """Call tool via MCP SDK — standard protocol, no hardcoded imports."""
    
    servers = get_all_active_servers()
    if not servers:
        raise MCPError("No active MCP servers")
    
    config = _get_server_config(servers[0])
    url = config.get("server_url", "")
    if not url:
        raise MCPError("No server URL configured")
    
    site = getattr(frappe.local, "site", None) or ""
    headers = {}
    if site:
        headers["Host"] = site
        headers["X-Frappe-Site-Name"] = site
    
    try:
        admin = frappe.get_doc("User", "Administrator")
        api_key = admin.api_key
        if api_key:
            api_secret = frappe.utils.password.get_decrypted_password("User", "Administrator", "api_secret")
            if api_secret:
                headers["Authorization"] = f"token {api_key}:{api_secret}"
    except Exception:
        pass
    
    _url = url
    _headers = dict(headers)
    _tool_name = tool_name
    _arguments = arguments
    
    async def _call():
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession
        import asyncio
        
        async with streamablehttp_client(_url, headers=_headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=15)
                result = await asyncio.wait_for(session.call_tool(_tool_name, _arguments), timeout=60)
                
                if result.isError:
                    error_text = ""
                    for c in result.content:
                        if hasattr(c, "text"):
                            error_text += c.text
                    raise MCPError(error_text or "Tool call failed")
                
                content = []
                for c in result.content:
                    if hasattr(c, "text"):
                        content.append({"type": "text", "text": c.text})
                    else:
                        content.append({"type": str(c.type), "text": str(c)})
                return {"content": content}
    
    try:
        return _run_async(_call())
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(f"Tool '{tool_name}' failed (SDK): {e}")


_sdk_available = None
_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _check_sdk():
    """Check if MCP SDK is importable. Cached result."""
    global _sdk_available
    if _sdk_available is not None:
        return _sdk_available
    try:
        import mcp  # noqa: F401
        import langchain_mcp_adapters  # noqa: F401
        _sdk_available = True
        frappe.logger().info("Niv MCP: SDK available (mcp + langchain-mcp-adapters)")
    except ImportError:
        _sdk_available = False
        frappe.logger().info("Niv MCP: SDK not installed. Install: pip install mcp langchain-mcp-adapters")
    return _sdk_available


def _get_event_loop():
    """Get or create a persistent event loop in a background thread."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop
        import asyncio
        import atexit
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()

        # Clean shutdown on process exit
        def _shutdown_loop():
            if _loop and _loop.is_running():
                _loop.call_soon_threadsafe(_loop.stop)
        atexit.register(_shutdown_loop)

        return _loop


def _run_async(coro):
    """Run an async coroutine from sync code. Thread-safe."""
    import asyncio
    loop = _get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


def _build_connection_config(doc):
    """Build SDK connection config for remote MCP server."""
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
                # Add timeouts for initialization and tool listing
                await asyncio.wait_for(session.initialize(), timeout=30)
                result = await asyncio.wait_for(session.list_tools(), timeout=30)
                tools = []
                for tool in result.tools:
                    t = {"name": tool.name}
                    if tool.description:
                        t["description"] = tool.description
                    t["inputSchema"] = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}
                    tools.append(t)
                return tools
        except asyncio.TimeoutError:
            last_err = MCPError("Connection timeout while listing tools")
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
                # Add timeouts for initialization and tool call
                await asyncio.wait_for(session.initialize(), timeout=30)
                result = await asyncio.wait_for(session.call_tool(tool_name, arguments), timeout=60)
                return {"content": [{"type": c.type, "text": getattr(c, "text", str(c))} for c in result.content]}
        except asyncio.TimeoutError:
            last_err = MCPError(f"Tool call '{tool_name}' timed out after 60s")
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


# ─── Server Config Helper ─────────────────────────────────────────

def _get_server_config(server_name):
    """Get MCP server config from Niv MCP Server DocType.
    Fallback: if DocType doesn't exist, assume FAC on same server."""
    cache_key = f"mcp_server_{server_name}"
    if hasattr(frappe.local, cache_key):
        return getattr(frappe.local, cache_key)

    config = None

    # Try reading from Niv MCP Server DocType
    try:
        if frappe.db.exists("DocType", "Niv MCP Server") and frappe.db.exists("Niv MCP Server", server_name):
            doc = frappe.get_doc("Niv MCP Server", server_name)
            config = frappe._dict({
                "server_name": doc.server_name,
                "transport_type": doc.transport_type or "http",
                "server_url": doc.server_url or f"http://localhost:{frappe.conf.get('webserver_port', 8000)}",
                "is_active": doc.is_active,
                "api_key": doc.api_key,
                "command": getattr(doc, "command", None),
                "args": getattr(doc, "args", None),
                "env_vars": getattr(doc, "env_vars", None),
            })
    except Exception:
        pass

    # Fallback — old behavior (FAC on same server)
    if not config:
        config = frappe._dict({
            "server_name": server_name,
            "transport_type": "http",
            "server_url": f"http://localhost:{frappe.conf.get('webserver_port', 8000)}",
            "is_active": 1,
        })

    setattr(frappe.local, cache_key, config)
    return config


# ─── High-Level API ────────────────────────────────────────────────

def get_all_active_servers():
    """Return active MCP servers from Niv MCP Server DocType.
    Fallback: if DocType doesn't exist, return FAC as default."""
    try:
        if frappe.db.exists("DocType", "Niv MCP Server"):
            servers = frappe.get_all(
                "Niv MCP Server",
                filters={"is_active": 1},
                fields=["server_name"],
                order_by="creation ASC",
            )
            if servers:
                return [s.server_name for s in servers]
    except Exception:
        pass
    # No servers configured
    return []


def discover_tools(server_name, use_cache=True):
    """Discover tools from an MCP server.

    Resolution:
    1. Check if server is active (from DocType)
    2. Worker memory cache
    3. Redis shared cache
    4. MCP SDK — standard protocol for all servers
    """
    # 0. Check if server is active
    try:
        config = _get_server_config(server_name)
        if not config.get("is_active", 1):
            # Server disabled — return empty, clear cache
            with _cache_lock:
                _tools_cache.pop(server_name, None)
            _redis_set(f"tools:{server_name}", [])
            return []
    except Exception:
        pass

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
        # ── SAME-SERVER: Direct Python first, SDK fallback ──
        try:
            tools = _direct_list_tools()
        except ImportError:
            frappe.logger().info(f"Niv MCP: FAC import failed, trying SDK for '{server_name}'")
        except Exception as e:
            frappe.logger().warning(f"Niv MCP: Direct discovery failed for '{server_name}': {e}")

        # SDK fallback for same-server (if direct failed)
        if not tools and _check_sdk():
            try:
                tools = _sdk_list_tools(doc)
                frappe.logger().info(f"Niv MCP: SDK discovery got {len(tools)} tools for '{server_name}'")
            except Exception as e:
                frappe.logger().warning(f"Niv MCP: SDK discovery also failed for '{server_name}': {e}")
    else:
        # ── REMOTE: SDK (if available) ──
        if _check_sdk():
            try:
                tools = _sdk_list_tools(doc)
            except Exception as e:
                frappe.logger().error(f"Niv MCP: SDK discovery failed for '{server_name}': {e}")

    # No tools found
    if not tools:
        frappe.logger().warning(f"Niv MCP: Discovery failed for '{server_name}'")

    # Cache results — NEVER cache empty tools (would hide real tools for 5 min)
    if tools:
        with _cache_lock:
            _tools_cache[server_name] = {"tools": tools, "expires": time.time() + CACHE_TTL}
        _redis_set(f"tools:{server_name}", tools)
    else:
        frappe.logger().error(f"Niv MCP: 0 tools discovered for '{server_name}' — NOT caching empty result")

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
    """Execute a tool via MCP SDK. All servers use SDK protocol."""
    # Circuit breaker check
    if not _check_circuit_breaker(server_name):
        raise MCPError(f"Server '{server_name}' is temporarily unavailable (circuit breaker open). Retry in ~60s.")

    doc = _get_server_config(server_name)
    same_server = doc.transport_type != "stdio" and _is_same_server(server_name, doc.server_url)

    if same_server:
        # ── SAME-SERVER: Direct Python first (fastest), SDK fallback ──
        try:
            result = _direct_call_tool(tool_name, arguments)
            _record_success(server_name)
            return result
        except ImportError:
            # FAC not installed or import changed — try SDK
            frappe.logger().info(f"Niv MCP: Direct import failed for {tool_name}, trying SDK...")
        except MCPError:
            _record_failure(server_name)
            raise
        except Exception as e:
            frappe.logger().warning(f"Niv MCP: Direct call failed for {tool_name}: {e}, trying SDK...")

        # Fallback to SDK for same-server
        if _check_sdk():
            try:
                result = _sdk_call_tool(doc, tool_name, arguments, user_api_key)
                _record_success(server_name)
                return result
            except Exception as e:
                _record_failure(server_name)
                raise MCPError(f"Tool '{tool_name}' failed (SDK): {e}")

        _record_failure(server_name)
        raise MCPError(f"Tool '{tool_name}' failed — no working connection method")
    else:
        # ── REMOTE: SDK ──
        if not _check_sdk():
            raise MCPError(
                f"Tool '{tool_name}' is on remote server '{server_name}' "
                "but MCP SDK is not installed. Run: pip install mcp langchain-mcp-adapters"
            )
        try:
            result = _sdk_call_tool(doc, tool_name, arguments, user_api_key)
            _record_success(server_name)
            return result
        except Exception as e:
            _record_failure(server_name)
            raise MCPError(f"Tool '{tool_name}' failed (SDK): {e}")


def warm_cache():
    """Pre-warm MCP tool caches after migrate. Called by hooks.py after_migrate."""
    try:
        tools = get_all_mcp_tools_cached()
        if tools:
            frappe.logger().info(f"Niv MCP: Cache warmed with {len(tools)} tools")
        else:
            frappe.logger().warning("Niv MCP: Cache warm returned 0 tools")
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: Cache warm failed (non-fatal): {e}")


def get_all_mcp_tools_cached():
    """Get all MCP tools in OpenAI function format. Cached.
    Returns empty list if no active servers.
    Active check reads from DB every time (not cached) to respect toggle."""
    global _openai_tools_cache

    # ALWAYS check active servers from DB (bypasses cache)
    # This ensures toggle OFF immediately stops tools
    try:
        if frappe.db.exists("DocType", "Niv MCP Server"):
            active_count = frappe.db.count("Niv MCP Server", {"is_active": 1})
            if active_count == 0:
                with _cache_lock:
                    _openai_tools_cache = {"tools": [], "expires": 0}
                return []
    except Exception:
        pass

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
    """Clear all caches — worker memory, Redis, and LangChain tools."""
    global _tool_index_expires, _openai_tools_cache
    with _cache_lock:
        if server_name:
            _tools_cache.pop(server_name, None)
        else:
            _tools_cache.clear()
        _tool_index.clear()
        _tool_index_expires = 0
        _openai_tools_cache = {"tools": [], "expires": 0}
    # Clear FAC server cache (force re-import on next call)
    # Clear Redis
    try:
        if server_name:
            frappe.cache().delete_value(f"{REDIS_KEY_PREFIX}tools:{server_name}")
        else:
            for key in ("openai_tools", "tool_index"):
                frappe.cache().delete_value(f"{REDIS_KEY_PREFIX}{key}")
            # Clear all server tool caches
            try:
                for sn in get_all_active_servers():
                    frappe.cache().delete_value(f"{REDIS_KEY_PREFIX}tools:{sn}")
            except Exception:
                pass
    except Exception:
        pass
    # Also clear LangChain tools cache
    try:
        from niv_ai.niv_core.langchain.tools import clear_tools_cache
        clear_tools_cache()
    except Exception:
        pass
