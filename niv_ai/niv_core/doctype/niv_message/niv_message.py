import frappe
from frappe.model.document import Document


class NivMessage(Document):
    def after_insert(self):
        # Update conversation stats
        frappe.db.sql("""
            UPDATE `tabNiv Conversation`
            SET message_count = message_count + 1,
                total_tokens_used = total_tokens_used + %s,
                last_message_at = NOW()
            WHERE name = %s
        """, (self.total_tokens or 0, self.conversation))


def has_permission(doc, ptype="read", user=None):
    """Message permission follows conversation ownership"""
    if not user:
        user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True
    conv_user = frappe.db.get_value("Niv Conversation", doc.conversation, "user")
    return conv_user == user
