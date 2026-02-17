# Niv AI - Intelligent Assistant for ERPNext

> 🤖 Smart AI assistant with auto-discovery, advanced memory, and efficient tool calling

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/kulharir7/niv_ai/releases)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15-green.svg)](https://erpnext.com)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## ✨ Features

### 🧠 Smart Tool Calling
- **Agent Routing** - Queries automatically routed to specialized agents (NBFC, Accounts, HR)
- **Reduced Tool Confusion** - 34 tools → 16-20 per agent
- **Few-shot Examples** - Tool descriptions include exact JSON examples
- **1-2 tool calls** instead of 7+ for simple queries

### 🔍 System Auto-Discovery
- Automatically scans your ERPNext system
- Discovers DocTypes, fields, workflows, modules
- Agent knows your system without manual configuration
- Zero tool calls for system info queries

### 💾 Advanced Memory System
- **Auto-extraction** - Learns preferences from conversations
- **Correction tracking** - Remembers user corrections (don't repeat mistakes!)
- **Entity tracking** - Frequently accessed records remembered
- **Cross-conversation** - Memory persists between sessions

### 🛠️ MCP Tools Integration
- Uses `frappe_assistant_core` for MCP tools
- Create, update, delete documents
- Run reports, SQL queries
- NBFC-specific tools (credit scoring, compliance)

---

## 📦 Installation

### Prerequisites
- ERPNext v15+
- `frappe_assistant_core` app installed
- Python 3.10+

### Step 1: Install frappe_assistant_core (MCP Tools)

```bash
bench get-app https://github.com/AdarshPS1/frappe_assistant_core.git
bench --site yoursite install-app frappe_assistant_core
```

### Step 2: Install Niv AI

```bash
# Latest version (recommended)
bench get-app https://github.com/kulharir7/niv_ai.git
bench --site yoursite install-app niv_ai
bench --site yoursite migrate
```

### Step 3: Configure AI Provider

1. Go to **Niv Settings** in ERPNext
2. Add your AI provider:
   - **Provider**: ollama-cloud / mistral / openai
   - **API Key**: Your API key
   - **Model**: mistral-large-latest (recommended)

### Step 4: Access Niv Chat

Navigate to: `https://yoursite/app/niv-chat`

---

## 🔧 Configuration

### Niv Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `default_provider` | AI provider to use | ollama-cloud |
| `default_model` | LLM model | mistral-large-3 |
| `enable_agent_routing` | Route queries to specialized agents | ✅ Enabled |
| `enable_knowledge_base` | Enable RAG/embeddings | Optional |

### Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| Ollama Cloud | mistral-large-3, gpt-oss | Recommended |
| Mistral | mistral-large-latest | Best for tool calling |
| OpenAI | gpt-4, gpt-4-turbo | Good but expensive |
| Anthropic | claude-3 | Good reasoning |

---

## 📁 Project Structure

```
niv_ai/
├── niv_core/
│   ├── langchain/           # LangChain agent
│   │   ├── agent.py         # Main agent logic
│   │   ├── agent_router.py  # Query routing
│   │   ├── tools.py         # MCP tool wrappers
│   │   └── memory.py        # Context building
│   │
│   ├── knowledge/           # Knowledge systems
│   │   ├── memory_service.py      # Advanced memory
│   │   └── unified_discovery.py   # System auto-scan
│   │
│   ├── api/                 # API endpoints
│   │   └── stream.py        # Chat streaming API
│   │
│   └── doctype/             # Frappe DocTypes
│       ├── niv_settings/
│       ├── niv_conversation/
│       ├── niv_message/
│       └── niv_ai_memory/
│
├── public/                  # Frontend (Niv Chat UI)
└── hooks.py                 # Frappe hooks
```

---

## 🚀 Usage

### Basic Chat
```
User: "Top 5 loans dikhao"
Niv:  [1 tool call] → Shows loan table with amounts
```

### System Queries (Zero Tool Calls!)
```
User: "Kitne workflows active hain?"
Niv:  "31 workflows active hain: Branch New, Payment Entry, Loan Application..."
```

### Memory
```
User: "Meri language Hindi yaad rakh"
Niv:  ✓ Remembered: language = Hindi

[Next conversation]
Niv:  [Replies in Hindi automatically]
```

---

## 📊 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v0.7.0 | 2026-02-17 | Smart tool calling, Advanced memory, System discovery |
| v0.6.1 | 2026-02-17 | LangChain agent, A2A deprecated |
| v0.6.0 | 2026-02-16 | Multi-agent (A2A), Visual charts |
| v0.5.0 | 2026-02-15 | MCP tools integration |

See [CHANGELOG.md](CHANGELOG.md) for full history.

---


---

## 📱 Telegram Integration

Connect Niv AI to Telegram for mobile access.

### Step 1: Create Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "My ERPNext Assistant")
4. Choose a username (e.g., "my_erp_bot")
5. Copy the **Bot Token** (looks like `123456789:ABCdefGHI...`)

### Step 2: Configure in ERPNext

1. Go to **Niv Settings**
2. Enter your **Telegram Bot Token**
3. Save

### Step 3: Set Webhook

Run this command (replace YOUR_DOMAIN and BOT_TOKEN):

```bash
curl -X POST "https://api.telegram.org/botBOT_TOKEN/setWebhook" \
  -d "url=https://YOUR_DOMAIN/api/method/niv_ai.niv_core.api.telegram.webhook"
```

Or use the health check:
```bash
bench --site yoursite execute niv_ai.niv_health.check_telegram
```

### Step 4: Link Telegram User to ERPNext User

1. Go to **Niv Telegram User** (create new)
2. Fields:
   - **Telegram User ID**: Your Telegram numeric ID (get from @userinfobot)
   - **Telegram Chat ID**: Same as User ID for private chats
   - **Frappe User**: Link to ERPNext user
   - **Enabled**: ✅ Check

### Step 5: Test

1. Open your bot in Telegram
2. Send `/start`
3. Try: "Top 5 loans dikhao"

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Help guide |
| Any text | AI processes your query |

### Features

- ✅ Real-time tool call updates ("📊 Searching documents...")
- ✅ Progressive text streaming
- ✅ Thought filtering (shows only final answer)
- ✅ Hindi/English support
- ✅ Same memory as web chat

---

## 🛠️ Development

### Running Locally

```bash
# Clone
git clone https://github.com/kulharir7/niv_ai.git
cd niv_ai

# Install in bench
bench get-app /path/to/niv_ai
bench --site yoursite install-app niv_ai
```

### Version Branches

| Branch | Description |
|--------|-------------|
| `main` | Latest stable (v0.7.0) |
| `v0.6.x` | Previous stable |

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

---

## 🙏 Credits

- **Frappe Framework** - [frappe.io](https://frappe.io)
- **ERPNext** - [erpnext.com](https://erpnext.com)
- **LangChain** - [langchain.com](https://langchain.com)
- **frappe_assistant_core** - MCP tools provider

---

<p align="center">
  Made with ❤️ for ERPNext
</p>
