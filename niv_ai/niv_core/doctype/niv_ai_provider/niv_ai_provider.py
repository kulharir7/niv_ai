import frappe
from frappe.model.document import Document


class NivAIProvider(Document):
    def validate(self):
        if not self.base_url:
            frappe.throw("Base URL is required")
        # Remove trailing slash
        self.base_url = self.base_url.rstrip("/")
