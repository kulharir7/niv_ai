"""
Chat API — thin Frappe wrapper around LangChain agent.
Non-streaming fallback endpoint.
"""
import frappe
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


@frappe.whitelist()
def send_message(conversation_id, message, model=None, provider=None):
    """Send message via LangChain agent (non-streaming fallback)."""
    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    validate_conversation(conversation_id, user)

    # Rate limit: max 60 messages per hour per user
    from datetime import datetime, timedelta
    one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    recent_count = frappe.db.count("Niv Message", {
        "role": "user", "owner": user, "creation": [">", one_hour_ago],
    })
    if recent_count > 60:
        frappe.throw(_("Rate limit exceeded. Please wait before sending more messages."))

    save_user_message(conversation_id, message)

    # Resolve provider/model once
    settings = frappe.get_cached_doc("Niv Settings")
    provider = provider or settings.default_provider
    model = model or settings.default_model

    from niv_ai.niv_core.langchain.agent import run_agent

    response_text = run_agent(
        message=message,
        conversation_id=conversation_id,
        provider_name=provider,
        model=model,
        user=user,
    )

    save_assistant_message(conversation_id, response_text)
    auto_title(conversation_id, message)

    return {
        "response": response_text,
        "conversation_id": conversation_id,
    }
