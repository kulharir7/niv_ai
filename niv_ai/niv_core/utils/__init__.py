# Niv AI Core Utilities
import frappe


def get_niv_settings():
    """Get Niv Settings safely — works in SSE streaming, --preload, and v14."""
    try:
        if not hasattr(frappe.local, "document_cache"):
            frappe.local.document_cache = {}
        return frappe.get_cached_doc("Niv Settings")
    except Exception:
        return frappe.get_doc("Niv Settings")
