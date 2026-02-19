## [0.9.2] - 2026-02-19

### ⚡ Performance & Reliability

#### Two-Model Tool Optimization
- **Fast model** (mistral-small) for tool selection (~1-2s) + **big model** for final answer streaming
- **~50% faster** tool-calling queries (7-10s vs 15-20s)
- Automatic fallback to single-model if fast model fails or not configured

#### Streaming Token Fix
- **Fixed missing spaces** between words — `_strip_thinking()` was stripping whitespace from each streaming token
- Words like "TheLoan", "ShouldI" now render correctly with proper spacing

#### DB Connection Resilience
- **Auto-retry** on FAC tool call DB errors — FAC has no internal reconnect, now retried once automatically
- System prompt instruction to never output tool calls as raw text

#### Voice Streaming (Producer-Consumer)
- Background TTS thread decouples LLM streaming from Edge TTS generation
- LLM continues producing clauses while TTS generates audio in parallel

#### UI Improvements
- **Close button** added to chat header (rightmost, after delete)
- **Softer widget background** — `#f5f6f8` instead of pure white
- Widget mode less harsh on eyes

#### Cleanup
- Removed unused dependencies: `litellm`, `google-adk`, `google-genai`, `aiohttp`, `python-dotenv`, `razorpay`, `pytesseract`
- Synced versions across `__init__.py`, `hooks.py`, `setup.py`, `pyproject.toml`
- Requirements.txt trimmed to actual dependencies only

---

## [0.9.0] - 2026-02-18

### 🔧 MCP Tools Optimization & UI Overhaul

#### Tool Selection Revolution
- **Removed keyword routing entirely** — LLM freely selects from all 34 tools (no filtering)
- **576 lines removed** from `agent_router.py` (dead routing code)
- **Few-shot examples** retained as hints, not routing rules
- **Proven improvement**: WRR query fixed (was 0%, now correctly returns IRR from data)

#### System Prompt Optimization
- **82% reduction**: 23,472 → 4,146 chars
- **Slim NBFC knowledge** (`domain_nbfc_slim.py`) — 1.2K chars for production, full 23K only in dev mode
- **Current date injected** into system prompt — LLM now knows today's date
- **Tool usage guidelines** trimmed from 10 lines to 4

#### Result Processing
- **4KB result cap** — large tool results intelligently summarized
- **Single document summarization** — 32KB+ responses reduced to ~3KB (child tables trimmed)
- **Result caching** — 2min TTL for read-only tools (e.g., `get_doctype_info`)
- **Consecutive failure cap** — after 2 identical failures, suggests different approach

#### Enhanced Tool Descriptions
- **20+ tools** enhanced with USE/DON'T USE guidance in `tool_descriptions.py`
- **Override at client layer** — FAC untouched, descriptions enhanced at Niv AI layer

#### WRR Definition Fix
- **Corrected**: WRR = Weighted Risk Rate (IRR on reducing balance), not "Weighted Risk Rating"
- **LLM now reads** `irr`/`rate_of_interest` fields from Loan documents instead of calculating

#### UI Improvements
- **Markdown table fix** — broken tables from LLM (missing newlines) auto-repaired in JS
- **Table wrapper** — horizontal scroll for wide tables
- **Table CSS** — dark theme with purple headers, hover effects, proper borders

#### Safety & Limits
- **Rate limiting** — 50 tool calls/min/user
- **Error sanitization** — internal errors cleaned before showing to user

---

## [0.7.0] - 2026-02-17

### 🚀 Major Release: Smart Tool Calling + Advanced Memory

#### Tool Calling Improvements
- **Model upgraded**: `gpt-oss:120b` → `mistral-large-3:675b` for better tool calling
- **Agent routing**: Queries automatically routed to specialized agents (NBFC, Accounts, HR)
- **Tool reduction**: 34 tools → 16-20 per agent (less confusion for LLM)
- **Few-shot examples**: Tool descriptions include exact JSON examples
- **Enhanced descriptions**: Short MCP tool descriptions replaced with detailed ones

#### System Discovery (Auto-Scan)
- **Unified discovery**: Single source of truth for system knowledge
- **Auto-scan**: Automatically discovers DocTypes, fields, workflows on any ERPNext
- **585 DocTypes, 31 workflows** discovered and injected into agent context
- **Zero tool calls** for system info queries - agent already knows!

#### Advanced Memory System
- **6 memory categories**: Preference, Correction, Entity, Fact, Summary, Habit
- **Auto-extraction**: Automatically detects language, format preferences from conversations
- **Correction tracking**: User corrections saved with HIGH importance (don't repeat mistakes!)
- **Entity tracking**: Frequently accessed records remembered
- **Memory decay**: Old unused memories automatically cleaned up
- **Semantic search**: Query-based memory retrieval
- **remember_user_preference tool**: Agent can explicitly save memories

#### Architecture
- **A2A deprecated**: Multi-agent system moved to `_a2a_deprecated/`
- **LangChain agent**: Single agent with LangGraph ReAct pattern
- **MCP tools**: All tools loaded from `frappe_assistant_core`

### Files Changed
- `niv_core/knowledge/memory_service.py` - Advanced Memory System (350+ lines)
- `niv_core/knowledge/unified_discovery.py` - System auto-scan
- `niv_core/langchain/agent_router.py` - Query routing + tool filtering
- `niv_core/langchain/tools.py` - Enhanced descriptions + memory tool
- `niv_core/langchain/memory.py` - Memory context injection
- `niv_core/langchain/agent.py` - Auto-extraction hook

### Performance
- Tool calls reduced from 7+ to 1-2 for simple queries
- System queries answered without any tool calls
- Memory persists across conversations


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
