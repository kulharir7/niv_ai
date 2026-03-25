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


@frappe.whitelist()
def get_ai_insights(days=30):
    """AI-generated daily insights about usage patterns."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)
    today = getdate()
    yesterday = add_days(today, -1)

    # Gather data for AI
    today_stats = frappe.db.sql("""
        SELECT COUNT(*) as requests, COALESCE(SUM(total_tokens), 0) as tokens,
               COUNT(DISTINCT user) as users
        FROM `tabNiv Usage Log` WHERE DATE(creation) = %s
    """, (today,), as_dict=True)[0]

    yesterday_stats = frappe.db.sql("""
        SELECT COUNT(*) as requests, COALESCE(SUM(total_tokens), 0) as tokens,
               COUNT(DISTINCT user) as users
        FROM `tabNiv Usage Log` WHERE DATE(creation) = %s
    """, (yesterday,), as_dict=True)[0]

    # Top user today
    top_user = frappe.db.sql("""
        SELECT l.user, u.full_name, COUNT(*) as cnt
        FROM `tabNiv Usage Log` l
        LEFT JOIN `tabUser` u ON u.name = l.user
        WHERE DATE(l.creation) = %s
        GROUP BY l.user, u.full_name ORDER BY cnt DESC LIMIT 1
    """, (today,), as_dict=True)

    # Most used tool today
    top_tool = frappe.db.sql("""
        SELECT tool_name, COUNT(*) as cnt FROM `tabNiv Usage Log`
        WHERE DATE(creation) = %s AND tool_name IS NOT NULL AND tool_name != ''
        GROUP BY tool_name ORDER BY cnt DESC LIMIT 1
    """, (today,), as_dict=True)

    # Error rate today
    total_tool_calls = frappe.db.sql("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) as errors
        FROM `tabNiv Tool Log` WHERE DATE(creation) = %s
    """, (today,), as_dict=True)[0]

    # Build insights
    insights = []

    # Usage trend
    if yesterday_stats.requests > 0:
        change = round(((today_stats.requests - yesterday_stats.requests) / yesterday_stats.requests) * 100)
        if change > 0:
            insights.append({"icon": "📈", "text": f"Usage is up {change}% today vs yesterday ({today_stats.requests} vs {yesterday_stats.requests} requests)"})
        elif change < 0:
            insights.append({"icon": "📉", "text": f"Usage is down {abs(change)}% today vs yesterday ({today_stats.requests} vs {yesterday_stats.requests} requests)"})
        else:
            insights.append({"icon": "➡️", "text": f"Usage same as yesterday — {today_stats.requests} requests"})
    else:
        insights.append({"icon": "📊", "text": f"Today: {today_stats.requests} requests from {today_stats.users} users"})

    # Top user
    if top_user:
        insights.append({"icon": "👤", "text": f"Most active: {top_user[0].full_name or top_user[0].user} ({top_user[0].cnt} queries)"})

    # Top tool
    if top_tool:
        insights.append({"icon": "🔧", "text": f"Most used tool: {top_tool[0].tool_name} ({top_tool[0].cnt} calls)"})

    # Error rate
    if total_tool_calls.total and total_tool_calls.total > 0:
        error_rate = round((total_tool_calls.errors or 0) / total_tool_calls.total * 100, 1)
        if error_rate > 20:
            insights.append({"icon": "⚠️", "text": f"High error rate: {error_rate}% tool calls failing — check logs"})
        elif error_rate > 0:
            insights.append({"icon": "✅", "text": f"Tool success rate: {100 - error_rate}%"})

    # Token usage
    insights.append({"icon": "🔤", "text": f"Tokens used today: {today_stats.tokens:,}"})

    return {"insights": insights, "generated_at": str(now_datetime())}


@frappe.whitelist()
def get_response_times(days=30):
    """Average response time data from tool logs."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    # Daily average response time
    daily = frappe.db.sql("""
        SELECT DATE(creation) as date,
               ROUND(AVG(execution_time_ms), 0) as avg_ms,
               ROUND(MAX(execution_time_ms), 0) as max_ms,
               ROUND(MIN(execution_time_ms), 0) as min_ms,
               COUNT(*) as count
        FROM `tabNiv Tool Log`
        WHERE DATE(creation) >= %s
        GROUP BY DATE(creation) ORDER BY date ASC
    """, (start_date,), as_dict=True)

    # Overall stats
    overall = frappe.db.sql("""
        SELECT ROUND(AVG(execution_time_ms), 0) as avg_ms,
               ROUND(MAX(execution_time_ms), 0) as max_ms,
               ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms), 0) as p95_ms
        FROM `tabNiv Tool Log`
        WHERE DATE(creation) >= %s
    """, (start_date,), as_dict=True)

    # Fallback if PERCENTILE not supported
    if not overall or overall[0].avg_ms is None:
        overall = frappe.db.sql("""
            SELECT ROUND(AVG(execution_time_ms), 0) as avg_ms,
                   ROUND(MAX(execution_time_ms), 0) as max_ms
            FROM `tabNiv Tool Log`
            WHERE DATE(creation) >= %s
        """, (start_date,), as_dict=True)

    # Slowest queries
    slowest = frappe.db.sql("""
        SELECT tool as tool_name, execution_time_ms, DATE(creation) as date,
               SUBSTRING(parameters_json, 1, 100) as params
        FROM `tabNiv Tool Log`
        WHERE DATE(creation) >= %s
        ORDER BY execution_time_ms DESC LIMIT 5
    """, (start_date,), as_dict=True)

    return {
        "daily": [{"date": str(d.date), "avg_ms": d.avg_ms, "max_ms": d.max_ms, "count": d.count} for d in daily],
        "overall": {
            "avg_ms": overall[0].avg_ms if overall else 0,
            "max_ms": overall[0].max_ms if overall else 0,
        },
        "slowest": [{"tool": s.tool_name, "ms": s.execution_time_ms, "date": str(s.date)} for s in slowest],
    }


@frappe.whitelist()
def get_satisfaction_stats(days=30):
    """User satisfaction from message reactions."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    messages = frappe.db.sql("""
        SELECT reactions_json FROM `tabNiv Message`
        WHERE role = 'assistant' AND reactions_json IS NOT NULL
        AND reactions_json != '' AND reactions_json != '{}'
        AND DATE(creation) >= %s
    """, (start_date,), as_dict=True)

    thumbs_up = 0
    thumbs_down = 0
    for m in messages:
        try:
            reactions = json.loads(m.reactions_json)
            for user, reaction in reactions.items():
                if reaction in ("up", "like", "thumbsup", "👍"):
                    thumbs_up += 1
                elif reaction in ("down", "dislike", "thumbsdown", "👎"):
                    thumbs_down += 1
        except (json.JSONDecodeError, AttributeError):
            pass

    total = thumbs_up + thumbs_down
    score = round((thumbs_up / total) * 100, 1) if total > 0 else 0

    # Daily trend
    daily = frappe.db.sql("""
        SELECT DATE(creation) as date, reactions_json
        FROM `tabNiv Message`
        WHERE role = 'assistant' AND reactions_json IS NOT NULL
        AND reactions_json != '' AND reactions_json != '{}'
        AND DATE(creation) >= %s
        ORDER BY date ASC
    """, (start_date,), as_dict=True)

    daily_map = {}
    for d in daily:
        dt = str(d.date)
        if dt not in daily_map:
            daily_map[dt] = {"up": 0, "down": 0}
        try:
            reactions = json.loads(d.reactions_json)
            for user, reaction in reactions.items():
                if reaction in ("up", "like", "thumbsup", "👍"):
                    daily_map[dt]["up"] += 1
                elif reaction in ("down", "dislike", "thumbsdown", "👎"):
                    daily_map[dt]["down"] += 1
        except Exception:
            pass

    return {
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "total_rated": total,
        "satisfaction_pct": score,
        "daily": [{"date": k, "up": v["up"], "down": v["down"]} for k, v in sorted(daily_map.items())],
    }


@frappe.whitelist()
def get_popular_questions(days=30, limit=10):
    """Most common query patterns."""
    _check_admin()
    days = int(days or 30)
    limit = int(limit or 10)
    start_date = add_days(getdate(), -days)

    # Get user messages
    messages = frappe.db.sql("""
        SELECT content FROM `tabNiv Message`
        WHERE role = 'user' AND DATE(creation) >= %s
        AND content IS NOT NULL AND content != ''
        ORDER BY creation DESC LIMIT 500
    """, (start_date,), as_dict=True)

    # Simple keyword extraction — count common phrases
    from collections import Counter
    word_counter = Counter()
    question_types = Counter()

    for m in messages:
        text = (m.content or "").lower().strip()
        if not text:
            continue

        # Categorize
        if any(w in text for w in ["list", "show", "dikhao", "batao", "all"]):
            question_types["List/Show Data"] += 1
        elif any(w in text for w in ["how many", "count", "kitne", "total"]):
            question_types["Count/Total"] += 1
        elif any(w in text for w in ["create", "make", "banao", "add"]):
            question_types["Create/Add"] += 1
        elif any(w in text for w in ["report", "summary", "analysis"]):
            question_types["Reports"] += 1
        elif any(w in text for w in ["status", "details", "info"]):
            question_types["Status/Details"] += 1
        elif any(w in text for w in ["update", "change", "modify", "edit"]):
            question_types["Update/Modify"] += 1
        elif any(w in text for w in ["delete", "remove", "hatao"]):
            question_types["Delete"] += 1
        elif any(w in text for w in ["help", "how", "kaise"]):
            question_types["Help/How-to"] += 1
        else:
            question_types["Other"] += 1

        # Extract key words (skip common words)
        skip = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for",
                "and", "or", "me", "my", "i", "you", "it", "this", "that", "mujhe",
                "ka", "ke", "ki", "ko", "se", "hai", "hain", "ye", "wo", "kya",
                "please", "show", "list", "get", "all"}
        words = text.split()
        for w in words:
            w = w.strip(".,!?;:'\"()[]{}").lower()
            if w and len(w) > 2 and w not in skip:
                word_counter[w] += 1

    return {
        "question_types": [{"type": k, "count": v} for k, v in question_types.most_common(limit)],
        "top_words": [{"word": k, "count": v} for k, v in word_counter.most_common(20)],
        "total_messages": len(messages),
    }


@frappe.whitelist()
def get_ai_recommendations(days=30):
    """Smart recommendations based on usage data."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)
    today = getdate()

    recommendations = []

    # 1. Check users hitting daily limits
    try:
        settings = frappe.get_single("Niv Settings")
        daily_limit = getattr(settings, "per_user_daily_limit", 0) or 0
        if daily_limit:
            heavy_users = frappe.db.sql("""
                SELECT user, SUM(total_tokens) as tokens
                FROM `tabNiv Usage Log`
                WHERE DATE(creation) = %s
                GROUP BY user HAVING tokens > %s * 0.8
            """, (today, daily_limit), as_dict=True)
            if heavy_users:
                recommendations.append({
                    "type": "warning",
                    "icon": "⚠️",
                    "text": f"{len(heavy_users)} user(s) near daily token limit — consider increasing limit",
                })
    except Exception:
        pass

    # 2. Check tool failure rate
    tool_stats = frappe.db.sql("""
        SELECT tool as tool_name,
               COUNT(*) as total,
               SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) as errors
        FROM `tabNiv Tool Log`
        WHERE DATE(creation) >= %s
        GROUP BY tool
        HAVING errors > 0
        ORDER BY errors DESC LIMIT 5
    """, (start_date,), as_dict=True)

    for t in tool_stats:
        error_rate = round((t.errors / t.total) * 100, 1) if t.total else 0
        if error_rate > 25:
            recommendations.append({
                "type": "danger",
                "icon": "🔴",
                "text": f"Tool '{t.tool_name}' failing {error_rate}% ({t.errors}/{t.total}) — check permissions or arguments",
            })

    # 3. Check pool balance burn rate
    try:
        settings = frappe.get_single("Niv Settings")
        if settings.billing_mode == "Shared Pool":
            balance = settings.shared_pool_balance or 0
            daily_avg = frappe.db.sql("""
                SELECT COALESCE(AVG(daily_tokens), 0) as avg_daily FROM (
                    SELECT DATE(creation) as dt, SUM(total_tokens) as daily_tokens
                    FROM `tabNiv Usage Log`
                    WHERE DATE(creation) >= %s
                    GROUP BY DATE(creation)
                ) sub
            """, (add_days(today, -7),), as_dict=True)[0].avg_daily

            if daily_avg > 0:
                days_left = int(balance / daily_avg)
                if days_left < 7:
                    recommendations.append({
                        "type": "danger",
                        "icon": "🔴",
                        "text": f"Token pool will run out in ~{days_left} days at current rate — recharge soon!",
                    })
                elif days_left < 30:
                    recommendations.append({
                        "type": "warning",
                        "icon": "🟡",
                        "text": f"Token pool lasts ~{days_left} days at current usage rate",
                    })
                else:
                    recommendations.append({
                        "type": "info",
                        "icon": "✅",
                        "text": f"Token pool healthy — ~{days_left} days remaining",
                    })
    except Exception:
        pass

    # 4. Inactive users
    inactive = frappe.db.sql("""
        SELECT COUNT(DISTINCT user) as cnt FROM `tabNiv Conversation`
        WHERE user NOT IN (
            SELECT DISTINCT user FROM `tabNiv Usage Log` WHERE DATE(creation) >= %s
        )
    """, (add_days(today, -7),), as_dict=True)[0].cnt

    if inactive > 0:
        recommendations.append({
            "type": "info",
            "icon": "💤",
            "text": f"{inactive} users haven't used AI in 7+ days",
        })

    # 5. Weekend activity
    weekend = frappe.db.sql("""
        SELECT COUNT(*) as cnt FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s AND DAYOFWEEK(creation) IN (1, 7)
    """, (start_date,), as_dict=True)[0].cnt

    weekday = frappe.db.sql("""
        SELECT COUNT(*) as cnt FROM `tabNiv Usage Log`
        WHERE DATE(creation) >= %s AND DAYOFWEEK(creation) NOT IN (1, 7)
    """, (start_date,), as_dict=True)[0].cnt

    if weekend == 0 and weekday > 0:
        recommendations.append({
            "type": "info",
            "icon": "📅",
            "text": "No weekend activity — consider scheduling automated reports for Monday",
        })

    return {"recommendations": recommendations, "generated_at": str(now_datetime())}


@frappe.whitelist()
def get_billing_overview(days=30):
    """Billing/pool overview with burn rate."""
    _check_admin()
    days = int(days or 30)
    today = getdate()

    settings = frappe.get_single("Niv Settings")
    billing_mode = settings.billing_mode or "Per User"

    result = {
        "billing_mode": billing_mode,
        "pool_balance": 0,
        "pool_used": 0,
        "burn_rate_daily": 0,
        "days_remaining": 0,
        "total_wallets": 0,
        "total_wallet_balance": 0,
        "per_user_costs": [],
    }

    if billing_mode == "Shared Pool":
        result["pool_balance"] = settings.shared_pool_balance or 0
        result["pool_used"] = settings.shared_pool_used or 0

        # Daily burn rate (last 7 days average)
        daily_usage = frappe.db.sql("""
            SELECT COALESCE(AVG(daily_tokens), 0) as avg_daily FROM (
                SELECT SUM(total_tokens) as daily_tokens
                FROM `tabNiv Usage Log`
                WHERE DATE(creation) >= %s
                GROUP BY DATE(creation)
            ) sub
        """, (add_days(today, -7),), as_dict=True)[0].avg_daily

        result["burn_rate_daily"] = round(daily_usage)
        result["days_remaining"] = int(result["pool_balance"] / daily_usage) if daily_usage > 0 else 999
    else:
        wallet_stats = frappe.db.sql("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(balance), 0) as total_balance
            FROM `tabNiv Wallet`
        """, as_dict=True)[0]
        result["total_wallets"] = wallet_stats.cnt
        result["total_wallet_balance"] = wallet_stats.total_balance

    # Per-user cost (top 5)
    per_user = frappe.db.sql("""
        SELECT l.user, u.full_name,
               COALESCE(SUM(l.total_tokens), 0) as tokens,
               COALESCE(SUM(COALESCE(l.cost, l.token_cost, 0)), 0) as cost
        FROM `tabNiv Usage Log` l
        LEFT JOIN `tabUser` u ON u.name = l.user
        WHERE DATE(l.creation) >= %s
        GROUP BY l.user, u.full_name
        ORDER BY tokens DESC LIMIT 5
    """, (add_days(today, -days),), as_dict=True)

    result["per_user_costs"] = [{"user": p.full_name or p.user, "tokens": p.tokens, "cost": flt(p.cost, 2)} for p in per_user]

    return result


@frappe.whitelist()
def get_conversation_quality(days=30):
    """Conversation quality metrics."""
    _check_admin()
    days = int(days or 30)
    start_date = add_days(getdate(), -days)

    # Avg messages per conversation
    avg_msgs = frappe.db.sql("""
        SELECT AVG(msg_count) as avg_msgs FROM (
            SELECT conversation, COUNT(*) as msg_count
            FROM `tabNiv Message`
            WHERE DATE(creation) >= %s
            GROUP BY conversation
        ) sub
    """, (start_date,), as_dict=True)[0].avg_msgs or 0

    # Tool success rate
    tool_stats = frappe.db.sql("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN is_error = 0 OR is_error IS NULL THEN 1 ELSE 0 END) as success
        FROM `tabNiv Tool Log`
        WHERE DATE(creation) >= %s
    """, (start_date,), as_dict=True)[0]

    tool_success_rate = round((tool_stats.success / tool_stats.total) * 100, 1) if tool_stats.total else 100

    # Empty/error response rate
    total_responses = frappe.db.sql("""
        SELECT COUNT(*) as total FROM `tabNiv Message`
        WHERE role = 'assistant' AND DATE(creation) >= %s
    """, (start_date,), as_dict=True)[0].total or 1

    error_responses = frappe.db.sql("""
        SELECT COUNT(*) as cnt FROM `tabNiv Message`
        WHERE role = 'assistant' AND DATE(creation) >= %s
        AND (content LIKE '%%Error:%%' OR content LIKE '%%could not%%' OR content LIKE '%%try again%%'
             OR content = '' OR content IS NULL)
    """, (start_date,), as_dict=True)[0].cnt or 0

    error_rate = round((error_responses / total_responses) * 100, 1)

    # Conversations with tool usage vs without
    with_tools = frappe.db.sql("""
        SELECT COUNT(DISTINCT conversation) as cnt FROM `tabNiv Tool Log`
        WHERE DATE(creation) >= %s
    """, (start_date,), as_dict=True)[0].cnt or 0

    total_convos = frappe.db.sql("""
        SELECT COUNT(DISTINCT conversation) as cnt FROM `tabNiv Message`
        WHERE DATE(creation) >= %s
    """, (start_date,), as_dict=True)[0].cnt or 1

    tool_usage_pct = round((with_tools / total_convos) * 100, 1)

    return {
        "avg_messages_per_convo": round(avg_msgs, 1),
        "tool_success_rate": tool_success_rate,
        "error_response_rate": error_rate,
        "tool_usage_pct": tool_usage_pct,
        "total_conversations": total_convos,
        "total_tool_calls": tool_stats.total or 0,
    }
