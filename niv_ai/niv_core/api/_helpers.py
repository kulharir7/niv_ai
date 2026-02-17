"""
Shared helpers for chat + stream API endpoints.
DRY — no duplicate logic.
"""
import json
import frappe
from datetime import datetime, timedelta


# ─── Per-User API Key for MCP Permission Isolation ─────────────────

def get_user_api_key(user: str = None) -> str:
    """Get or auto-generate API key for a user.
    
    Returns 'api_key:api_secret' string for MCP auth.
    Falls back to None if user is Guest or key generation fails.
    
    This enables per-user permission isolation:
    - Each user's MCP tool calls use THEIR credentials
    - ERPNext permission rules apply automatically
    - No manual API key setup needed per user
    """
    user = user or frappe.session.user

    # Guest/API users — no per-user key, fallback to admin
    if user in ("Guest", "Administrator"):
        return None

    try:
        # BUG-018: use for_update to prevent race condition in concurrent requests
        user_doc = frappe.get_doc("User", user, for_update=True)
        
        # Auto-generate API key if missing
        if not user_doc.api_key:
            api_key = frappe.generate_hash(length=15)
            api_secret = frappe.generate_hash(length=15)
            user_doc.api_key = api_key
            user_doc.api_secret = api_secret
            user_doc.save(ignore_permissions=True)
            frappe.db.commit()
            # BUG-017: audit trail for auto-generated API keys
            frappe.logger().info(f"Niv AI: Auto-generated API key for user {user}")
            try:
                frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Info",
                    "reference_doctype": "User",
                    "reference_name": user,
                    "content": "Niv AI: Auto-generated API key for MCP permission isolation.",
                }).insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass
        
        # Get decrypted secret
        api_secret = frappe.utils.password.get_decrypted_password(
            "User", user, fieldname="api_secret"
        )
        
        if user_doc.api_key and api_secret:
            return f"{user_doc.api_key}:{api_secret}"
        
        return None
        
    except Exception as e:
        frappe.logger().warning(f"Niv AI: Could not get API key for {user}: {e}")
        return None


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
