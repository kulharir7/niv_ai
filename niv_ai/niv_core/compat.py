"""
Compatibility layer for Frappe v14 and v15.
Import helpers from here instead of using version-specific APIs directly.
"""
import frappe

# Detect Frappe major version
try:
    FRAPPE_VERSION = int(frappe.__version__.split(".")[0])
except Exception:
    FRAPPE_VERSION = 15  # default to latest


def set_single_value(doctype, field, value=None):
    """Set value on a Single doctype — works on v14 and v15.
    Supports: set_single_value("DT", "field", value) or set_single_value("DT", {"f1": v1, "f2": v2})
    """
    if isinstance(field, dict):
        for k, v in field.items():
            if FRAPPE_VERSION >= 15:
                frappe.db.set_single_value(doctype, k, v)
            else:
                frappe.db.set_value(doctype, doctype, k, v)
    else:
        if FRAPPE_VERSION >= 15:
            frappe.db.set_single_value(doctype, field, value)
        else:
            frappe.db.set_value(doctype, doctype, field, value)


# Alias used by billing/payment modules
db_set_single_value = set_single_value


def get_single_value(doctype, field):
    """Get value from a Single doctype."""
    return frappe.db.get_single_value(doctype, field)


def safe_json_loads(val, default=None):
    """Safely parse JSON — handles None, empty string, already-parsed objects."""
    if val is None or val == "":
        return default if default is not None else {}
    if isinstance(val, (dict, list)):
        return val
    try:
        import json
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def check_min_version():
    """Check that Frappe version is >= 14. Call from install.py."""
    if FRAPPE_VERSION < 14:
        frappe.throw(
            "Niv AI requires Frappe/ERPNext v14 or later. "
            f"You are running v{frappe.__version__}. "
            "Please upgrade before installing."
        )
