"""
Shared helpers for chat + stream API endpoints.
DRY — no duplicate logic.
"""
import json
import frappe
from datetime import datetime, timedelta


def validate_conversation(conversation_id: str, user: str):
    """Validate user owns the conversation (or is admin)."""
    if not conversation_id:
        return
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Access denied", frappe.PermissionError)


def save_user_message(conversation_id: str, message: str, dedup: bool = False):
    """Save user message to Niv Message. Optional 30s dedup."""
    if dedup:
        cutoff = (datetime.now() - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
        if frappe.db.exists("Niv Message", {
            "conversation": conversation_id,
            "role": "user",
            "content": message,
            "creation": (">", cutoff),
        }):
            return  # Already saved (e.g., by stream retry)

    frappe.get_doc({
        "doctype": "Niv Message",
        "conversation": conversation_id,
        "role": "user",
        "content": message,
    }).insert(ignore_permissions=True)
    frappe.db.commit()


def save_assistant_message(conversation_id: str, content: str, tool_calls: list = None):
    """Save assistant response to Niv Message."""
    try:
        msg_data = {
            "doctype": "Niv Message",
            "conversation": conversation_id,
            "role": "assistant",
            "content": content or "",
        }
        if tool_calls:
            msg_data["tool_calls_json"] = json.dumps(tool_calls, default=str)

        frappe.get_doc(msg_data).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"Save assistant message error: {e}", "Niv AI")


def auto_title(conversation_id: str, message: str):
    """Set conversation title from first user message if untitled."""
    try:
        conv = frappe.get_doc("Niv Conversation", conversation_id)
        if not conv.title or conv.title.startswith("New Chat"):
            title = message[:80].strip()
            if len(message) > 80:
                title += "..."
            conv.title = title
            conv.save(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        pass
