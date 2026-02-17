"""
Stream API — SSE endpoint powered by Simple Agent.
Primary chat endpoint (frontend uses EventSource).

SIMPLIFIED VERSION - Replaces A2A/LangChain with direct LLM + MCP tools
"""
import json
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


def _smart_route_model(message, default_model, dev_mode, settings):
    """Route to optimal model based on message complexity. Zero API call — keyword based."""
    import re

    model_light = getattr(settings, "model_light", "") or ""
    model_medium = getattr(settings, "model_medium", "") or ""
    model_heavy = getattr(settings, "model_heavy", "") or ""

    if not (model_light or model_medium or model_heavy):
        return default_model

    msg = message.strip().lower()
    msg_len = len(message.strip())

    _casual = {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye",
               "good morning", "good evening", "good night", "haan", "ha", "nahi",
               "theek hai", "shukriya", "dhanyavaad", "namaste", "kya haal"}
    if msg in _casual or (msg_len < 15 and "?" not in msg and not dev_mode):
        return model_light or default_model

    _heavy_patterns = [
        r"(create|banao|bana do|build|design|write|likh)",
        r"(doctype|custom field|script|workflow|print format|report)",
        r"(code|function|api|endpoint|hook|migration)",
        r"(analyze|analysis|trend|pattern|compare|optimize)",
    ]
    if dev_mode or any(re.search(p, msg) for p in _heavy_patterns) or msg_len > 200:
        return model_heavy or default_model

    return model_medium or default_model


def _check_rate_limit(user):
    """Check rate limits from Niv Settings."""
    settings = get_niv_settings()
    limit_hour = getattr(settings, "rate_limit_per_hour", 60) or 0
    limit_day = getattr(settings, "rate_limit_per_day", 500) or 0
    custom_msg = getattr(settings, "rate_limit_message", "") or "Rate limit exceeded. Please try again later."

    if limit_hour > 0:
        from datetime import datetime, timedelta
        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        count = frappe.db.count("Niv Message", {"role": "user", "owner": user, "creation": [">", one_hour_ago]})
        if count >= limit_hour:
            frappe.throw(_(custom_msg))

    if limit_day > 0:
        from datetime import datetime, timedelta
        today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        count = frappe.db.count("Niv Message", {"role": "user", "owner": user, "creation": [">", today_start]})
        if count >= limit_day:
            frappe.throw(_(custom_msg))


def _sse(data):
    """Format SSE event"""
    return f"data: {json.dumps(data)}\n\n"


@frappe.whitelist(methods=["GET", "POST"])
def stream_chat(**kwargs):
    """Stream chat via Simple Agent (SSE)."""
    # Support both GET (legacy EventSource) and POST (new fetch)
    if frappe.request.method == "POST":
        try:
            data = frappe.request.get_json(silent=True) or {}
        except Exception:
            data = {}
        conversation_id = data.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = data.get("message") or frappe.form_dict.get("message")
        model = data.get("model") or frappe.form_dict.get("model")
        provider = data.get("provider") or frappe.form_dict.get("provider")
        dev_mode = data.get("dev_mode") or frappe.form_dict.get("dev_mode")
    else:
        conversation_id = kwargs.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = kwargs.get("message") or frappe.form_dict.get("message")
        model = kwargs.get("model") or frappe.form_dict.get("model")
        provider = kwargs.get("provider") or frappe.form_dict.get("provider")
        dev_mode = kwargs.get("dev_mode") or frappe.form_dict.get("dev_mode")

    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    dev_mode = bool(int(dev_mode or 0))
    if dev_mode and "System Manager" not in frappe.get_roles(user):
        dev_mode = False

    # Auto-create conversation if not provided
    if not conversation_id:
        conv = frappe.get_doc({
            "doctype": "Niv Conversation",
            "user": user,
            "title": message[:50],
            "channel": "web",
        })
        conv.insert(ignore_permissions=True)
        frappe.db.commit()
        conversation_id = conv.name

    validate_conversation(conversation_id, user)
    _check_rate_limit(user)
    save_user_message(conversation_id, message, dedup=True)

    settings = get_niv_settings()
    provider = provider or settings.default_provider
    model = model or settings.default_model

    _site_name = frappe.local.site

    # Smart Model Routing
    if not kwargs.get("model"):
        model = _smart_route_model(message, model, dev_mode, settings)

    def generate():
        import time as _time
        import asyncio
        full_response = ""
        tool_calls_data = []
        last_db_check = _time.time()

        def _ensure_db():
            nonlocal last_db_check
            if _time.time() - last_db_check > 30:
                try:
                    frappe.db.sql("SELECT 1")
                except Exception:
                    try:
                        frappe.db.connect()
                    except Exception:
                        frappe.init(site=_site_name)
                        frappe.connect()
                last_db_check = _time.time()

        try:
            frappe.init(site=_site_name)
            frappe.connect()

            # ─── SIMPLE AGENT (New Architecture) ───
            from niv_ai.niv_core.agent import NivAgent
            
            # Get conversation history
            history = _get_conversation_history(conversation_id)
            
            # Run agent async in sync context
            async def run_agent():
                agent = NivAgent(user=user)
                await agent.initialize()
                
                chunks = []
                async for chunk in agent.run(message, history=history, stream=True):
                    chunks.append(chunk)
                return chunks
            
            # Run async agent
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                chunks = loop.run_until_complete(run_agent())
                loop.close()
            except Exception as e:
                # Fallback for async issues
                frappe.log_error(f"Async agent error: {e}", "Niv AI Stream")
                chunks = [f"Error: {str(e)}"]
            
            # Stream chunks
            for chunk in chunks:
                _ensure_db()
                full_response += chunk
                yield _sse({"type": "token", "content": chunk})

        except Exception as e:
            full_response = f"Something went wrong: {str(e)}"
            try:
                frappe.log_error(f"Stream error: {e}", "Niv AI Stream")
            except Exception:
                print(f"[Niv AI Stream] Error: {e}")
            yield _sse({"type": "error", "content": full_response})

        # Save response
        if full_response.strip():
            try:
                frappe.db.sql("SELECT 1")
            except Exception:
                frappe.init(site=_site_name)
                frappe.connect()
            save_assistant_message(conversation_id, full_response, tool_calls_data)
            auto_title(conversation_id)

        yield _sse({"type": "done", "content": ""})

    from werkzeug.wrappers import Response
    return Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


def _get_conversation_history(conversation_id: str, limit: int = 10) -> list:
    """Get recent conversation history for context"""
    try:
        messages = frappe.get_all(
            "Niv Message",
            filters={"conversation": conversation_id},
            fields=["role", "content"],
            order_by="creation desc",
            limit=limit
        )
        # Reverse to get chronological order
        messages.reverse()
        return [{"role": m.role, "content": m.content} for m in messages]
    except Exception:
        return []


# ─── Sync Endpoint (Non-Streaming) ───
@frappe.whitelist()
def generate_sync(message: str, conversation_id: str = None):
    """Non-streaming endpoint - returns complete response"""
    import asyncio
    
    user = frappe.session.user
    
    try:
        from niv_ai.niv_core.agent import NivAgent
        
        async def run():
            agent = NivAgent(user=user)
            await agent.initialize()
            
            history = _get_conversation_history(conversation_id) if conversation_id else None
            
            chunks = []
            async for chunk in agent.run(message, history=history, stream=False):
                chunks.append(chunk)
            return "".join(chunks)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(run())
        loop.close()
        
        return {"success": True, "response": response}
        
    except Exception as e:
        frappe.log_error(f"Generate sync error: {e}", "Niv AI")
        return {"success": False, "error": str(e)}


# ─── Tools List Endpoint ───
@frappe.whitelist()
def get_available_tools():
    """Get list of available tools for current user"""
    from niv_ai.niv_core.tools.mcp_loader import load_mcp_tools
    
    user = frappe.session.user
    tools = load_mcp_tools(user)
    
    return {
        "tools": [{"name": t.name, "description": t.description} for t in tools],
        "count": len(tools)
    }
