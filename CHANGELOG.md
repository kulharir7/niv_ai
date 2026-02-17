# Changelog

## v0.6.1 (2026-02-17)
### Fixed
- **Simple Mode reverted** — caused errors, removed for stability
- A2A brain-first calculation rule in prompts
- LLM brain for calculations instead of tools
- Table overflow with scrollable container
- Removed disclaimer text from UI

---

## v0.6.0 (2026-02-16)
### Added
- **A2A Multi-Agent System** — Google ADK powered agent-to-agent orchestration
  - Specialist agents for different domains
  - Agent transfer badges in UI
  - Thinking/critique signals filtering
  - Robust streaming with deduplication
- **Artifact Panel** — Code preview and visualization
  - Split view with better tabs
  - Syntax highlighting (Phase 3)
  - Mobile responsive design
  - Frappe CSS injection for preview
  - "Apply to System" button
- **Knowledge Graph Visualizer** — Full-screen premium visualization
- **Multi-Conversation Concurrency** — Parallel streaming and background progress
- **Dev Mode Confirmation** — Safety confirmation for all write tools
- Premium Thought Block UI with subtle styling

### Fixed
- A2A confirmation flow with Redis flag
- Force immediate tool calls (no AI confirmation)
- Streaming duplicates and blob memory leak
- Empty tool results handling
- Billing cost calculation
- MCPFunctionTool ADK argument filtering
- Tool name extraction and frontend rendering

---

## v0.5.0 (2026-02-14)
### Added
- **Auto-Discovery Engine** — Scans ERPNext on install, builds knowledge
- **Niv Health System** — Self-healing and auto-setup
- Router + Dev-mode safety improvements
- NBFC domain knowledge injection

### Fixed
- Frappe v14 SSE streaming context issues
- Document cache AttributeError in SSE
- Safe_eval fallback and automation hook recursion
- Recursion limit tuning (prevent infinite tool loops)
- Tool result truncation (save tokens for response)
- RAG embeddings prefer Mistral provider

---

## v0.4.0 (2026-02-12)
### Added
- English as primary response language setting
- Knowledge Graph rendering for Artifact Preview
- Robust preview_html prioritization

### Fixed
- Various streaming and tool calling improvements
- Better error handling in agent flows

---

## v0.3.1 (2026-02-11)
### Added
- **Per-User Tool Permissions** — automatic permission isolation for AI tool calls
  - When enabled, each user's MCP tool calls use their **own** ERPNext API credentials
  - API keys are **auto-generated** on first chat — zero manual setup per user
  - Tool results respect ERPNext role permissions (e.g., Sales User only sees their Sales Orders)
  - Thread-safe via `threading.local()` — multiple concurrent users fully isolated
  - Graceful fallback: if key generation fails, falls back to admin key (never breaks chat)
  - New toggle in Niv Settings: **"Per-User Tool Permissions"** (default: OFF for backward compatibility)
  - Guest and Administrator users are excluded (always use admin key)

### Changed
- `mcp_client.py`: `call_tool_fast()` accepts optional `user_api_key` override
- `langchain/tools.py`: Thread-local API key storage for per-request user context
- `langchain/agent.py`: Auto-setup/cleanup of user API key in `run_agent()` and `stream_agent()`
- `_helpers.py`: New `get_user_api_key(user)` helper with auto-generation

---

## v0.3.0 (2026-02-11)
### Breaking Changes
- **LangChain/LangGraph engine** replaces all manual AI logic (no toggle, clean replacement)
- **MCP-only architecture**: All 29 native Python tools removed. Tools come exclusively from MCP servers.
- Old code deleted — use `git revert` if needed

### Added
- LangGraph ReAct agent with automatic tool calling loop (max 12 iterations)
- Multi-provider auto-detection: OpenAI/Mistral/Ollama → ChatOpenAI, Claude → ChatAnthropic, Gemini → ChatGoogleGenerativeAI
- MCP session init caching (10 min TTL) for faster tool calls
- Token-aware memory truncation (~4 chars/token estimate)
- RAG knowledge base with FAISS + HuggingFace embeddings
- Configurable rate limiting: per-hour, per-day, custom message (Niv Settings)
- `handle_tool_error=True` on all tools — prevents agent crash on bad tool args
- Premium UI redesign (~2800 lines CSS): Claude/ChatGPT-level SaaS look
- Settings panel as centered modal overlay
- Conversational voice mode with browser-based interrupt detection
- Frappe v14 compatibility (naming_rule removed, sync_fixtures disabled)
- 20 DocTypes including Niv MCP Server, Niv MCP Tool, Niv Custom Instruction, Niv Knowledge Base

### Fixed
- SSE streaming: `werkzeug.wrappers.Response` instead of unsupported `frappe.response["type"] = "generator"`
- ToolMessage callback crash: `'ToolMessage' object is not subscriptable` in callbacks
- INVALID_CHAT_HISTORY: tool errors now return proper ToolMessage instead of crashing agent
- Widget white line artifact: dark `#212121` background on panel and iframe
- Navbar disappearing: `on_page_hide`/`on_page_show` Frappe page handlers for body class cleanup
- Billing token estimation: fallback to `~4 chars/token` when streaming providers don't report usage
- Tool Log `tool` field changed from Link to Data (MCP tools aren't Niv Tool records)
- Duplicate user messages: 30-second dedup check before saving
- Nginx SSE endpoint name: `stream_message` → `stream_chat`

---

## v0.2.0 (2026-02-10)
### Added
- MCP-only tool architecture (removed 29 native tools)
- Conversational voice mode
- Frappe v14 compatibility fixes
- 85 features catalogued

---

## v0.1.1 (2026-02-10)
### Fixed
- `@handle_errors` decorator removed from all whitelisted APIs (was breaking Frappe route resolution)
- `db_set_single_value` import error in billing/payment modules (added alias in compat.py)
- Piper TTS `synthesize()` → `synthesize_wav()` (wave params not set by old method)
- TTS file folder changed from "Home/Niv AI" to "Home" (folder didn't exist)
- Tool calls now render ABOVE response text in chat history (was reversed)
- Fresh welcome screen on page load instead of auto-opening last conversation
- `niv-dashboard` page added to hooks.py `page_modules`
- Stale `niv-recharge` route fixed to `niv-credits` in hooks.py
- Voice mode interrupt: tapping orb during speech now immediately starts listening
- Browser `speechSynthesis.cancel()` added to stop voice playback properly

### Improved
- Table CSS: rounded corners, uppercase headers, hover effects, dark mode
- Markdown: blockquote styling, HR lines, link colors, heading borders, better spacing
- Output formatting: improved line-height, nested list support

---

## v0.1.0 (2026-02-09)
### Initial Release
- Complete AI chat assistant for ERPNext
- 26 built-in tools (documents, search, reports, workflows, database, email, utilities)
- SSE streaming responses
- Voice mode (Piper TTS + browser STT)
- Dual billing modes (Shared Pool / Per-User Wallets)
- Razorpay integration with demo mode
- MCP protocol support (stdio, SSE, HTTP streamable)
- FAC adapter for Frappe Assistant Core
- Embedded widget + full-page chat
- 6 color themes + dark mode
- Admin analytics dashboard
- Knowledge base (RAG)
- Auto-actions, scheduled reports, custom instructions
- Mobile responsive with touch gestures
