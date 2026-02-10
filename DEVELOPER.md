# 🔧 Niv AI — Developer Guide

> Architecture, APIs, customization, and contribution guide.

---

## 📁 Project Structure

```
niv_ai/
├── niv_ai/
│   ├── hooks.py                    # App config, routes, events
│   ├── install.py                  # Post-install setup (DocTypes, tools, prompts)
│   ├── modules.txt                 # Frappe modules list
│   │
│   ├── niv_core/                   # Core AI engine
│   │   ├── api/
│   │   │   ├── chat.py             # Non-streaming chat API
│   │   │   ├── stream.py           # SSE streaming chat API
│   │   │   ├── conversation.py     # CRUD for conversations
│   │   │   ├── voice.py            # TTS (Piper/OpenAI/Browser) + STT
│   │   │   ├── mcp.py              # MCP server management
│   │   │   ├── knowledge.py        # RAG knowledge base
│   │   │   ├── scheduler.py        # Scheduled reports
│   │   │   ├── automation.py       # Auto-actions on doc events
│   │   │   ├── instructions.py     # Custom user instructions
│   │   │   └── health.py           # Health check endpoint
│   │   ├── mcp_client.py           # MCP protocol client (JSON-RPC 2.0)
│   │   ├── compat.py               # Frappe v14/v15 compatibility layer
│   │   ├── utils/
│   │   │   ├── rate_limiter.py     # Request rate limiting
│   │   │   ├── error_handler.py    # Structured error responses
│   │   │   ├── logger.py           # API call logging
│   │   │   ├── retry.py            # Retry logic for API calls
│   │   │   └── validators.py       # Input validation
│   │   └── doctype/                # 12 DocTypes (see below)
│   │
│   ├── niv_billing/                # Billing & payments
│   │   ├── api/
│   │   │   ├── billing.py          # Balance check, deduction, dual modes
│   │   │   ├── payment.py          # Razorpay integration + demo mode
│   │   │   └── admin.py            # Analytics APIs (8 endpoints)
│   │   └── doctype/                # 4 DocTypes
│   │
│   ├── niv_tools/                  # Tool execution engine
│   │   ├── api/
│   │   │   ├── tool_executor.py    # 3-path resolution: Niv → FAC → MCP
│   │   │   └── tool_registry.py    # Tool registration
│   │   ├── fac_adapter.py          # Frappe Assistant Core wrapper
│   │   ├── tools/                  # 26 built-in tools
│   │   │   ├── document_tools.py   # CRUD operations (6 tools)
│   │   │   ├── search_tools.py     # Search & filter (3 tools)
│   │   │   ├── report_tools.py     # Report generation (3 tools)
│   │   │   ├── workflow_tools.py   # Workflow actions (2 tools)
│   │   │   ├── database_tools.py   # Raw DB queries (2 tools)
│   │   │   ├── email_tools.py      # Email drafts (3 tools)
│   │   │   ├── image_tools.py      # Image generation
│   │   │   └── utility_tools.py    # Date, math, format (7 tools)
│   │   └── doctype/
│   │
│   ├── niv_ui/                     # Frontend pages
│   │   └── page/
│   │       ├── niv_chat/           # Main chat (3000+ lines JS, 3200+ lines CSS)
│   │       ├── niv_chat_shared/    # Read-only shared chat view
│   │       ├── niv_credits/        # Recharge & billing page
│   │       └── niv_dashboard/      # Admin analytics dashboard
│   │
│   └── public/                     # Global assets (widget)
│       ├── js/niv_widget.js        # Floating chat widget
│       └── css/niv_widget.css      # Widget styles
│
├── docker/                         # Docker helper scripts
├── scripts/                        # Dev tools
│   └── validate_before_deploy.py   # Pre-deploy safety checks
├── requirements.txt
└── setup.py
```

---

## 🗄️ DocTypes

### Core (niv_core)
| DocType | Type | Purpose |
|---------|------|---------|
| **Niv Settings** | Single | Global config (provider, model, billing, widget) |
| **Niv AI Provider** | Regular | AI API providers (URL, key, model) |
| **Niv Conversation** | Regular | Chat sessions per user |
| **Niv Message** | Regular | Individual messages (user/assistant/system) |
| **Niv System Prompt** | Regular | System prompt templates |
| **Niv File** | Regular | File attachments metadata |
| **Niv MCP Server** | Regular | External MCP server connections |
| **Niv MCP Tool** | Child | Tools discovered from MCP servers |
| **Niv Knowledge Base** | Regular | RAG document collections |
| **Niv KB Chunk** | Regular | Text chunks for RAG search |
| **Niv Shared Chat** | Regular | Shared chat links |
| **Niv Auto Action** | Regular | Document event triggers |
| **Niv Custom Instruction** | Regular | Per-user custom system prompts |
| **Niv Scheduled Report** | Regular | Automated report schedules |

### Billing (niv_billing)
| DocType | Type | Purpose |
|---------|------|---------|
| **Niv Credit Plan** | Regular | Token plans (free/paid) |
| **Niv Wallet** | Regular | Per-user credit balance |
| **Niv Recharge** | Regular | Payment/recharge records |
| **Niv Usage Log** | Regular | Per-request token usage |

### Tools (niv_tools)
| DocType | Type | Purpose |
|---------|------|---------|
| **Niv Tool** | Regular | Registered AI tools with schemas |
| **Niv Tool Log** | Regular | Tool execution history |

---

## 🔌 API Reference

### Chat
```python
# Non-streaming
POST /api/method/niv_ai.niv_core.api.chat.send_message
  args: conversation_id, message, model?, attachments?, context?

# Streaming (SSE)
GET /api/method/niv_ai.niv_core.api.stream.stream_message
  args: conversation_id, message, model?, attachments?, context?
  returns: EventSource with types: token, tool_call, tool_result, suggestions, done
```

### Conversation
```python
POST /api/method/niv_ai.niv_core.api.conversation.create_conversation
POST /api/method/niv_ai.niv_core.api.conversation.list_conversations
POST /api/method/niv_ai.niv_core.api.conversation.get_messages
POST /api/method/niv_ai.niv_core.api.conversation.delete_conversation
POST /api/method/niv_ai.niv_core.api.conversation.update_title
```

### Voice
```python
POST /api/method/niv_ai.niv_core.api.voice.text_to_speech
POST /api/method/niv_ai.niv_core.api.voice.speech_to_text
POST /api/method/niv_ai.niv_core.api.voice.voice_chat
POST /api/method/niv_ai.niv_core.api.voice.get_tts_status
POST /api/method/niv_ai.niv_core.api.voice.get_available_voices
```

### Billing
```python
POST /api/method/niv_ai.niv_billing.api.billing.check_balance
POST /api/method/niv_ai.niv_billing.api.payment.get_plans
POST /api/method/niv_ai.niv_billing.api.payment.create_order
POST /api/method/niv_ai.niv_billing.api.payment.verify_payment
```

---

## 🛠️ Adding Custom Tools

1. Create a Python file in `niv_tools/tools/`:

```python
# niv_tools/tools/my_tools.py

TOOLS = [
    {
        "name": "my_custom_tool",
        "description": "Does something useful",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "First parameter"}
            },
            "required": ["param1"]
        }
    }
]

def execute_my_custom_tool(params):
    """Execute the tool and return result"""
    return {"result": f"Processed: {params['param1']}"}
```

2. Register in `install.py` DEFAULT_TOOLS list
3. Run `bench migrate` to create tool records

---

## 🔗 Adding MCP Servers

Via UI: **Niv Settings → MCP Servers → Add**

Via API:
```python
frappe.get_doc({
    "doctype": "Niv MCP Server",
    "server_name": "My Server",
    "server_url": "http://localhost:3000/mcp",
    "transport_type": "streamable-http",
    "api_key": "your-key",
    "is_active": 1
}).insert()
```

The MCP client (`mcp_client.py`) implements JSON-RPC 2.0 directly — no `mcp` pip package needed.

---

## 🔄 Tool Resolution Order

When AI calls a tool, `tool_executor.py` resolves in order:
1. **Niv Tool** (DocType) — registered built-in tools
2. **FAC Adapter** — Frappe Assistant Core tools (if installed)
3. **MCP Servers** — External MCP server tools
4. **Error** — Tool not found

---

## 🏗️ Development Setup

```bash
# Clone
git clone https://github.com/kulharir7/niv_ai.git
cd niv_ai

# Install in dev mode
bench get-app ./niv_ai
bench --site your-site install-app niv_ai

# Build frontend
bench build --app niv_ai

# Run validation before deploy
python scripts/validate_before_deploy.py
```

### Pre-deploy Safety Rules
The validation script checks:
1. **No single quotes** in HTML page files (Frappe template wrapping breaks)
2. **No HTML comments** in JS page files (breaks template literals)
3. **No unprotected utils imports** in API files (need try/except fallback)

---

## 🧪 Testing

```bash
# Test install
bench --site test-site install-app niv_ai
bench --site test-site migrate

# Test API
bench --site test-site execute niv_ai.niv_core.api.chat.send_message \
  --kwargs '{"conversation_id": "...", "message": "hello"}'

# Test TTS
bench --site test-site execute niv_ai.niv_core.api.voice.get_tts_status
```

---

## 📝 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Pure Frappe, no MongoDB | Simple install, no extra infra |
| OpenAI-compatible API format | Works with 10+ providers |
| SSE for streaming | Native browser support, no WebSocket needed |
| Piper TTS over Coqui | 30MB vs 3GB, 1-2s vs 10s on CPU |
| MCP via direct JSON-RPC | No `mcp` pip package (needs Python 3.10+) |
| SQL LIKE for knowledge search | No vector DB dependency |
| `functools.wraps` but no `@handle_errors` on whitelist | Frappe whitelist breaks with wrapper decorators |
| `tar chf` not `tar cf` | Frappe assets use symlinks, must follow them |

---

## 🐛 Common Issues

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md)

---

## 📄 License

MIT
