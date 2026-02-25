import frappe
from frappe import _
from frappe.utils import now_datetime, flt
import json
import random
import string
from niv_ai.niv_core.compat import db_set_single_value


def _get_payment_mode():
    """Detect payment mode: 'growth' | 'demo'"""
    settings = frappe.get_single("Niv Settings")

    # Growth Billing if configured
    erp_url = getattr(settings, "billing_erp_url", None)
    erp_key = getattr(settings, "billing_erp_api_key", None)
    erp_secret = settings.get_password("billing_erp_api_secret")
    if erp_url and erp_key and erp_secret:
        return "growth"

    return "demo"


def _is_demo_mode():
    """Returns True if no real payment gateway configured"""
    return _get_payment_mode() == "demo"


@frappe.whitelist(allow_guest=False)
def get_plans():
    """List available credit plans for recharge.

    Priority:
    1) Billing server Token Plan (single source of truth)
    2) Local Niv Credit Plan fallback
    """
    payment_mode = _get_payment_mode()
    plans = []

    # Try billing-side plans first when growth billing is configured
    if payment_mode == "growth":
        settings = frappe.get_single("Niv Settings")
        erp_url = (settings.billing_erp_url or "").rstrip("/")
        api_key = settings.billing_erp_api_key
        api_secret = settings.get_password("billing_erp_api_secret")

        if erp_url and api_key and api_secret:
            try:
                import requests as req

                fields = json.dumps(["name", "plan_name", "tokens", "price", "currency", "description", "is_active", "sort_order"])
                filters = json.dumps([["Token Plan", "is_active", "=", 1]])
                order_by = "sort_order asc"

                resp = req.get(
                    f"{erp_url}/api/resource/Token Plan",
                    headers={"Authorization": f"token {api_key}:{api_secret}"},
                    params={"fields": fields, "filters": filters, "order_by": order_by, "limit_page_length": 100},
                    timeout=20,
                )
                resp.raise_for_status()
                data = (resp.json() or {}).get("data", [])

                for p in data:
                    plans.append({
                        "name": p.get("name"),
                        "plan_name": p.get("plan_name") or p.get("name"),
                        "tokens": int(p.get("tokens") or 0),
                        "price": flt(p.get("price") or 0),
                        "description": p.get("description") or "",
                        "currency": p.get("currency") or "INR",
                        "credits": int(p.get("tokens") or 0),
                    })
            except Exception as e:
                frappe.log_error(f"Billing plans fetch failed: {e}", "Niv Growth Billing Plans")

    # Fallback to local plans if billing plans unavailable
    if not plans:
        plans = frappe.get_all(
            "Niv Credit Plan",
            filters={"is_active": 1},
            fields=["name", "plan_name", "tokens", "price", "validity_days", "description"],
            order_by="price ASC",
        )
        for p in plans:
            p["credits"] = p.get("tokens", 0)
            p["currency"] = p.get("currency") or "INR"

    return {
        "plans": plans,
        "payment_mode": payment_mode,
        "demo_mode": _is_demo_mode(),
    }


@frappe.whitelist(allow_guest=False)
def create_order(plan_name):
    """Create a payment order for a credit plan.

    Supports 2 modes:
    - growth: Creates Sales Order on vendor's ERPNext via Growth Billing
    - demo: Fake order for testing
    """
    payment_mode = _get_payment_mode()

    # Resolve plan - in growth mode, billing server is source of truth
    plan = None
    if payment_mode == "growth":
        # Growth mode: fetch from billing server's Token Plan (source of truth)
        billing_plans = get_plans().get("plans", [])
        matched = next((p for p in billing_plans if p.get("name") == plan_name or p.get("plan_name") == plan_name), None)
        if matched:
            plan = frappe._dict({
                "name": matched.get("name") or matched.get("plan_name"),
                "plan_name": matched.get("plan_name") or matched.get("name"),
                "tokens": int(matched.get("tokens") or 0),
                "price": flt(matched.get("price") or 0),
                "description": matched.get("description") or "",
                "is_active": 1,
                "currency": matched.get("currency") or "INR",
            })
    
    # Fallback to local Niv Credit Plan (for demo mode or if billing fetch failed)
    if not plan and frappe.db.exists("Niv Credit Plan", plan_name):
        plan = frappe.get_doc("Niv Credit Plan", plan_name)

    if not plan:
        frappe.throw(_("Selected plan not found."))

    if not getattr(plan, "is_active", 1):
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

    if payment_mode == "growth":
        return _create_growth_order(plan, user, settings, currency)
    else:
        return _create_demo_order(plan, user, currency)


def _create_growth_order(plan, user, settings, currency):
    """Create Sales Order on vendor's ERPNext via Growth Billing."""
    import requests as req

    erp_url = settings.billing_erp_url.rstrip("/")
    api_key = settings.billing_erp_api_key
    api_secret = settings.get_password("billing_erp_api_secret")
    user_email = frappe.db.get_value("User", user, "email") or user
    customer = getattr(settings, "billing_erp_customer", None) or "Niv AI Customer"
    item_code = getattr(settings, "billing_erp_item", None) or "Niv AI Token Recharge"

    site_url = frappe.utils.get_url()

    so_data = {
        "doctype": "Sales Order",
        "customer": customer,
        "transaction_date": frappe.utils.today(),
        "delivery_date": frappe.utils.today(),
        "currency": currency,
        "contact_email": user_email,
        "items": [{
            "item_code": item_code,
            "qty": int(plan.tokens),  # qty itself represents token count
            "rate": flt(plan.price) / max(int(plan.tokens), 1),
            "description": f"{plan.plan_name} - {plan.tokens:,} tokens",
        }],
        "custom_niv_recharge_tokens": int(plan.tokens),
        "custom_niv_callback_url": f"{site_url}/api/method/niv_ai.niv_billing.api.payment.erpnext_webhook",
        "custom_niv_plan": plan.plan_name,
        "custom_niv_site": frappe.local.site,
        "custom_niv_user_email": user_email,
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
        frappe.log_error(f"Growth Billing order creation failed: {e}", "Niv Growth Billing")
        frappe.throw(_("Failed to create recharge order. Please try again."))

    recharge = frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": int(plan.tokens),
        "transaction_type": "recharge",
        "plan": plan.name,
        "amount": plan.price,
        "currency": currency,
        "razorpay_order_id": so_name,
        "status": "Pending",
        "remarks": f"Recharge: {plan.plan_name} | SO: {so_name} (Growth Billing)",
    })
    recharge.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "order_id": so_name,
        "payment_mode": "growth",
        "message": f"Recharge request sent! Order {so_name} created. Tokens will be credited after payment confirmation.",
        "plan_name": plan.plan_name,
        "tokens": plan.tokens,
        "amount": int(flt(plan.price) * 100),
        "currency": currency,
        "redirect_url": f"{erp_url}/app/sales-order/{so_name}",
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
        "user_email": user,
        "user_name": frappe.get_value("User", user, "full_name") or user,
        "demo_mode": True,
    }


@frappe.whitelist(allow_guest=True)
def erpnext_webhook(**kwargs):
    """Webhook callback from vendor's ERPNext (Growth Billing) when Sales Order is submitted.

    Called via ERPNext Webhook (DocType: Sales Order, Event: on_submit).
    Verifies the request and credits tokens to the shared pool.
    """
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
        frappe.log_error(f"Growth Billing webhook secret mismatch for SO {so_name}", "Niv Billing Webhook")
        frappe.throw(_("Unauthorized webhook request"), frappe.AuthenticationError)

    # Find pending recharge
    recharge_name = frappe.db.get_value(
        "Niv Recharge",
        {"razorpay_order_id": so_name, "status": "Pending"},
        "name"
    )

    if not recharge_name:
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
    result = _credit_tokens(recharge)

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
def verify_payment(order_id, payment_id="", signature="", **kwargs):
    """Verify payment and credit tokens.

    Demo mode: auto-verify.
    Growth mode: verified via webhook (this is fallback).

    Also accepts legacy razorpay_order_id/razorpay_payment_id kwargs for backward compat.
    """
    # Backward compat: accept old razorpay_* param names
    order_id = order_id or kwargs.get("razorpay_order_id", "")
    payment_id = payment_id or kwargs.get("razorpay_payment_id", "")

    # Find pending recharge
    recharge_name = frappe.db.get_value(
        "Niv Recharge",
        {"razorpay_order_id": order_id, "status": "Pending"},
        "name"
    )
    # Backward compat: also check razorpay_order_id field
    if not recharge_name:
        recharge_name = frappe.db.get_value(
            "Niv Recharge",
            {"razorpay_order_id": order_id, "status": "Pending"},
            "name"
        )
    if not recharge_name:
        frappe.throw(_("Order not found or already processed."))

    recharge = frappe.get_doc("Niv Recharge", recharge_name)

    # Credit tokens
    result = _credit_tokens(recharge)

    recharge.status = "Completed"
    recharge.payment_id = payment_id
    recharge.balance_after = result["new_balance"]
    recharge.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "tokens_added": recharge.tokens,
        "new_balance": result["new_balance"],
        "mode": result["mode"],
        "demo_mode": _is_demo_mode(),
    }


# Backward compat aliases
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


# Backward compat alias
get_payment_history = get_recharge_history
