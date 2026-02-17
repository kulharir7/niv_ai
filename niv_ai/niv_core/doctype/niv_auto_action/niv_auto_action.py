import frappe
from frappe.model.document import Document


class NivAutoAction(Document):
    def validate(self):
        if self.condition:
            # Basic syntax check
            try:
                compile(self.condition, "<string>", "eval")
            except SyntaxError as e:
                frappe.throw(f"Invalid condition syntax: {str(e)}")
