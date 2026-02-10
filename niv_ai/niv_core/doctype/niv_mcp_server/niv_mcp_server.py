import frappe
from frappe.model.document import Document


class NivMCPServer(Document):
    def validate(self):
        if not self.server_name:
            frappe.throw("Server Name is required")
        if self.transport_type in ("sse", "streamable-http") and not self.server_url:
            frappe.throw("Server URL is required for SSE/Streamable HTTP transport")
        if self.transport_type == "stdio" and not self.command:
            frappe.throw("Command is required for stdio transport")
