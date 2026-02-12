import frappe
from frappe import _
from frappe.utils import now_datetime, flt
import json
import hashlib
import hmac
import time
import random
import string
from niv_ai.niv_core.compat import db_set_single_value


def _is_demo_mode():
    """Returns True if Razorpay keys are not configured → demo mode"""
    settings = frappe.get_single("Niv Settings")
    key_id = settings.razorpay_key_id
    key_secret = settings.get_password("razorpay_key_secret") if settings.razorpay_key_secret else None
    return not (key_id and key_secret)


def _get_razorpay_client():
    """Get authenticated Razorpay client. Only call when NOT in demo mode."""
    import razorpay
    settings = frappe.get_single("Niv Settings")
    key_id = settings.razorpay_key_id
    key_secret = settings.get_password("razorpay_key_secret")
    if not key_id or not key_secret:
        frappe.throw(_("Razorpay credentials not configured."))
    return razorpay.Client(auth=(key_id, key_secret)), settings


@frappe.whitelist(allow_guest=False)
def get_plans():
    """List available credit plans for recharge"""
    plans = frappe.get_all(
        "Niv Credit Plan",
        filters={"is_active": 1},
        fields=["name", "plan_name", "tokens", "price", "validity_days", "description"],
        order_by="price ASC",
    )
    for p in plans:
        p["credits"] = p.get("tokens", 0)
        p["currency"] = "INR"

    return {
        "plans": plans,
        "demo_mode": _is_demo_mode(),
    }


@frappe.whitelist(allow_guest=False)
def create_order(plan_name):
    """Create a payment order for a credit plan.
    Demo mode: returns fake order. Real mode: creates Razorpay order."""
    plan = frappe.get_doc("Niv Credit Plan", plan_name)
    if not plan.is_active:
        frappe.throw(_("This plan is not available."))

    user = frappe.session.user
    settings = frappe.get_single("Niv Settings")
    currency = getattr(plan, "currency", None) or getattr(settings, "payment_currency", None) or "INR"
    amount_paise = int(flt(plan.price) * 100)

    # Free plan — auto-credit without payment
    if amount_paise <= 0:
        tokens = int(flt(plan.tokens))
        if tokens <= 0:
            frappe.throw(_("Invalid plan."))
        # Create recharge record
        recharge = frappe.get_doc({
            "doctype": "Niv Recharge",
            "user": user,
            "plan": plan_name,
            "tokens": tokens,
            "amount": 0,
            "status": "Completed",
            "payment_id": "free_claim",
            "transaction_type": "recharge",
        })
        recharge.insert(ignore_permissions=True)
        frappe.db.set_value("Niv Recharge", recharge.name, "status", "Completed")
        result = _credit_tokens(recharge)
        frappe.db.commit()
        return {
            "free": True,
            "message": f"{tokens:,} tokens credited!",
            "tokens": tokens,
            "new_balance": result.get("new_balance"),
        }

    demo_mode = _is_demo_mode()

    if demo_mode:
        # Generate fake order ID
        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=14))
        order_id = f"demo_order_{rand}"
        razorpay_key = "demo_key_not_real"
    else:
        # Real Razorpay order
        client, settings = _get_razorpay_client()
        receipt = f"niv_{frappe.generate_hash(length=12)}"
        try:
            order = client.order.create({
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "notes": {
                    "user": user,
                    "plan": plan_name,
                    "tokens": str(plan.tokens),
                }
            })
            order_id = order["id"]
        except Exception as e:
            frappe.log_error(f"Razorpay order creation failed: {e}", "Razorpay Error")
            frappe.throw(_("Failed to create payment order. Please try again."))
        razorpay_key = settings.razorpay_key_id

    # Save pending recharge record
    frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": int(plan.tokens),
        "transaction_type": "recharge" if demo_mode else "razorpay",
        "plan": plan_name,
        "amount": plan.price,
        "currency": currency,
        "razorpay_order_id": order_id,
        "status": "Pending",
        "remarks": f"Recharge: {plan.plan_name}" + (" [DEMO]" if demo_mode else ""),
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "order_id": order_id,
        "amount": amount_paise,
        "currency": currency,
        "plan_name": plan.plan_name,
        "tokens": plan.tokens,
        "razorpay_key": razorpay_key,
        "user_email": user,
        "user_name": frappe.get_value("User", user, "full_name") or user,
        "demo_mode": demo_mode,
    }


@frappe.whitelist(allow_guest=False)
def verify_payment(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """Verify payment signature.
    Demo mode: auto-verify. Real mode: verify Razorpay signature."""
    demo_mode = _is_demo_mode()

    # Find the pending recharge
    recharge_name = frappe.db.get_value(
        "Niv Recharge",
        {"razorpay_order_id": razorpay_order_id, "status": "Pending"},
        "name"
    )
    if not recharge_name:
        frappe.throw(_("Order not found or already processed."))

    recharge = frappe.get_doc("Niv Recharge", recharge_name)

    if demo_mode:
        # Demo mode: auto-verify (always pass)
        pass
    else:
        # Real Razorpay verification
        client, settings = _get_razorpay_client()
        try:
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            })
        except Exception:
            recharge.status = "Failed"
            recharge.razorpay_payment_id = razorpay_payment_id
            recharge.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.throw(_("Payment verification failed. If amount was deducted, it will be refunded."))

    # Credit tokens
    result = _credit_tokens(recharge)

    # Update recharge record
    recharge.status = "Completed"
    recharge.razorpay_payment_id = razorpay_payment_id
    recharge.razorpay_signature = razorpay_signature
    recharge.balance_after = result["new_balance"]
    recharge.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "tokens_added": recharge.tokens,
        "new_balance": result["new_balance"],
        "mode": result["mode"],
        "demo_mode": demo_mode,
    }


# Alias for backward compat
process_payment = verify_payment


def _credit_tokens(recharge):
    """Credit tokens to wallet or shared pool based on billing mode."""
    settings = frappe.get_single("Niv Settings")

    if settings.billing_mode == "Shared Pool":
        new_balance = (settings.shared_pool_balance or 0) + recharge.tokens
        db_set_single_value("Niv Settings", "shared_pool_balance", new_balance)
        return {"new_balance": new_balance, "mode": "shared_pool"}
    else:
        from niv_ai.niv_billing.api.billing import get_or_create_wallet
        wallet = get_or_create_wallet(recharge.user)
        wallet.balance += recharge.tokens
        wallet.total_allocated = (wallet.total_allocated or 0) + recharge.tokens
        wallet.last_recharged = now_datetime()
        if recharge.plan:
            wallet.current_plan = recharge.plan
        wallet.save(ignore_permissions=True)
        return {"new_balance": wallet.balance, "mode": "per_user"}


@frappe.whitelist(allow_guest=False)
def get_recharge_history(page=1, page_size=20):
    """Get current user's recharge/payment history"""
    user = frappe.session.user
    page = int(page)
    page_size = min(int(page_size), 50)
    offset = (page - 1) * page_size

    records = frappe.get_all(
        "Niv Recharge",
        filters={"user": user},
        fields=["name", "tokens", "transaction_type", "plan", "amount",
                "status", "balance_after", "remarks", "creation"],
        order_by="creation DESC",
        limit_start=offset,
        limit_page_length=page_size,
    )

    total = frappe.db.count("Niv Recharge", {"user": user})

    return {
        "records": records,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# Keep backward compat alias
get_payment_history = get_recharge_history
