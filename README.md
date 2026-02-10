<div align="center">

<img src="docs/logo.svg" width="120" alt="Niv AI Logo"/>

# Niv AI

### The Complete AI Assistant for ERPNext

*ChatGPT-level AI, built natively into ERPNext. One command install.*

[![Version](https://img.shields.io/badge/version-0.3.1-blueviolet?style=for-the-badge)](CHANGELOG.md)
[![Frappe](https://img.shields.io/badge/Frappe-v14%20|%20v15-0089FF?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHZpZXdCb3g9IjAgMCAyMCAyMCIgZmlsbD0id2hpdGUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMTAiIGN5PSIxMCIgcj0iOCIvPjwvc3ZnPg==)](https://frappeframework.com)
[![ERPNext](https://img.shields.io/badge/ERPNext-Compatible-00A651?style=for-the-badge)](https://erpnext.com)
[![License](https://img.shields.io/badge/license-MIT-orange?style=for-the-badge)](LICENSE)
[![LangChain](https://img.shields.io/badge/LangChain-Powered-1C3C3C?style=for-the-badge)](https://langchain.com)
[![MCP](https://img.shields.io/badge/MCP-Protocol-FF6B6B?style=for-the-badge)](https://modelcontextprotocol.io)

<br/>

**No MongoDB** · **No Docker Dependency** · **No Separate Login** · **Just `bench install-app niv_ai`**

<br/>

[📦 Install](#-quick-install) · [✨ Features](#-features) · [🔌 MCP Setup](#-connecting-mcp-servers) · [📋 Roadmap](NIV_AI_ROADMAP.md) · [🐛 Issues](https://github.com/kulharir7/niv_ai/issues)

---

</div>

## 🎬 What Can Niv AI Do?

<table>
<tr>
<td width="50%">

### 💬 Natural Language Queries
> *"Show me all pending Sales Orders from last month"*
> 
> *"Kitne customers hain mere paas?"*
> 
> *"Create a Sales Order for Demo Customer with 5 units of Widget A"*

AI understands Hindi, English, Hinglish — queries your ERPNext data using tools.

</td>
<td width="50%">

### 🔧 Automatic Tool Calling
> AI automatically picks the right tool, calls it, reads the result, and explains it in plain language.

```
You: "Total revenue from all invoices?"

🔧 Using: run_database_query
📊 Result: ₹4,52,380.00 across 5 invoices

AI: "Your total revenue is ₹4,52,380 from 5 Sales Invoices..."
```

</td>
</tr>
<tr>
<td width="50%">

### 🎤 Voice Conversations
> Speak to your ERPNext. AI responds with voice.
> 
> Works **free** with browser APIs — no API key needed.
> Premium voice with Piper TTS (local, fast, CPU-friendly).

</td>
<td width="50%">

### 💰 Token Billing Built-in
> **Shared Pool**: Admin buys credits → all users consume
> 
> **Per User**: Individual wallets with Razorpay recharge
> 
> Demo mode when keys empty → real payments when keys filled. Zero code change.

</td>
</tr>
</table>

---

## 🚀 Quick Install

```bash
# Get the app
bench get-app https://github.com/kulharir7/niv_ai.git

# Install on your site
bench --site your-site.com install-app niv_ai

# Migrate & restart
bench --site your-site.com migrate
bench --site your-site.com clear-cache
bench restart
```

**That's it!** Visit `/app/niv-chat` ✨

<details>
<summary><b>⚙️ First-Time Setup (click to expand)</b></summary>
<br/>

1. Go to **Niv Settings** → `/app/niv-settings`
2. Add your AI provider:
   - **Niv AI Provider** → `+ Add`
   - Provider Name: `Mistral` (or OpenAI, Claude, Ollama...)
   - Base URL: `https://api.mistral.ai/v1`
   - API Key: Your key
   - Default Model: `mistral-medium-2508`
3. In Niv Settings → set Default Provider & Default Model
4. Save → Start chatting!

> 💡 Works with **any OpenAI-compatible API**: Mistral, OpenAI, Claude, Ollama, Groq, Together AI, Gemini, and more.

</details>

<details>
<summary><b>🐳 Docker Setup (click to expand)</b></summary>
<br/>

```bash
# After container start, install in ALL containers:
docker exec <backend> pip install -e apps/niv_ai
docker exec <worker-short> pip install -e apps/niv_ai
docker exec <worker-long> pip install -e apps/niv_ai
docker exec <worker-default> pip install -e apps/niv_ai

# Migrate
docker exec <backend> bench --site your-site migrate

# Add nginx SSE config (see docker/nginx-patch.sh)
docker cp docker/nginx-patch.sh <frontend>:/tmp/
docker exec <frontend> bash /tmp/nginx-patch.sh

# Restart
docker restart <backend> <frontend>
```

See `docker/` folder for persistence scripts.

</details>

---

## ✨ Features

<table>
<tr>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/chat.png" width="40"/><br/>
<b>AI Chat</b><br/>
<sub>LangChain/LangGraph ReAct agent with streaming SSE</sub>
</td>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/connection-status-on.png" width="40"/><br/>
<b>MCP Protocol</b><br/>
<sub>Add URL → tools auto-discover. Like ChatGPT plugins.</sub>
</td>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/microphone.png" width="40"/><br/>
<b>Voice Mode</b><br/>
<sub>Speak ↔ AI responds with voice. Free browser APIs.</sub>
</td>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/money-bag.png" width="40"/><br/>
<b>Billing</b><br/>
<sub>Shared Pool or Per-User. Razorpay payments.</sub>
</td>
</tr>
<tr>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/shield.png" width="40"/><br/>
<b>Per-User Permissions</b><br/>
<sub>AI respects ERPNext roles. Auto API key generation.</sub>
</td>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/artificial-intelligence.png" width="40"/><br/>
<b>Multi-Provider</b><br/>
<sub>OpenAI, Mistral, Claude, Ollama, Gemini, Groq</sub>
</td>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/paint-palette.png" width="40"/><br/>
<b>Premium UI</b><br/>
<sub>Dark mode, themes, mobile responsive, widget</sub>
</td>
<td align="center" width="25%">
<br/>
<img src="https://img.icons8.com/3d-fluency/50/bar-chart.png" width="40"/><br/>
<b>Analytics</b><br/>
<sub>Usage dashboard, cost tracking, tool stats</sub>
</td>
</tr>
</table>

<details>
<summary><b>📋 Full Feature List (85+ features — click to expand)</b></summary>
<br/>

#### 💬 AI Chat Engine
- LangChain/LangGraph ReAct agent with automatic tool calling loops (max 12 iterations)
- Streaming responses via SSE (token-by-token)
- Multi-model support — switch models mid-conversation
- Auto-detection — provider type detected from URL/name
- Token-aware conversation memory with auto-truncation
- RAG knowledge base (FAISS + HuggingFace embeddings)
- Follow-up suggestions

#### 🔧 MCP Tool Ecosystem
- MCP-only architecture — all tools from external MCP servers
- Auto-discovery — add server URL → tools appear
- 3 transport types: stdio, SSE, HTTP streamable
- Session caching (10-min TTL) for performance
- Frappe Assistant Core — 23 ERPNext tools out of the box
- `handle_tool_error=True` — tools never crash the agent

#### 🎤 Voice Mode
- Voice-to-voice conversations
- Interrupt support (tap to stop AI mid-speech)
- Piper TTS (free, local, fast, CPU-friendly)
- Browser fallback via Web Speech API
- Silence detection (auto-stop after 2s)

#### 💰 Billing
- Shared Pool mode (admin buys, all consume)
- Per-User Wallets (individual balances)
- Razorpay integration (demo ↔ real, zero code change)
- Usage tracking per-user, per-model
- Configurable rate limits (per-hour, per-day)

#### 🔐 Security & Access
- Per-user tool permissions (auto API key generation)
- Role-based conversation isolation
- Encrypted API key storage (Frappe Password fields)
- Rate limiting with custom messages
- Error sanitization (no raw Python errors to users)
- Tool execution audit log

#### 🎨 UI/UX
- Premium SaaS interface (Claude/ChatGPT-level)
- 6 color themes
- Dark mode with system-aware toggle
- Mobile responsive with touch gestures
- Embedded floating widget on every page
- Full-screen dedicated chat page
- Markdown rendering (tables, code blocks, syntax highlighting)
- Tool call accordions (expandable)
- Copy, regenerate, edit messages
- Search conversations (Ctrl+F)
- Keyboard shortcuts
- Pin messages, shared chats, export

</details>

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│                    Frontend                        │
│        niv_chat.js  ·  niv_chat.css               │
│        EventSource (SSE)  |  frappe.call           │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│              Frappe API Layer                      │
│    stream.py (werkzeug SSE)  ·  chat.py (sync)    │
│    Rate Limit  ·  Auth  ·  Billing  ·  CRUD       │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│          LangChain / LangGraph Engine             │
│                                                    │
│  🤖 agent.py    → create_react_agent()            │
│  🧠 llm.py      → auto-detect provider            │
│  🔧 tools.py    → MCP → StructuredTool            │
│  💾 memory.py   → token-aware history              │
│  📡 callbacks   → streaming + billing + logging    │
│  📚 rag.py      → FAISS vectorstore               │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│              MCP Client (JSON-RPC 2.0)            │
│     HTTP Streamable  ·  SSE  ·  stdio             │
│     Session Cache  ·  Tool Index  ·  Auto-Discover │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│           External MCP Servers                     │
│  ┌─────────────────────────────────────────────┐  │
│  │  Frappe Assistant Core (23 tools)           │  │
│  │  Custom MCP servers · Any MCP-compatible    │  │
│  └─────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 🔌 Connecting MCP Servers

Niv AI uses **MCP (Model Context Protocol)** — add a URL, tools auto-discover. Like ChatGPT plugins.

```
Step 1:  Niv MCP Server → + Add
Step 2:  Paste URL + API key
Step 3:  Save → Tools appear ✨
```

<details>
<summary><b>📖 Detailed MCP Setup Guide</b></summary>
<br/>

#### Recommended: Frappe Assistant Core (FAC)

```bash
bench get-app https://github.com/frappe-assistant/frappe_assistant_core.git
bench --site your-site.com install-app frappe_assistant_core
```

Then in Niv AI:
1. **Niv MCP Server** → `+ Add`
2. Server Name: `Frappe Assistant Core`
3. Transport: `streamable-http`
4. URL: `http://your-site:8000/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp`
5. API Key: `your_api_key:your_api_secret`
6. Save → 23 tools discovered!

#### Available FAC Tools
`list_documents` · `get_document` · `create_document` · `update_document` · `delete_document` · `search_documents` · `run_database_query` · `get_report` · `count_documents` · `get_metadata` · and 13 more...

#### Remote MCP Servers
FAC can be on a **different server** — just point the URL to any server running FAC. This is the ChatGPT model: paste URL → get tools.

</details>

---

## 📊 What's Included

<details>
<summary><b>📦 20 DocTypes</b></summary>
<br/>

| DocType | Purpose |
|---------|---------|
| **Niv Settings** | Global configuration (Single) |
| **Niv AI Provider** | AI provider configs (API keys, URLs, models) |
| **Niv Conversation** | Chat conversations (per-user isolated) |
| **Niv Message** | Individual messages with role, content, tool_calls |
| **Niv System Prompt** | Reusable system prompt templates |
| **Niv MCP Server** | MCP server connections & credentials |
| **Niv MCP Tool** | Discovered MCP tools (child table) |
| **Niv Custom Instruction** | Per-user custom AI instructions |
| **Niv Auto Action** | Document event → AI action triggers |
| **Niv Scheduled Report** | Automated report generation configs |
| **Niv Knowledge Base** | RAG knowledge sources |
| **Niv KB Chunk** | RAG document chunks (vectorized) |
| **Niv Shared Chat** | Shared conversation links |
| **Niv File** | Uploaded file references |
| **Niv Tool** | Custom tool definitions (future use) |
| **Niv Tool Log** | Tool execution audit log |
| **Niv Wallet** | Per-user token wallet balances |
| **Niv Credit Plan** | Recharge plan definitions |
| **Niv Recharge** | Payment transaction records |
| **Niv Usage Log** | Token usage records per message |

</details>

<details>
<summary><b>🔗 14 API Endpoints</b></summary>
<br/>

| Endpoint | Description |
|----------|-------------|
| `stream.stream_chat` | SSE streaming chat (primary) |
| `chat.send_message` | Non-streaming fallback |
| `conversation.create_conversation` | Create new conversation |
| `conversation.list_conversations` | List user's conversations |
| `conversation.get_messages` | Load message history |
| `conversation.delete_conversation` | Delete conversation |
| `conversation.rename_conversation` | Rename conversation |
| `mcp.get_mcp_servers` | List MCP servers + tools |
| `mcp.test_connection` | Test MCP server connection |
| `billing.check_balance` | Get billing status |
| `billing.get_usage_stats` | Usage analytics data |
| `voice.text_to_speech` | TTS (Piper/OpenAI/Browser) |
| `voice.voice_chat` | Voice-to-voice conversation |
| `instructions.get_instructions` | Get/save custom instructions |

</details>

<details>
<summary><b>📁 Project Structure</b></summary>
<br/>

```
niv_ai/
├── niv_ai/
│   ├── niv_core/              # Core AI engine
│   │   ├── api/               # stream, chat, conversation, voice, mcp
│   │   ├── langchain/         # agent, llm, tools, memory, callbacks, rag
│   │   ├── doctype/           # 14 DocTypes
│   │   └── mcp_client.py      # MCP JSON-RPC 2.0 client
│   ├── niv_billing/           # Token billing system
│   │   ├── api/               # billing, payment APIs
│   │   └── doctype/           # wallet, plans, recharge, usage
│   ├── niv_tools/             # Tool framework
│   │   ├── tools/             # email_tools, image_tools
│   │   └── doctype/           # tool, tool_log
│   ├── niv_ui/                # Frontend
│   │   └── page/niv_chat/     # 3079 lines JS + 2990 lines CSS
│   └── public/                # Widget (css + js)
├── docker/                    # Docker scripts
├── scripts/                   # Validation utilities
├── CHANGELOG.md               # Version history
├── DEVELOPER.md               # Dev setup guide
├── KNOWN_ISSUES.md            # Bug tracker
├── NIV_AI_ROADMAP.md          # Roadmap to v1.0.0
└── requirements.txt           # Python dependencies
```

</details>

---

## 🛠️ Troubleshooting

<details>
<summary><b>"Error: Something went wrong"</b></summary>

Old conversations may have corrupted history. **Start a New Chat.**

```bash
bench --site your-site.com clear-cache
bench restart
```
</details>

<details>
<summary><b>SSE Streaming Not Working</b></summary>

Add nginx SSE block:
```nginx
location /api/method/niv_ai.niv_core.api.stream.stream_chat {
    proxy_pass http://backend:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Host $host;
    proxy_set_header X-Frappe-Site-Name your-site.com;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}
```
</details>

<details>
<summary><b>MCP Tools Not Found</b></summary>

```bash
bench --site your-site.com console
>>> from niv_ai.niv_core.mcp_client import discover_tools
>>> tools = discover_tools("Your Server Name", use_cache=False)
>>> print(len(tools), "tools found")
```
</details>

<details>
<summary><b>Docker: Features Lost After Restart</b></summary>

Use `docker/startup.sh` via compose override. See `docker/niv_ai_override.yml`.
</details>

---

## 🗺️ Roadmap

We're building towards **v1.0.0** with **160+ features** across 7 versions:

| Version | Codename | Focus |
|---------|----------|-------|
| ~~v0.3.1~~ ✅ | Permission Isolation | Per-user tool permissions |
| **v0.4.0** 🏗️ | Rock Solid 🪨 | Bug fixes, roles, sidebar |
| **v0.5.0** | See & Read 👁️ | Image vision, file upload, PDF/Excel |
| **v0.6.0** | Big Brain 🧠 | Memory, web search, intelligence |
| **v0.7.0** | Power Tools ⚡ | Templates, automation, tool builder |
| **v0.8.0** | Beautiful 🎨 | Themes, PWA, artifacts panel |
| **v0.9.0** | Dashboard 📊 | Analytics, billing v2, WhatsApp bot |
| **v1.0.0** | Enterprise 🏢 | Security, compliance, CI/CD |

👉 **[Full Roadmap →](NIV_AI_ROADMAP.md)**

---

## 🤝 Contributing

```bash
# Fork → Clone → Branch → Code → Push → PR

git clone https://github.com/YOUR_USERNAME/niv_ai.git
cd niv_ai
git checkout -b feature/amazing-feature

# Make changes...

git commit -m "feat: amazing feature"
git push origin feature/amazing-feature
# Open PR on GitHub
```

See **[DEVELOPER.md](DEVELOPER.md)** for architecture details and dev setup.

---

## 📄 License

MIT License — use it, modify it, sell it. See [LICENSE](LICENSE).

---

<div align="center">

**Made with ❤️ for the ERPNext community**

[⭐ Star this repo](https://github.com/kulharir7/niv_ai) · [🐛 Report Bug](https://github.com/kulharir7/niv_ai/issues) · [💡 Request Feature](https://github.com/kulharir7/niv_ai/issues)

<sub>Built by <a href="https://github.com/kulharir7">@kulharir7</a></sub>

</div>
