# Niv AI — Intelligent Business Assistant for ERPNext

> AI-powered assistant with voice, MCP tools, Excel/PDF export, and developer mode

[![Version](https://img.shields.io/badge/version-0.9.0-blue.svg)](https://github.com/kulharir7/niv_ai/releases)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15-green.svg)](https://erpnext.com)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## Features

- **34 MCP Tools** — LLM picks the right tool freely, no hardcoded routing
- **Voice Mode** — Hindi + English STT (Voxtral Mini) → LLM → TTS (ElevenLabs/Edge TTS, Indian accent)
- **Excel/CSV/PDF Export** — Download table data directly from chat responses
- **Developer Mode** — Create DocTypes, Custom Fields, Scripts, Workflows via chat with impact analysis
- **Streaming** — Real-time SSE token streaming with sentence-level TTS
- **Floating Widget** — Small chat window on every ERPNext page, context-aware
- **Multi-user Isolation** — Each user sees only their conversations, role-based tool permissions
- **Dark Mode** — Premium dark theme with purple accents
- **Telegram & WhatsApp** — Chat with Niv from mobile messaging apps

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    USER INPUT                        │
│              Text / Voice / Widget                   │
└──────────────────┬──────────────────────────────────┘
                   │
          ┌────────┴────────┐
          │  Voice?         │
          │  Browser STT    │──→ Voxtral Mini STT (server)
          │  (hi-IN)        │    → Transcript
          └────────┬────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              SSE Stream (stream.py)                   │
│  • Validate conversation ownership                   │
│  • Save user message                                 │
│  • Init DB connection for generator                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│           LangGraph ReAct Agent                      │
│                                                      │
│  System Prompt (memory.py)                           │
│  ├── Brand name + rules + today's date               │
│  ├── NBFC domain knowledge (slim)                    │
│  ├── Few-shot tool examples                          │
│  ├── Key DocType schemas (Loan, Customer, etc.)      │
│  └── Tool usage guidelines                           │
│                                                      │
│  LLM: Mistral Large 675B (via Niv AI Provider)      │
│  ├── Streaming tokens via SSE                        │
│  ├── Tool selection: LLM decides freely              │
│  └── Max 12 tool calls (40 in dev mode)              │
│                                                      │
│  34 MCP Tools (from FAC)                             │
│  ├── list_documents, get_document                    │
│  ├── run_database_query (SQL SELECT)                 │
│  ├── create/update/delete_document                   │
│  ├── generate_report, report_list                    │
│  ├── search_documents, get_doctype_info              │
│  ├── create_visualization, analyze_business_data     │
│  └── ... and more                                    │
│                                                      │
│  MCP Client (mcp_client.py)                          │
│  ├── Same-server: direct Python call to FAC          │
│  ├── Result Processor: caps at 4KB                   │
│  └── Result Cache: 2min TTL for read-only tools      │
│                                                      │
│  Callbacks: Streaming, Billing, Logging              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              Response Delivery                        │
│                                                      │
│  Text Mode:                                          │
│  ├── Tokens → Markdown rendering → UI                │
│  ├── Tables → Excel/CSV/PDF download buttons         │
│  └── Charts → Frappe Charts visualization            │
│                                                      │
│  Voice Mode:                                         │
│  ├── Tokens → Sentence buffer                        │
│  ├── Sentence ready → clean_text_for_tts()           │
│  ├── → stream_tts API                                │
│  ├── → ElevenLabs / Edge TTS (Indian accent)         │
│  └── → Audio queue → play sequentially               │
│                                                      │
│  Save response + auto-title + cleanup DB             │
└─────────────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites
- ERPNext v15+
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
   - **API Key**: Your key
   - **Default Model**: `mistral-large-latest`
3. Optional: Set ElevenLabs API key for premium voice
4. Navigate to `/app/niv-chat`

---

## Project Structure

```
niv_ai/
├── niv_core/
│   ├── langchain/                 # Core agent
│   │   ├── agent.py              # LangGraph ReAct agent (stream + run)
│   │   ├── agent_router.py       # Few-shot examples, DocType schemas
│   │   ├── llm.py                # LLM provider factory (OpenAI/Anthropic/Google)
│   │   ├── tools.py              # MCP tools → LangChain wrappers
│   │   ├── memory.py             # System prompt builder + chat history
│   │   ├── callbacks.py          # Streaming, billing, logging callbacks
│   │   └── rag.py                # RAG context (optional)
│   │
│   ├── knowledge/                 # System knowledge
│   │   ├── unified_discovery.py  # Auto-scan system (DocTypes, relationships)
│   │   ├── memory_service.py     # User memory (entities, preferences)
│   │   ├── domain_nbfc.py        # Full NBFC knowledge (dev mode)
│   │   └── domain_nbfc_slim.py   # Slim NBFC knowledge (normal mode)
│   │
│   ├── tools/                     # Tool enhancements
│   │   ├── tool_descriptions.py  # Enhanced MCP tool descriptions
│   │   ├── result_processor.py   # Cap results at 4KB, summarize
│   │   └── result_cache.py       # Cache read-only tool results
│   │
│   ├── api/                       # API endpoints
│   │   ├── stream.py             # SSE chat streaming
│   │   ├── chat.py               # Non-streaming chat + reactions
│   │   ├── voice.py              # STT + TTS (Voxtral, ElevenLabs, Edge, Piper)
│   │   ├── export.py             # Excel/CSV/PDF file generation
│   │   ├── conversation.py       # CRUD conversations
│   │   ├── telegram.py           # Telegram bot webhook
│   │   └── whatsapp.py           # WhatsApp webhook
│   │
│   ├── mcp_client.py             # MCP protocol client (calls FAC tools)
│   │
│   └── doctype/                   # Frappe DocTypes
│       ├── niv_settings/         # App configuration
│       ├── niv_conversation/     # Chat conversations
│       ├── niv_message/          # Chat messages
│       ├── niv_ai_memory/        # User memory storage
│       └── niv_system_prompt/    # Custom system prompts
│
├── niv_ui/
│   └── page/niv_chat/            # Chat UI (JS + HTML)
│
├── public/
│   ├── js/niv_widget.js          # Floating widget (every page)
│   └── css/
│       ├── niv_widget.css        # Widget styles
│       └── niv_chat_premium.css  # Dark mode premium theme
│
└── hooks.py                       # Frappe hooks + app config
```

---

## Modes

### Normal Mode (Default)
- Business queries: "Show all loans", "Total disbursed amount"
- Data export: Tables → Excel/CSV/PDF
- Voice: Hindi + English with Indian accent
- 12 tool calls max, 90s timeout

### Developer Mode (Toggle in settings)
- Create DocTypes, Custom Fields, Property Setters
- Write Client Scripts, Server Scripts, Workflows
- Impact analysis before modifications (checks dependencies)
- Confirmation required before any create/update/delete
- 40 tool calls max, 180s timeout

---

## Voice Pipeline

| Stage | Engine | Details |
|-------|--------|---------|
| **STT** (primary) | Voxtral Mini | Mistral API, Hindi+English |
| **STT** (fallback) | Browser Web Speech | `hi-IN` lang, instant |
| **TTS** (primary) | ElevenLabs | `eleven_multilingual_v2`, auto Hindi/English |
| **TTS** (fallback 1) | Edge TTS | `en-IN-NeerjaExpressiveNeural` (English), `hi-IN-SwaraNeural` (Hindi) |
| **TTS** (fallback 2) | Piper | Local, offline, English only |
| **TTS** (fallback 3) | Browser TTS | Last resort |

---

## Security

- **Conversation isolation**: Users see only their own chats (`if_owner` permission)
- **Ownership validation**: Every API checks `conv.user == session.user`
- **Per-user tool permissions**: MCP tools use user's API credentials (optional)
- **Rate limiting**: 50 tool calls/min/user
- **Error sanitization**: No stack traces exposed to users

---

## Supported AI Providers

| Provider | Type | Models |
|----------|------|--------|
| Mistral | OpenAI-compatible | mistral-large-3, mistral-small |
| OpenAI | Native | gpt-4, gpt-4-turbo |
| Anthropic | Native | claude-3, claude-3.5 |
| Google | Native | gemini-pro, gemini-1.5 |
| Ollama | OpenAI-compatible | Any local model |
| Groq | OpenAI-compatible | llama, mixtral |

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v0.9.0** | 2026-02-18 | MCP optimization (82% prompt reduction), voice overhaul (Voxtral STT, ElevenLabs TTS, Indian accent), Excel/CSV/PDF export, dark mode fix, 5451 lines dead code removed |
| v0.8.0 | 2026-02-17 | Voice pipeline (Faster-Whisper STT, Edge TTS, Piper, SSML) |
| v0.7.0 | 2026-02-17 | Single agent architecture, removed A2A multi-agent |
| v0.6.0 | 2026-02-16 | Multi-agent (A2A), visual charts |
| v0.5.0 | 2026-02-15 | MCP tools integration |

See [CHANGELOG.md](CHANGELOG.md) for full history.

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Credits

- [Frappe Framework](https://frappe.io)
- [ERPNext](https://erpnext.com)
- [LangChain](https://langchain.com) + [LangGraph](https://langchain-ai.github.io/langgraph/)
- [frappe_assistant_core](https://github.com/AdarshPS1/frappe_assistant_core) — MCP tool provider

---

<p align="center">Built for ERPNext businesses</p>
