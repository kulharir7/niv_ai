import frappe
from frappe.model.document import Document


class NivAIProvider(Document):
    def validate(self):
        # Base URL not required for Setup Token (auto-set to Anthropic)
        if self.auth_type == "Setup Token":
            if not self.base_url:
                self.base_url = "https://api.anthropic.com/v1"
            if not self.provider_type or self.provider_type == "openai_compatible":
                self.provider_type = "anthropic"
        elif not self.base_url:
            frappe.throw("Base URL is required")
        # Remove trailing slash
        if self.base_url:
            self.base_url = self.base_url.rstrip("/")
