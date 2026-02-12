# Copyright (c) 2026, Niv AI
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class NivTrigger(Document):
    def validate(self):
        if self.reference_doctype:
            if not frappe.db.exists("DocType", self.reference_doctype):
                frappe.throw("DocType '{}' does not exist".format(self.reference_doctype))

    def on_update(self):
        # Clear cached triggers when trigger config changes
        clear_trigger_cache()

    def on_trash(self):
        clear_trigger_cache()


def clear_trigger_cache():
    """Clear all cached trigger data."""
    frappe.cache().delete_key("niv_ai:triggers")


def get_triggers_for_event(doctype, event):
    """Get all active triggers for a doctype + event combination.
    
    Cached for performance — cleared on Niv Trigger save/delete.
    """
    cache_key = "niv_ai:triggers"
    all_triggers = frappe.cache().get_value(cache_key)
    
    if all_triggers is None:
        # Load all enabled triggers
        all_triggers = frappe.get_all(
            "Niv Trigger",
            filters={"enabled": 1},
            fields=[
                "name", "trigger_name", "reference_doctype", "doc_event",
                "condition", "prompt_template", "include_document_data",
                "system_prompt", "model"
            ]
        )
        frappe.cache().set_value(cache_key, all_triggers, expires_in_sec=300)
    
    # Map event names: Frappe uses lowercase, we store Title Case
    event_map = {
        "before_save": "Before Save",
        "after_save": "After Save",  
        "on_update": "After Save",
        "before_submit": "Before Submit",
        "on_submit": "After Submit",
        "before_cancel": "Before Cancel",
        "on_cancel": "After Cancel",
        "before_delete": "Before Delete",
        "on_trash": "Before Delete",
    }
    mapped_event = event_map.get(event, event)
    
    return [
        t for t in all_triggers
        if t.reference_doctype == doctype and t.doc_event == mapped_event
    ]
