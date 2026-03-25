"""
Self-service mobile pairing API — any logged-in user can generate their own pairing code.
File: niv_ai/niv_core/api/mobile_self_pair.py
"""
import frappe
import random
import string
from datetime import datetime, timedelta

@frappe.whitelist(allow_guest=False)
def get_my_pairing_code():
    """Generate or return existing pairing code for the current user."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Please login first")

    # Check if user already has an active code
    existing = frappe.db.get_value(
        "Niv Pairing Code",
        {"frappe_user": user, "status": "Active"},
        ["name", "code", "expires_at"],
        as_dict=True
    )

    if existing and existing.expires_at and existing.expires_at > datetime.now():
        settings = frappe.get_single("Niv Settings")
        site_url = getattr(settings, "mobile_site_url", "") or frappe.utils.get_url()
        return {
            "success": True,
            "code": existing.code,
            "expires_at": str(existing.expires_at),
            "site_url": site_url,
        }

    # Generate new code
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    settings = frappe.get_single("Niv Settings")
    expiry_hours = getattr(settings, "pairing_code_expiry_hours", 24) or 24
    site_url = getattr(settings, "mobile_site_url", "") or frappe.utils.get_url()
    expires_at = datetime.now() + timedelta(hours=int(expiry_hours))

    # Expire old codes for this user
    old_codes = frappe.get_all(
        "Niv Pairing Code",
        filters={"frappe_user": user, "status": "Active"},
        pluck="name"
    )
    for old in old_codes:
        frappe.db.set_value("Niv Pairing Code", old, "status", "Expired")

    # Create new pairing code
    doc = frappe.get_doc({
        "doctype": "Niv Pairing Code",
        "code": code,
        "frappe_user": user,
        "status": "Active",
        "expires_at": expires_at,
        "site_url": site_url,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "code": code,
        "expires_at": str(expires_at),
        "site_url": site_url,
    }
