"""Daily Digest for Niv AI.

Convenience wrapper around Scheduled Reports for daily business summaries.
Usage: Create via Niv AI chat: "Set up a daily digest at 9 AM"
Or via run_python_code:
    from niv_ai.niv_core.tools.daily_digest import setup_daily_digest, get_digest_status
"""
import frappe


# Default digest prompts for different business types
DIGEST_TEMPLATES = {
    "nbfc": (
        "Give me today's business summary in a table format:\n"
        "1. Total loan disbursements today (count and amount)\n"
        "2. Total collections today (count and amount)\n"
        "3. Overdue loans count and total overdue amount\n"
        "4. New loan applications received today\n"
        "5. NPA status summary (Standard, Sub-Standard, Doubtful, Loss counts)\n"
        "6. Top 5 branches by collection today\n"
        "Keep it concise. Use tables for numbers."
    ),
    "general": (
        "Give me today's business summary:\n"
        "1. New orders/transactions today\n"
        "2. Revenue collected today\n"
        "3. Pending approvals\n"
        "4. Overdue items\n"
        "5. Key metrics vs yesterday\n"
        "Keep it concise with tables."
    ),
    "sales": (
        "Give me today's sales summary:\n"
        "1. New Sales Orders today (count and total)\n"
        "2. Invoices raised today\n"
        "3. Payments received today\n"
        "4. Overdue invoices count and amount\n"
        "5. Top 5 customers by order value this week\n"
    ),
}


@frappe.whitelist()
def setup_daily_digest(
    template: str = "nbfc",
    custom_prompt: str = None,
    time: str = "09:00:00",
    schedule: str = "Daily",
    day_of_week: str = None
) -> dict:
    """Set up a daily digest for the current user.
    
    Args:
        template: Digest template ('nbfc', 'general', 'sales') or use custom_prompt
        custom_prompt: Custom digest prompt (overrides template)
        time: Time to send digest (HH:MM:SS format)
        schedule: 'Daily', 'Weekly', or 'Monthly'
        day_of_week: Required for Weekly schedule (e.g., 'Monday')
    
    Returns:
        dict with created report info
    """
    user = frappe.session.user
    prompt = custom_prompt or DIGEST_TEMPLATES.get(template, DIGEST_TEMPLATES["general"])
    
    # Check if user already has a daily digest
    existing = frappe.get_all("Niv Scheduled Report", 
        filters={"user": user, "is_active": 1, "report_prompt": ["like", "%summary%"]},
        limit=1)
    
    if existing:
        return {
            "status": "exists",
            "name": existing[0].name,
            "message": "You already have an active daily digest. Use get_digest_status() to check or deactivate it first."
        }
    
    doc = frappe.get_doc({
        "doctype": "Niv Scheduled Report",
        "user": user,
        "report_prompt": prompt,
        "schedule": schedule,
        "time": time,
        "day_of_week": day_of_week or "",
        "is_active": 1,
    })
    doc.insert()
    frappe.db.commit()
    
    return {
        "status": "created",
        "name": doc.name,
        "message": f"Daily digest set up! You'll receive a business summary {schedule.lower()} at {time}.",
        "template": template if not custom_prompt else "custom",
        "schedule": schedule,
        "time": time
    }


@frappe.whitelist()
def get_digest_status() -> dict:
    """Get status of current user's daily digest(s)."""
    user = frappe.session.user
    
    reports = frappe.get_all("Niv Scheduled Report",
        filters={"user": user},
        fields=["name", "report_prompt", "schedule", "time", "is_active", "last_run", "day_of_week"],
        order_by="creation desc",
        limit=10)
    
    if not reports:
        return {"status": "none", "message": "No daily digest configured. Use setup_daily_digest() to create one."}
    
    return {
        "status": "active" if any(r.is_active for r in reports) else "inactive",
        "digests": [{
            "name": r.name,
            "prompt": r.report_prompt[:100] + "..." if len(r.report_prompt) > 100 else r.report_prompt,
            "schedule": r.schedule,
            "time": str(r.time),
            "active": bool(r.is_active),
            "last_run": str(r.last_run) if r.last_run else "Never"
        } for r in reports]
    }
