import frappe
from frappe.model.document import Document


class NivCustomInstruction(Document):
    def validate(self):
        if self.scope == "Global" and "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw("Only System Managers can create global instructions.")

        if self.scope == "Per User" and not self.user:
            self.user = frappe.session.user
