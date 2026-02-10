"""
Stream V2 API — LangChain-powered SSE endpoint.
Parallel to stream.py — old endpoint still works.
"""
import json
import frappe
from frappe import _


@frappe.whitelist()
def stream_chat(conversation_id, message, model=None, provider=None):
    """Stream chat via LangChain agent (SSE)."""
    user = frappe.session.user
    
    if not message or not message.strip():
        frappe.throw(_("Message cannot be empty"))
    
    # Validate conversation ownership
    if conversation_id:
        conv = frappe.get_doc("Niv Conversation", conversation_id)
        if conv.user != user and "System Manager" not in frappe.get_roles(user):
            frappe.throw(_("Access denied"), frappe.PermissionError)
    
    # Save user message (dedup check like chat.py)
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
    existing = frappe.db.exists("Niv Message", {
        "conversation": conversation_id,
        "role": "user",
        "content": message.strip(),
        "creation": (">", cutoff),
    })
    
    if not existing:
        frappe.get_doc({
            "doctype": "Niv Message",
            "conversation": conversation_id,
            "role": "user",
            "content": message.strip(),
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    
    # Resolve provider/model
    settings = frappe.get_cached_doc("Niv Settings")
    provider = provider or settings.default_provider
    model = model or settings.default_model
    
    def generate():
        full_response = ""
        tool_calls_data = []
        
        try:
            from niv_ai.niv_core.langchain.agent import stream_agent
            
            for event in stream_agent(
                message=message.strip(),
                conversation_id=conversation_id,
                provider_name=provider,
                model=model,
                user=user,
            ):
                event_type = event.get("type", "")
                
                if event_type == "token":
                    content = event.get("content", "")
                    full_response += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n".encode("utf-8")
                
                elif event_type == "tool_call":
                    tc_data = {
                        "tool": event.get("tool", ""),
                        "arguments": event.get("arguments", {}),
                    }
                    tool_calls_data.append(tc_data)
                    yield f"data: {json.dumps({'type': 'tool_call', **tc_data})}\n\n".encode("utf-8")
                
                elif event_type == "tool_result":
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': event.get('tool', ''), 'result': event.get('result', '')})}\n\n".encode("utf-8")
                
                elif event_type == "tool_error":
                    yield f"data: {json.dumps({'type': 'tool_error', 'error': event.get('error', '')})}\n\n".encode("utf-8")
        
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            full_response = error_msg
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n".encode("utf-8")
        
        # Save assistant message
        try:
            msg_data = {
                "doctype": "Niv Message",
                "conversation": conversation_id,
                "role": "assistant",
                "content": full_response,
            }
            if tool_calls_data:
                msg_data["tool_calls"] = json.dumps(tool_calls_data)
            
            frappe.get_doc(msg_data).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Save assistant msg error: {e}", "Niv AI V2")
        
        # Auto-title
        _maybe_auto_title(conversation_id, message)
        
        # Done event
        yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n".encode("utf-8")
    
    frappe.response["type"] = "generator"
    frappe.response["content_type"] = "text/event-stream"
    frappe.response["result"] = generate()


def _maybe_auto_title(conversation_id, message):
    try:
        conv = frappe.get_doc("Niv Conversation", conversation_id)
        if not conv.title or conv.title.startswith("New Chat"):
            title = message.strip()[:80]
            if len(message.strip()) > 80:
                title += "..."
            conv.title = title
            conv.save(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        pass
