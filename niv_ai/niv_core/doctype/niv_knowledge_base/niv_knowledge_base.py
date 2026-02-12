import frappe
from frappe.model.document import Document


class NivKnowledgeBase(Document):
    def on_update(self):
        """Auto-index document into chunks when saved"""
        from niv_ai.niv_core.api.knowledge import index_document
        index_document(self.name)
