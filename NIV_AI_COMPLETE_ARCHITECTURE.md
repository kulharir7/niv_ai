# Niv AI - Complete Architecture & Workflow Guide

## 📋 Project Overview
**Niv AI v0.6.1** - Multi-Agent AI System for ERPNext/Frappe
- **Multi-Provider LLM Support** via LiteLLM (OpenAI, Anthropic, Google, Ollama, custom)
- **Google ADK A2A** (Agent-to-Agent) for multi-agent collaboration
- **MCP Protocol** for tool execution via Frappe Assistant Core
- **Billing System** (Shared Pool + Per-User Wallets)
- **Telegram + WhatsApp** integrations
- **Artifacts** (HTML/JS apps with versioning)
- **Knowledge Graph** (System Discovery + RAG)

---

## 🏗️ Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACES                                │
├──────────────┬──────────────┬──────────────┬───────────────────────────┤
│  niv_chat.js │  Telegram    │   WhatsApp   │   Widget (any page)       │
│  (Web UI)    │  Bot         │   Bot        │   niv_widget.js           │
└──────┬───────┴──────┬───────┴──────┬───────┴────────────┬──────────────┘
       │              │              │                    │
       └──────────────┼──────────────┼────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API LAYER (Frappe)                               │
├─────────────────────────────────────────────────────────────────────────┤
│  stream.py        │  chat.py         │  telegram.py    │  whatsapp.py  │
│  (SSE Stream)     │  (Non-stream)    │  (Webhook)      │  (Webhook)    │
└─────────┬─────────┴─────────┬────────┴────────┬────────┴───────┬───────┘
          │                   │                 │                │
          └───────────────────┼─────────────────┘                │
                              ▼                                  │
┌─────────────────────────────────────────────────────────────────────────┐
│                        ROUTING DECISION                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  if settings.enable_a2a:                                                 │
│      → A2A Runner (runner.py) → Google ADK Multi-Agent                  │
│  else:                                                                   │
│      → LangChain Agent (agent.py) → Single Agent + Tools                │
└─────────┬──────────────────────────────────────────┬────────────────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────────────────┐    ┌─────────────────────────────────────┐
│      A2A SYSTEM (ADK)       │    │     LANGCHAIN AGENT (Legacy)        │
├─────────────────────────────┤    ├─────────────────────────────────────┤
│                             │    │                                     │
│  ┌───────────────────────┐  │    │  LangGraph ReAct Agent              │
│  │   niv_orchestrator    │  │    │  - Smart Model Routing              │
│  │   (Routes to agents)  │  │    │  - Agent Classification             │
│  └───────────┬───────────┘  │    │  - RAG Context Injection            │
│              │              │    │  - Dev Mode (Confirmation)          │
│   ┌──────────┼──────────┐   │    │                                     │
│   ▼          ▼          ▼   │    └─────────────────────────────────────┘
│ ┌─────┐  ┌───────┐  ┌────┐ │
│ │Coder│  │Analyst│  │NBFC│ │
│ └─────┘  └───────┘  └────┘ │
│ ┌─────────┐  ┌──────────┐  │
│ │Discovery│  │ Critique │  │
│ └─────────┘  └──────────┘  │
│ ┌─────────┐                │
│ │ Planner │                │
│ └─────────┘                │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           MCP TOOLS LAYER                                │
├─────────────────────────────────────────────────────────────────────────┤
│  mcp_client.py                                                          │
│  ├── Same-Server (FAC): Direct Python Import (No HTTP)                  │
│  └── Remote Server: Official MCP SDK (langchain-mcp-adapters)           │
│                                                                         │
│  Circuit Breaker: 3 failures → 60s cooldown                            │
│  Caching: Worker Memory → Redis → Live Discovery → DB Fallback         │
└─────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   FRAPPE ASSISTANT CORE (FAC)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  23 MCP Tools (4 Plugins):                                              │
│  • run_database_query    • list_documents    • get_document             │
│  • create_document       • update_document   • delete_document          │
│  • get_doctype_info      • search_doctype    • run_python_code          │
│  • generate_report       • universal_search  • introspect_system        │
│  • ... more                                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Directory Structure

```
niv_ai/
├── hooks.py                 # Frappe hooks, schedulers, doc_events
├── install.py               # After install/migrate
├── niv_health.py            # Health check utility
│
├── niv_core/                # Core AI functionality
│   ├── api/
│   │   ├── stream.py        # ⭐ Main SSE endpoint (primary)
│   │   ├── chat.py          # Non-streaming fallback
│   │   ├── artifacts.py     # Artifact CRUD
│   │   ├── telegram.py      # Telegram bot webhook
│   │   ├── whatsapp.py      # WhatsApp bot webhook
│   │   ├── automation.py    # Doc event triggers
│   │   ├── _helpers.py      # Common utilities
│   │   └── scheduler.py     # Scheduled reports
│   │
│   ├── a2a/                 # ⭐ Google ADK Multi-Agent System
│   │   ├── runner.py        # Main A2A stream handler
│   │   ├── config.py        # Agent configurations
│   │   ├── session.py       # ADK session service
│   │   └── agents/
│   │       ├── factory.py   # ⭐ Agent factory (7 agents)
│   │       └── __init__.py
│   │
│   ├── adk/                 # ADK utilities
│   │   ├── agent_factory.py # Legacy factory (unused now)
│   │   ├── stream_handler.py# Wrapper for Telegram/WhatsApp
│   │   └── discovery.py     # Discovery engine
│   │
│   ├── langchain/           # LangChain (legacy/fallback)
│   │   ├── agent.py         # ⭐ LangGraph ReAct agent
│   │   ├── llm.py           # LLM factory (LiteLLM)
│   │   ├── tools.py         # LangChain tool wrappers
│   │   ├── memory.py        # System prompts, history
│   │   ├── rag.py           # RAG context builder
│   │   ├── callbacks.py     # Streaming, billing callbacks
│   │   └── agent_router.py  # Query classification
│   │
│   ├── knowledge/           # Knowledge & RAG
│   │   ├── system_map.py    # ⭐ DocType relationship graph
│   │   ├── nbfc_knowledge.py# NBFC domain knowledge
│   │   ├── dev_quick_reference.py
│   │   ├── planner_service.py
│   │   ├── memory_service.py
│   │   ├── auditor_service.py
│   │   └── fts_store.py     # SQLite FTS5 (future)
│   │
│   ├── mcp_client.py        # ⭐ MCP tool execution
│   ├── utils.py             # Settings helper
│   ├── compat.py            # v14/v15 compatibility
│   │
│   └── doctype/             # 20 DocTypes
│       ├── niv_settings/
│       ├── niv_ai_provider/
│       ├── niv_conversation/
│       ├── niv_message/
│       ├── niv_artifact/
│       ├── niv_artifact_version/
│       ├── niv_mcp_server/
│       ├── niv_mcp_tool/
│       ├── niv_knowledge_base/
│       ├── niv_kb_chunk/
│       └── ... (10 more)
│
├── niv_billing/             # Credits & Usage
│   ├── api/
│   │   ├── billing.py       # ⭐ Token deduction, balance
│   │   └── payment.py       # Payment gateway (future)
│   └── doctype/
│       ├── niv_wallet/
│       ├── niv_usage_log/
│       ├── niv_credit_plan/
│       └── niv_recharge/
│
├── niv_tools/               # Tool logging
│   └── doctype/
│       └── niv_tool_log/
│
├── niv_ui/                  # UI Pages
│   └── page/
│       ├── niv_chat/        # ⭐ Main chat UI
│       ├── niv_chat_shared/ # Public shared chats
│       ├── niv_credits/     # Credit/usage view
│       ├── niv_dashboard/   # Admin dashboard
│       └── niv_settings/    # Settings UI
│
└── public/
    ├── css/
    │   ├── niv_chat_premium.css  # ⭐ Dark theme, glow effects
    │   └── niv_widget.css
    └── js/
        └── niv_widget.js         # Global widget
```

---

## 🔄 Complete Workflows

### 1. Chat Message Flow (Web UI)

```
User types message in niv_chat.js
         │
         ▼
    POST /api/method/niv_ai.niv_core.api.stream.stream_chat
         │
         ▼
    ┌────────────────────────────────┐
    │ 1. Validate conversation       │
    │ 2. Check rate limits           │
    │ 3. Save user message           │
    │ 4. Smart model routing         │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ if enable_a2a:                 │
    │   → stream_a2a() [runner.py]   │
    │ else:                          │
    │   → stream_agent() [agent.py]  │
    └────────────────────────────────┘
         │
         ▼
    SSE Events: token, tool_call, tool_result, thought, agent_transfer, error, done
         │
         ▼
    niv_chat.js renders:
    - Streaming text
    - Tool call accordions
    - Thought bubbles
    - Agent badges
```

### 2. A2A Multi-Agent Flow

```
runner.py: stream_a2a()
         │
         ▼
    ┌────────────────────────────────┐
    │ 1. Create Orchestrator         │
    │    └── NivAgentFactory         │
    │        └── 7 Sub-Agents        │
    │ 2. Create ADK Runner           │
    │ 3. Setup Session State         │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ Orchestrator receives message  │
    │                                │
    │ Routing Decision:              │
    │ - Data query → data_analyst    │
    │ - Code/DocType → frappe_coder  │
    │ - Loans → nbfc_specialist      │
    │ - System scan → system_discovery│
    │ - Complex task → niv_planner   │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ Specialist Agent               │
    │ - Calls MCP tools              │
    │ - Stores result in state       │
    │ - Returns to orchestrator      │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ Orchestrator formats response  │
    │ - Optional: niv_critique check │
    │ - Returns final answer         │
    └────────────────────────────────┘
```

### 3. MCP Tool Execution Flow

```
Agent calls tool (e.g., list_documents)
         │
         ▼
    ┌────────────────────────────────┐
    │ mcp_client.py                  │
    │ 1. Find server: find_tool_server()│
    │ 2. Check circuit breaker       │
    │ 3. Check cache (Worker→Redis)  │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ Same Server? (localhost)       │
    │ YES → _direct_call()           │
    │       └── FAC Python import    │
    │ NO  → _sdk_call_tool()         │
    │       └── MCP SDK (HTTP)       │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ FAC: mcp._handle_tools_call()  │
    │ - Executes Frappe API          │
    │ - Returns MCP response         │
    └────────────────────────────────┘
         │
         ▼
    Result → Agent → User
```

### 4. Billing Flow

```
Token usage in callbacks.py
         │
         ▼
    ┌────────────────────────────────┐
    │ NivBillingCallback.finalize()  │
    │ - Count input_tokens           │
    │ - Count output_tokens          │
    └────────────────────────────────┘
         │
         ▼
    billing.py: deduct_tokens()
         │
         ▼
    ┌────────────────────────────────┐
    │ if billing_mode == "Shared Pool":│
    │   - Check daily limit          │
    │   - Deduct from pool           │
    │ else:                          │
    │   - Check user wallet          │
    │   - Deduct from wallet         │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ Calculate cost:                │
    │ cost = (input/1000 * rate_in)  │
    │      + (output/1000 * rate_out)│
    └────────────────────────────────┘
         │
         ▼
    Create Niv Usage Log
```

### 5. Artifact Flow

```
Agent creates HTML/visualization
         │
         ▼
    artifacts.py: create_artifact()
         │
         ▼
    ┌────────────────────────────────┐
    │ Niv Artifact DocType           │
    │ - artifact_title               │
    │ - artifact_content (Code field)│
    │ - preview_html                 │
    │ - version_count                │
    └────────────────────────────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │ Niv Artifact Version (snapshot)│
    │ - version_no                   │
    │ - content_snapshot             │
    │ - change_summary               │
    └────────────────────────────────┘
         │
         ▼
    niv_chat.js: Artifact Panel
         │
         ▼
    ┌────────────────────────────────┐
    │ Preview Tab: <iframe>          │
    │   - Blob URL → srcdoc          │
    │   - frappe-charts injected     │
    │                                │
    │ Code Tab: <pre><code>          │
    └────────────────────────────────┘
```

### 6. Telegram/WhatsApp Flow

```
User sends message via Telegram
         │
         ▼
    Telegram API → webhook (telegram.py)
         │
         ▼
    ┌────────────────────────────────┐
    │ 1. Parse chat_id, text         │
    │ 2. Map telegram_user → frappe  │
    │ 3. Get/create conversation     │
    │ 4. Add platform hint to prompt │
    └────────────────────────────────┘
         │
         ▼
    Stream agent (A2A or LangChain)
         │
         ▼
    ┌────────────────────────────────┐
    │ Progressive updates:           │
    │ - "⏳ Thinking..."             │
    │ - "📊 Checking database..."    │
    │ - [Delete status message]      │
    │ - Send final response          │
    └────────────────────────────────┘
         │
         ▼
    Format for platform:
    - Telegram: Markdown tables, *bold*
    - WhatsApp: Bullet lists (no tables)
```

---

## 🤖 The 7 Agents

| Agent | Name | Purpose | Tools | Output Key |
|-------|------|---------|-------|------------|
| 🎯 | `niv_orchestrator` | Routes to specialists | universal_search, list_documents, get_doctype_info | orchestrator_result |
| 💻 | `frappe_coder` | DocTypes, Scripts, Fields | create/update/delete_document, get_doctype_info, run_python_code | coder_result |
| 📊 | `data_analyst` | Queries, Reports, Counts | run_database_query, list_documents, generate_report | analyst_result |
| 🏦 | `nbfc_specialist` | Loans, EMI, Borrowers | run_nbfc_audit, run_database_query, list_documents | nbfc_result |
| 🔍 | `system_discovery` | DocType mapping, Graph | get_system_knowledge_graph, visualize_system_map | discovery_result |
| ✅ | `niv_critique` | Quality check, Verify data | None (LLM only) | critique_result |
| 📋 | `niv_planner` | Multi-step task planning | create_task_plan | planner_result |

---

## 📊 20 DocTypes

### Core
- **Niv Settings** — Global config (provider, model, billing mode, rate limits)
- **Niv AI Provider** — LLM providers (API key, base URL)
- **Niv Conversation** — Chat sessions
- **Niv Message** — Individual messages (user/assistant)

### MCP
- **Niv MCP Server** — MCP server configs (FAC, remote)
- **Niv MCP Tool** — Individual tools (auto-discovered)

### Knowledge
- **Niv Knowledge Base** — RAG sources
- **Niv KB Chunk** — Embedded chunks
- **Niv AI Memory** — Long-term user memory

### Artifacts
- **Niv Artifact** — Generated apps/visualizations
- **Niv Artifact Version** — Version history

### Billing
- **Niv Wallet** — Per-user credit balance
- **Niv Usage Log** — Token usage tracking
- **Niv Credit Plan** — Recharge plans
- **Niv Recharge** — Transaction history

### Automation
- **Niv System Prompt** — Custom prompts
- **Niv Custom Instruction** — Per-user instructions
- **Niv Trigger** — Doc event triggers
- **Niv Auto Action** — Automated actions
- **Niv Scheduled Report** — Scheduled reports

### Messaging
- **Niv Telegram User** — Telegram→Frappe mapping
- **Niv WhatsApp User** — WhatsApp→Frappe mapping
- **Niv Shared Chat** — Public shared conversations

### Planning
- **Niv Task Plan** — Multi-step task plans
- **Niv Task Plan Step** — Individual steps

---

## ⚠️ Known Issues & Bugs to Fix

### 1. **Artifact Preview** ✅ FIXED
- **Issue**: Iframe not rendering content
- **Status**: Fixed by using `Code` field type instead of `Long Text`

### 2. **Streaming Duplicate Text**
- **Issue**: Sometimes text appears twice (once from event.text, once from state)
- **Location**: `runner.py` line ~260
- **Fix**: Check content hash before yielding

### 3. **Tool Call Name Extraction**
- **Issue**: ADK returns tool names in different formats
- **Location**: `runner.py` lines 150-200
- **Status**: Handled with 5 fallback methods

### 4. **Frappe Context in Threads**
- **Issue**: ADK runs tools in ThreadPoolExecutor, loses Frappe context
- **Location**: `factory.py` `_make_tool_executor()`
- **Fix**: Re-init Frappe with `frappe.init(site=site)` in each tool

### 5. **Rate Limit Error Messages**
- **Issue**: Generic error instead of helpful message
- **Location**: `stream.py` `_check_rate_limit()`
- **Status**: Has custom message from settings

### 6. **Memory Leak in Blob URLs**
- **Issue**: Creating Blob URLs without revoking
- **Location**: `niv_chat.js` `show_live_preview()`
- **Fix**: Track and revoke previous URL

### 7. **WhatsApp Table Formatting**
- **Issue**: WhatsApp doesn't support markdown tables
- **Location**: `whatsapp.py` `_format_for_whatsapp()`
- **Status**: Converts to bullet lists

### 8. **Session State Overflow**
- **Issue**: Large tool results bloat session state
- **Location**: `factory.py` `store_tool_result_in_state()`
- **Fix**: Truncate to 5000 chars

---

## 🔧 Configuration Checklist

### Niv Settings
- [ ] `default_provider` — Set to your LLM provider
- [ ] `default_model` — Set to your model
- [ ] `enable_a2a` — Enable for multi-agent
- [ ] `billing_mode` — "Shared Pool" or "Per User"
- [ ] `shared_pool_balance` — Initial credits
- [ ] `cost_per_1k_input` — e.g., 0.0001
- [ ] `cost_per_1k_output` — e.g., 0.0002

### Niv AI Provider
- [ ] `provider_name` — e.g., "GPT-OSS"
- [ ] `base_url` — e.g., "https://ollama.com/v1"
- [ ] `api_key` — Your API key

### Niv MCP Server
- [ ] `server_name` — e.g., "Frappe Assistant Core"
- [ ] `transport_type` — "sse" for FAC
- [ ] `server_url` — e.g., "http://localhost:8000/api/method/fac_endpoint"
- [ ] `is_active` — Enabled

---

## 🚀 Testing Commands

```bash
# Test A2A setup
bench --site frontend execute niv_ai.niv_core.a2a.runner.test_a2a_setup

# List MCP tools
bench --site frontend execute niv_ai.niv_core.mcp_client.get_all_mcp_tools_cached

# Clear MCP cache
bench --site frontend execute niv_ai.niv_core.mcp_client.clear_cache

# Update knowledge graph
bench --site frontend execute niv_ai.niv_core.knowledge.system_map.update_knowledge_graph
```

---

## 📝 Summary

**Niv AI is a complete multi-agent AI system** that:
1. Routes user queries to specialized agents via ADK orchestrator
2. Executes tools through MCP protocol (FAC integration)
3. Tracks usage and billing per-user or shared pool
4. Supports Telegram & WhatsApp bots
5. Creates HTML artifacts with versioning
6. Builds knowledge graphs of ERPNext DocTypes

**Key Technologies:**
- Google ADK (Agent Development Kit)
- LangChain/LangGraph (fallback)
- MCP Protocol (Model Context Protocol)
- LiteLLM (Multi-provider)
- Frappe Assistant Core (MCP Server)
