import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class NivConversation(Document):
    def before_insert(self):
        if not self.user:
            self.user = frappe.session.user
        if not self.provider:
            settings = frappe.get_single("Niv Settings")
            self.provider = settings.default_provider
            self.model = settings.default_model
        if not self.system_prompt:
            settings = frappe.get_single("Niv Settings")
            self.system_prompt = settings.system_prompt


def has_permission(doc, ptype="read", user=None):
    """Users can only access their own conversations. System Manager can access all."""
    if not user:
        user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True
    return doc.user == user


def after_insert(doc, method=None):
    """Hook after conversation creation — placeholder for future logic"""
    pass
