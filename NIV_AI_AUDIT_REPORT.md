# Niv AI Codebase Audit Report

**Date:** 2026-02-18  
**Server:** 65.1.106.8 (production)  
**Path:** `/home/gws/frappe-bench/apps/niv_ai`  
**Auditor:** Automated deep audit

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | 5 |
| 🟡 WARNING | 14 |
| 🟢 CLEANUP | 12 |

---

## 🔴 CRITICAL Issues (Will break or cause problems in production)

### C1. `niv_core/agent.py` — Dead/Orphaned Agent Class (NivAgent)
**File:** `niv_ai/niv_core/agent.py`  
**Issue:** This file contains an **async-based `NivAgent` class** that is completely separate from the actual working agent in `niv_core/langchain/agent.py`. The `NivAgent` class uses `async/await`, `AsyncGenerator`, and direct `openai`/`anthropic` SDK calls — but the entire production flow (stream.py, chat.py, telegram.py, whatsapp.py) uses the **LangChain-based agent** in `langchain/agent.py`.

The `test_agent.py` at the root still imports `from niv_ai.niv_core.agent import NivAgent`, and this class imports from `niv_ai.niv_core.tools.mcp_loader` and `niv_ai.niv_core.llm.provider` — modules that exist but are NOT used by the production flow.

**Risk:** If anyone calls `NivAgent` thinking it's the production agent, it will fail or produce different results. It also imports `load_mcp_tools` and `execute_tool` from `mcp_loader.py` which may or may not work correctly.  
**Fix:** Remove or clearly mark as deprecated. Safe to remove since production uses `langchain/agent.py`.

### C2. `niv_core/llm/provider.py` — Duplicate, Unused LLM Provider
**File:** `niv_ai/niv_core/llm/provider.py`  
**Issue:** This is a **full async LLM provider** (`LLMProvider` class) with OpenAI, Anthropic, Google support — but production uses `niv_core/langchain/llm.py` which creates LangChain `ChatOpenAI`/`ChatAnthropic`/etc. objects directly.

The `provider.py` has **2 bare `except:` clauses** (lines 180, 206) that silently swallow JSON parse errors during tool call argument parsing. This could hide real bugs if this code were ever invoked.

Additionally, `get_llm_provider()` at the bottom reads `settings.get("api_key")` and `settings.get("base_url")` directly from Niv Settings fields that may not exist in the current schema (the production flow uses `Niv AI Provider` DocType).

**Risk:** If referenced by mistake, it reads wrong config and fails silently.  
**Fix:** Remove or clearly mark as deprecated.

### C3. `_helpers.py` — `for_update=True` on User Doc Creates Lock Contention
**File:** `niv_ai/niv_core/api/_helpers.py`, function `get_user_api_key()`  
**Issue:** Line `user_doc = frappe.get_doc("User", user, for_update=True)` acquires a **database row lock** on the User document for EVERY chat message. Under concurrent users, this creates serialized access and potential deadlocks.

**Risk:** Performance degradation under load; potential deadlocks with other processes that lock User rows.  
**Fix:** Remove `for_update=True`. The race condition for API key generation is extremely rare and not worth the lock. Use `frappe.db.get_value` to check if key exists first, then only lock if creation is needed.

### C4. `stream.py` — Double Message Save (user message saved twice)
**File:** `niv_ai/niv_core/api/stream.py` + `telegram.py`  
**Issue:** In `stream_chat()`, `save_user_message()` is called with `dedup=True`, which checks for duplicates within 30 seconds. However, in `telegram.py`, `save_user_message()` is called **after** the agent runs (at the bottom), while the stream itself may also trigger message saves. The dedup window of 30s may not catch fast retries.

More critically, the `save_user_message` in `stream.py` happens **before** the generator starts, but the generator runs in a separate DB connection (after `frappe.init`/`frappe.connect`). If the original connection commits but the generator fails to start, the user message is saved but no response is generated.

**Risk:** Duplicate messages in conversation history; orphaned user messages without responses.  
**Fix:** Move message save inside the generator or add stronger dedup.

### C5. `stream.py` — No DB Connection Cleanup in Generator
**File:** `niv_ai/niv_core/api/stream.py`  
**Issue:** The `generate()` inner function calls `frappe.init(site=_site_name)` and `frappe.connect()` but never calls `frappe.destroy()`. For Werkzeug Response generators, this means DB connections can leak if the client disconnects mid-stream.

**Risk:** Database connection pool exhaustion under load.  
**Fix:** Add `finally: frappe.destroy()` in the generator, or use a context manager.

---

## 🟡 WARNING Issues (Should fix, not immediately urgent)

### W1. Bare `except:` Clauses in Active Code
**Files & Lines:**
- `niv_core/agent.py` — Line 251 (inside stream_agent finally block: `except:` after `frappe.db.sql("SELECT 1")`)
- `niv_core/agent.py` — Line 269 (inside stream_agent finally: `except:` after `frappe.db.connect()`)  
- `niv_core/knowledge/memory_service.py` — Lines 199, 291

**Issue:** Bare `except:` catches everything including `KeyboardInterrupt`, `SystemExit`. While these are in cleanup code, they can mask real errors.  
**Fix:** Change to `except Exception:`.

### W2. Thread-Safety Issue in `tools.py` Failure/Rate Trackers
**File:** `niv_ai/niv_core/langchain/tools.py`  
**Issue:** `_failure_tracker` and `_rate_limit_tracker` are plain dicts accessed from multiple Gunicorn worker threads without locks. While Gunicorn gthread typically handles one request per thread, LangGraph's `ThreadPoolExecutor` runs tools in separate threads, so concurrent tool executions within a single request could corrupt these dicts.

**Risk:** Rare data corruption in failure tracking; unlikely to cause crashes but could lead to incorrect rate limiting.  
**Fix:** Use `threading.Lock()` or `collections.defaultdict` with proper locking.

### W3. `niv_core/adk/` — Entire ADK Folder is Dead Code
**Files:** `agent_factory.py`, `stream_handler.py`, `discovery.py`, `final_test.py`, `db_check.py`, `chart_prototype.html`  
**Issue:** The ADK (Agent Development Kit) folder contains an alternative agent implementation using Google's ADK framework. None of these files are imported by any production code. `final_test.py` and `db_check.py` are test/debug scripts with hardcoded site names.

**Risk:** Confusion for developers; dead code increases maintenance burden.  
**Fix:** Move to `_adk_deprecated/` or remove entirely.

### W4. Root-Level Orphan Scripts
**Files:** `dump_prompt.py`, `temp_index_new.py`, `check_settings.py`, `get_fields.py`, `test_agent.py`  
**Issue:** These are developer debug/test scripts at the repository root. They contain hardcoded site names (`erp024.growthsystem.in`), direct `frappe.connect()` calls, and import from potentially broken paths (e.g., `test_agent.py` imports `NivAgent` which is the dead async agent).

**Risk:** Accidentally running these could connect to production and execute queries. `check_settings.py` prints API keys to stdout.  
**Fix:** Remove or move to a `scripts/dev/` folder with .gitignore.

### W5. `telegram.py` — Webhook Allows Guest Without Token Validation
**File:** `niv_ai/niv_core/api/telegram.py`  
**Issue:** The `webhook()` function is decorated with `@frappe.whitelist(allow_guest=True)`. While Telegram sends a secret token in the URL, the code does **not validate the webhook secret** — any POST to this endpoint with the right JSON structure will be processed.

**Risk:** Anyone who knows the endpoint URL can send fake messages and trigger agent responses as mapped users.  
**Fix:** Validate `X-Telegram-Bot-Api-Secret-Token` header or implement webhook URL secret.

### W6. `whatsapp.py` — Same Guest Webhook Issue
**File:** `niv_ai/niv_core/api/whatsapp.py`  
**Issue:** Same as W5 — `allow_guest=True` with no request signature validation. Meta sends `X-Hub-Signature-256` header for webhook verification, but the code only validates the initial GET challenge, not POST message authenticity.

**Risk:** Fake WhatsApp messages can trigger agent responses.  
**Fix:** Validate `X-Hub-Signature-256` on POST requests using the app secret.

### W7. `mobile.py` — `verify_token` Doesn't Actually Verify Secret
**File:** `niv_ai/niv_core/api/mobile.py`, function `verify_token()`  
**Issue:** The function extracts `api_key` and `api_secret` from the token but **only validates the api_key** (checks if a user exists with that key). It never compares the `api_secret` against the stored value. An attacker with just the api_key could pass verification.

**Risk:** Weak authentication — api_key alone is sufficient to pass verification.  
**Fix:** Add `api_secret` validation (compare with `user_doc.get_password("api_secret")`).

### W8. `mobile.py` — `mobile_login` Sets User to Administrator Before Validation
**File:** `niv_ai/niv_core/api/mobile.py`, function `mobile_login()`  
**Issue:** Line `frappe.set_user("Administrator")` is called BEFORE validating the API secret. If the secret validation throws an exception for any reason other than mismatch, the session remains as Administrator.

**Risk:** Potential privilege escalation if error handling changes.  
**Fix:** Use `frappe.utils.password.get_decrypted_password()` directly without switching user context, or ensure `finally` block resets user.

### W9. `voice.py` — TTS Files Written to Public Directory Without Cleanup
**File:** `niv_ai/niv_core/api/voice.py`  
**Issue:** Edge TTS and ElevenLabs write audio files directly to `public/files/` directory. While there's a `cleanup_voice_file` endpoint, nothing automatically cleans up files if the client never calls it. Over time, this accumulates hundreds of MB of audio files.

**Risk:** Disk space exhaustion on production server.  
**Fix:** Add a scheduled task to clean up `tts_*.mp3` files older than 1 hour from public/files.

### W10. `mcp_client.py` — Event Loop Thread Never Joins
**File:** `niv_ai/niv_core/mcp_client.py`, function `_get_event_loop()`  
**Issue:** Creates a daemon thread with `asyncio.run_forever()` and registers an atexit handler, but the thread is never properly joined. The `atexit` handler calls `loop.stop()` but the thread may not terminate cleanly.

**Risk:** Potential resource leak on worker restart; non-critical but messy.  
**Fix:** Add thread join with timeout in the atexit handler.

### W11. `langchain/rag.py` and `rag_indexer.py` — Referenced but Not Audited
**Files:** `niv_ai/niv_core/langchain/rag.py`, `rag_indexer.py`  
**Issue:** These are imported conditionally in `agent.py` (with `try/except`). If RAG is enabled but these files have issues, errors will be silently swallowed.

**Risk:** Silent RAG failures.  
**Fix:** At minimum, log a warning when RAG import fails.

### W12. `_helpers.py` — Auto-generates API Keys for Every User
**File:** `niv_ai/niv_core/api/_helpers.py`  
**Issue:** `get_user_api_key()` auto-generates API key + secret for any user who chats. This modifies the User document, creates a Comment audit trail, and commits — all as a side effect of sending a chat message. This is unexpected behavior.

**Risk:** All chat users get API keys they didn't request; potential compliance issue.  
**Fix:** Make auto-generation opt-in via a setting, or only generate when per_user_tool_permissions is enabled.

### W13. `save_reaction` in `chat.py` — Uses `conv.owner` Instead of `conv.user`
**File:** `niv_ai/niv_core/api/chat.py`, function `save_reaction()`  
**Issue:** Permission check uses `conv.owner` but conversations are typically created with `ignore_permissions=True` which sets owner to the session user. However, the `validate_conversation` helper uses `conv.user`. This inconsistency could allow/deny reactions incorrectly.

**Risk:** Users may not be able to react to their own messages if `owner != user`.  
**Fix:** Use `conv.user` consistently.

### W14. `tools.py` — Memory Tool Appended After Cache
**File:** `niv_ai/niv_core/langchain/tools.py`, function `get_langchain_tools()`  
**Issue:** The memory tool is appended to `lc_tools` AFTER `_lc_tools_cache["tools"] = lc_tools` — but since lists are mutable, it actually IS included in the cache. However, on the next cache hit, the memory tool is NOT re-appended (it's already there from the first call). This works by accident but is fragile — if the cache list is ever copied/replaced, the memory tool would be lost.

**Risk:** Low — works currently but fragile code.  
**Fix:** Append memory tool before caching.

---

## 🟢 CLEANUP Issues (Nice to have)

### CL1. `_a2a_deprecated/` — Not Imported Anywhere ✅
**Status:** Confirmed safe. No imports of `_a2a_deprecated` found in any active code.  
**Action:** Can be safely deleted to reduce repo size.

### CL2. `niv_core/langchain/nbfc_knowledge.py` and `dev_knowledge.py`
**Issue:** These knowledge files exist but are never imported by the production agent flow. The system prompt is built from `memory.py` + `agent_router.py` + `discovery.py`.  
**Action:** Verify if used by any manual script, then remove.

### CL3. `niv_core/langchain/temp_index_new.py`
**Issue:** Test/dev script inside the langchain module. Should not be in production.  
**Action:** Remove.

### CL4. `niv_core/langchain/callbacks.py` — Not Audited but Active
**Issue:** Referenced by `agent.py` (imports `NivStreamingCallback`, `NivBillingCallback`, `NivLoggingCallback`). Should be audited for proper error handling.  
**Action:** Review callbacks for proper exception handling.

### CL5. Multiple Duplicate CSS Files
**Issue:** `niv_chat_premium.css`, `niv_settings_premium.css`, `niv_thought.css` exist in both `page/niv_chat/` and `public/css/`. May be stale duplicates.  
**Action:** Verify which are loaded and remove duplicates.

### CL6. `system_prompt_dump.txt` — Debug Artifact at Root
**Issue:** Contains a dump of the system prompt. Should not be in production repo.  
**Action:** Remove and add to `.gitignore`.

### CL7. `niv_core/tools/mcp_loader.py` — Potentially Orphaned
**Issue:** Only imported by the dead `niv_core/agent.py` (NivAgent class). The production flow uses `mcp_client.py` directly via `langchain/tools.py`.  
**Action:** Verify no other imports, then remove.

### CL8. `niv_core/tools/result_cache.py` and `result_processor.py`
**Issue:** Imported by `langchain/tools.py` — these are active. But `result_cache.py` should be audited for cache invalidation issues.  
**Action:** Review for stale cache bugs.

### CL9. Unused Imports in Various Files
**Issue:** Several files import modules not used in function bodies (e.g., `from typing import AsyncGenerator` in `agent.py` which is sync-only). These don't cause errors but add clutter.  
**Action:** Run a linter (`ruff` or `flake8`) to clean up.

### CL10. `niv_core/knowledge/` — Multiple Knowledge Files with Overlapping Purpose
**Files:** `domain_nbfc.py`, `domain_nbfc_slim.py`, `dev_quick_reference.py`, `module_templates.py`, `system_map.py`, `fts_store.py`  
**Issue:** These appear to be various iterations of knowledge injection. Only `unified_discovery.py` and `memory_service.py` have `__pycache__` files (indicating recent use).  
**Action:** Audit which are actively used; remove the rest.

### CL11. `docs/convert_to_html.py` and `docs/generate_book.js`
**Issue:** Build scripts in docs folder. Not harmful but could be in a `scripts/` folder.  
**Action:** Low priority cleanup.

### CL12. `niv_ai.egg-info/` — Should be in .gitignore
**Issue:** Python package metadata directory committed to repo.  
**Action:** Add to `.gitignore` and remove from tracking.

---

## Workflow Trace: User Message → Response

**Happy Path (confirmed working):**
1. **User sends message** → `stream.py:stream_chat()` (SSE endpoint)
2. **Validation** → `_helpers.py:validate_conversation()` + `save_user_message()`
3. **Generator starts** → `frappe.init()` + `frappe.connect()` (new DB connection)
4. **Agent invoked** → `langchain/agent.py:stream_agent()`
5. **Agent created** → `create_niv_agent()` → gets LLM, tools, system prompt, callbacks
6. **LLM** → `langchain/llm.py:get_llm()` → creates `ChatOpenAI`/`ChatAnthropic`/etc.
7. **Tools** → `langchain/tools.py:get_langchain_tools()` → wraps MCP tools as LangChain StructuredTools
8. **MCP** → `mcp_client.py` → same-server: direct Python call to FAC; remote: SDK
9. **System prompt** → `langchain/memory.py:get_system_prompt()` + `agent_router.py`
10. **LangGraph ReAct** → `create_react_agent()` → streams tokens, tool calls, tool results
11. **Response saved** → `_helpers.py:save_assistant_message()`
12. **SSE done** → `{"type": "done"}`

**Gaps identified:**
- No `frappe.destroy()` in generator (C5)
- User message saved before generator starts but response saved inside generator (C4)
- No timeout on DB reconnect in finally block

---

## Security Summary

| Issue | Severity | Description |
|-------|----------|-------------|
| Telegram webhook no auth | 🟡 | Accepts any POST without secret validation |
| WhatsApp webhook no signature | 🟡 | No X-Hub-Signature-256 validation |
| Mobile verify_token weak | 🟡 | Doesn't verify api_secret |
| mobile_login Admin escalation | 🟡 | Sets Administrator before validation |
| Auto API key generation | 🟡 | Modifies User docs as side effect |
| check_settings.py leaks | 🟡 | Debug script prints config to stdout |
| No rate limit on webhooks | 🟢 | Telegram/WhatsApp have no rate limiting |

---

## Recommendations (Priority Order)

1. **Fix C3** — Remove `for_update=True` from `get_user_api_key()` (5 min fix, big impact)
2. **Fix C5** — Add `frappe.destroy()` in stream generator finally block (5 min fix)
3. **Fix W5/W6** — Add webhook authentication for Telegram and WhatsApp
4. **Fix W7/W8** — Fix mobile token verification
5. **Clean CL1** — Delete `_a2a_deprecated/` folder
6. **Clean W3/W4** — Move/remove ADK folder and root-level scripts
7. **Fix W2** — Add threading lock to failure/rate trackers
8. **Clean C1/C2** — Remove or deprecate `niv_core/agent.py` and `niv_core/llm/provider.py`
9. **Fix W9** — Add scheduled cleanup for TTS audio files
10. **Fix W1** — Replace bare `except:` with `except Exception:`

---

*End of audit. All findings are read-only observations. No files were modified.*
