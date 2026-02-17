import frappe
from frappe import _
from frappe.utils import now_datetime, flt, getdate, add_days, get_datetime
import json
import csv
import io


def _check_admin():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Managers can access this"))


@frappe.whitelist()
def get_dashboard_stats():
    """Get comprehensive dashboard statistics. System Manager only."""
    _check_admin()

    today = getdate()
    week_ago = add_days(today, -7)
    month_ago = add_days(today, -30)
    prev_month_start = add_days(today, -60)

    # Total users
    total_users = frappe.db.sql(
        "SELECT COUNT(DISTINCT user) as cnt FROM `tabNiv Conversation`",
        as_dict=True
    )[0].cnt or 0

    # Total conversations
    total_conversations = frappe.db.count("Niv Conversation")

    # Total messages
    total_messages = frappe.db.count("Niv Message")

    # Token/cost totals (current month)
    current = frappe.db.sql("""
        SELECT
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(COALESCE(cost, token_cost, 0)), 0) as total_cost,
            COUNT(*) as request_count
        FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s
    """, (month_ago,), as_dict=True)[0]

    # Previous month for trend
    prev = frappe.db.sql("""
        SELECT
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(COALESCE(cost, token_cost, 0)), 0) as total_cost,
            COUNT(*) as request_count,
            COUNT(DISTINCT user) as active_users
        FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s AND DATE(creation) < %s
    """, (prev_month_start, month_ago), as_dict=True)[0]

    # Active users
    active_today = frappe.db.sql(
        "SELECT COUNT(DISTINCT user) as cnt FROM `tabNiv Usage Log` WHERE DATE(creation) = %s",
        (today,), as_dict=True
    )[0].cnt or 0

    active_week = frappe.db.sql(
        "SELECT COUNT(DISTINCT user) as cnt FROM `tabNiv Usage Log` WHERE DATE(creation) >= %s",
        (week_ago,), as_dict=True
    )[0].cnt or 0

    active_month = frappe.db.sql(
        "SELECT COUNT(DISTINCT user) as cnt FROM `tabNiv Usage Log` WHERE DATE(creation) >= %s",
        (month_ago,), as_dict=True
    )[0].cnt or 0

    # Trend calculations
    def trend(current_val, prev_val):
        if not prev_val:
            return 100 if current_val else 0
        return round(((current_val - prev_val) / prev_val) * 100, 1)

    return {
        "total_users": total_users,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_tokens": current.total_tokens,
        "total_cost": flt(current.total_cost, 2),
        "active_today": active_today,
        "active_week": active_week,
        "active_month": active_month,
        "request_count": current.request_count,
        "trends": {
            "tokens": trend(current.total_tokens, prev.total_tokens),
            "cost": trend(flt(current.total_cost), flt(prev.total_cost)),
            "requests": trend(current.request_count, prev.request_count),
            "users": trend(active_month, prev.active_users),
        }
    }


@frappe.whitelist()
def get_usage_over_time(period="daily", days=30):
    """Time series data for charts."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    if period == "weekly":
        group_expr = "YEARWEEK(creation, 1)"
        date_expr = "MIN(DATE(creation))"
    elif period == "monthly":
        group_expr = "DATE_FORMAT(creation, '%Y-%m')"
        date_expr = "MIN(DATE(creation))"
    else:
        group_expr = "DATE(creation)"
        date_expr = "DATE(creation)"

    data = frappe.db.sql("""
        SELECT
            {date_expr} as date,
            COUNT(*) as requests,
            COUNT(DISTINCT user) as users,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(COALESCE(cost, token_cost, 0)), 0) as cost
        FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s
        GROUP BY {group_expr}
        ORDER BY date ASC
    """.format(date_expr=date_expr, group_expr=group_expr), (start_date,), as_dict=True)

    # Also get message counts per day
    msg_data = frappe.db.sql("""
        SELECT DATE(creation) as date, COUNT(*) as messages
        FROM `tabNiv Message`
        WHERE DATE(creation) >= %s
        GROUP BY DATE(creation)
    """, (start_date,), as_dict=True)
    msg_map = {str(m.date): m.messages for m in msg_data}

    return [{
        "date": str(d.date),
        "requests": d.requests,
        "users": d.users,
        "total_tokens": d.total_tokens,
        "input_tokens": d.input_tokens,
        "output_tokens": d.output_tokens,
        "cost": flt(d.cost, 2),
        "messages": msg_map.get(str(d.date), 0),
    } for d in data]


@frappe.whitelist()
def get_top_users(limit=10, days=30):
    """Most active users by tokens/messages."""
    _check_admin()
    limit = int(limit or 10)
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    users = frappe.db.sql("""
        SELECT
            u.user,
            u.full_name,
            COUNT(*) as requests,
            COUNT(DISTINCT u.conversation) as conversations,
            COALESCE(SUM(u.total_tokens), 0) as total_tokens,
            COALESCE(SUM(u.input_tokens), 0) as input_tokens,
            COALESCE(SUM(u.output_tokens), 0) as output_tokens,
            COALESCE(SUM(COALESCE(u.cost, u.token_cost, 0)), 0) as cost,
            MAX(u.creation) as last_active
        FROM (
            SELECT l.*, usr.full_name
            FROM `tabNiv Usage Log` l
            LEFT JOIN `tabUser` usr ON usr.name = l.user
            WHERE DATE(l.creation) >= %s
        ) u
        GROUP BY u.user, u.full_name
        ORDER BY total_tokens DESC
        LIMIT %s
    """, (start_date, limit), as_dict=True)

    max_tokens = users[0].total_tokens if users else 1

    return [{
        "user": u.user,
        "full_name": u.full_name or u.user,
        "requests": u.requests,
        "conversations": u.conversations,
        "total_tokens": u.total_tokens,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cost": flt(u.cost, 2),
        "last_active": str(u.last_active) if u.last_active else None,
        "bar_pct": round((u.total_tokens / max_tokens) * 100, 1) if max_tokens else 0,
    } for u in users]


@frappe.whitelist()
def get_model_usage(days=30):
    """Breakdown by model."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    data = frappe.db.sql("""
        SELECT
            COALESCE(model, 'unknown') as model,
            COUNT(*) as count,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(COALESCE(cost, token_cost, 0)), 0) as cost
        FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s
        GROUP BY model
        ORDER BY total_tokens DESC
    """, (start_date,), as_dict=True)

    return [{
        "model": d.model,
        "count": d.count,
        "total_tokens": d.total_tokens,
        "input_tokens": d.input_tokens,
        "output_tokens": d.output_tokens,
        "cost": flt(d.cost, 2),
    } for d in data]


@frappe.whitelist()
def get_tool_usage(days=30):
    """Which tools used most, success/fail rates."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    data = frappe.db.sql("""
        SELECT
            COALESCE(tool_name, 'none') as tool_name,
            COUNT(*) as count,
            SUM(CASE WHEN COALESCE(tool_success, 1) = 1 THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN COALESCE(tool_success, 1) = 0 THEN 1 ELSE 0 END) as fail_count
        FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s AND tool_name IS NOT NULL AND tool_name != ''
        GROUP BY tool_name
        ORDER BY count DESC
    """, (start_date,), as_dict=True)

    return [{
        "tool_name": d.tool_name,
        "count": d.count,
        "success_count": d.success_count,
        "fail_count": d.fail_count,
        "success_rate": round((d.success_count / d.count) * 100, 1) if d.count else 0,
    } for d in data]


@frappe.whitelist()
def get_hourly_distribution(days=30):
    """Messages by hour of day for heatmap."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    data = frappe.db.sql("""
        SELECT
            HOUR(creation) as hour,
            DAYOFWEEK(creation) as dow,
            COUNT(*) as count
        FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s
        GROUP BY HOUR(creation), DAYOFWEEK(creation)
        ORDER BY dow, hour
    """, (start_date,), as_dict=True)

    # Build 7x24 matrix (dow 1=Sun, 7=Sat)
    matrix = [[0]*24 for _ in range(7)]
    for d in data:
        matrix[d.dow - 1][d.hour] = d.count

    # Also flat hourly totals
    hourly = [0]*24
    for d in data:
        hourly[d.hour] += d.count

    return {
        "matrix": matrix,
        "hourly_totals": hourly,
        "day_labels": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    }


@frappe.whitelist()
def get_user_details(user):
    """Individual user stats."""
    _check_admin()
    if not user:
        frappe.throw(_("User is required"))

    stats = frappe.db.sql("""
        SELECT
            COUNT(*) as requests,
            COUNT(DISTINCT conversation) as conversations,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(COALESCE(cost, token_cost, 0)), 0) as cost,
            MIN(creation) as first_active,
            MAX(creation) as last_active
        FROM `tabNiv Usage Log`
        WHERE user = %s
    """, (user,), as_dict=True)[0]

    daily = frappe.db.sql("""
        SELECT DATE(creation) as date, COUNT(*) as requests,
            COALESCE(SUM(total_tokens), 0) as tokens
        FROM `tabNiv Usage Log`
        WHERE user = %s AND DATE(creation) >= %s
        GROUP BY DATE(creation) ORDER BY date ASC
    """, (user, add_days(getdate(), -30)), as_dict=True)

    models = frappe.db.sql("""
        SELECT COALESCE(model, 'unknown') as model, COUNT(*) as count,
            COALESCE(SUM(total_tokens), 0) as tokens
        FROM `tabNiv Usage Log` WHERE user = %s
        GROUP BY model ORDER BY tokens DESC
    """, (user,), as_dict=True)

    # Wallet info
    wallet = frappe.db.get_value("Niv Wallet", {"user": user},
        ["balance", "total_used", "current_plan"], as_dict=True)

    return {
        "user": user,
        "full_name": frappe.db.get_value("User", user, "full_name") or user,
        "stats": {
            "requests": stats.requests,
            "conversations": stats.conversations,
            "total_tokens": stats.total_tokens,
            "input_tokens": stats.input_tokens,
            "output_tokens": stats.output_tokens,
            "cost": flt(stats.cost, 2),
            "first_active": str(stats.first_active) if stats.first_active else None,
            "last_active": str(stats.last_active) if stats.last_active else None,
        },
        "daily_usage": [{"date": str(d.date), "requests": d.requests, "tokens": d.tokens} for d in daily],
        "model_usage": [{"model": d.model, "count": d.count, "tokens": d.tokens} for d in models],
        "wallet": wallet or {},
    }


@frappe.whitelist()
def export_usage_csv(from_date=None, to_date=None):
    """Export usage data as CSV. Returns CSV string."""
    _check_admin()

    from_date = from_date or str(add_days(getdate(), -30))
    to_date = to_date or str(getdate())

    data = frappe.db.sql("""
        SELECT
            l.user, l.conversation, l.model, l.tool_name,
            l.input_tokens, l.output_tokens, l.total_tokens,
            COALESCE(l.cost, l.token_cost, 0) as cost,
            l.creation as timestamp
        FROM `tabNiv Usage Log` l
        WHERE DATE(l.creation) >= %s AND DATE(l.creation) <= %s
        ORDER BY l.creation DESC
    """, (from_date, to_date), as_dict=True)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User", "Conversation", "Model", "Tool", "Input Tokens",
                     "Output Tokens", "Total Tokens", "Cost", "Timestamp"])
    for row in data:
        writer.writerow([
            row.user, row.conversation, row.model, row.tool_name,
            row.input_tokens, row.output_tokens, row.total_tokens,
            row.cost, str(row.timestamp),
        ])

    return output.getvalue()


@frappe.whitelist()
def get_my_usage():
    """Current user's own stats."""
    user = frappe.session.user
    today = getdate()
    month_ago = add_days(today, -30)

    stats = frappe.db.sql("""
        SELECT
            COUNT(*) as total_requests,
            COUNT(DISTINCT conversation) as conversations,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(COALESCE(cost, token_cost, 0)), 0) as cost
        FROM `tabNiv Usage Log`
        WHERE user = %s
    """, (user,), as_dict=True)[0]

    today_stats = frappe.db.sql("""
        SELECT COUNT(*) as requests, COALESCE(SUM(total_tokens), 0) as tokens
        FROM `tabNiv Usage Log`
        WHERE user = %s AND DATE(creation) = %s
    """, (user, today), as_dict=True)[0]

    daily = frappe.db.sql("""
        SELECT DATE(creation) as date, COUNT(*) as requests,
            COALESCE(SUM(total_tokens), 0) as tokens
        FROM `tabNiv Usage Log`
        WHERE user = %s AND DATE(creation) >= %s
        GROUP BY DATE(creation) ORDER BY date ASC
    """, (user, month_ago), as_dict=True)

    # Wallet
    wallet = frappe.db.get_value("Niv Wallet", {"user": user},
        ["balance", "total_used", "current_plan", "plan_expiry"], as_dict=True)

    return {
        "user": user,
        "total_requests": stats.total_requests,
        "conversations": stats.conversations,
        "total_tokens": stats.total_tokens,
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
        "cost": flt(stats.cost, 2),
        "today_requests": today_stats.requests,
        "today_tokens": today_stats.tokens,
        "daily_usage": [{"date": str(d.date), "requests": d.requests, "tokens": d.tokens} for d in daily],
        "wallet": wallet or {},
    }


# ── Keep existing admin functions ──

@frappe.whitelist()
def allocate_tokens(user, tokens, reason=None):
    """Allocate tokens to a user's wallet (Admin only)"""
    _check_admin()

    tokens = flt(tokens)
    if tokens <= 0:
        frappe.throw(_("Token amount must be positive"))

    from niv_ai.niv_billing.api.billing import get_or_create_wallet
    wallet = get_or_create_wallet(user)
    wallet.balance += tokens
    wallet.last_recharged = now_datetime()
    wallet.save(ignore_permissions=True)

    frappe.get_doc({
        "doctype": "Niv Recharge",
        "user": user,
        "tokens": int(tokens),
        "transaction_type": "allocation",
        "remarks": reason or "Admin allocation",
        "balance_after": wallet.balance,
    }).insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "success": True,
        "user": user,
        "allocated": tokens,
        "new_balance": wallet.balance,
    }


@frappe.whitelist()
def bulk_allocate(users=None, tokens=0, plan=None, reason=None):
    """Allocate tokens to multiple users or all users on a plan"""
    _check_admin()

    tokens = flt(tokens)
    if tokens <= 0:
        frappe.throw(_("Token amount must be positive"))

    if isinstance(users, str):
        users = json.loads(users)

    if not users and plan:
        wallets = frappe.get_all("Niv Wallet", filters={"current_plan": plan}, fields=["user"])
        users = [w.user for w in wallets]

    if not users:
        frappe.throw(_("No users specified"))

    results = []
    for user in users:
        try:
            result = allocate_tokens(user, tokens, reason or "Bulk allocation")
            results.append(result)
        except Exception as e:
            results.append({"user": user, "success": False, "error": str(e)})

    return {
        "total": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results,
    }


@frappe.whitelist()
def get_all_wallets(page=1, page_size=50, sort_by="balance", sort_order="DESC"):
    """Get all user wallets (Admin only)"""
    _check_admin()

    page = int(page)
    page_size = min(int(page_size), 100)
    offset = (page - 1) * page_size

    valid_sort_fields = ["balance", "total_used", "creation", "modified", "user"]
    if sort_by not in valid_sort_fields:
        sort_by = "balance"
    sort_order = "ASC" if sort_order.upper() == "ASC" else "DESC"

    wallets = frappe.get_all(
        "Niv Wallet",
        fields=["name", "user", "balance", "total_used", "total_allocated",
                "current_plan", "plan_expiry", "last_recharged", "creation"],
        order_by=f"{sort_by} {sort_order}",
        limit_start=offset,
        limit_page_length=page_size,
    )

    total = frappe.db.count("Niv Wallet")

    stats = frappe.db.sql("""
        SELECT
            COUNT(*) as total_wallets,
            COALESCE(SUM(balance), 0) as total_balance,
            COALESCE(SUM(total_used), 0) as total_used,
            COALESCE(AVG(balance), 0) as avg_balance
        FROM `tabNiv Wallet`
    """, as_dict=True)[0]

    return {
        "wallets": wallets,
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": stats,
    }


@frappe.whitelist()
def sync_balances():
    """Recalculate all wallet balances from recharge and usage logs (Admin only)"""
    _check_admin()

    wallets = frappe.get_all("Niv Wallet", fields=["name", "user"])
    updated = 0

    for w in wallets:
        recharged = frappe.db.sql("""
            SELECT COALESCE(SUM(tokens), 0) as total
            FROM `tabNiv Recharge` WHERE user = %s
        """, w.user, as_dict=True)[0].total

        used = frappe.db.sql("""
            SELECT COALESCE(SUM(total_tokens), 0) as total
            FROM `tabNiv Usage Log` WHERE user = %s
        """, w.user, as_dict=True)[0].total

        new_balance = flt(recharged) - flt(used)
        wallet = frappe.get_doc("Niv Wallet", w.name)
        if flt(wallet.balance) != new_balance:
            wallet.balance = max(new_balance, 0)
            wallet.total_used = flt(used)
            wallet.save(ignore_permissions=True)
            updated += 1

    frappe.db.commit()

    return {
        "success": True,
        "total_wallets": len(wallets),
        "updated": updated,
    }
