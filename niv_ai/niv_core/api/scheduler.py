import frappe
import json
from datetime import datetime, timedelta


def run_scheduled_reports():
    """
    Called by scheduler (daily). Finds due reports and runs them.
    """
    now = frappe.utils.now_datetime()
    today = now.date()
    current_time = now.time()
    day_name = now.strftime("%A")  # e.g., "Monday"

    reports = frappe.get_all(
        "Niv Scheduled Report",
        filters={"is_active": 1},
        fields=["name", "user", "report_prompt", "schedule", "day_of_week",
                "time", "last_run", "conversation"],
    )

    for report in reports:
        if not _is_due(report, today, day_name, current_time):
            continue

        try:
            _execute_report(report)
        except Exception as e:
            frappe.log_error(
                f"Scheduled report {report.name} failed: {e}",
                "Niv Scheduled Report Error"
            )


def _is_due(report, today, day_name, current_time):
    """Check if a report is due to run."""
    # If already run today, skip
    if report.last_run:
        last_run_date = frappe.utils.get_datetime(report.last_run).date()
        if last_run_date == today:
            return False

    schedule = report.schedule

    if schedule == "Daily":
        return True

    if schedule == "Weekly":
        return report.day_of_week == day_name

    if schedule == "Monthly":
        # Run on 1st of each month
        return today.day == 1

    return False


def _execute_report(report):
    """Execute a scheduled report: create/use conversation, send prompt, save response."""
    from niv_ai.niv_core.api.chat import send_message

    user = report.user
    conversation_id = report.conversation

    # Create or reuse conversation
    if not conversation_id or not frappe.db.exists("Niv Conversation", conversation_id):
        conv = frappe.get_doc({
            "doctype": "Niv Conversation",
            "user": user,
            "title": f"Scheduled: {report.report_prompt[:40]}...",
        })
        conv.insert(ignore_permissions=True)
        conversation_id = conv.name
        frappe.db.set_value("Niv Scheduled Report", report.name, "conversation", conversation_id)

    # Execute as the report's user
    frappe.set_user(user)
    try:
        result = send_message(
            conversation_id=conversation_id,
            message=report.report_prompt,
        )
    finally:
        frappe.set_user("Administrator")

    # Update last_run
    frappe.db.set_value("Niv Scheduled Report", report.name, "last_run", frappe.utils.now_datetime())
    frappe.db.commit()

    return result


@frappe.whitelist()
def create_scheduled_report(prompt, schedule="Daily", time="08:00:00", day_of_week=None):
    """Create a scheduled report for the current user."""
    user = frappe.session.user

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
        "name": doc.name,
        "message": f"Scheduled report created: {schedule} at {time}",
    }
