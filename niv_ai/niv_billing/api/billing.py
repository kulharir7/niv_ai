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

        # Atomic deduction — prevents race condition when multiple users query simultaneously
        # Uses SQL UPDATE with balance check in WHERE clause
        pool_balance = settings.shared_pool_balance or 0
        if pool_balance < total_tokens:
            frappe.throw(_("Company credit pool exhausted. Contact admin to recharge."))

        affected = frappe.db.sql("""
            UPDATE `tabSingles`
            SET `value` = CAST(CAST(`value` AS SIGNED) - %(tokens)s AS CHAR)
            WHERE `doctype` = 'Niv Settings' AND `field` = 'shared_pool_balance'
            AND CAST(`value` AS SIGNED) >= %(tokens)s
        """, {"tokens": total_tokens})
        rows_affected = frappe.db.sql("SELECT ROW_COUNT()")[0][0]

        if rows_affected == 0:
            frappe.throw(_("Company credit pool exhausted. Contact admin to recharge."))

        # Update used counter (not critical if slightly off)
        frappe.db.sql("""
            UPDATE `tabSingles`
            SET `value` = CAST(CAST(IFNULL(`value`, '0') AS SIGNED) + %(tokens)s AS CHAR)
            WHERE `doctype` = 'Niv Settings' AND `field` = 'shared_pool_used'
        """, {"tokens": total_tokens})

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

    # Calculate cost based on rates
    cost_per_1k_input = flt(getattr(settings, 'cost_per_1k_input', 0) or 0)
    cost_per_1k_output = flt(getattr(settings, 'cost_per_1k_output', 0) or 0)
    token_cost = (input_tokens / 1000 * cost_per_1k_input) + (output_tokens / 1000 * cost_per_1k_output)

    # Log usage (always, both modes) — log errors instead of silently swallowing
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
            "token_cost": token_cost,
            "cost": token_cost,
        }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Failed to insert Niv Usage Log: {e}", "Niv AI Billing")

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


# ══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INTEGRATION APIs — For Billing Server Connection
# ══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def credit_tokens_external(api_key, user_email, tokens, token_type="purchased", 
                           plan_name=None, expiry_days=None, source_ref=None):
    """
    External API for billing server to credit tokens to a user.
    
    Args:
        api_key: Secret key for authentication
        user_email: User's email address
        tokens: Number of tokens to credit
        token_type: 'purchased' | 'daily_free' | 'bonus'
        plan_name: Optional plan name to set
        expiry_days: For daily_free, how many days until expiry (0 = end of day)
        source_ref: Reference from billing server (e.g. Sales Order name)
    
    Returns:
        dict with success status and new balance
    """
    # Validate API key (uses webhook secret from Growth Billing section)
    settings = frappe.get_single("Niv Settings")
    expected_key = settings.get_password('billing_erp_webhook_secret') if settings.billing_erp_webhook_secret else None
    
    if not expected_key:
        frappe.throw(_("Billing webhook secret not configured in Niv Settings → Growth Billing"), frappe.AuthenticationError)
    
    if api_key != expected_key:
        frappe.throw(_("Invalid API key"), frappe.AuthenticationError)
    
    # Validate inputs
    tokens = int(tokens or 0)
    if tokens <= 0:
        frappe.throw(_("Tokens must be positive"))

    user_email = (user_email or "").strip().lower()

    # Idempotency guard: prevent duplicate credit for same source_ref
    ext_payment_id = f"ext_{source_ref}" if source_ref else None
    if ext_payment_id and frappe.db.exists("Niv Recharge", {"payment_id": ext_payment_id}):
        existing = frappe.db.get_value(
            "Niv Recharge",
            {"payment_id": ext_payment_id},
            ["name", "user", "balance_after"],
            as_dict=True,
        )
        return {
            "success": True,
            "idempotent": True,
            "message": f"Already credited for source_ref {source_ref}",
            "recharge": existing.get("name") if existing else None,
            "user": existing.get("user") if existing else None,
            "new_balance": existing.get("balance_after") if existing else None,
        }
    
    # Find user by email
    user = frappe.db.get_value("User", {"email": user_email}, "name")
    if not user:
        frappe.throw(_("User not found: {0}").format(user_email))
    
    # Get or create wallet
    wallet = get_or_create_wallet(user)
    
    # Credit tokens
    wallet.balance += tokens
    wallet.total_allocated = (wallet.total_allocated or 0) + tokens
    wallet.last_recharged = now_datetime()
    
    # Set plan if provided
    if plan_name and frappe.db.exists("Niv Credit Plan", plan_name):
        wallet.current_plan = plan_name
        plan = frappe.get_doc("Niv Credit Plan", plan_name)
        validity = expiry_days if expiry_days is not None else (plan.validity_days or 30)
        wallet.plan_expiry = add_days(getdate(), validity)
    
    wallet.save(ignore_permissions=True)
    
    # Map external type to allowed Niv Recharge transaction_type values
    tx_type = "recharge"
    if token_type in ["allocation", "deduction", "recharge", "expiry", "adjustment"]:
        tx_type = token_type
    elif token_type in ["purchased", "purchase", "topup"]:
        tx_type = "recharge"

    # Check if pending recharge row exists for this source_ref (created by create_order)
    # If found, update it to Completed instead of creating duplicate row
    pending_recharge_name = None
    if source_ref:
        pending_recharge_name = frappe.db.get_value(
            "Niv Recharge",
            {"razorpay_order_id": source_ref, "status": "Pending"},
            "name"
        )
    
    if pending_recharge_name:
        # Update existing pending row to Completed
        frappe.db.set_value("Niv Recharge", pending_recharge_name, {
            "status": "Completed",
            "payment_id": ext_payment_id,
            "balance_after": wallet.balance,
            "remarks": f"Completed via external credit. Ref: {source_ref}",
        }, update_modified=True)
    else:
        # Create new recharge record (fallback for direct API calls without prior pending row)
        frappe.get_doc({
            "doctype": "Niv Recharge",
            "user": user,
            "tokens": tokens,
            "transaction_type": tx_type,
            "status": "Completed",
            "payment_id": ext_payment_id,
            "remarks": f"External credit from billing server. Ref: {source_ref or 'N/A'}",
            "balance_after": wallet.balance,
        }).insert(ignore_permissions=True)
    
    frappe.db.commit()
    
    return {
        "success": True,
        "user": user,
        "user_email": user_email,
        "tokens_credited": tokens,
        "token_type": token_type,
        "new_balance": wallet.balance,
        "plan": wallet.current_plan,
        "plan_expiry": str(wallet.plan_expiry) if wallet.plan_expiry else None,
    }


@frappe.whitelist(allow_guest=True)
def get_plans_external(api_key):
    """
    External API for billing server to fetch plans.
    Used to sync plans to billing server.
    """
    settings = frappe.get_single("Niv Settings")
    expected_key = settings.get_password('billing_erp_webhook_secret') if settings.billing_erp_webhook_secret else None
    
    if not expected_key or api_key != expected_key:
        frappe.throw(_("Invalid API key"), frappe.AuthenticationError)
    
    plans = frappe.get_all("Niv Credit Plan",
        fields=["name", "plan_name", "tokens", "price", "currency", 
                "description", "validity_days", "is_default", "is_active"],
        filters={"is_active": 1},
        order_by="price ASC"
    )
    return {"success": True, "plans": plans}


@frappe.whitelist(allow_guest=True)
def check_balance_external(api_key, user_email):
    """
    External API to check user's token balance.
    """
    settings = frappe.get_single("Niv Settings")
    expected_key = settings.get_password('billing_erp_webhook_secret') if settings.billing_erp_webhook_secret else None
    
    if not expected_key or api_key != expected_key:
        frappe.throw(_("Invalid API key"), frappe.AuthenticationError)
    
    user = frappe.db.get_value("User", {"email": user_email}, "name")
    if not user:
        return {"success": False, "error": "User not found", "balance": 0}
    
    wallet = get_or_create_wallet(user)
    return {
        "success": True,
        "user": user,
        "user_email": user_email,
        "balance": wallet.balance,
        "current_plan": wallet.current_plan,
        "plan_expiry": str(wallet.plan_expiry) if wallet.plan_expiry else None,
    }


@frappe.whitelist(allow_guest=True) 
def credit_daily_free_tokens(api_key, user_email, tokens):
    """
    Credit daily free tokens that expire at end of day.
    Called by billing server's daily cron job.
    """
    settings = frappe.get_single("Niv Settings")
    expected_key = settings.get_password('billing_erp_webhook_secret') if settings.billing_erp_webhook_secret else None
    
    if not expected_key or api_key != expected_key:
        frappe.throw(_("Invalid API key"), frappe.AuthenticationError)
    
    tokens = int(tokens or 0)
    if tokens <= 0:
        return {"success": False, "error": "Tokens must be positive"}
    
    user = frappe.db.get_value("User", {"email": user_email}, "name")
    if not user:
        return {"success": False, "error": f"User not found: {user_email}"}
    
    # For daily free tokens, we add to wallet but track separately
    # The expiry is handled by a daily cleanup job
    wallet = get_or_create_wallet(user)
    wallet.balance += tokens
    wallet.total_allocated = (wallet.total_allocated or 0) + tokens
    wallet.save(ignore_permissions=True)
    
    # Log using valid transaction type + daily marker in remarks
    frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": tokens,
        "transaction_type": "recharge",
        "remarks": f"Daily free tokens - expires at midnight",
        "balance_after": wallet.balance,
    }).insert(ignore_permissions=True)
    
    frappe.db.commit()
    
    return {
        "success": True,
        "user": user,
        "tokens_credited": tokens,
        "new_balance": wallet.balance,
    }
