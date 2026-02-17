"""
Stream API ??? SSE endpoint using LangChain Agent
Uses existing battle-tested LangChain agent (sync, no async issues)
"""
import json
import frappe
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


def _check_rate_limit(user=None):
    """Rate limit check - uses settings if configured"""
    try:
        from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
        check_rate_limit(user)
    except ImportError:
        pass  # Rate limiter not available, skip


def _sse(data):
    """Format SSE event"""
    return f"data: {json.dumps(data)}\n\n"


@frappe.whitelist(methods=["GET", "POST"])
def stream_chat(**kwargs):
    """Stream chat via LangChain Agent (SSE)"""
    # Parse request
    if frappe.request.method == "POST":
        try:
            data = frappe.request.get_json(silent=True) or {}
        except Exception:
            data = {}
        conversation_id = data.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = data.get("message") or frappe.form_dict.get("message")
    else:
        conversation_id = kwargs.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = kwargs.get("message") or frappe.form_dict.get("message")

    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

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
    save_user_message(conversation_id, message, dedup=True)

    _site_name = frappe.local.site

    def generate():
        full_response = ""
        tool_calls_data = []
        
        try:
            frappe.init(site=_site_name)
            frappe.connect()

            # Use existing LangChain agent - it handles everything!
            from niv_ai.niv_core.langchain.agent import stream_agent
            
            for event in stream_agent(
                message=message,
                conversation_id=conversation_id,
                user=user,
            ):
                event_type = event.get("type", "")
                
                if event_type == "token":
                    content = event.get("content", "")
                    full_response += content
                    yield _sse(event)
                
                elif event_type == "tool_call":
                    tool_calls_data.append({
                        "tool": event.get("tool", ""),
                        "arguments": event.get("arguments", {})
                    })
                    yield _sse(event)
                
                elif event_type == "tool_result":
                    yield _sse(event)
                
                elif event_type == "thought":
                    # Pass through thought events for UI
                    yield _sse(event)
                
                elif event_type == "error":
                    yield _sse(event)
                    full_response = event.get("content", "Error occurred")
                
                else:
                    # Pass through any other events
                    yield _sse(event)

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            full_response = error_msg
            frappe.log_error(f"Stream error: {e}", "Niv AI Stream")
            yield _sse({"type": "error", "content": error_msg})

        # Save response
        if full_response.strip():
            try:
                frappe.db.sql("SELECT 1")
            except Exception:
                frappe.init(site=_site_name)
                frappe.connect()
            save_assistant_message(conversation_id, full_response, tool_calls_data)
            auto_title(conversation_id, message)

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
