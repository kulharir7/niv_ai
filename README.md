# 🤖 Niv AI — Complete AI Assistant for ERPNext

> **ChatGPT-level AI, built natively into ERPNext.** One command install. No external services required.

[![Frappe](https://img.shields.io/badge/Frappe-v14%20%7C%20v15-blue)](https://frappeframework.com)
[![ERPNext](https://img.shields.io/badge/ERPNext-Compatible-green)](https://erpnext.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## ✨ What is Niv AI?

Niv AI is a **full-featured AI chat assistant** that lives inside your ERPNext. Ask questions about your business data, create documents, run reports, and automate workflows — all through natural conversation.

**No MongoDB. No Docker dependency. No separate login. Just `bench install-app niv_ai`.**

---

## 🚀 Quick Install

```bash
# Get the app
bench get-app https://github.com/kulharir7/niv_ai.git

# Install on your site
bench --site your-site.com install-app niv_ai

# Done! Visit /app/niv-chat
```

---

## 🎯 Features

### 💬 AI Chat
- **Streaming responses** — Real-time token-by-token output via SSE
- **Tool calling** — AI automatically queries your ERPNext data
- **26 built-in tools** — Documents, search, reports, workflows, email, database
- **Multi-model support** — OpenAI, Mistral, Claude, Ollama, Gemini (any OpenAI-compatible API)
- **Conversation history** — Full chat history with search
- **Follow-up suggestions** — AI suggests next questions
- **Context awareness** — Widget knows which page you're on

### 🎤 Voice Mode
- **Voice-to-voice conversation** — Speak → AI responds with voice
- **Interrupt support** — Tap to interrupt AI mid-speech, start talking
- **Piper TTS** — Free, local, fast text-to-speech (no API key needed)
- **Browser fallback** — Works without any TTS setup via Web Speech API
- **Silence detection** — Auto-stops recording after 2s silence

### 💰 Token Billing
- **Shared Pool mode** — Admin buys credits, all users consume from one pool
- **Per-User Wallets** — Individual credit balances per user
- **Razorpay integration** — Real payments with zero-code switch from demo mode
- **Free plans** — Auto-credit without payment gateway
- **Usage tracking** — Per-user, per-model token consumption logs
- **Recharge page** — Modern UI with balance card, plan grid, transaction history

### 🔌 MCP Protocol
- **Real MCP support** — Connect external tool servers (like ChatGPT/Claude)
- **Auto-discover tools** — Connect a server, tools appear automatically
- **3 transports** — stdio, SSE, HTTP streamable
- **Frappe Assistant Core compatible** — 23 FAC tools via MCP

### 📊 Admin Dashboard
- **Usage analytics** — Charts, time series, top users, model usage
- **Tool usage stats** — See which tools are used most
- **Hourly heatmap** — When are users most active
- **CSV export** — Download usage data

### 🎨 UI & UX
- **ChatGPT-quality interface** — Dark sidebar, clean chat area, suggestion cards
- **6 color themes** — Purple, Blue, Green, Orange, Pink, Slate
- **Dark mode** — System-aware with manual toggle
- **Mobile responsive** — Touch-friendly, swipe gestures, full-screen widget
- **Embedded widget** — Floating chat button on every ERPNext page
- **Full-screen mode** — Dedicated `/app/niv-chat` page
- **Markdown rendering** — Tables, code blocks with syntax highlighting, headings, lists
- **File upload** — Attach files to conversations
- **Keyboard shortcuts** — Ctrl+Enter send, Ctrl+G search, etc.

### 🔧 Advanced
- **Knowledge Base (RAG)** — Upload documents for AI to reference
- **Custom Instructions** — Per-user system prompts
- **Auto-actions** — Trigger AI workflows on document events
- **Scheduled Reports** — Automated report generation
- **Shared Chats** — Share conversations via link
- **Pin Messages** — Bookmark important responses
- **Slash Commands** — `/clear`, `/export`, `/model`, `/help`, etc.
- **Export** — Download chats as Markdown

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│             ERPNext / Frappe             │
├─────────────────────────────────────────┤
│  Niv AI (Single Frappe App)             │
│  ├── niv_core    → Chat, Stream, Voice  │
│  ├── niv_billing → Credits, Payments    │
│  ├── niv_tools   → 26 Tools + MCP      │
│  └── niv_ui      → Pages, Widget       │
├─────────────────────────────────────────┤
│  MariaDB (Frappe default — no MongoDB)  │
├─────────────────────────────────────────┤
│  AI Provider (OpenAI-compatible API)    │
│  ├── Mistral  ├── OpenAI  ├── Claude    │
│  ├── Ollama   ├── Gemini  └── Any       │
└─────────────────────────────────────────┘
```

**Pure Frappe.** No external databases. No Docker dependency for AI features. ERPNext native auth.

---

## ⚙️ Configuration

After install, go to **Niv Settings** (single DocType):

1. **Add AI Provider** — Create a "Niv AI Provider" with your API base URL and key
2. **Set default model** — e.g., `mistral-medium-2508`, `gpt-4o`, `claude-3-sonnet`
3. **Enable billing** — Choose Shared Pool or Per-User mode
4. **Enable widget** — Floating chat button appears on all pages
5. **Add MCP servers** (optional) — Connect external tool servers

---

## 📱 Screenshots

| Welcome Screen | Chat with Tools | Voice Mode |
|:-:|:-:|:-:|
| Greeting + suggestions | Tool calls + table output | Full-screen voice UI |

| Recharge Page | Settings Panel | Widget |
|:-:|:-:|:-:|
| Balance + plans + history | Theme, model, MCP config | Floating chat panel |

---

## 🔑 Supported AI Providers

| Provider | Base URL | Notes |
|----------|----------|-------|
| **Mistral** | `https://api.mistral.ai/v1` | Great value, fast |
| **OpenAI** | `https://api.openai.com/v1` | GPT-4o, GPT-4 |
| **Anthropic** | Via proxy | Claude models |
| **Ollama** | `http://localhost:11434/v1` | Free, local |
| **Google Gemini** | Via OpenAI-compat proxy | Gemini Pro |
| **Any OpenAI-compatible** | Custom URL | LiteLLM, vLLM, etc. |

---

## 📋 Requirements

- **Frappe** v14 or v15
- **ERPNext** (any recent version)
- **Python** 3.9+
- **AI Provider API Key** (any OpenAI-compatible service)

### Optional
- **Piper TTS** — `pip install piper-tts` for free local text-to-speech
- **Tesseract OCR** — For image/PDF text extraction
- **Razorpay** — For real payment processing (demo mode works without)

---

## 📄 License

MIT — Use it, modify it, sell it. Just keep the license.

---

## 🤝 Contributing

See [DEVELOPER.md](DEVELOPER.md) for architecture details and contribution guidelines.

---

## 🐛 Known Issues

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for tracked bugs and workarounds.

---

**Built with ❤️ for the ERPNext community.**
