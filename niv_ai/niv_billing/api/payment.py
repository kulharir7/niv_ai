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


def _get_payment_mode():
    """Detect payment mode: 'erpnext' | 'razorpay' | 'demo'"""
    settings = frappe.get_single("Niv Settings")
    
    # ERPNext billing takes priority if configured
    erp_url = getattr(settings, "billing_erp_url", None)
    erp_key = getattr(settings, "billing_erp_api_key", None)
    if erp_url and erp_key:
        return "erpnext"
    
    # Razorpay if keys configured
    key_id = settings.razorpay_key_id
    key_secret = settings.get_password("razorpay_key_secret") if settings.razorpay_key_secret else None
    if key_id and key_secret and key_id.startswith("rzp_"):
        return "razorpay"
    
    return "demo"


def _is_demo_mode():
    """Returns True if no real payment gateway configured"""
    return _get_payment_mode() == "demo"


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
        "payment_mode": _get_payment_mode(),
        "demo_mode": _is_demo_mode(),
    }


@frappe.whitelist(allow_guest=False)
def create_order(plan_name):
    """Create a payment order for a credit plan.
    
    Supports 3 modes:
    - erpnext: Creates Sales Order on vendor's ERPNext via REST API
    - razorpay: Creates Razorpay payment order
    - demo: Fake order for testing
    """
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

    payment_mode = _get_payment_mode()

    if payment_mode == "erpnext":
        return _create_erpnext_order(plan, user, settings, currency)
    elif payment_mode == "razorpay":
        return _create_razorpay_order(plan, user, settings, currency, amount_paise)
    else:
        return _create_demo_order(plan, user, currency)


def _create_erpnext_order(plan, user, settings, currency):
    """Create Sales Order on vendor's ERPNext via REST API."""
    import requests as req

    erp_url = settings.billing_erp_url.rstrip("/")
    api_key = settings.billing_erp_api_key
    api_secret = settings.get_password("billing_erp_api_secret")
    customer = getattr(settings, "billing_erp_customer", None) or "Niv AI Customer"
    item_code = getattr(settings, "billing_erp_item", None) or "Niv AI Token Recharge"

    # Our site URL for webhook callback
    site_url = frappe.utils.get_url()

    # Create Sales Order on vendor ERPNext
    so_data = {
        "doctype": "Sales Order",
        "customer": customer,
        "transaction_date": frappe.utils.today(),
        "delivery_date": frappe.utils.today(),
        "currency": currency,
        "items": [{
            "item_code": item_code,
            "qty": 1,
            "rate": flt(plan.price),
            "description": f"{plan.plan_name} - {plan.tokens:,} tokens",
        }],
        "custom_niv_recharge_tokens": int(plan.tokens),
        "custom_niv_callback_url": f"{site_url}/api/method/niv_ai.niv_billing.api.payment.erpnext_webhook",
        "custom_niv_plan": plan.plan_name,
        "custom_niv_site": frappe.local.site,
    }

    try:
        resp = req.post(
            f"{erp_url}/api/resource/Sales Order",
            headers={
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json",
            },
            json={"data": json.dumps(so_data)},
            timeout=30,
        )
        resp.raise_for_status()
        so_result = resp.json()
        so_name = so_result.get("data", {}).get("name", "")
    except Exception as e:
        frappe.log_error(f"ERPNext Sales Order creation failed: {e}", "Niv Billing ERPNext")
        frappe.throw(_("Failed to create recharge order. Please try again."))

    # Save pending recharge record locally
    recharge = frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": int(plan.tokens),
        "transaction_type": "recharge",
        "plan": plan.name,
        "amount": plan.price,
        "currency": currency,
        "razorpay_order_id": so_name,  # Reuse field for SO reference
        "status": "Pending",
        "remarks": f"Recharge: {plan.plan_name} | SO: {so_name} (vendor ERPNext)",
    })
    recharge.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "order_id": so_name,
        "payment_mode": "erpnext",
        "message": f"Recharge request sent! Order {so_name} created. Tokens will be credited after payment confirmation.",
        "plan_name": plan.plan_name,
        "tokens": plan.tokens,
        "amount": int(flt(plan.price) * 100),
        "currency": currency,
    }


def _create_razorpay_order(plan, user, settings, currency, amount_paise):
    """Create Razorpay payment order."""
    client, settings = _get_razorpay_client()
    receipt = f"niv_{frappe.generate_hash(length=12)}"
    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": {
                "user": user,
                "plan": plan.name,
                "tokens": str(plan.tokens),
            }
        })
        order_id = order["id"]
    except Exception as e:
        frappe.log_error(f"Razorpay order creation failed: {e}", "Razorpay Error")
        frappe.throw(_("Failed to create payment order. Please try again."))

    frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": int(plan.tokens),
        "transaction_type": "razorpay",
        "plan": plan.name,
        "amount": plan.price,
        "currency": currency,
        "razorpay_order_id": order_id,
        "status": "Pending",
        "remarks": f"Recharge: {plan.plan_name}",
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "order_id": order_id,
        "payment_mode": "razorpay",
        "amount": amount_paise,
        "currency": currency,
        "plan_name": plan.plan_name,
        "tokens": plan.tokens,
        "razorpay_key": settings.razorpay_key_id,
        "user_email": user,
        "user_name": frappe.get_value("User", user, "full_name") or user,
    }


def _create_demo_order(plan, user, currency):
    """Create fake order for demo/testing."""
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=14))
    order_id = f"demo_order_{rand}"

    frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": int(plan.tokens),
        "transaction_type": "recharge",
        "plan": plan.name,
        "amount": plan.price,
        "currency": currency,
        "razorpay_order_id": order_id,
        "status": "Pending",
        "remarks": f"Recharge: {plan.plan_name} [DEMO]",
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "order_id": order_id,
        "payment_mode": "demo",
        "amount": int(flt(plan.price) * 100),
        "currency": currency,
        "plan_name": plan.plan_name,
        "tokens": plan.tokens,
        "razorpay_key": "demo_key_not_real",
        "user_email": user,
        "user_name": frappe.get_value("User", user, "full_name") or user,
        "demo_mode": True,
    }


@frappe.whitelist(allow_guest=True)
def erpnext_webhook(**kwargs):
    """Webhook callback from vendor's ERPNext when Sales Order is submitted.
    
    Called via ERPNext Webhook (DocType: Sales Order, Event: on_submit).
    Verifies the request and credits tokens to the shared pool.
    
    Expected POST data (from ERPNext webhook body):
        - name: Sales Order name (e.g., SO-00123)
        - custom_niv_recharge_tokens: number of tokens to credit
        - custom_niv_plan: plan name
        - webhook_secret: shared secret for verification
    """
    # Parse webhook data
    data = frappe.form_dict
    if not data:
        try:
            data = json.loads(frappe.request.data or "{}")
        except Exception:
            data = {}

    so_name = data.get("name") or data.get("docname", "")
    tokens = int(data.get("custom_niv_recharge_tokens") or data.get("tokens") or 0)
    webhook_secret = data.get("webhook_secret", "")

    if not so_name or not tokens:
        frappe.throw(_("Invalid webhook data: missing order name or tokens"), frappe.ValidationError)

    # Verify webhook secret
    settings = frappe.get_single("Niv Settings")
    expected_secret = ""
    try:
        expected_secret = settings.get_password("billing_erp_webhook_secret") or ""
    except Exception:
        pass

    if expected_secret and webhook_secret != expected_secret:
        frappe.log_error(f"ERPNext webhook secret mismatch for SO {so_name}", "Niv Billing Webhook")
        frappe.throw(_("Unauthorized webhook request"), frappe.AuthenticationError)

    # Find the pending recharge record
    recharge_name = frappe.db.get_value(
        "Niv Recharge",
        {"razorpay_order_id": so_name, "status": "Pending"},
        "name"
    )

    if not recharge_name:
        # No pending record — might be a direct credit (admin initiated from vendor side)
        # Create a new recharge record
        recharge = frappe.get_doc({
            "doctype": "Niv Recharge",
            "user": "Administrator",
            "tokens": tokens,
            "transaction_type": "recharge",
            "amount": 0,
            "razorpay_order_id": so_name,
            "status": "Pending",
            "remarks": f"Webhook credit from vendor SO: {so_name}",
        })
        recharge.insert(ignore_permissions=True)
        recharge_name = recharge.name
    
    recharge = frappe.get_doc("Niv Recharge", recharge_name)

    # Credit tokens
    result = _credit_tokens(recharge)

    # Mark as completed
    recharge.status = "Completed"
    recharge.payment_id = f"erp_webhook_{so_name}"
    recharge.balance_after = result["new_balance"]
    recharge.remarks = (recharge.remarks or "") + f" | Confirmed via webhook"
    recharge.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "tokens_credited": recharge.tokens,
        "new_balance": result["new_balance"],
        "recharge": recharge_name,
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
