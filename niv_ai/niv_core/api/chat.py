"""
Chat API — LangChain-powered endpoint.
"""
import json
import frappe
from frappe import _


@frappe.whitelist()
def send_message(conversation_id, message, model=None, provider=None):
    """Send message via LangChain agent (non-streaming)."""
    user = frappe.session.user
    
    if not message or not message.strip():
        frappe.throw(_("Message cannot be empty"))
    
    # Validate conversation ownership
    if conversation_id:
        conv = frappe.get_doc("Niv Conversation", conversation_id)
        if conv.user != user and "System Manager" not in frappe.get_roles(user):
            frappe.throw(_("Access denied"), frappe.PermissionError)
    
    # Save user message
    user_msg = frappe.get_doc({
        "doctype": "Niv Message",
        "conversation": conversation_id,
        "role": "user",
        "content": message.strip(),
    })
    user_msg.insert(ignore_permissions=True)
    frappe.db.commit()
    
    # Run agent
    from niv_ai.niv_core.langchain.agent import run_agent
    
    # Resolve provider/model
    if not provider:
        settings = frappe.get_cached_doc("Niv Settings")
        provider = settings.default_provider
    if not model:
        settings = frappe.get_cached_doc("Niv Settings")
        model = settings.default_model
    
    try:
        response_text = run_agent(
            message=message.strip(),
            conversation_id=conversation_id,
            provider_name=provider,
            model=model,
            user=user,
        )
    except Exception as e:
        frappe.log_error(f"LangChain agent error: {e}", "Niv AI V2")
        response_text = f"Sorry, I encountered an error: {str(e)}"
    
    # Save assistant message
    assistant_msg = frappe.get_doc({
        "doctype": "Niv Message",
        "conversation": conversation_id,
        "role": "assistant",
        "content": response_text,
    })
    assistant_msg.insert(ignore_permissions=True)
    frappe.db.commit()
    
    # Auto-title if first message
    _maybe_auto_title(conversation_id, message)
    
    return {
        "response": response_text,
        "conversation_id": conversation_id,
    }


def _maybe_auto_title(conversation_id, message):
    """Set conversation title from first message if untitled."""
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
