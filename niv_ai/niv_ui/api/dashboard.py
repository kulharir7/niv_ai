"""
AI Dashboard API — Auto-discovers system, generates dynamic insights.
Zero hardcoded DocTypes. Works on any Frappe site.
"""
import json
import frappe
from frappe import _
from datetime import datetime, timedelta


@frappe.whitelist()
def get_dashboard_data():
    """Master endpoint — returns all dashboard data dynamically."""
    user = frappe.session.user
    
    return {
        "system_overview": get_system_overview(),
        "top_doctypes": get_top_doctypes(),
        "recent_activity": get_recent_activity(),
        "user_stats": get_user_stats(user),
        "growth_data": get_growth_data(),
        "ai_health": get_ai_health(),
    }


@frappe.whitelist()
def get_system_overview():
    """Auto-discover system stats — total docs, users, activity."""
    try:
        total_users = frappe.db.count("User", {"enabled": 1, "user_type": "System User"})
    except Exception:
        total_users = 0
    
    try:
        total_docs = 0
        # Get top DocTypes by count (skip system/internal ones)
        skip_modules = ("Core", "Email", "Printing", "Website", "Desk", "Custom", "Integrations", "Data Migration")
        skip_doctypes = ("DocType", "DocField", "DocPerm", "Module Def", "Translation",
                         "File", "Comment", "Activity Log", "Error Log", "Scheduled Job Log",
                         "Session Default", "Navbar Item", "Block Module", "Has Role",
                         "DefaultValue", "Version", "Communication", "Email Queue",
                         "Prepared Report", "Dashboard Chart", "Number Card")
        
        all_dts = frappe.get_all("DocType",
            filters={
                "istable": 0,
                "issingle": 0,
                "module": ("not in", skip_modules),
                "name": ("not in", skip_doctypes),
            },
            fields=["name", "module"],
            limit_page_length=500,
        )
        
        for dt in all_dts:
            try:
                c = frappe.db.count(dt["name"])
                total_docs += c
            except Exception:
                pass
    except Exception:
        total_docs = 0
    
    # Today's activity
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        today_created = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabVersion` WHERE DATE(creation) = %s", today
        )[0][0]
    except Exception:
        today_created = 0
    
    try:
        active_sessions = frappe.db.sql(
            "SELECT COUNT(DISTINCT user) FROM `tabActivity Log` WHERE DATE(creation) = %s",
            today
        )[0][0]
    except Exception:
        active_sessions = 0
    
    return {
        "total_users": total_users,
        "total_documents": total_docs,
        "today_changes": today_created,
        "active_today": active_sessions,
    }


@frappe.whitelist()
def get_top_doctypes(limit=10):
    """Get top DocTypes by document count — fully dynamic."""
    skip_modules = ("Core", "Email", "Printing", "Website", "Desk", "Custom", "Integrations", "Data Migration")
    skip_doctypes = ("DocType", "DocField", "DocPerm", "Module Def", "Translation",
                     "File", "Comment", "Activity Log", "Error Log", "Scheduled Job Log",
                     "Session Default", "Navbar Item", "Block Module", "Has Role",
                     "DefaultValue", "Version", "Communication", "Email Queue",
                     "Prepared Report", "Dashboard Chart", "Number Card",
                     "Niv Conversation", "Niv Message", "Niv AI Provider",
                     "Niv Settings", "Niv MCP Server", "Niv Token Ledger",
                     "Niv Billing Plan")
    
    all_dts = frappe.get_all("DocType",
        filters={
            "istable": 0,
            "issingle": 0,
            "module": ("not in", skip_modules),
            "name": ("not in", skip_doctypes),
        },
        fields=["name", "module"],
        limit_page_length=200,
    )
    
    results = []
    for dt in all_dts:
        try:
            count = frappe.db.count(dt["name"])
            if count > 0:
                # Get today's count
                try:
                    today = datetime.now().strftime("%Y-%m-%d")
                    today_count = frappe.db.count(dt["name"], {"creation": (">=", today)})
                except Exception:
                    today_count = 0
                
                results.append({
                    "doctype": dt["name"],
                    "module": dt["module"],
                    "count": count,
                    "today": today_count,
                })
        except Exception:
            pass
    
    results.sort(key=lambda x: x["count"], reverse=True)
    return results[:int(limit)]


@frappe.whitelist()
def get_recent_activity(limit=15):
    """Get recent system activity — auto-detect what changed."""
    try:
        activities = frappe.db.sql("""
            SELECT 
                v.docname, v.ref_doctype, v.owner, v.creation,
                CASE 
                    WHEN v.creation = v.modified THEN 'Created'
                    ELSE 'Modified'
                END as action_type
            FROM `tabVersion` v
            WHERE v.ref_doctype NOT IN ('Session Default', 'Activity Log', 'Error Log', 
                'Scheduled Job Log', 'Comment', 'Communication', 'Email Queue',
                'Niv Message', 'Niv Conversation', 'Niv Token Ledger')
            ORDER BY v.creation DESC
            LIMIT %s
        """, limit, as_dict=True)
        
        for a in activities:
            a["time_ago"] = frappe.utils.pretty_date(a["creation"])
            a["user_fullname"] = frappe.db.get_value("User", a["owner"], "full_name") or a["owner"]
        
        return activities
    except Exception:
        return []


@frappe.whitelist()
def get_user_stats(user=None):
    """Current user's stats."""
    user = user or frappe.session.user
    
    try:
        ai_chats = frappe.db.count("Niv Conversation", {"user": user})
    except Exception:
        ai_chats = 0
    
    try:
        ai_messages = frappe.db.count("Niv Message", {"user": user})
    except Exception:
        ai_messages = 0
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        today_messages = frappe.db.count("Niv Message", {"user": user, "creation": (">=", today)})
    except Exception:
        today_messages = 0
    
    return {
        "total_chats": ai_chats,
        "total_messages": ai_messages,
        "today_messages": today_messages,
    }


@frappe.whitelist()
def get_growth_data(days=7):
    """Document creation trend — last N days."""
    days = int(days)
    data = []
    
    for i in range(days - 1, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_label = (datetime.now() - timedelta(days=i)).strftime("%a")
        
        try:
            count = frappe.db.sql(
                "SELECT COUNT(*) FROM `tabVersion` WHERE DATE(creation) = %s", date
            )[0][0]
        except Exception:
            count = 0
        
        data.append({"date": date, "day": day_label, "count": count})
    
    return data


@frappe.whitelist()
def get_ai_health():
    """AI system health — conversations, tokens, providers."""
    try:
        total_convs = frappe.db.count("Niv Conversation")
    except Exception:
        total_convs = 0
    
    try:
        total_msgs = frappe.db.count("Niv Message")
    except Exception:
        total_msgs = 0
    
    try:
        providers = frappe.get_all("Niv AI Provider", 
            filters={"enabled": 1}, 
            fields=["provider_name", "default_model"])
    except Exception:
        providers = []
    
    try:
        mcp_servers = frappe.get_all("Niv MCP Server",
            filters={"is_active": 1},
            fields=["server_name", "tool_count"])
    except Exception:
        mcp_servers = []
    
    total_tools = sum(int(s.get("tool_count", 0)) for s in mcp_servers)
    
    return {
        "total_conversations": total_convs,
        "total_messages": total_msgs,
        "active_providers": len(providers),
        "providers": providers,
        "mcp_servers": len(mcp_servers),
        "total_tools": total_tools,
    }


@frappe.whitelist()
def get_ai_summary():
    """Ask AI to generate a summary of system state — called on-demand."""
    from niv_ai.niv_core.utils import get_niv_settings
    
    # Gather context
    overview = get_system_overview()
    top_dts = get_top_doctypes(5)
    ai_health = get_ai_health()
    
    context = f"""System Overview:
- Total Users: {overview['total_users']}
- Total Documents: {overview['total_documents']:,}
- Changes Today: {overview['today_changes']}
- Active Users Today: {overview['active_today']}

Top Document Types:
"""
    for dt in top_dts:
        context += f"- {dt['doctype']}: {dt['count']:,} records (+{dt['today']} today)\n"
    
    context += f"""
AI System:
- Total Conversations: {ai_health['total_conversations']}
- Total Messages: {ai_health['total_messages']}
- Active Providers: {ai_health['active_providers']}
- MCP Tools: {ai_health['total_tools']}
"""
    
    prompt = f"""You are an AI business analyst. Analyze this system data and provide:
1. A 2-line executive summary
2. 3 key insights (emoji + one line each)
3. 1 recommendation

Be concise, professional, use numbers. Respond in the same language the system data suggests.

{context}"""
    
    try:
        from niv_ai.niv_core.langchain.llm import get_llm
        llm = get_llm(streaming=False)
        response = llm.invoke(prompt)
        return {"summary": response.content}
    except Exception as e:
        return {"summary": f"AI summary unavailable: {str(e)}"}
