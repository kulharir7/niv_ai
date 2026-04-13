# ✦ Chanakya AI — Intelligent Business Assistant

> Your business data, one question away. Ask in Hindi or English — get real answers from real data.

[![Version](https://img.shields.io/badge/version-1.5.0-7c3aed.svg)](https://github.com/kulharir7/niv_ai/releases)
[![Frappe](https://img.shields.io/badge/Frappe-v14%2B-0ea5e9.svg)](https://frappe.io)
[![License](https://img.shields.io/badge/license-MIT-10b981.svg)](LICENSE)

---

## ⚡ What is Chanakya AI?

Chanakya AI is a **production-ready AI assistant** that lives inside your Frappe/ERPNext system. It understands your business — fetches live data, generates reports, creates documents, and automates workflows. No coding needed.

```
"Show me all pending invoices"     → Fetches live data from your system
"Create a Sales Order for ₹50,000" → Creates the document for you
"Branch-wise collection report"    → Runs SQL, formats as table + chart
"Translate this to Hindi"          → Instant translation
```

**Production-tested** • **234+ active users** • **Domain-agnostic** (works with any Frappe app)

---

## 🔥 Core Features

### 🧠 AI Agent with 34 MCP Tools
- **Tool Calling** — AI decides which tools to use, executes them, chains results
- **Two-Model Optimization** — Fast model picks tools → Big model answers (2x faster)
- **MCP Protocol** — Standard protocol, connect any MCP-compatible server
- **Auto-retry** — Handles DB errors, corrects field names, retries automatically

### 🎤 Voice Mode
- Speak in Hindi or English → AI listens, thinks, speaks back
- **< 2s** time-to-first-audio with streaming TTS
- ElevenLabs (premium) / Edge TTS (free) / Browser STT

### 🎨 Premium Chat UI
- **8 Themes** — Classic, Glass, Terminal, Cyberpunk, Aurora, Minimal, Sunset, Ocean Deep
- **Smart Formatting** — Number pills, status badges, info cards, code blocks with language labels
- **Callout Boxes** — 💡 Tip, ⚠️ Warning, ❌ Error auto-detected
- **Metric Tiles** — KPI data → beautiful dashboard cards
- **Toggleable Sections** — Long responses auto-collapse into organized sections
- **Table Export** — One-click Excel / CSV / PDF from any table

### 📊 Business Intelligence Dashboard
- 13 real-time sections from your database
- Financial KPIs, pipeline funnel, branch performance
- AI predictions — revenue forecast, seasonal patterns
- Click any metric → drill down to filtered list

### 🛠️ Developer Mode
- Create DocTypes, scripts, APIs via natural language
- Bulk operations with dry-run preview
- Excel import with auto-field mapping
- Undo support (30 min window)

### 👁️ Vision & Documents
- Upload images → AI reads with OCR
- PDF, Excel, Word support
- Generate loan agreements, receipts, SOA as PDF

### 📱 Multi-Channel
- **Web Chat** — Full-page + floating widget
- **Telegram Bot** — Voice, buttons, scheduled reports
- **Artifacts Panel** — Live code preview + fullscreen

---

## 🏗️ Architecture

```
User (Text / Voice / File)
        │
        ▼
  ┌─────────────┐     ┌──────────────┐
  │  Fast Model  │────▶│  34 MCP Tools │
  │  (select)    │     │  (execute)    │
  └──────┬──────┘     └──────┬───────┘
         │                    │
         ▼                    ▼
  ┌─────────────────────────────────┐
  │        Big Model (stream)       │
  │   Markdown → Premium HTML       │
  │   Numbers → Pills & Badges     │
  │   Tables → Exportable Cards     │
  └─────────────────────────────────┘
         │
         ▼
  Web Chat │ Telegram │ Voice TTS
```

---

## 🚀 Quick Start

### Prerequisites
- Frappe v14+ or ERPNext
- Python 3.10+
- [Frappe Assistant Core](https://github.com/buildswithpaul/Frappe_Assistant_Core) v2.2+

### Install

```bash
# 1. Install MCP Tool Server
bench get-app https://github.com/buildswithpaul/Frappe_Assistant_Core
bench --site your-site install-app frappe_assistant_core

# 2. Install Chanakya AI
bench get-app https://github.com/kulharir7/niv_ai
bench --site your-site install-app niv_ai
bench --site your-site migrate
sudo supervisorctl restart all
```

### Configure

1. **Niv Settings** → Set AI Provider + Model
2. **Niv MCP Server** → Verify tool server connected
3. **Niv Chat** → Start chatting!

> **Frappe v14?** Run `bash apps/niv_ai/scripts/fac_v14_compat.sh` for compatibility fix.

---

## 🤖 Supported Providers

| Provider | Models | Notes |
|----------|--------|-------|
| **Ollama Cloud** | Gemma 4, Qwen3, Kimi, DeepSeek | Recommended — free tier available |
| **Mistral** | Mistral Large, Small | Fast, good tool calling |
| **OpenAI** | GPT-4o, GPT-4 Turbo | Premium quality |
| **Anthropic** | Claude 3.5 Sonnet | Best reasoning |
| **Google** | Gemini 1.5 Pro | Multimodal |
| **Groq** | Llama 3, Mixtral | Ultra-fast inference |

---

## 🎨 Response Formatting

Chanakya AI automatically enhances responses:

| Feature | What it does |
|---------|--------------|
| **Number Pills** | ₹5,00,000 → colored pill (green=currency, blue=%, purple=numbers) |
| **Status Badges** | Active → 🟢, Pending → 🟡, Failed → 🔴, Cancelled → ⚪ |
| **Info Cards** | Key-value pairs → clean card layout |
| **Step Lists** | Numbered lists → timeline with connected dots |
| **Code Blocks** | Language label, line count, collapse long code |
| **Callout Boxes** | 💡 Tip, ⚠️ Warning, ❌ Error → colored cards |
| **Metric Tiles** | Stats → dashboard KPI tiles with icons |
| **Link Cards** | URLs → mini preview cards |
| **Table Enhancement** | Small tables → colored headers, hover effects |

---

## 📂 Project Structure

```
niv_ai/
├── niv_core/
│   ├── langchain/          # AI Agent (two-model, streaming, tools)
│   ├── knowledge/          # Domain detection, system discovery
│   ├── tools/              # Tool enhancements, bulk ops, exports
│   ├── api/                # REST endpoints (stream, voice, export)
│   └── mcp_client.py       # MCP protocol client
├── niv_billing/            # Token billing & wallet system
├── niv_ui/page/niv_chat/   # Premium chat UI (JS + CSS + HTML)
├── public/                 # Widget, logo, styles
├── scripts/                # Utilities (keepalive, compat fixes)
└── install.py              # Auto-setup with defaults
```

---

## 📋 Version History

| Version | Highlights |
|---------|------------|
| **v1.5.0** | Premium formatting (10 features), callout boxes, metric tiles, toggleable sections, thinking accordion, NBFC hardcode removal, keep-alive ping, 20+ ERP status badges |
| **v1.4.0** | AI Dashboard (13 sections), Claude-style tool UI, MCP SDK (34 tools), thinking display |
| **v1.3.0** | Vision/OCR, Form Guide v6, Smart Auto-Fill, FAC v2.3 compat |
| **v1.2.0** | Smart Agent — tool chaining, bulk ops, script templates |
| **v1.1.0** | PWA, E2E tests, mobile responsive |
| **v1.0.0** | Stable — streaming, two-model optimization, export |

---

## 🔒 Security

- Per-user conversation isolation
- Per-user tool permissions (API key isolation)
- Rate limiting (configurable per hour/day)
- Error sanitization — no stack traces exposed
- SQL injection prevention in all tool calls

---

## 🤝 Contributing

PRs welcome! See [DEVELOPER.md](DEVELOPER.md) for architecture details.

---

## 📄 License

MIT License — see [LICENSE](LICENSE).

---

## 👨‍💻 Built by

<a href="https://github.com/kulharir7">
  <img src="https://github.com/kulharir7.png" width="50" style="border-radius:50%" alt="Ravindra Kulhari"/>
</a>

**[Ravindra Kulhari](https://github.com/kulharir7)** — Full-stack AI Engineer

---

<p align="center">
  <strong>✦ Chanakya AI</strong> — Your business, powered by intelligence.
</p>
