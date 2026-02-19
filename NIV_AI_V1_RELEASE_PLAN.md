# Niv AI v1.0.0 — Stable Release Plan

**Date:** 2026-02-19  
**Current Version:** 0.9.0  
**Author:** Roma (AI Assistant)  
**Scope:** Complete audit → Prioritized fix plan → Effort estimates

---

## A. Current State Assessment

### ✅ What's Working Well
- **Core chat flow** — SSE streaming via LangGraph ReAct agent is solid and battle-tested
- **MCP tool system** — 34 tools with LLM-driven selection (no keyword routing), enhanced descriptions, result processing (4KB cap), failure tracking, rate limiting, circuit breakers
- **Multi-provider LLM** — OpenAI-compatible (Mistral/OpenAI/Ollama/Groq), Anthropic, Google all working via `llm.py`
- **Same-server MCP optimization** — Direct Python calls to FAC, no HTTP overhead. Smart.
- **Voice pipeline** — Full STT→LLM→TTS chain: Voxtral Mini STT + ElevenLabs/Edge TTS/Piper TTS with SSML, language detection, text cleaning
- **Export** — Excel/CSV/PDF all working with proper formatting, auto-fit columns, frozen headers
- **Artifact preview** — HTML apps render in iframe, fixed race condition with DB load
- **Page context** — JS sends current doctype/docname, injected into system prompt
- **Model switching** — User can pick model per message, saved in DB
- **Auto-routing** — Simple queries → fast_model, complex → default_model
- **Confirmation flow** — Write operations need user approval (dev mode: all writes, normal: dangerous only)
- **Token tracking** — Input/output/total tokens tracked per message via billing callback
- **Unified discovery** — Single system knowledge source with Redis caching
- **User memory** — `remember_user_preference` tool + memory service
- **Result caching** — Read-only tools (get_doctype_info, etc.) cached for 2 min
- **NBFC domain knowledge** — Slim + full versions, DocType schemas in agent router

### 🔴 What's Broken/Buggy
1. **DB connection leak** — `stream.py` generator calls `frappe.init()`/`frappe.connect()` but NEVER calls `frappe.destroy()`. Comment says "don't call it" but that leaks connections under load. Partial fix exists (`_ensure_db`) but only in `finally` block, not cleanup.
2. **MCP tools return empty intermittently** — `get_all_mcp_tools_cached()` can return `[]` if FAC's `_import_tools()` fails silently or Redis cache expires between check and rebuild. The `_openai_tools_cache` has a race: tools can be [] in cache with valid expiry.
3. **Double user message save** — `save_user_message()` called before generator starts (main thread), but response saved inside generator (new DB connection). If generator fails to start, orphaned user message with no response.
4. **`for_update=True` on User doc** — `get_user_api_key()` acquires row lock on User for EVERY chat message. Serializes all concurrent users.
5. **Telegram webhook — no secret validation** — `allow_guest=True` with zero authentication. Anyone who knows the URL can inject fake messages.
6. **WhatsApp webhook — no signature verification** — Same issue. `X-Hub-Signature-256` not checked.
7. **Mobile `verify_token` doesn't verify secret** — Only checks api_key exists, never compares api_secret.
8. **Mobile `mobile_login` sets Administrator before validation** — Potential privilege escalation.

### 🟡 What's Half-Built
1. **OAuth (Claude/ChatGPT)** — Full PKCE flow coded, token exchange works, refresh works. BUT: Claude OAuth client_id conflicts with same account on OpenClaw. ChatGPT CLI-only client_id won't work in browser. **Status: Code complete, unusable in practice for most users.**
2. **Voice mode flag** — `is_voice_request` flag concept exists in improvement plan but NOT implemented. Voice responses are still long/verbose.
3. **TTS file cleanup** — `cleanup_voice_file` endpoint exists but nothing auto-cleans. TTS files accumulate forever in `public/files/`.
4. **Scheduled reports** — DocType `Niv Scheduled Report` exists but `scheduler.py` API is just scaffolding.
5. **Knowledge base/RAG** — `rag.py` and `rag_indexer.py` exist, imported with try/except. Silently fails if broken.
6. **NBFC compound tools** — Full implementation plan in `MCP_TOOLS_IMPLEMENTATION_PLAN.md` Phase 3, not coded.

### 🔵 Code Quality Issues
1. **`niv_chat.js` is 4,471 lines** — Monolithic monster. Chat, voice, sidebar, themes, artifacts, mobile, settings all in one file.
2. **Two copies of `niv_chat.js`** — `public/js/niv_chat.js` (wrong, unused by page) and `niv_ui/page/niv_chat/niv_chat.js` (correct). Confusing.
3. **Dead `niv_core/agent.py`** — Async NivAgent class, completely separate from production LangChain agent. Imports dead `llm/provider.py` and `tools/mcp_loader.py`.
4. **Dead `niv_core/llm/provider.py`** — Full async LLM provider with bare `except:` clauses. Never used.
5. **Dead `_a2a_deprecated/` folder** — Old A2A multi-agent code. Safe to delete.
6. **Dead ADK folder** — `niv_core/adk/` with alternative agent implementation. Never imported.
7. **Root-level debug scripts** — `dump_prompt.py`, `temp_index_new.py`, `check_settings.py`, `get_fields.py`, `test_agent.py` with hardcoded prod site names.
8. **Bare `except:` clauses** — In `agent.py` (lines 251, 269), `memory_service.py` (lines 199, 291).
9. **Thread-safety** — `_failure_tracker` and `_rate_limit_tracker` are plain dicts without locks, accessed from LangGraph's ThreadPoolExecutor.
10. **Multiple duplicate CSS files** — `niv_chat_premium.css`, `niv_settings_premium.css` exist in both `page/niv_chat/` and `public/css/`.
11. **Unused knowledge files** — `nbfc_knowledge.py`, `dev_knowledge.py`, `domain_nbfc.py` (full version only used in dev mode, `domain_nbfc_slim.py` is the active one).

---

## B. CRITICAL Fixes (Must Do Before 1.0)

### B1. DB Connection Leak — stream.py generator
**File:** `niv_ai/niv_core/api/stream.py`  
**Problem:** Generator calls `frappe.init()`/`frappe.connect()` but never `frappe.destroy()`. Under load, DB pool exhaustion.  
**Fix:** Add `frappe.destroy()` in a SEPARATE finally block AFTER yielding the final `done` event. The current comment "don't call it" is wrong — the generator IS a separate request context. Use a flag to only destroy if we connected.  
**Risk:** HIGH — production server will run out of DB connections under sustained load.  
**Effort:** 1 hour

### B2. MCP Tools Empty Intermittently
**File:** `niv_ai/niv_core/mcp_client.py`  
**Problem:** Race condition in `get_all_mcp_tools_cached()` — can cache empty list with valid expiry. Also `_direct_list_tools()` can return [] if FAC's `_import_tools()` is slow.  
**Fix:** 
1. Never cache empty tool lists: add `if result:` check before caching
2. Add a minimum tool count check: if cached < 5 tools, force re-discovery
3. Add a stale-while-revalidate pattern: serve old cache while refreshing in background  
**Effort:** 2 hours

### B3. Security — Webhook Authentication
**Files:** `telegram.py`, `whatsapp.py`, `mobile.py`  
**Fixes:**
- Telegram: Validate `X-Telegram-Bot-Api-Secret-Token` header
- WhatsApp: Validate `X-Hub-Signature-256` using app secret (HMAC-SHA256)
- Mobile: Compare `api_secret` against stored value, remove `frappe.set_user("Administrator")` before validation  
**Effort:** 3 hours

### B4. Remove `for_update=True` Lock
**File:** `niv_ai/niv_core/api/_helpers.py`  
**Problem:** Row lock on User doc for every message.  
**Fix:** Use `frappe.db.get_value("User", user, "api_key")` first. Only lock+create if missing.  
**Effort:** 30 minutes

### B5. Dead Code Cleanup
**Delete these files/folders:**
- `niv_ai/niv_core/agent.py` (dead async NivAgent)
- `niv_ai/niv_core/llm/provider.py` (dead async LLM provider)
- `niv_ai/niv_core/tools/mcp_loader.py` (only imported by dead agent.py)
- `_a2a_deprecated/` folder
- `niv_core/adk/` folder
- Root scripts: `dump_prompt.py`, `temp_index_new.py`, `check_settings.py`, `get_fields.py`, `test_agent.py`, `system_prompt_dump.txt`
- `public/js/niv_chat.js` (wrong copy, unused)
- `niv_ai.egg-info/` (add to .gitignore)  
**Effort:** 1 hour

### B6. Thread-Safety Fix
**File:** `niv_ai/niv_core/langchain/tools.py`  
**Fix:** Add `threading.Lock()` around `_failure_tracker` and `_rate_limit_tracker` access.  
**Effort:** 30 minutes

### B7. Bare `except:` → `except Exception:`
**Files:** `agent.py`, `memory_service.py`  
**Effort:** 15 minutes

---

## C. Feature Completion Status

### C1. OAuth (Claude/ChatGPT)
**Code:** ✅ Complete — `oauth.py` has full PKCE flow, token exchange, auto-refresh  
**Reality:** ❌ Unusable — Claude client_id conflicts with same-account on other apps. ChatGPT client_id is CLI-only (browser login blocked by OpenAI).  
**v1.0 Decision:** Keep the code. Document that OAuth requires separate Claude/ChatGPT accounts. Add a "Paste Token" manual flow as fallback. Mark as "experimental" in UI.  
**Effort:** 2 hours (documentation + UI label)

### C2. Model Switching
**Status:** ✅ Complete  
- `stream.py` reads `model` param from JS
- Model saved per message in DB (`model` field on Niv Message)
- UI has model dropdown  
**Remaining:** None for v1.0

### C3. Auto Model Routing
**Status:** ✅ Complete  
- `_is_simple_query()` detects greetings/thanks/yes/no
- Routes to `fast_model` from Niv Settings
- Falls through to `default_model` for complex queries  
**Remaining:** Could add more patterns but functional for v1.0

### C4. Voice Pipeline
**Status:** 🟡 90% Complete  
**Working:** STT (Voxtral + Whisper fallback), TTS (ElevenLabs → Edge TTS → Piper → browser), SSML, language detection, text cleaning, streaming TTS  
**Missing for v1.0:**
- TTS file auto-cleanup (scheduled task) — **MUST FIX** (disk exhaustion)
- Voice mode flag (shorter responses for voice) — nice to have
- Indian number formatting ("50 lakh" not "5000000") — nice to have  
**Effort:** 2 hours (cleanup task), 3 hours (voice mode flag)

### C5. Export (Excel/CSV/PDF)
**Status:** ✅ Complete  
- All three formats working with proper formatting
- Markdown table parser for direct export from chat
- PDF via wkhtmltopdf with fallback  
**Remaining:** None for v1.0

### C6. Artifact Preview
**Status:** ✅ Complete (fixed in session 2 on Feb 19)  
- HTML detection broadened (`<style>` alone triggers)
- Preview renders directly without DB load chain
- `select_artifact` skips placeholder content
- Race condition between `append_message` and `load_artifacts_list` resolved  
**Remaining:** None for v1.0

### C7. Page Context
**Status:** ✅ Complete  
- JS sends `context` with current doctype/docname/route
- `stream.py` passes to `agent.py` → `memory.py`
- Injected into system prompt via `format_page_context()`  
**Remaining:** None for v1.0

---

## D. Code Quality

### D1. Files That Need Refactoring
| File | Lines | Issue | Priority |
|------|-------|-------|----------|
| `niv_chat.js` | 4,471 | Monolithic — everything in one file | HIGH |
| `tools.py` | ~500 | Confirmation flow + dev mode + undo mixed with tool loading | MEDIUM |
| `voice.py` | ~600 | TTS engines + STT + text cleaning all in one file | LOW |
| `mcp_client.py` | ~400 | Fine for now but complex | LOW |

### D2. niv_chat.js Split Plan
Split the 4,471-line monolith into focused modules:

```
niv_chat/
├── niv_chat.js          (~200 lines) — Page init, event binding, routing
├── chat_core.js         (~800 lines) — Message send/receive, SSE, append_message
├── voice.js             (~600 lines) — STT, TTS, voice mode, waveform
├── sidebar.js           (~400 lines) — Conversation list, search, new chat
├── artifacts.js         (~500 lines) — Artifact panel, preview, save
├── themes.js            (~200 lines) — Dark mode, theme switching
├── settings_panel.js    (~300 lines) — Settings sidebar, model picker
├── export.js            (~200 lines) — Download buttons, export API calls
├── mobile.js            (~300 lines) — Mobile layout, touch handlers
├── utils.js             (~200 lines) — Markdown render, formatters, helpers
```

**Approach:** Frappe pages load all JS files in the page folder. Use IIFE modules or a simple namespace (`NivChat.voice`, `NivChat.sidebar`) for now. No bundler needed.  
**Effort:** 8-10 hours

### D3. Duplicate Code to Consolidate
- `_execute_single_tool()` in `tools.py` duplicates the MCP result parsing logic from `_make_mcp_executor()`. Extract to shared helper.
- `clean_text_for_tts()` thinking tag removal duplicates `_strip_thinking()` in `agent.py`. Extract to shared util.
- Voice config loading (`_get_voice_config()`) is called multiple times per request. Cache it.

### D4. Dead Files to Remove
(Listed in B5 above — 12+ files/folders)

### D5. Unused Knowledge Files
Verify and remove if unused:
- `niv_core/langchain/nbfc_knowledge.py`
- `niv_core/langchain/dev_knowledge.py`
- `niv_core/knowledge/domain_nbfc.py` (keep `domain_nbfc_slim.py`)
- `niv_core/knowledge/system_map.py`
- `niv_core/knowledge/fts_store.py`
- `niv_core/knowledge/auditor_service.py`
- `niv_core/knowledge/planner_service.py`

---

## E. Testing Checklist

### E1. Core Chat
- [ ] Send simple message → get response
- [ ] Send complex query with tool calls → correct data returned
- [ ] Send message with no conversation_id → auto-creates conversation
- [ ] Send empty message → proper error
- [ ] Test with 50+ message conversation → token truncation works
- [ ] Multiple concurrent users → no DB lock contention (after B4 fix)
- [ ] Stream disconnect mid-response → DB connection cleaned up (after B1 fix)

### E2. MCP Tools
- [ ] All 34 tools discoverable after fresh restart
- [ ] Tool cache refresh after 5 min
- [ ] Tool call with wrong params → recovery hint returned
- [ ] Tool call fails 3x → failure limit stops retries
- [ ] Read-only tool results cached (get_doctype_info called twice = 1 MCP call)
- [ ] Write tool → confirmation prompt shown
- [ ] Delete tool → extra warning shown
- [ ] Rate limit: >50 calls/min → rate limit message

### E3. Voice
- [ ] Record voice → STT returns text
- [ ] Text → TTS → audio plays (ElevenLabs if key set, else Edge TTS)
- [ ] Hindi text → Hindi voice selected
- [ ] English text → English voice selected
- [ ] Streaming TTS: each sentence gets separate audio
- [ ] Voice cleanup endpoint works
- [ ] TTS with no engines available → browser fallback signal

### E4. Model Switching
- [ ] Select different model in dropdown → uses that model
- [ ] Model saved on Niv Message record
- [ ] Simple greeting → auto-routes to fast_model (if configured)
- [ ] Complex query → uses default_model

### E5. Export
- [ ] Export table data as Excel → downloads formatted .xlsx
- [ ] Export as CSV → proper UTF-8 with BOM
- [ ] Export as PDF → landscape for wide tables
- [ ] Export markdown table from chat → parses correctly

### E6. Artifacts
- [ ] "Build a calculator" → HTML generated in code block
- [ ] Artifact panel opens → iframe renders the HTML
- [ ] Interactive elements (buttons, forms) work in preview
- [ ] Normal chat message → no artifact panel triggered

### E7. Page Context
- [ ] On Sales Invoice form → "what is this?" → gets the specific invoice
- [ ] On Loan list → "filter these" → understands Loan list context
- [ ] On dashboard → context shows in system prompt

### E8. Security
- [ ] Telegram webhook without secret → rejected (after B3 fix)
- [ ] WhatsApp webhook without signature → rejected (after B3 fix)
- [ ] Mobile login with wrong api_secret → rejected (after B3 fix)
- [ ] Guest user → cannot access chat APIs

### E9. Edge Cases
- [ ] LLM returns thinking tags → stripped before display
- [ ] Very long response (>10K chars) → renders without crash
- [ ] Tool returns 50KB+ result → truncated to 4KB
- [ ] Network timeout to LLM → friendly error message
- [ ] Rate limit from LLM → friendly message
- [ ] Conversation history > 32K tokens → oldest messages dropped

---

## F. Performance

### F1. Current Response Times (Estimated)
| Operation | Time | Notes |
|-----------|------|-------|
| First token | 1-3s | Depends on LLM provider |
| Simple greeting | 0.5-1s | If fast_model configured |
| Tool call (same-server) | 100-300ms | Direct Python, no HTTP |
| Tool call (remote) | 500-2000ms | SDK with network roundtrip |
| TTS (Edge TTS) | 500-1500ms | Per sentence |
| TTS (ElevenLabs) | 300-800ms | Per sentence |
| STT (Voxtral) | 500-1500ms | API call |
| STT (Whisper local) | 1-3s | CPU, base model |
| Export Excel | 200-500ms | Small datasets |

### F2. Optimization Opportunities
1. **DB connection in generator** — After B1 fix, consider connection pooling instead of new connection per stream
2. **Voice config loading** — `_get_voice_config()` reads Niv Settings on every call. Cache for 60s.
3. **Tool description enhancement** — `get_enhanced_description()` called per tool per cache rebuild. Fine at 5-min intervals.
4. **System prompt building** — Multiple DB queries per message (settings, conversation, discovery, memory). Could cache assembled prompt per conversation for 30s.
5. **LLM connection reuse** — `get_llm()` creates new ChatOpenAI instance per request. Could cache per provider for 5 min.
6. **Parallel tool calls** — LangGraph supports parallel tool execution. Currently sequential. Enable `tool_choice: "parallel"` or similar.

---

## G. Phase-wise Plan

### Phase 1: Critical Fixes (MUST before 1.0)
| Task | Effort | Priority |
|------|--------|----------|
| B1. DB connection leak fix | 1h | P0 |
| B2. MCP tools empty fix | 2h | P0 |
| B3. Webhook security (Telegram + WhatsApp + Mobile) | 3h | P0 |
| B4. Remove `for_update=True` lock | 0.5h | P0 |
| B5. Dead code cleanup (12+ files) | 1h | P1 |
| B6. Thread-safety fix | 0.5h | P1 |
| B7. Bare except fix | 0.25h | P1 |
| C4. TTS file auto-cleanup task | 2h | P1 |
| **Subtotal** | **~10 hours** | |

### Phase 2: Feature Polish (Should do)
| Task | Effort | Priority |
|------|--------|----------|
| C1. OAuth documentation + "Paste Token" flow | 2h | P2 |
| Voice mode flag (shorter responses) | 3h | P2 |
| Conversation title auto-generation via LLM | 1h | P2 |
| Shared chat improvements | 2h | P2 |
| Dashboard page polish | 2h | P2 |
| **Subtotal** | **~10 hours** | |

### Phase 3: Code Quality (Should do)
| Task | Effort | Priority |
|------|--------|----------|
| D2. niv_chat.js split into modules | 10h | P2 |
| D3. Duplicate code consolidation | 2h | P3 |
| D5. Remove unused knowledge files | 1h | P3 |
| D1. tools.py refactor (separate confirmation logic) | 3h | P3 |
| Duplicate CSS cleanup | 1h | P3 |
| Add .gitignore entries (egg-info, debug files) | 0.25h | P3 |
| **Subtotal** | **~17 hours** | |

### Phase 4: Testing & Stabilization
| Task | Effort | Priority |
|------|--------|----------|
| E1-E3 Core + Tools + Voice testing | 4h | P1 |
| E4-E7 Feature testing | 3h | P1 |
| E8 Security testing | 2h | P1 |
| E9 Edge case testing | 2h | P2 |
| Fix bugs found during testing | 4h (estimate) | P1 |
| **Subtotal** | **~15 hours** | |

### Total Effort Estimate

| Phase | Hours | Can Ship Without? |
|-------|-------|-------------------|
| Phase 1: Critical Fixes | 10h | ❌ NO |
| Phase 2: Feature Polish | 10h | ⚠️ Maybe (reduced scope) |
| Phase 3: Code Quality | 17h | ✅ Yes (tech debt) |
| Phase 4: Testing | 15h | ❌ NO |
| **TOTAL** | **~52 hours** | |

### Minimum Viable 1.0 (Phases 1 + 4 only)
**25 hours** — Fix critical bugs, test everything, ship.

### Recommended 1.0 (Phases 1 + 2 + 4)
**35 hours** — Fix bugs, polish features, test, ship. Leave JS refactor for 1.1.

### Full 1.0 (All phases)
**52 hours** — Everything including code quality. Ideal but not strictly necessary.

---

## Release Checklist (Day of Release)

- [ ] All Phase 1 fixes merged and tested
- [ ] `bench build` succeeds (or verify Frappe page loads correctly)
- [ ] Git tag `v1.0.0` created
- [ ] CHANGELOG.md updated
- [ ] Production deploy: `git pull upstream main && bench migrate && sudo supervisorctl restart all`
- [ ] Smoke test on production: send message, voice, export, artifact
- [ ] Monitor error logs for 1 hour post-deploy

---

*This plan is brutally honest. The codebase is 80% solid with a strong architecture, but the remaining 20% has real production risks (DB leaks, security holes, dead code confusion). Phase 1 is non-negotiable. Ship after that.*
