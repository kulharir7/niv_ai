# Niv AI — Intelligent Business Assistant for ERPNext

> AI-powered assistant with voice, MCP tools, two-model optimization, Excel/PDF export, and developer mode

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/kulharir7/niv_ai/releases)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15-green.svg)](https://erpnext.com)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## What is Niv AI?

Niv AI is a production-ready AI assistant that sits inside your ERPNext system. Users ask questions in natural language — Hindi or English — and Niv fetches real data, generates reports, creates documents, and exports to Excel/CSV/PDF. No coding required for end users.

**Live in production** at MDFC Financiers (NBFC) with 234+ users.

---

## Key Features

### 🧠 Smart Tool Calling
- **34 MCP Tools** — LLM picks the right tool freely, no hardcoded routing
- **Two-Model Optimization** — Fast model (mistral-small, ~2s) selects tools → Big model (mistral-large) streams the answer. Total: ~8s
- **Auto-retry** on tool errors — DB connection resilience, field name correction hints
- **Result processing** — Large results capped at 4KB, intelligently summarized

### 🎤 Voice Mode
- **Browser STT** (hi-IN) → Server STT (Voxtral Mini) → LLM → TTS
- **ElevenLabs** (primary) / **Edge TTS** (free fallback) — Indian accent, Hindi + English
- **Clause-level chunking** — first audio plays in ~2s, not after full response

### 📊 Data Export
- **Excel** — Styled headers, auto-width columns, freeze panes, auto-filter
- **CSV** — UTF-8 BOM for Hindi support
- **PDF** — Styled tables via wkhtmltopdf, A4 landscape for wide tables
- Export buttons appear automatically below any table response

### 🛠️ Developer Mode
- Create DocTypes, Custom Fields, Client/Server Scripts via chat
- Impact analysis before modifications (checks dependencies across system)
- Confirmation required before any create/update/delete
- Undo support for recently created documents

### 💬 Multi-Channel
- **Web Chat** — Full-page chat + floating widget on every ERPNext page
- **Telegram Bot** — Voice messages, inline buttons, scheduled reports
- **WhatsApp** — Webhook integration
- **Dark Mode** — Premium dark theme with purple accents

### 🔒 Security
- Per-user conversation isolation (users see only their own chats)
- Per-user tool permissions via API key isolation
- Rate limiting (50 tool calls/min)
- Error sanitization — no stack traces exposed to users
- Atomic token deduction — prevents negative balance race conditions

---

## Architecture

```
User Input (Text / Voice / Widget)
         │
         ▼
┌─────────────────────────────────┐
│     SSE Stream (stream.py)      │  Parse request, save user message,
│                                 │  route simple queries to fast model
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│   Two-Model Optimization        │
│                                 │
│  1. Fast Model (mistral-small)  │──→ Tool needed? Which one?
│     Non-streaming, ~2s          │
│                                 │
│  2a. Tools needed:              │
│      Execute MCP tools (~1s)    │──→ FAC (frappe_assistant_core)
│      Big Model streams answer   │
│                                 │
│  2b. No tools:                  │
│      Big Model streams directly │
│                                 │
│  Fallback: LangGraph ReAct      │──→ Single-model with retry
│  agent (handles multi-step)     │    capability
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│      Response Delivery          │
│                                 │
│  • Markdown → rendered HTML     │
│  • Tables → Excel/CSV/PDF btns  │
│  • Voice → Edge TTS / ElevenLabs│
│  • Save to DB + billing         │
└─────────────────────────────────┘
```

---

## Installation

### Prerequisites
- ERPNext v15+ (v14 supported with limitations)
- `frappe_assistant_core` (FAC) installed
- Python 3.10+

### Install

```bash
# 1. Install FAC (MCP tool provider)
bench get-app https://github.com/AdarshPS1/frappe_assistant_core.git
bench --site yoursite install-app frappe_assistant_core

# 2. Install Niv AI
bench get-app https://github.com/kulharir7/niv_ai.git
bench --site yoursite install-app niv_ai
bench --site yoursite migrate
```

### Configure

1. Go to **Niv Settings** (`/app/niv-settings`)
2. Set up an AI Provider:
   - **Provider Name**: e.g., "Mistral"
   - **Base URL**: `https://api.mistral.ai/v1`
   - **API Key**: Your Mistral API key
   - **Default Model**: `mistral-large-latest`
3. Set **Fast Model**: `mistral-small-latest` (for two-model optimization)
4. Optional: Set ElevenLabs API key for premium voice
5. Navigate to `/app/niv-chat` and start chatting

---

## Project Structure

```
niv_ai/
├── niv_core/
│   ├── langchain/                 # Core agent
│   │   ├── agent.py              # Two-model + single-model streaming
│   │   ├── agent_router.py       # Few-shot examples, DocType schemas
│   │   ├── llm.py                # LLM provider factory
│   │   ├── tools.py              # MCP tools → LangChain wrappers
│   │   ├── memory.py             # System prompt + chat history
│   │   ├── callbacks.py          # Streaming, billing, logging
│   │   └── rag.py                # RAG context (optional)
│   │
│   ├── knowledge/                 # System knowledge
│   │   ├── unified_discovery.py  # Auto-scan DocTypes & relationships
│   │   ├── memory_service.py     # User memory (preferences, entities)
│   │   └── domain_nbfc_slim.py   # NBFC domain knowledge
│   │
│   ├── tools/                     # Tool enhancements
│   │   ├── tool_descriptions.py  # Enhanced descriptions with field hints
│   │   ├── result_processor.py   # Cap results at 4KB
│   │   └── result_cache.py       # 2min TTL for read-only tools
│   │
│   ├── api/                       # Endpoints
│   │   ├── stream.py             # SSE chat streaming
│   │   ├── voice.py              # STT + TTS
│   │   ├── export.py             # Excel/CSV/PDF generation
│   │   ├── telegram.py           # Telegram bot
│   │   └── whatsapp.py           # WhatsApp webhook
│   │
│   └── mcp_client.py             # MCP protocol client
│
├── niv_billing/                   # Token billing system
│   ├── api/billing.py            # Atomic pool deduction
│   └── api/payment.py            # Demo + Growth Billing modes
│
├── niv_ui/
│   └── page/niv_chat/            # Chat UI (JS + HTML + CSS)
│
└── public/
    ├── js/niv_widget.js          # Floating widget
    └── css/niv_chat_premium.css  # Dark mode theme
```

---

## Supported AI Providers

| Provider | Type | Tested Models |
|----------|------|---------------|
| **Mistral** | OpenAI-compatible | mistral-large-2512, mistral-small-latest |
| OpenAI | Native | gpt-4o, gpt-4-turbo |
| Anthropic | Native | claude-3.5-sonnet |
| Google | Native | gemini-1.5-pro |
| Ollama | OpenAI-compatible | Any local model |
| Groq | OpenAI-compatible | llama-3, mixtral |

---

## Voice Pipeline

| Stage | Engine | Details |
|-------|--------|---------|
| **STT** (primary) | Browser Web Speech | `hi-IN`, instant, no upload needed |
| **STT** (server) | Voxtral Mini | Mistral API, Hindi+English |
| **TTS** (primary) | ElevenLabs | `eleven_multilingual_v2`, auto language |
| **TTS** (free) | Edge TTS | `en-IN-NeerjaExpressiveNeural` / `hi-IN-SwaraNeural` |
| **TTS** (offline) | Piper | Local, English only |

---

## Billing

Two modes available:

- **Demo Mode** — Free tokens for testing, no payment gateway needed
- **Growth Billing** — Server-to-server billing via external ERPNext (Sales Invoice based)

Token pool is shared across all users. Atomic SQL deduction prevents negative balance.

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v1.0.0** | 2026-02-19 | Stable release — reliable streaming, two-model optimization, tool error resilience, export buttons restored, Razorpay removed |
| v0.9.2 | 2026-02-19 | Two-model tool optimization, streaming fix, DB resilience, billing accuracy |
| v0.9.0 | 2026-02-18 | MCP optimization (82% prompt reduction), voice overhaul, Excel/CSV/PDF export |
| v0.8.0 | 2026-02-17 | Voice pipeline (STT + TTS + VAD) |
| v0.7.0 | 2026-02-17 | Single agent architecture, unified discovery |
| v0.6.0 | 2026-02-16 | A2A multi-agent (deprecated), artifact panel |
| v0.5.0 | 2026-02-14 | Auto-discovery engine, MCP tools |
| v0.3.0 | 2026-02-11 | LangChain/LangGraph engine, premium UI |
| v0.1.0 | 2026-02-09 | Initial release |

See [CHANGELOG.md](CHANGELOG.md) for full history.

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Credits

- [Frappe Framework](https://frappe.io) & [ERPNext](https://erpnext.com)
- [LangChain](https://langchain.com) + [LangGraph](https://langchain-ai.github.io/langgraph/)
- [frappe_assistant_core](https://github.com/AdarshPS1/frappe_assistant_core) — MCP tool provider
- [Edge TTS](https://github.com/rany2/edge-tts) — Free Microsoft TTS

---

<p align="center">Built for ERPNext businesses by <a href="https://github.com/kulharir7">Ravindra Kulhari</a></p>
