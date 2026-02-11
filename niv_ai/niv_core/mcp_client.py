"""
MCP (Model Context Protocol) Client for Niv AI

Bulletproof, multi-worker safe MCP client.
- Redis shared cache — all gunicorn workers share tool definitions
- DB fallback — tools stored in Niv MCP Server child table (never lost)
- Per-worker memory cache — fast path (no Redis hit on every call)
- Self-referencing deadlock protection — detects same-server and uses internal call
- JSON-RPC 2.0 protocol — no mcp pip package needed
- Circuit breaker — auto-skip failing servers, self-heal after 60s
- Retry with exponential backoff — transient error resilience
"""

import json
import os
import subprocess
import threading
import time
import frappe
from typing import Dict, Any, List, Optional


# ─── Global Caches (per-worker memory, fast path) ─────────────────

_cache_lock = threading.Lock()


# ─── Circuit Breaker (per server, Redis-shared across workers) ────
# States: CLOSED (normal), OPEN (skip HTTP), HALF_OPEN (testing one call)
# BUG-007: Moved from module-level dict to Redis so all gunicorn workers share state.

CIRCUIT_CLOSED = "CLOSED"
CIRCUIT_OPEN = "OPEN"
CIRCUIT_HALF_OPEN = "HALF_OPEN"

CIRCUIT_FAILURE_THRESHOLD = 3   # consecutive failures before opening
CIRCUIT_RECOVERY_TIMEOUT = 60   # seconds before trying again (half-open)

_CB_REDIS_PREFIX = "niv_mcp_cb:"
_CB_TTL = 300  # 5 min TTL for circuit breaker state in Redis


def _cb_redis_get(server_name):
    """Get circuit breaker state from Redis."""
    try:
        data = frappe.cache().get_value(f"{_CB_REDIS_PREFIX}{server_name}")
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if isinstance(data, str):
                return json.loads(data)
            return data
    except Exception:
        pass
    return None


def _cb_redis_set(server_name, state):
    """Set circuit breaker state in Redis."""
    try:
        val = json.dumps(state)
        try:
            frappe.cache().set_value(f"{_CB_REDIS_PREFIX}{server_name}", val, expires_in_sec=_CB_TTL)
        except TypeError:
            frappe.cache().setex(f"{_CB_REDIS_PREFIX}{server_name}", _CB_TTL, val)
    except Exception:
        pass


def _circuit_check(server_name):
    """Check if circuit is open (should skip HTTP). Returns True if should skip."""
    cb = _cb_redis_get(server_name)
    if not cb or cb["state"] == CIRCUIT_CLOSED:
        return False
    if cb["state"] == CIRCUIT_OPEN:
        # Check if recovery timeout has elapsed → transition to HALF_OPEN
        if time.time() - cb["opened_at"] >= CIRCUIT_RECOVERY_TIMEOUT:
            cb["state"] = CIRCUIT_HALF_OPEN
            _cb_redis_set(server_name, cb)
            frappe.logger().info(f"Niv MCP: Circuit half-open for '{server_name}', testing one call")
            return False  # Allow one test call
        return True  # Still open, skip
    # HALF_OPEN — allow the test call
    return False


def _circuit_record_success(server_name):
    """Record a successful call — close the circuit."""
    cb = _cb_redis_get(server_name)
    if cb and cb["state"] != CIRCUIT_CLOSED:
        frappe.logger().info(f"Niv MCP: Circuit closed for '{server_name}' (recovered)")
    _cb_redis_set(server_name, {"state": CIRCUIT_CLOSED, "failures": 0, "opened_at": 0})


def _circuit_record_failure(server_name):
    """Record a failed call — may open the circuit."""
    cb = _cb_redis_get(server_name) or {"state": CIRCUIT_CLOSED, "failures": 0, "opened_at": 0}
    cb["failures"] += 1
    if cb["state"] == CIRCUIT_HALF_OPEN:
        # Test call failed — re-open
        cb["state"] = CIRCUIT_OPEN
        cb["opened_at"] = time.time()
        frappe.logger().warning(f"Niv MCP: Circuit re-opened for '{server_name}' (half-open test failed)")
    elif cb["failures"] >= CIRCUIT_FAILURE_THRESHOLD:
        cb["state"] = CIRCUIT_OPEN
        cb["opened_at"] = time.time()
        frappe.logger().warning(f"Niv MCP: Circuit opened for '{server_name}' after {cb['failures']} failures")
    _cb_redis_set(server_name, cb)


# ─── Retry with Exponential Backoff ───────────────────────────────

_RETRY_MAX = 2          # max retries (total 3 attempts)
_RETRY_BACKOFFS = [0.5, 1.5]  # seconds between retries
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


def _is_retryable_error(exc):
    """Check if an exception is transient and worth retrying."""
    import requests
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, 'response', None)
        if resp is not None and resp.status_code in _RETRYABLE_STATUS_CODES:
            return True
    return False

# Per-worker tool cache: server_name → {"tools": [...], "expires": ts}
_tools_cache = {}

# Tool-to-server index: tool_name → server_name
_tool_index = {}
_tool_index_expires = 0

# OpenAI format cache
_openai_tools_cache = {"tools": [], "expires": 0}

# HTTP session reuse
_http_sessions = {}

# MCP session init cache
_mcp_init_cache = {}
_MCP_INIT_TTL = 600  # 10 min

CACHE_TTL = 300  # 5 minutes
REDIS_CACHE_TTL = 600  # 10 minutes — Redis cache lives longer than worker cache
REDIS_KEY_PREFIX = "niv_mcp_tools:"


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


# ─── Redis Shared Cache ───────────────────────────────────────────

def _redis_get(key):
    """Get from Redis cache. Returns None on miss or error.
    BUG-006: handles bytes returned by some Redis configs.
    """
    try:
        data = frappe.cache().get_value(f"{REDIS_KEY_PREFIX}{key}")
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data) if isinstance(data, str) else data
    except Exception:
        pass
    return None


def _redis_set(key, value, ttl=REDIS_CACHE_TTL):
    """Set in Redis cache.
    BUG-015: v14 compat — fallback to setex if expires_in_sec not supported.
    """
    try:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        try:
            frappe.cache().set_value(
                f"{REDIS_KEY_PREFIX}{key}",
                serialized,
                expires_in_sec=ttl,
            )
        except TypeError:
            frappe.cache().setex(f"{REDIS_KEY_PREFIX}{key}", ttl, serialized)
    except Exception:
        pass


def _redis_get_tools(server_name):
    """Get tool definitions from Redis. Returns list or None."""
    return _redis_get(f"tools:{server_name}")


def _redis_set_tools(server_name, tools):
    """Store tool definitions in Redis."""
    _redis_set(f"tools:{server_name}", tools)


def _redis_get_openai_tools():
    """Get OpenAI-format tools from Redis."""
    return _redis_get("openai_tools")


def _redis_set_openai_tools(tools):
    """Store OpenAI-format tools in Redis."""
    _redis_set("openai_tools", tools)


def _redis_get_tool_index():
    """Get tool→server index from Redis."""
    return _redis_get("tool_index")


def _redis_set_tool_index(index):
    """Store tool→server index in Redis."""
    _redis_set("tool_index", index)


# ─── DB Fallback (last resort — tools stored in DocType) ──────────

def _db_get_tools(server_name):
    """Get tools from Niv MCP Server child table. Always works, never deadlocks."""
    try:
        doc = frappe.get_doc("Niv MCP Server", server_name)
        raw = doc.get("tools_discovered")
        if raw:
            return json.loads(raw)
        # Fallback: reconstruct from child table
        tools = []
        for row in (doc.get("tools") or []):
            tool = {"name": row.tool_name}
            if hasattr(row, "description") and row.description:
                tool["description"] = row.description
            if hasattr(row, "input_schema") and row.input_schema:
                try:
                    tool["inputSchema"] = json.loads(row.input_schema)
                except Exception:
                    tool["inputSchema"] = {"type": "object", "properties": {}}
            else:
                tool["inputSchema"] = {"type": "object", "properties": {}}
            tools.append(tool)
        return tools if tools else None
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: DB fallback failed for '{server_name}': {e}")
        return None


# ─── Self-Reference Detection ─────────────────────────────────────

def _is_same_server(url):
    """Detect if MCP server URL points to the same Frappe instance.
    This causes deadlocks when gunicorn workers are limited."""
    if not url:
        return False
    try:
        site = frappe.local.site if hasattr(frappe.local, "site") else None
        if not site:
            return False
        # Check if URL contains the site name or is localhost
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return True
        if site in host or host in site:
            return True
        # Check site_config for host_name
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
    """Try to list tools via direct Python import (no HTTP, no deadlock)."""
    try:
        from frappe_assistant_core.api.fac_endpoint import handle_mcp
        # Simulate MCP tools/list request internally
        payload = _jsonrpc("tools/list", {}, req_id=1)
        
        # Save and set up frappe context for internal call
        import io
        old_request_data = getattr(frappe.local, 'request_data', None)
        
        frappe.local.request_data = json.dumps(payload).encode("utf-8")
        
        # We need to call the handler differently — let's try the internal route
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
        return None  # FAC not installed
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: Direct FAC call failed: {e}")
        return None


def _direct_fac_call_tool(tool_name, arguments, api_key=None):
    """Try to call a tool via direct Python import (no HTTP, no deadlock)."""
    try:
        from frappe_assistant_core.api.fac_endpoint import handle_mcp
        
        payload = _jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, req_id=1)
        
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
        frappe.logger().warning(f"Niv MCP: Direct FAC tool call failed: {e}")
        return None


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
            "clientInfo": {"name": "niv-ai", "version": "0.4.0"},
        }, req_id=_next_id()))
        recv()
        send(_jsonrpc("notifications/initialized"))
        return proc, send, recv
    except Exception:
        proc.terminate()
        raise


# BUG-013: stdio process cache to avoid new subprocess per call
_stdio_cache = {}  # command → {"proc": proc, "send": fn, "recv": fn, "expires": ts}
_STDIO_CACHE_TTL = 120  # 2 minutes


def _get_stdio_session(command, args_str, env_vars_str):
    """Get or create a cached stdio session. BUG-013 fix."""
    cache_key = f"{command}:{args_str or ''}"
    cached = _stdio_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        # Check if process is still alive
        if cached["proc"].poll() is None:
            return cached["proc"], cached["send"], cached["recv"]
        # Process died, remove from cache
        _stdio_cache.pop(cache_key, None)

    proc, send, recv = _stdio_initialize(command, args_str, env_vars_str)
    _stdio_cache[cache_key] = {
        "proc": proc, "send": send, "recv": recv,
        "expires": time.time() + _STDIO_CACHE_TTL,
    }
    return proc, send, recv


def stdio_list_tools(command, args_str, env_vars_str) -> List[Dict]:
    proc, send, recv = _get_stdio_session(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("tools/list", {}, req_id=_next_id()))
        resp = recv()
        return resp.get("result", {}).get("tools", [])
    except Exception:
        # Evict bad cached session
        cache_key = f"{command}:{args_str or ''}"
        cached = _stdio_cache.pop(cache_key, None)
        if cached and cached["proc"].poll() is None:
            cached["proc"].terminate()
        raise


def stdio_call_tool(command, args_str, env_vars_str, tool_name, arguments) -> Any:
    proc, send, recv = _get_stdio_session(command, args_str, env_vars_str)
    try:
        send(_jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, req_id=_next_id()))
        resp = recv(timeout=30)
        if "error" in resp:
            raise MCPError(resp["error"].get("message", str(resp["error"])))
        return resp.get("result", {})
    except MCPError:
        raise
    except Exception:
        cache_key = f"{command}:{args_str or ''}"
        cached = _stdio_cache.pop(cache_key, None)
        if cached and cached["proc"].poll() is None:
            cached["proc"].terminate()
        raise


# ─── HTTP Transport (streamable-http) ──────────────────────────────

def _build_headers(api_key=None, server_name=None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        if ":" in api_key:
            headers["Authorization"] = f"token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    try:
        site = frappe.local.site if hasattr(frappe.local, "site") else None
        if site:
            headers["Host"] = site
            headers["X-Frappe-Site-Name"] = site
    except Exception:
        pass
    # Add MCP session ID if available
    if server_name:
        session_id = _redis_get(f"session:{server_name}")
        if session_id:
            headers["Mcp-Session-Id"] = session_id
    return headers


def _http_post(url, payload, api_key=None, timeout=15, server_name=None):
    """HTTP POST with retry + circuit breaker integration."""
    session = _get_http_session(url)
    headers = _build_headers(api_key, server_name=server_name)
    last_exc = None
    for attempt in range(_RETRY_MAX + 1):
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            # Capture MCP session ID from response
            sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
            if sid and server_name:
                _redis_set(f"session:{server_name}", sid, ttl=3600)
            result = resp.json()
            if server_name:
                _circuit_record_success(server_name)
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_MAX and _is_retryable_error(exc):
                time.sleep(_RETRY_BACKOFFS[attempt])
                continue
            if server_name:
                _circuit_record_failure(server_name)
            raise
    raise last_exc  # should not reach here


def _ensure_initialized(url, api_key=None, server_name=None):
    """Initialize MCP session only if not already done (cached)."""
    cache_key = url
    cached = _mcp_init_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return

    try:
        _http_post(url, _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "niv-ai", "version": "0.4.0"},
        }, req_id=_next_id()), api_key, server_name=server_name)
        try:
            _http_post(url, _jsonrpc("notifications/initialized"), api_key, timeout=5, server_name=server_name)
        except Exception:
            pass
        _mcp_init_cache[cache_key] = {"initialized": True, "expires": time.time() + _MCP_INIT_TTL}
    except Exception:
        _mcp_init_cache.pop(cache_key, None)
        raise


def http_list_tools(url, api_key=None, server_name=None) -> List[Dict]:
    _ensure_initialized(url, api_key, server_name=server_name)
    resp = _http_post(url, _jsonrpc("tools/list", {}, req_id=_next_id()), api_key, server_name=server_name)
    return resp.get("result", {}).get("tools", [])


def http_call_tool(url, api_key, tool_name, arguments, server_name=None) -> Any:
    _ensure_initialized(url, api_key, server_name=server_name)
    resp = _http_post(url, _jsonrpc("tools/call", {
        "name": tool_name, "arguments": arguments
    }, req_id=_next_id()), api_key, timeout=30, server_name=server_name)
    if "error" in resp:
        raise MCPError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result", {})


# ─── SSE Transport ─────────────────────────────────────────────────

def _sse_request(url, payload, api_key=None, timeout=30, server_name=None):
    """SSE request with retry + circuit breaker integration."""
    import requests
    last_exc = None
    for attempt in range(_RETRY_MAX + 1):
        try:
            headers = _build_headers(api_key, server_name=server_name)
            headers["Accept"] = "text/event-stream"
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
            resp.raise_for_status()
            # Capture MCP session ID from response
            sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
            if sid and server_name:
                _redis_set(f"session:{server_name}", sid, ttl=3600)

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                result = resp.json()
                if server_name:
                    _circuit_record_success(server_name)
                return result

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                    if isinstance(data, dict) and ("result" in data or "error" in data):
                        if server_name:
                            _circuit_record_success(server_name)
                        return data
                except json.JSONDecodeError:
                    continue

            raise MCPError("No valid response from SSE stream")
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_MAX and _is_retryable_error(exc):
                time.sleep(_RETRY_BACKOFFS[attempt])
                continue
            if server_name:
                _circuit_record_failure(server_name)
            raise
    raise last_exc


def _ensure_sse_initialized(url, api_key=None, server_name=None):
    cache_key = f"sse_{url}"
    cached = _mcp_init_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return

    try:
        _sse_request(url, _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "niv-ai", "version": "0.4.0"},
        }, req_id=_next_id()), api_key, server_name=server_name)
        try:
            _sse_request(url, _jsonrpc("notifications/initialized"), api_key, timeout=5, server_name=server_name)
        except Exception:
            pass
        _mcp_init_cache[cache_key] = {"initialized": True, "expires": time.time() + _MCP_INIT_TTL}
    except Exception:
        _mcp_init_cache.pop(cache_key, None)
        raise


def sse_list_tools(url, api_key=None, server_name=None) -> List[Dict]:
    _ensure_sse_initialized(url, api_key, server_name=server_name)
    resp = _sse_request(url, _jsonrpc("tools/list", {}, req_id=_next_id()), api_key, server_name=server_name)
    return resp.get("result", {}).get("tools", [])


def sse_call_tool(url, api_key, tool_name, arguments, server_name=None) -> Any:
    _ensure_sse_initialized(url, api_key, server_name=server_name)
    resp = _sse_request(url, _jsonrpc("tools/call", {
        "name": tool_name, "arguments": arguments
    }, req_id=_next_id()), api_key, timeout=30, server_name=server_name)
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
    cache_key = f"mcp_server_{server_name}"
    if hasattr(frappe.local, cache_key):
        return getattr(frappe.local, cache_key)
    doc = frappe.get_doc("Niv MCP Server", server_name)
    setattr(frappe.local, cache_key, doc)
    return doc


# ─── High-Level API (Bulletproof) ──────────────────────────────────

def get_all_active_servers() -> List[str]:
    """Get names of all active MCP servers."""
    return [d.name for d in frappe.get_all("Niv MCP Server", filters={"is_active": 1}, fields=["name"])]


def discover_tools(server_name: str, use_cache: bool = True) -> List[Dict]:
    """Discover tools from an MCP server.
    
    Resolution order:
    1. Worker memory cache (fastest, per-process)
    2. Redis shared cache (shared across all workers)
    3. HTTP/SSE MCP call (real discovery)
    4. Direct Python import for same-server FAC (deadlock-safe)
    5. DB fallback — tools_discovered JSON from Niv MCP Server doc
    
    NEVER returns empty if tools were ever discovered.
    """
    # 1. Worker memory cache
    if use_cache:
        with _cache_lock:
            cached = _tools_cache.get(server_name)
            if cached and cached["expires"] > time.time():
                return cached["tools"]

    # 2. Redis shared cache
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

    # 3. Try direct Python call for same-server (avoids HTTP deadlock)
    if same_server:
        tools = _direct_fac_list_tools() or []

    # 4. HTTP/SSE/stdio MCP call (only if not same-server or direct call failed)
    #    Circuit breaker: skip HTTP if circuit is open for this server
    if not tools and not _circuit_check(server_name):
        try:
            if doc.transport_type == "stdio":
                tools = stdio_list_tools(doc.command, doc.args, doc.env_vars)
            elif doc.transport_type == "streamable-http":
                tools = http_list_tools(doc.server_url, _get_api_key(doc), server_name=server_name)
            elif doc.transport_type == "sse":
                tools = sse_list_tools(doc.server_url, _get_api_key(doc), server_name=server_name)
            else:
                frappe.logger().warning(f"Niv MCP: Unknown transport '{doc.transport_type}' for '{server_name}'")
        except Exception as e:
            frappe.logger().error(f"Niv MCP: HTTP discovery failed for '{server_name}': {e}")
    elif not tools:
        frappe.logger().info(f"Niv MCP: Circuit open for '{server_name}', skipping HTTP discovery")

    # 5. DB fallback — NEVER return empty if we have stored tools
    if not tools:
        frappe.logger().warning(f"Niv MCP: All discovery methods failed for '{server_name}', using DB fallback")
        tools = _db_get_tools(server_name) or []

    # Store in all cache layers if we got tools
    if tools:
        with _cache_lock:
            _tools_cache[server_name] = {"tools": tools, "expires": time.time() + CACHE_TTL}
        _redis_set_tools(server_name, tools)

    return tools


def _rebuild_tool_index():
    """Rebuild the tool_name → server_name index from all active servers."""
    global _tool_index, _tool_index_expires
    
    # Try Redis first
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


def find_tool_server(tool_name: str) -> Optional[str]:
    """Find which MCP server has this tool. Uses cached index — instant lookup."""
    global _tool_index_expires

    with _cache_lock:
        if _tool_index_expires > time.time() and tool_name in _tool_index:
            return _tool_index[tool_name]

    _rebuild_tool_index()

    with _cache_lock:
        return _tool_index.get(tool_name)


def call_tool_fast(server_name: str, tool_name: str, arguments: Dict[str, Any], user_api_key: str = None) -> Any:
    """Execute a tool on an MCP server.
    
    For same-server FAC: tries direct Python import first (no HTTP deadlock).
    Falls back to HTTP if direct call fails.
    """
    doc = _get_server_config(server_name)
    api_key = user_api_key or _get_api_key(doc)

    # Same-server optimization: direct Python call (no HTTP, no deadlock)
    if doc.transport_type != "stdio" and _is_same_server(doc.server_url):
        result = _direct_fac_call_tool(tool_name, arguments, api_key)
        if result is not None:
            return result
        # Direct call failed, fall through to HTTP

    # Circuit breaker: if open, raise immediately so caller gets fallback
    if _circuit_check(server_name):
        raise MCPError(f"Circuit breaker open for '{server_name}' — server temporarily unavailable")

    if doc.transport_type == "stdio":
        return stdio_call_tool(doc.command, doc.args, doc.env_vars, tool_name, arguments)
    elif doc.transport_type == "streamable-http":
        return http_call_tool(doc.server_url, api_key, tool_name, arguments, server_name=server_name)
    elif doc.transport_type == "sse":
        return sse_call_tool(doc.server_url, api_key, tool_name, arguments, server_name=server_name)
    else:
        raise MCPError(f"Unknown transport: {doc.transport_type}")


def get_all_mcp_tools_cached() -> List[Dict]:
    """Get all MCP tools in OpenAI function calling format.
    
    Bulletproof: checks worker cache → Redis → MCP discovery → DB fallback.
    NEVER returns empty if tools were ever discovered.
    """
    global _openai_tools_cache

    # 1. Worker memory cache
    with _cache_lock:
        if _openai_tools_cache["expires"] > time.time() and _openai_tools_cache["tools"]:
            return _openai_tools_cache["tools"]

    # 2. Redis shared cache
    redis_tools = _redis_get_openai_tools()
    if redis_tools:
        with _cache_lock:
            _openai_tools_cache = {"tools": redis_tools, "expires": time.time() + CACHE_TTL}
        return redis_tools

    # 3. Build from MCP discovery (with all fallbacks)
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
                # BUG-005: ensure parameters always has proper structure
                if not isinstance(params, dict):
                    params = {"type": "object", "properties": {}}
                if "type" not in params:
                    params["type"] = "object"
                if "properties" not in params:
                    params["properties"] = {}
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

    # Store in all cache layers
    if result:
        with _cache_lock:
            _openai_tools_cache = {"tools": result, "expires": time.time() + CACHE_TTL}
        _redis_set_openai_tools(result)
        _rebuild_tool_index()
    else:
        frappe.logger().error("Niv MCP: WARNING — 0 tools loaded! All discovery + fallbacks failed.")

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


def close_all_sessions():
    """Close all HTTP sessions and stdio processes. BUG-014 fix.
    Call during worker shutdown or cache clear."""
    for key, session in list(_http_sessions.items()):
        try:
            session.close()
        except Exception:
            pass
    _http_sessions.clear()
    for key, cached in list(_stdio_cache.items()):
        try:
            if cached["proc"].poll() is None:
                cached["proc"].terminate()
        except Exception:
            pass
    _stdio_cache.clear()


def clear_cache(server_name: str = None):
    """Clear all caches (worker + Redis)."""
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
    
    # Clear Redis too
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
