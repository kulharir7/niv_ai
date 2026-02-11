# Bug Fix Summary — Niv AI

## BUG-001: EventSource GET truncation
**Status:** Already fixed. **Verified** in `niv_chat.js` — uses `fetch()` POST, no EventSource.

## BUG-002: CSRF bypass
**Status:** Already fixed. **Verified** in `niv_chat.js` line 1170 — sends `X-Frappe-CSRF-Token: frappe.csrf_token` header. `stream.py` accepts both GET and POST.

## BUG-003: MCP Session ID persistence
**Status:** Already handled. **Verified** in `mcp_client.py` — `_redis_set(f"session:{server_name}", sid, ttl=3600)` in `_http_post()` and `_build_headers()` retrieves it.

## BUG-004: Streaming chunks drop tool arguments
**File:** `niv_ai/niv_core/langchain/agent.py`
**Fix:** Added `_parse_tc_args()` helper that parses accumulated args string via `json.loads()` with fallback to `{}`. All 3 flush points in `stream_agent()` now use it.

## BUG-005: Missing input_schema structure
**File:** `niv_ai/niv_core/mcp_client.py`
**Fix:** In `get_all_mcp_tools_cached()`, added validation to ensure `parameters` always has `type` and `properties` keys.

## BUG-006: Redis bytes vs str mismatch
**File:** `niv_ai/niv_core/mcp_client.py`
**Fix:** `_redis_get()` now checks `isinstance(data, bytes)` and decodes before `json.loads()`. Also added to `_cb_redis_get()`.

## BUG-007: Circuit breaker per-worker not shared
**File:** `niv_ai/niv_core/mcp_client.py`
**Fix:** Replaced module-level `_circuit_breaker` dict with Redis-backed `_cb_redis_get()`/`_cb_redis_set()`. All workers now share circuit breaker state.

## BUG-008: Sensitive messages logged
**File:** `niv_ai/niv_core/langchain/callbacks.py`
**Fix:** Truncated `input_str` from 5000→500 chars in `NivLoggingCallback.on_tool_start()` and from 2000→500 in `NivStreamingCallback.on_tool_start()`.

## BUG-009: hash() cache key collisions
**File:** `niv_ai/niv_core/langchain/tools.py`
**Fix:** Replaced `hash(json.dumps(...))` with `hashlib.md5(json.dumps(..., sort_keys=True).encode()).hexdigest()`.

## BUG-010: Fragile system prompt
**Status:** Already handled. **Verified** in `memory.py` — `get_system_prompt()` has try/except around all lookups and returns `default_prompt` on any failure.

## BUG-011: Approximate token counting
**File:** `niv_ai/niv_core/langchain/callbacks.py`
**Fix:** Added `_estimate_token_count()` that tries `tiktoken` first, falls back to `len(text) // 4`.

## BUG-012: Tool description truncation
**Status:** Already fixed. **Verified** in `tools.py` — description uses `[:1024]` (not 200).

## BUG-013: New subprocess per stdio call
**File:** `niv_ai/niv_core/mcp_client.py`
**Fix:** Added `_stdio_cache` dict and `_get_stdio_session()` that caches initialized stdio processes with 2-minute TTL. `stdio_list_tools` and `stdio_call_tool` now reuse cached processes.

## BUG-014: HTTP client connection leaks
**File:** `niv_ai/niv_core/mcp_client.py`
**Fix:** Added `close_all_sessions()` function that closes all HTTP sessions and terminates cached stdio processes.

## BUG-015: v14 cache TTL incompatibility
**File:** `niv_ai/niv_core/mcp_client.py`
**Fix:** `_redis_set()` and `_cb_redis_set()` now wrap `expires_in_sec=` in try/except, falling back to `frappe.cache().setex()` for v14.

## BUG-016: Billing callback empty string
**File:** `niv_ai/niv_core/langchain/callbacks.py`
**Fix:** In `finalize()`, when `response_text` is falsy (empty string), now sets minimum 1 token for both prompt and completion.

## BUG-017: No audit trail for API key generation
**File:** `niv_ai/niv_core/api/_helpers.py`
**Fix:** Added Comment doc creation when auto-generating API keys, providing audit trail in the User doctype.

## BUG-018: Race condition in API key generation
**File:** `niv_ai/niv_core/api/_helpers.py`
**Fix:** Changed `frappe.get_doc("User", user)` to `frappe.get_doc("User", user, for_update=True)` to acquire row lock and prevent concurrent duplicate key generation.
