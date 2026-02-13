# Niv AI Core Utilities
import frappe


def get_niv_settings():
    """Get Niv Settings with v14 fallback for missing document_cache."""
    try:
        return frappe.get_cached_doc("Niv Settings")
    except AttributeError:
        return frappe.get_doc("Niv Settings")
