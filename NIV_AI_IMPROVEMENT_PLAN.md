# Niv AI — Complete Improvement Plan
**Date:** 2026-02-18 | **Current Version:** 0.9.0 | **Model:** Mistral Large 3 675B

---

## Current State Summary
- **Agent:** LangGraph ReAct agent with 34 MCP tools (from FAC)
- **Voice:** STT (Voxtral Mini) → LLM → TTS (ElevenLabs/Edge TTS/Piper)
- **UI:** 4348-line JS monolith, dark mode, themes, charts, file upload, mobile support
- **System Prompt:** ~4K chars + NBFC domain + few-shot examples + DocType schemas
- **Streaming:** SSE token-by-token with sentence-level TTS queue
- **Context:** 32K token limit, history truncation, user memory

---

## 🔴 PRIORITY 1 — Critical Fixes (This Week)

### 1.1 Voice Quality Polish
**Problem:** TTS still reads artifacts, "." sounds unnatural, responses too verbose for voice
**Files:** `voice.py`, `niv_chat.js`, `memory.py`

- [ ] **Smart voice detection:** Add `is_voice_request` flag in stream API → system prompt gets extra rule: "Respond in 1-2 short sentences, conversational Hindi/English"
- [ ] **Sentence splitting fix:** Current regex `[.!?]\s+` breaks on "Rs. 50,000" and "Dr. Sharma" — use smart sentence tokenizer (abbreviation-aware)
- [ ] **Number pronunciation:** "₹50,00,000" should become "50 lakh rupees" for TTS — add Indian number formatting in `clean_text_for_tts()`
- [ ] **Silence handling:** If TTS produces empty/very short audio (<0.5s), skip it instead of playing silence gap

### 1.2 Response Speed
**Problem:** Each voice sentence → separate HTTP call to `stream_tts` → slow
**Files:** `voice.py`, `niv_chat.js`

- [ ] **Batch TTS:** Instead of 1 sentence = 1 API call, buffer 2-3 sentences and send as one → fewer round trips
- [ ] **Audio prefetch depth:** Currently queues 1 ahead. Queue 3 ahead while playing current
- [ ] **Edge TTS async fix:** `asyncio.run()` inside sync Frappe = thread pool overhead. Use `edge_tts` in a persistent async worker thread

### 1.3 Error Resilience
**Problem:** If LLM tool call fails, user gets cryptic error
**Files:** `agent.py`, `tools.py`

- [ ] **Retry with different approach:** If `get_document` fails (404), auto-try `search_documents`. Currently just errors out
- [ ] **Graceful tool timeout:** Tool calls >10s should abort with friendly message, not hang
- [ ] **Connection recovery in stream:** If DB connection drops mid-stream (line 317 in agent.py), reconnect + continue instead of crashing

---

## 🟡 PRIORITY 2 — Better Intelligence (Week 2-3)

### 2.1 Conversation Memory Improvement
**Problem:** LLM has no context of what user asked 5 messages ago in long conversations
**Files:** `memory.py`, `callbacks.py`

- [ ] **Conversation summarization:** After 10 messages, summarize older messages into 1 system message → keeps context without token bloat
- [ ] **Entity extraction:** Track entities mentioned (loan IDs, customer names) in conversation → auto-inject as context
- [ ] **Cross-conversation memory:** "Remember that customer X has issue Y" → persists in `Niv AI Memory` DocType

### 2.2 Smarter Tool Usage
**Problem:** LLM sometimes calls wrong tool or uses unnecessary calls
**Files:** `agent_router.py`, `tools.py`, `result_processor.py`

- [ ] **Tool result learning:** If LLM called tool A and it worked, cache that pattern. Next similar query → hint that pattern
- [ ] **Schema-aware validation:** Before executing `run_database_query`, validate SQL against known table/column names → prevent "column not found" errors
- [ ] **Compound tool results:** When LLM calls `list_documents` then `get_document` for each item → detect this pattern, suggest `run_database_query` instead
- [ ] **Tool call analytics:** Log which tools are called per query type → dashboard showing tool usage patterns → identify optimization opportunities

### 2.3 Multi-turn Context
**Problem:** "Show loans" → (shows) → "filter by branch Delhi" → LLM doesn't know to re-run with filter
**Files:** `agent.py`, `memory.py`

- [ ] **Implicit context carry:** Detect follow-up queries ("filter this", "sort by", "show more") → inject previous tool call context
- [ ] **Pronoun resolution:** "What's its interest rate?" → resolve "its" to previously mentioned loan
- [ ] **Conversation state tracking:** Track last query type + last tool results → use as context for ambiguous follow-ups

---

## 🟢 PRIORITY 3 — UX & Features (Week 3-4)

### 3.1 UI Improvements
**Problem:** 4348-line monolith JS, some UI gaps
**Files:** `niv_chat.js`, `niv_chat_premium.css`

- [ ] **Split JS into modules:** `niv_chat.js` → `chat_core.js` + `voice.js` + `sidebar.js` + `themes.js` + `mobile.js` → easier maintenance
- [ ] **Quick action buttons:** After showing loans, show "📊 Chart" "📄 Export" "🔍 Filter" buttons below response
- [ ] **Typing indicators:** Show "Niv is thinking..." with tool name when tool is being called
- [ ] **Message reactions:** 👍/👎 on responses → feeds into quality tracking
- [ ] **Copy button:** One-click copy for code blocks, tables, and full responses
- [ ] **Keyboard shortcuts:** Ctrl+N (new chat), Ctrl+/ (focus input), Esc (cancel voice), ↑ (edit last message)

### 3.2 Voice Mode UX
**Problem:** Voice mode feels robotic, not conversational
**Files:** `niv_chat.js`, `voice.py`

- [ ] **Wake word (optional):** "Hey Niv" to start listening → reduces accidental triggers
- [ ] **Voice activity UI:** Animated waveform during listening (like Google Assistant) instead of static icon
- [ ] **Auto language switch:** If user speaks Hindi, respond in Hindi. If English, respond in English. Currently browser STT is fixed `hi-IN`
- [ ] **Voice speed control:** User can set TTS speed (0.8x - 1.5x) in settings
- [ ] **Continuous conversation:** After TTS finishes playing, auto-start listening again (toggle-able)

### 3.3 WhatsApp/Telegram Integration
**Problem:** Voice features limited to web UI only
**Files:** `whatsapp.py`, `telegram.py`

- [ ] **WhatsApp voice notes:** Receive voice note → Voxtral STT → process → reply text (or voice note back)
- [ ] **Telegram voice:** Same flow for Telegram voice messages
- [ ] **Rich formatting:** WhatsApp bold/lists, Telegram markdown in responses
- [ ] **Quick replies:** Suggest buttons in WhatsApp for common follow-ups

---

## 🔵 PRIORITY 4 — Advanced Features (Month 2)

### 4.1 NBFC Compound Tools
**Problem:** "Give me loan summary for customer X" takes 3-4 tool calls
**Files:** New `niv_core/tools/nbfc/`

- [ ] **`nbfc_loan_summary`:** Single call → loan details + repayment status + NPA classification + outstanding
- [ ] **`nbfc_portfolio_dashboard`:** Branch-wise summary, DPD distribution, NPA %, collection efficiency — one call
- [ ] **`nbfc_calculate_emi`:** Pure calculation, no DB needed. EMI/IRR/flat rate conversion
- [ ] **`nbfc_customer_360`:** All loans + repayments + applications for a customer — one call
- [ ] These are Niv AI client-side tools (hooks/overrides), NOT FAC modifications

### 4.2 Document Generation
**Problem:** Users can query data but can't generate reports
**Files:** New `niv_core/api/reports.py`

- [ ] **PDF Export:** "Generate NPA report as PDF" → query data → format → PDF download
- [ ] **Excel Export:** "Export loan list to Excel" → structured export
- [ ] **Scheduled Reports:** "Send me branch-wise NPA report every Monday" → `Niv Scheduled Report` DocType
- [ ] **Email Reports:** Auto-email generated reports to configured recipients

### 4.3 Proactive Alerts
**Problem:** Niv only responds to queries, never proactively alerts
**Files:** New `niv_core/alerts/`, `scheduler.py`

- [ ] **NPA Alert:** "Customer X crossed 90 DPD" → auto-alert via WhatsApp/Telegram
- [ ] **Collection Reminder:** "EMI due tomorrow for 50 customers" → daily digest
- [ ] **Anomaly Detection:** Unusual loan amount, multiple applications from same customer → flag
- [ ] **Dashboard Widget:** Frappe desk widget showing today's key metrics from Niv

### 4.4 Analytics & Monitoring
**Problem:** No visibility into how Niv is performing
**Files:** `callbacks.py`, new `niv_core/analytics/`

- [ ] **Query analytics dashboard:** Response time, tool calls per query, success rate, most common queries
- [ ] **Cost tracking:** Token usage per user/day/month with billing dashboard
- [ ] **Error tracking:** Failed queries with root cause → auto-fix suggestions
- [ ] **User satisfaction:** Track 👍/👎 ratio → identify weak areas

---

## 🟣 PRIORITY 5 — Architecture (Month 3+)

### 5.1 Performance
- [ ] **Connection pooling:** Reuse LLM connections instead of creating per request
- [ ] **Redis-based streaming:** Replace SSE with Redis pub/sub for multi-worker support
- [ ] **Parallel tool calls:** When LLM needs 2+ tools, call them in parallel (LangGraph supports this)
- [ ] **Response caching:** Identical queries within 5 min → cached response (opt-in)

### 5.2 Multi-Model Support
- [ ] **Model routing:** Simple queries → fast small model (Mistral Small), complex → Large model
- [ ] **Fallback chain:** If Mistral fails → auto-try OpenAI/Claude
- [ ] **Model comparison:** A/B test different models on same queries → quality metrics

### 5.3 Security & Governance
- [ ] **Audit log:** Every query + response + tool call logged with user, time, cost
- [ ] **PII detection:** Mask Aadhaar/PAN/phone in logs automatically
- [ ] **Role-based tool access:** Admin sees all tools, Sales User sees only sales-related
- [ ] **Query blacklist:** Block destructive queries ("delete all loans") at prompt level

### 5.4 Knowledge Base Enhancement
- [ ] **RAG improvement:** Better chunking strategy for uploaded documents
- [ ] **Auto-index:** New DocType created → auto-index schema for LLM
- [ ] **FAQ learning:** Common queries + good answers → auto-learn for faster response
- [ ] **Frappe Help integration:** "How to create a loan?" → search Frappe/ERPNext docs

---

## Implementation Order (Recommended)

| Week | Focus | Impact |
|------|-------|--------|
| **This week** | 1.1 Voice polish + 1.2 Speed + 1.3 Errors | Users stop complaining about voice quality |
| **Week 2** | 2.1 Memory + 2.3 Multi-turn | Conversations feel natural, not robotic |
| **Week 3** | 3.1 UI split + 3.2 Voice UX | Professional feel, easier to maintain |
| **Week 4** | 4.1 NBFC compound tools | 60% fewer tool calls for NBFC queries |
| **Month 2** | 4.2 Reports + 4.3 Alerts + 4.4 Analytics | Real business value |
| **Month 3** | 5.x Architecture | Scale & security |

---

## Quick Wins (Can do today/tomorrow)

1. ✅ Indian accent voice (done)
2. ✅ Emoji stripping (done)
3. ✅ Short greetings (done)
4. [ ] Indian number formatting ("50 lakh" instead of "5000000")
5. [ ] Smart sentence splitting (abbreviation-aware)
6. [ ] Voice mode flag → shorter responses
7. [ ] Audio prefetch depth increase (1→3)
8. [ ] Add ElevenLabs API key and test

---

*This plan is Niv AI client-side only. FAC (server/tool provider) will NOT be modified.*
