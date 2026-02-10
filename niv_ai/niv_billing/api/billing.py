import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, add_days, flt
from niv_ai.niv_core.compat import db_set_single_value


@frappe.whitelist(allow_guest=False)
def check_balance(user=None):
    """Check credit balance — shared pool or per-user based on settings"""
    user = user or frappe.session.user
    settings = frappe.get_single("Niv Settings")

    if settings.billing_mode == "Shared Pool":
        return {
            "user": user,
            "balance": settings.shared_pool_balance or 0,
            "total_used": settings.shared_pool_used or 0,
            "mode": "shared_pool",
            "daily_limit": settings.per_user_daily_limit or 0,
            "daily_used": _get_user_daily_usage(user),
        }

    wallet = get_or_create_wallet(user)
    return {
        "user": user,
        "balance": wallet.balance,
        "total_used": wallet.total_used,
        "total_allocated": wallet.total_allocated,
        "current_plan": wallet.current_plan,
        "plan_expiry": str(wallet.plan_expiry) if wallet.plan_expiry else None,
        "last_recharged": str(wallet.last_recharged) if wallet.last_recharged else None,
        "mode": "per_user",
    }


@frappe.whitelist(allow_guest=False)
def deduct_tokens(user=None, input_tokens=0, output_tokens=0,
                  conversation=None, message=None, model=None):
    """Deduct tokens — shared pool or per-user based on settings"""
    user = user or frappe.session.user
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    total_tokens = input_tokens + output_tokens
    if total_tokens <= 0:
        return {"success": True, "deducted": 0}

    settings = frappe.get_single("Niv Settings")

    if settings.billing_mode == "Shared Pool":
        # Check daily limit
        if settings.per_user_daily_limit:
            daily_used = _get_user_daily_usage(user)
            if daily_used + total_tokens > settings.per_user_daily_limit:
                frappe.throw(_("Daily limit reached ({0}/{1} tokens). Try again tomorrow.").format(
                    daily_used, settings.per_user_daily_limit
                ))

        # Check pool balance
        pool_balance = settings.shared_pool_balance or 0
        if pool_balance < total_tokens:
            frappe.throw(_("Company credit pool exhausted. Contact admin to recharge."))

        # Deduct from shared pool
        db_set_single_value("Niv Settings", {
            "shared_pool_balance": pool_balance - total_tokens,
            "shared_pool_used": (settings.shared_pool_used or 0) + total_tokens,
        })
        remaining = pool_balance - total_tokens
    else:
        # Per-user wallet
        wallet = get_or_create_wallet(user)
        if wallet.balance < total_tokens:
            frappe.throw(_("Insufficient credits. Balance: {0}, Required: {1}").format(
                wallet.balance, total_tokens
            ))
        wallet.balance -= total_tokens
        wallet.total_used = (wallet.total_used or 0) + total_tokens
        wallet.save(ignore_permissions=True)
        remaining = wallet.balance

    # Log usage (always, both modes)
    try:
        frappe.get_doc({
            "doctype": "Niv Usage Log",
            "user": user,
            "conversation": conversation,
            "message": message,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }).insert(ignore_permissions=True)
    except Exception:
        pass

    frappe.db.commit()
    return {
        "success": True,
        "deducted": total_tokens,
        "remaining_balance": remaining,
    }


@frappe.whitelist(allow_guest=False)
def get_usage_stats(user=None, period="month"):
    """Get usage statistics for the current user (or specified user for admins)"""
    if user and user != frappe.session.user:
        if "System Manager" not in frappe.get_roles():
            frappe.throw(_("Only System Managers can view other users' stats"))
    else:
        user = frappe.session.user

    if period == "today":
        start_date = getdate()
    elif period == "week":
        start_date = add_days(getdate(), -7)
    else:
        start_date = add_days(getdate(), -30)

    usage = frappe.db.sql("""
        SELECT
            COUNT(*) as total_requests,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens
        FROM `tabNiv Usage Log`
        WHERE user = %s AND DATE(creation) >= %s
    """, (user, start_date), as_dict=True)[0]

    # Daily breakdown
    daily = frappe.db.sql("""
        SELECT
            DATE(creation) as date,
            COUNT(*) as requests,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens
        FROM `tabNiv Usage Log`
        WHERE user = %s AND DATE(creation) >= %s
        GROUP BY DATE(creation)
        ORDER BY DATE(creation) ASC
    """, (user, start_date), as_dict=True)

    settings = frappe.get_single("Niv Settings")
    if settings.billing_mode == "Shared Pool":
        balance = settings.shared_pool_balance or 0
        current_plan = "Shared Pool"
    else:
        wallet = get_or_create_wallet(user)
        balance = wallet.balance
        current_plan = wallet.current_plan

    return {
        "period": period,
        "balance": balance,
        "current_plan": current_plan,
        "summary": usage,
        "daily": daily,
    }


def _get_user_daily_usage(user):
    """Get total tokens used by user today"""
    today = getdate()
    result = frappe.db.sql("""
        SELECT COALESCE(SUM(total_tokens), 0) as total
        FROM `tabNiv Usage Log`
        WHERE user = %s AND DATE(creation) = %s
    """, (user, today), as_dict=True)
    return result[0].total if result else 0


@frappe.whitelist(allow_guest=False)
def recharge_shared_pool(amount):
    """Add credits to shared pool. System Manager only."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Managers can recharge the pool"))
    amount = int(amount or 0)
    if amount <= 0:
        frappe.throw(_("Amount must be positive"))

    settings = frappe.get_single("Niv Settings")
    new_balance = (settings.shared_pool_balance or 0) + amount
    db_set_single_value("Niv Settings", "shared_pool_balance", new_balance)
    frappe.db.commit()
    return {"success": True, "new_balance": new_balance}


@frappe.whitelist(allow_guest=False)
def get_credit_plans():
    """Get available credit plans for recharge UI"""
    plans = frappe.get_all("Niv Credit Plan",
        fields=["name", "plan_name", "tokens", "price", "description", "validity_days"],
        filters={"is_active": 1},
        order_by="price ASC"
    )
    return plans


def get_or_create_wallet(user):
    """Get or create a wallet for the user"""
    if frappe.db.exists("Niv Wallet", user):
        return frappe.get_doc("Niv Wallet", user)

    wallet = frappe.get_doc({
        "doctype": "Niv Wallet",
        "user": user,
        "balance": 1000,
        "total_allocated": 1000,
        "total_used": 0,
    })
    wallet.insert(ignore_permissions=True)
    frappe.db.commit()
    return wallet


# Alias for convenience
get_balance = check_balance


@frappe.whitelist(allow_guest=False)
def admin_allocate_credits(user, amount):
    """Add credits to a user's wallet. System Manager only."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Managers can allocate credits"))

    amount = int(amount or 0)
    if amount <= 0:
        frappe.throw(_("Amount must be positive"))

    wallet = get_or_create_wallet(user)
    wallet.balance += amount
    wallet.total_allocated = (wallet.total_allocated or 0) + amount
    wallet.last_recharged = now_datetime()
    wallet.save(ignore_permissions=True)

    frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": amount,
        "transaction_type": "allocation",
        "remarks": f"Admin allocation by {frappe.session.user}",
        "balance_after": wallet.balance,
    }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {"success": True, "user": user, "allocated": amount, "new_balance": wallet.balance}


def cleanup_expired_credits():
    """Daily scheduler: placeholder for expired plan handling"""
    pass


def generate_usage_summary():
    """Weekly scheduler placeholder"""
    pass
