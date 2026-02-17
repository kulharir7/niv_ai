# 🛠️ Niv AI — Developer Guide

## Development Setup

```bash
# Clone
git clone https://github.com/kulharir7/niv_ai.git
cd niv_ai

# Install in development mode
cd /path/to/frappe-bench
bench get-app /path/to/niv_ai  # or from GitHub
bench --site your-site.com install-app niv_ai

# Install Python dependencies
pip install -e apps/niv_ai

# Run migrations
bench --site your-site.com migrate
```

## Architecture Overview

### Engine: LangChain/LangGraph

The AI engine is entirely powered by LangChain and LangGraph:

```
User Message → stream.py/chat.py
    → agent.py (create_react_agent)
        → llm.py (auto-detect provider → ChatOpenAI/ChatAnthropic/ChatGoogleGenerativeAI)
        → tools.py (MCP tools → LangChain StructuredTool)
        → memory.py (conversation history → LangChain messages)
        → callbacks.py (streaming + billing + logging)
    → MCP Client → External MCP Servers
```

### Key Design Decisions

1. **MCP-Only Tools**: No native Python tool implementations. All tools come from MCP servers. This keeps Niv AI lightweight and extensible.

2. **Auto-Detection**: Provider type auto-detected from URL/name:
   - URL contains "anthropic" or "claude" → `ChatAnthropic`
   - URL contains "google" or "gemini" → `ChatGoogleGenerativeAI`
   - Everything else → `ChatOpenAI` (OpenAI-compatible)

3. **handle_tool_error=True**: All tools have this flag to prevent LangGraph from crashing on bad tool arguments.

4. **werkzeug.wrappers.Response for SSE**: Frappe v15 does NOT support `frappe.response["type"] = "generator"`. SSE uses werkzeug Response directly.

5. **Billing via Callbacks**: `NivBillingCallback` accumulates tokens across multi-step tool loops, commits once via `finalize()`.

## Code Map

### `niv_ai/niv_core/langchain/`

| File | Purpose |
|------|---------|
| `agent.py` | Creates LangGraph ReAct agent, `run_agent()` (sync), `stream_agent()` (SSE) |
| `llm.py` | `get_llm()` — multi-provider factory with auto-detection |
| `tools.py` | Wraps MCP tools as LangChain `StructuredTool` objects |
| `memory.py` | Loads Niv Message → LangChain messages, token-aware truncation |
| `callbacks.py` | `NivStreamingCallback`, `NivBillingCallback`, `NivLoggingCallback` |
| `rag.py` | FAISS vectorstore with HuggingFace embeddings |

### `niv_ai/niv_core/api/`

| File | Purpose |
|------|---------|
| `stream.py` | SSE endpoint (primary) — `stream_chat()` |
| `chat.py` | Non-streaming fallback — `send_message()` |
| `conversation.py` | CRUD for conversations + messages |
| `voice.py` | TTS (Piper/OpenAI/browser), STT, voice chat |
| `mcp.py` | MCP server management APIs |
| `instructions.py` | Custom instructions CRUD |
| `_helpers.py` | Shared utilities (validate, save message, auto-title) |

### `niv_ai/niv_core/mcp_client.py`

MCP protocol client — JSON-RPC 2.0 over HTTP/SSE/stdio:
- `get_all_mcp_tools_cached()` — Returns tools in OpenAI function format
- `find_tool_server(tool_name)` — Instant lookup via cached index
- `call_tool_fast(server, tool, args)` — Execute with session reuse
- `clear_cache()` — Clear all caches (after server changes)

## Adding a New Feature

### Adding a New API Endpoint

```python
# niv_ai/niv_core/api/my_feature.py
import frappe
from frappe import _

@frappe.whitelist()  # MUST be the ONLY decorator — never stack with others
def my_endpoint(param1, param2=None):
    """Docstring here."""
    user = frappe.session.user
    # ... your logic
    return {"result": "ok"}
```

**Rules:**
- `@frappe.whitelist()` must be directly above `def` — no other decorators
- Never expose raw Python errors — use `frappe.log_error()` + return friendly messages
- Always validate `frappe.session.user` for auth

### Adding a New DocType

1. Create JSON in the appropriate module directory
2. Add to `fixtures` in `hooks.py` if it needs seed data
3. Run `bench --site your-site.com migrate`
4. For Frappe v14 compatibility: NO `naming_rule` field, NO `sync_fixtures` (use `install.py` instead)

## Testing

```bash
# Quick API test
bench --site your-site.com console
>>> from niv_ai.niv_core.langchain.agent import run_agent
>>> result = run_agent("hello", user="Administrator")
>>> print(result)

# Test MCP connection
>>> from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached
>>> tools = get_all_mcp_tools_cached()
>>> print(f"{len(tools)} tools")

# Test streaming
>>> from niv_ai.niv_core.langchain.agent import stream_agent
>>> for event in stream_agent("how many customers?", user="Administrator"):
...     print(event["type"], event.get("content", event.get("tool", ""))[:50])
```

## Common Pitfalls

| Issue | Solution |
|-------|----------|
| `not whitelisted` error | Clear `__pycache__` + restart gunicorn (`kill -HUP 1`) |
| Gunicorn serves old code | `find apps/niv_ai -name '__pycache__' -exec rm -rf {} +` then restart |
| Frappe v14 migration fails | Remove `naming_rule` from DocType JSONs, disable `sync_fixtures` |
| SSE returns 500 | Must return `werkzeug.wrappers.Response`, NOT `frappe.response["type"] = "generator"` |
| ToolMessage not subscriptable | `on_tool_end(output)` — `output` can be ToolMessage object, use `output.content` |
| INVALID_CHAT_HISTORY | Set `handle_tool_error=True` on StructuredTool |
| HTML comments in JS templates | NEVER use `<!-- -->` in template literals — causes blank page |
| Single quotes in HTML | Frappe wraps page HTML in `'...'` — unescaped `'` breaks eval |
| Nginx SSE not working | Add `proxy_buffering off` + `Host` + `X-Frappe-Site-Name` headers |

## Docker Development

```bash
# Copy code to container
docker cp niv_ai/niv_core/api/stream.py container:/home/frappe/frappe-bench/apps/niv_ai/niv_ai/niv_core/api/stream.py

# Clear cache + restart
docker exec container bash -c "find /home/frappe/frappe-bench/apps/niv_ai -name '__pycache__' -exec rm -rf {} + 2>/dev/null; kill -HUP 1"

# Run migrations
docker exec container bench --site your-site migrate

# Check logs
docker logs container --tail 50 2>&1 | grep -i "error\|niv"
```

## Release Process

```bash
# 1. Update version in hooks.py and setup.py
# 2. Update CHANGELOG.md
# 3. Commit
git add -A
git commit -m "release: vX.Y.Z — description"

# 4. Tag
git tag -a vX.Y.Z -m "vX.Y.Z — description"

# 5. Push
git push origin main --tags
```
