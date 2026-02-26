# Chanakya Ai — Intelligent Business Assistant for ERPNext

> AI-powered assistant with voice, MCP tools, two-model optimization, smart conversations, Excel/PDF export, vision/OCR, developer mode, and Telegram bot

[![Version](https://img.shields.io/badge/version-1.3.1-blue.svg)](https://github.com/kulharir7/niv_ai/releases)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15%2B-green.svg)](https://erpnext.com)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## What is Chanakya Ai?

Chanakya Ai (formerly Niv AI) is a production-ready AI assistant that sits inside your ERPNext system. Users ask questions in natural language — Hindi or English — and Chanakya fetches real data, generates reports, creates documents, and exports to Excel/CSV/PDF. No coding required for end users.

**Live in production** at MDFC Financiers (NBFC) with 234+ users.

---

## Key Features

### 🧠 Smart Tool Calling
- **34 MCP Tools** — LLM picks the right tool freely, no hardcoded routing
- **Two-Model Optimization** — Fast model selects tools → Big model streams the answer
- **Auto-retry** on tool errors — DB connection resilience, field name correction hints
- **Result processing** — Large results capped at 4KB, intelligently summarized

### 🎤 Voice Mode
- **Browser STT** (hi-IN) → Server STT (Voxtral Mini) → LLM → TTS
- **ElevenLabs** (primary) / **Edge TTS** (free fallback) — Hindi + English
- **Optimized pipeline** — Cached config, lightweight text cleaning, fast Edge TTS
- **Streaming voice** — First audio plays in ~2s, not after full response

### 👁️ Vision & Document Upload
- **Image OCR** — Upload images, AI reads and understands content
- **Document upload** — PDF, Excel, Word, images all supported
- **Two-model vision** — Gemma3:27b (OCR) → Main model (reasoning)
- **Document generator** — Loan agreements, receipts, SOA, letters as PDF

### 📊 Data Export
- **Excel** — Styled headers, auto-width columns, freeze panes, auto-filter
- **CSV** — UTF-8 BOM for Hindi support
- **PDF** — Styled tables via wkhtmltopdf, A4 landscape for wide tables

### 🛠️ Developer Mode
- Create DocTypes, Custom Fields, Client/Server Scripts via chat
- **API Builder** — Generate whitelisted API endpoints with dry-run preview
- **Script templates** — 5 Client Script + 4 Server Script ready-to-use patterns
- **Bulk operations** — Safe batch update/create/delete (max 50, dry-run preview)
- **Bulk import** — Import data from Excel with auto-field mapping
- Confirmation required before any create/update/delete
- Undo support for recently created documents (30 min window)

### 🧠 Smart Conversations
- **Sequential tool chaining** — AI calls additional tools based on first results
- **Conversation summarization** — 20+ messages auto-summarized
- **Follow-up understanding** — "Show loan X" → "iska status kya hai" works naturally
- **Smart date parsing** — "pichhle hafte ki collections" understood in Hindi/English

### 💬 Multi-Channel
- **Web Chat** — Full-page chat + floating widget on every ERPNext page
- **Telegram Bot** — Voice messages, inline buttons, scheduled reports, group chat
- **Artifacts Panel** — Live code preview, auto-open toggle, fullscreen mode
- **Dark Mode** — Premium dark theme with purple accents

### ⚙️ Customizable Branding
- **Widget Title** — Change name from Niv Settings
- **Widget Logo** — Upload custom logo for chat header + bot avatar
- **Auto-Open Artifacts** — Toggle from settings
- **All branding dynamic** — Header, placeholder, thinking text, avatars

### 🏥 System Health
- **Health check API** — Quick + deep system diagnosis
- **Error log scan** — Last 24h errors analyzed
- **Auto-fix actions** — TTS engine reset, cache cleanup, config fixes
- **Performance monitoring** — Response time tracking

### 🔒 Security
- Per-user conversation isolation
- Per-user tool permissions via API key isolation
- Rate limiting (configurable per hour/day)
- Error sanitization — no stack traces exposed to users

---

## Architecture

```
User Input (Text / Voice / File Upload)
         │
         ▼
┌─────────────────────────────────┐
│     SSE Stream (stream.py)      │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│   Two-Model Optimization        │
│                                 │
│  1. Fast Model → Tool selection │
│  2. MCP Tools → Execute         │
│  3. Big Model → Stream answer   │
│                                 │
│  Vision: Gemma3 → OCR → Main    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│      Response Delivery          │
│  • Markdown → HTML              │
│  • Tables → Excel/CSV/PDF       │
│  • Voice → Edge TTS / ElevenLabs│
│  • Telegram → Webhook + Buttons │
└─────────────────────────────────┘
```

---

## Installation

### Prerequisites
- ERPNext v15+ 
- `frappe_assistant_core` (FAC) for MCP tools
- Python 3.10+

### Quick Setup

```bash
cd /path/to/frappe-bench

# 1. Install FAC (MCP tool provider)
bench get-app https://github.com/AdarshPS1/frappe_assistant_core.git
bench --site yoursite install-app frappe_assistant_core

# 2. Install Chanakya Ai
bench get-app https://github.com/kulharir7/niv_ai.git
bench --site yoursite install-app niv_ai
bench --site yoursite migrate

# 3. Setup AI Provider (one command)
# Mistral (recommended):
bash apps/niv_ai/setup.sh yoursite https://api.mistral.ai/v1 YOUR_KEY

# Ollama (free, local):
bash apps/niv_ai/setup.sh yoursite http://localhost:11434/v1 ollama llama3.1

# OpenAI:
bash apps/niv_ai/setup.sh yoursite https://api.openai.com/v1 YOUR_KEY gpt-4o gpt-4o-mini
```

### What's Auto-Configured on Install

| Setting | Default |
|---------|---------|
| Widget Title | Chanakya Ai |
| Logo | Bundled (purple icon) |
| System Prompt | NBFC/Business expert |
| Voice (STT/TTS) | Auto-detect |
| Vision (OCR) | gemma3:27b |
| Billing | Shared Pool, 1Cr tokens |
| Rate Limits | 500/hr, 5000/day |
| Artifacts Auto-Open | ON |
| MariaDB Timeouts | Optimized (net_timeout=300s, wait=24h) |

**Only manual setup needed:** AI Provider + API Key (and optionally Telegram Bot Token).

> **Note:** MariaDB optimization requires `sudo` access. If it fails during install, run manually:
> ```bash
> sudo mysql -e "SET GLOBAL net_read_timeout=300; SET GLOBAL net_write_timeout=300; SET GLOBAL wait_timeout=86400; SET GLOBAL interactive_timeout=86400; SET GLOBAL max_connections=300;"
> ```

Open `/app/niv-chat` and start chatting! 🚀

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
│   │   └── domain_nbfc.py        # NBFC domain knowledge
│   │
│   ├── tools/                     # Tool enhancements
│   │   ├── tool_descriptions.py  # Enhanced descriptions with field hints
│   │   ├── result_processor.py   # Cap results at 4KB
│   │   ├── result_cache.py       # 2min TTL for read-only tools
│   │   ├── bulk_ops.py           # Bulk update/create/delete helpers
│   │   ├── bulk_import.py        # Excel data import with auto-mapping
│   │   ├── script_templates.py   # Client/Server Script patterns
│   │   ├── api_builder.py        # API endpoint generator
│   │   └── doc_generator.py      # PDF document generation
│   │
│   ├── api/                       # Endpoints
│   │   ├── stream.py             # SSE chat streaming
│   │   ├── voice.py              # STT + TTS (optimized pipeline)
│   │   ├── export.py             # Excel/CSV/PDF generation
│   │   ├── health.py             # System health check + auto-fix
│   │   ├── artifacts.py          # Artifact CRUD
│   │   ├── telegram.py           # Telegram bot (webhook + background jobs)
│   │   └── whatsapp.py           # WhatsApp webhook
│   │
│   └── mcp_client.py             # MCP protocol client
│
├── niv_billing/                   # Token billing system
│   ├── api/billing.py            # Atomic pool deduction
│   └── api/payment.py            # Shared Pool + Growth Billing
│
├── niv_ui/
│   └── page/niv_chat/            # Chat UI (JS + HTML + CSS)
│
├── public/
│   ├── images/niv_logo.png       # Bundled logo
│   ├── js/niv_widget.js          # Floating widget
│   └── css/niv_chat_premium.css  # Dark mode theme
│
└── install.py                     # Auto-setup with all defaults
```

---

## Supported AI Providers

| Provider | Type | Tested Models |
|----------|------|---------------|
| **Mistral** | OpenAI-compatible | mistral-large, mistral-small |
| **Ollama** | OpenAI-compatible | Any local/cloud model |
| OpenAI | Native | gpt-4o, gpt-4-turbo |
| Anthropic | Native | claude-3.5-sonnet |
| Google | Native | gemini-1.5-pro |
| Groq | OpenAI-compatible | llama-3, mixtral |

---

## Voice Pipeline

| Stage | Engine | Details |
|-------|--------|---------|
| **STT** (browser) | Web Speech API | `hi-IN`, instant, no upload |
| **STT** (server) | Voxtral Mini | Mistral API, Hindi+English |
| **TTS** (primary) | ElevenLabs | Multilingual, human-like |
| **TTS** (free) | Edge TTS | Hindi + English voices |
| **TTS** (offline) | Piper | Local, English only |

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v1.3.1** | 2026-02-26 | Scroll stability fix (no jump after response), custom FAB logo, widget→full page preserves conversation, settings panel navigation fix, Frappe toast suppression on chat page |
| **v1.3.0** | 2026-02-21 | Vision/OCR, document upload, API builder, bulk import, system health doctor, codebase cleanup (~2500 lines dead code removed), dynamic branding (logo/title/avatar from settings), auto-fill defaults on install |
| **v1.2.0** | 2026-02-20 | Smart Agent — tool chaining, summarization, diff view, bulk ops, script templates |
| **v1.1.0** | 2026-02-20 | Sentry, PWA, CI/CD, E2E tests, mobile responsive |
| **v1.0.0** | 2026-02-19 | Stable release — reliable streaming, two-model optimization, export |
| v0.9.0 | 2026-02-18 | MCP optimization, voice overhaul, Excel/CSV/PDF export |
| v0.8.0 | 2026-02-17 | Voice pipeline (STT + TTS + VAD) |
| v0.7.0 | 2026-02-17 | Single agent architecture |

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

## Contributors

<a href="https://github.com/kulharir7">
  <img src="https://github.com/kulharir7.png" width="60" style="border-radius:50%" alt="Ravindra Kulhari"/>
</a>
<a href="https://github.com/parinita22-cyber">
  <img src="https://github.com/parinita22-cyber.png" width="60" style="border-radius:50%" alt="parinita22-cyber"/>
</a>

---

<p align="center">Built for ERPNext businesses by <a href="https://github.com/kulharir7">Ravindra Kulhari</a></p>
