# Chanakya Ai — Intelligent Business Assistant for Growth System

> AI-powered assistant with voice, MCP tools, two-model optimization, smart conversations, Excel/PDF export, vision/OCR, developer mode, and Telegram bot

[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)](https://github.com/kulharir7/niv_ai/releases)
[![Growth System](https://img.shields.io/badge/Growth System-v15%2B-green.svg)](https://erpnext.com)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## What is Chanakya Ai?

Chanakya Ai (formerly Niv AI) is a production-ready AI assistant that sits inside your Growth System system. Users ask questions in natural language — Hindi or English — and Chanakya fetches real data, generates reports, creates documents, and exports to Excel/CSV/PDF. No coding required for end users.

**Live in production** at MDFC Financiers (NBFC) with 234+ users.

---

## Key Features

### 🧠 Smart Tool Calling
- **34 MCP Tools** via official MCP SDK — standard protocol, no hardcoded imports
- **MCP SDK** (`mcp` v1.26 + `langchain-mcp-adapters` v0.2.1) — same protocol as ChatGPT/Claude
- **Niv MCP Server DocType** — manage connections via UI, add multiple servers, toggle ON/OFF
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
- **Web Chat** — Full-page chat + floating widget on every Growth System page
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
- Frappe/ERPNext v14 or v15+
- [Frappe Assistant Core (FAC)](https://github.com/buildswithpaul/Frappe_Assistant_Core) v2.2+

### Step 1: Install FAC (MCP Tool Server)
```bash
cd frappe-bench
bench get-app https://github.com/buildswithpaul/Frappe_Assistant_Core
bench --site your-site install-app frappe_assistant_core
```

### Step 2: Install Niv AI
```bash
bench get-app https://github.com/kulharir7/niv_ai
bench --site your-site install-app niv_ai
bench --site your-site migrate
sudo supervisorctl restart all
```

### Step 3: Frappe v14 Fix (Skip if v15+)
FAC v2.3+ uses `frappe.cache.` syntax which requires Frappe v15+. For **Frappe v14**, run this one-time fix:
```bash
bash apps/niv_ai/scripts/fac_v14_compat.sh /path/to/frappe-bench
sudo supervisorctl restart all
```
This fixes `frappe.cache.` → `frappe.cache().` across all FAC files. Safe to run multiple times.

### Step 4: Configure
1. **Niv Settings** (`/app/niv-settings`) → Set AI Provider + Model
2. **Niv MCP Server** (`/app/niv-mcp-server`) → Verify FAC connected (click "Test Connection")
3. **Niv Chat** (`/app/niv-chat`) → Start chatting!

---

## MCP Server Management

Niv AI connects to MCP-compatible tool servers via the **Niv MCP Server** DocType (`/app/niv-mcp-server`).

| Feature | Description |
|---------|-------------|
| **Add servers** | New → Enter Server Name, URL, API Key → Save |
| **Test Connection** | Click "Test Connection" button → Discovers tools |
| **Toggle ON/OFF** | Enable/disable servers — tools instantly appear/disappear |
| **Multiple servers** | Connect FAC + any other MCP server simultaneously |
| **No hardcode** | All server configs stored in DB, not code |

After install, a default FAC server record is auto-created pointing to `localhost:8000`.


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

- [Frappe Framework](https://frappe.io) & [Growth System](https://erpnext.com)
- [LangChain](https://langchain.com) + [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Frappe Assistant Core](https://github.com/buildswithpaul/Frappe_Assistant_Core) — MCP tool provider (v2.3+)
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

<p align="center">Built for Growth System businesses by <a href="https://github.com/kulharir7">Ravindra Kulhari</a></p>
