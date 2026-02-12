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

    # Rate limiting
    from niv_ai.niv_core.api.stream import _check_rate_limit
    _check_rate_limit(user)

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


@frappe.whitelist()
def save_reaction(message_name, reaction=""):
    """Save user reaction (up/down) on a message."""
    if not message_name:
        return

    msg = frappe.get_doc("Niv Message", message_name)

    # Only allow reacting to messages in user's own conversations
    conv = frappe.get_doc("Niv Conversation", msg.conversation)
    if conv.owner != frappe.session.user and frappe.session.user != "Administrator":
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    import json
    reactions = {}
    if msg.reactions_json:
        try:
            reactions = json.loads(msg.reactions_json)
        except Exception:
            reactions = {}

    user = frappe.session.user
    if reaction:
        reactions[user] = reaction
    else:
        reactions.pop(user, None)

    msg.db_set("reactions_json", json.dumps(reactions), update_modified=False)
    return {"ok": True}
