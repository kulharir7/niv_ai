"""
Niv AI — Mobile App API
Pairing code generation, verification, and mobile chat endpoints.
"""
import json
import secrets
import string
import frappe
from frappe import _
from datetime import datetime, timedelta


@frappe.whitelist(methods=["POST"])
def generate_pairing_code(user_email=None):
    """Generate a pairing code for a user. Admin only."""
    frappe.only_for("System Manager")

    user_email = user_email or frappe.form_dict.get("user_email")
    if not user_email:
        frappe.throw(_("User email is required"))
    if not frappe.db.exists("User", user_email):
        frappe.throw(_("User {} does not exist").format(user_email))

    # Generate unique 8-char alphanumeric code
    code = _generate_unique_code()

    # Get expiry hours from settings
    settings = frappe.get_cached_doc("Niv Settings")
    expiry_hours = getattr(settings, "pairing_code_expiry_hours", 24) or 24
    expires_at = datetime.now() + timedelta(hours=int(expiry_hours))

    # Get site URL
    site_url = getattr(settings, "mobile_site_url", "") or frappe.utils.get_url()

    # Create pairing code doc
    doc = frappe.get_doc({
        "doctype": "Niv Pairing Code",
        "code": code,
        "frappe_user": user_email,
        "status": "Active",
        "expires_at": expires_at,
        "site_url": site_url,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "code": code,
        "expires_at": str(expires_at),
        "site_url": site_url,
        "user": user_email,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def pair(code=None, device_name=None):
    """
    Pair a mobile device using a pairing code.
    Returns auth credentials and config on success.
    Called from the mobile app.
    """
    code = code or frappe.form_dict.get("code", "").strip().upper()
    device_name = device_name or frappe.form_dict.get("device_name", "Mobile App")

    if not code:
        frappe.throw(_("Pairing code is required"), frappe.ValidationError)

    # Find active pairing code
    codes = frappe.get_all(
        "Niv Pairing Code",
        filters={"code": code, "status": "Active"},
        fields=["name", "frappe_user", "expires_at", "site_url"],
        limit=1,
    )

    if not codes:
        frappe.throw(_("Invalid or expired pairing code"), frappe.ValidationError)

    pairing = codes[0]

    # Check expiry
    if pairing.expires_at and datetime.now() > pairing.expires_at:
        frappe.db.set_value("Niv Pairing Code", pairing.name, "status", "Expired")
        frappe.db.commit()
        frappe.throw(_("Pairing code has expired. Please request a new one."), frappe.ValidationError)

    user_email = pairing.frappe_user
    site_url = pairing.site_url or frappe.utils.get_url()

    # Generate API key + secret for this user
    api_key, api_secret = _generate_api_credentials(user_email)

    # Mark code as used
    frappe.db.set_value("Niv Pairing Code", pairing.name, {
        "status": "Used",
        "paired_at": datetime.now(),
        "device_name": device_name,
        "api_key": api_key,
    })
    # Store secret separately (Password field)
    doc = frappe.get_doc("Niv Pairing Code", pairing.name)
    doc.api_secret = api_secret
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Get user info
    user_doc = frappe.get_doc("User", user_email)

    # Get AI config
    settings = frappe.get_cached_doc("Niv Settings")

    return {
        "success": True,
        "site_url": site_url,
        "auth": {
            "api_key": api_key,
            "api_secret": api_secret,
            "token": "token {}:{}".format(api_key, api_secret),
        },
        "user": {
            "email": user_email,
            "full_name": user_doc.full_name,
            "user_image": user_doc.user_image,
        },
        "config": {
            "model": getattr(settings, "default_model", ""),
            "enable_voice": bool(getattr(settings, "enable_voice", 0)),
            "enable_tools": bool(getattr(settings, "enable_tools", 1)),
            "widget_title": getattr(settings, "widget_title", "Niv AI"),
        },
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_token():
    """Verify if a stored token is still valid. Called on app startup."""
    auth_header = frappe.get_request_header("Authorization")
    if not auth_header or not auth_header.startswith("token "):
        return {"valid": False, "reason": "No auth token"}

    try:
        token = auth_header.replace("token ", "")
        api_key, api_secret = token.split(":")

        # Validate API key exists and is active
        key_doc = frappe.db.get_value(
            "User API Key",
            {"api_key": api_key},
            ["name", "user"],
            as_dict=True,
        )

        if not key_doc:
            return {"valid": False, "reason": "Invalid API key"}

        user_doc = frappe.get_doc("User", key_doc.user)
        if not user_doc.enabled:
            return {"valid": False, "reason": "User disabled"}

        return {
            "valid": True,
            "user": {
                "email": key_doc.user,
                "full_name": user_doc.full_name,
                "user_image": user_doc.user_image,
            },
        }
    except Exception:
        return {"valid": False, "reason": "Token verification failed"}


@frappe.whitelist(methods=["POST"])
def revoke_pairing(pairing_code_name):
    """Revoke a pairing code and its API key. Admin only."""
    frappe.only_for("System Manager")

    doc = frappe.get_doc("Niv Pairing Code", pairing_code_name)

    # Revoke API key if exists
    if doc.api_key:
        api_keys = frappe.get_all(
            "User API Key",
            filters={"api_key": doc.api_key},
            limit=1,
        )
        if api_keys:
            frappe.delete_doc("User API Key", api_keys[0].name, ignore_permissions=True)

    doc.status = "Expired"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"ok": True, "message": "Pairing revoked and API key deleted"}


# ── Helper Functions ──

def _generate_unique_code():
    """Generate a unique 8-character alphanumeric pairing code."""
    chars = string.ascii_uppercase + string.digits
    # Remove confusing chars: O, 0, I, 1, L
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "").replace("L", "")

    for _ in range(100):  # max attempts
        code = "".join(secrets.choice(chars) for _ in range(8))
        if not frappe.db.exists("Niv Pairing Code", {"code": code}):
            return code

    frappe.throw(_("Could not generate unique code. Try again."))


def _generate_api_credentials(user_email):
    """Generate API key + secret for a user."""
    # Check if user already has an API key from Niv
    existing = frappe.get_all(
        "User API Key",
        filters={"user": user_email},
        fields=["name", "api_key"],
        order_by="creation desc",
        limit=1,
    )

    if existing:
        # Reuse existing key
        key_doc = frappe.get_doc("User API Key", existing[0].name)
        api_secret = key_doc.get_password("api_secret")
        return existing[0].api_key, api_secret

    # Create new API key
    key_doc = frappe.get_doc({
        "doctype": "User API Key",
        "user": user_email,
    })
    key_doc.insert(ignore_permissions=True)

    api_key = key_doc.api_key
    api_secret = key_doc.get_password("api_secret")

    return api_key, api_secret
