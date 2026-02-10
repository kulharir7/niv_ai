import frappe
import json
import re


def send_email(to, subject, body, cc=None, confirmed=False):
    """
    Send an email. If not confirmed, creates a draft first and asks for confirmation.
    Call again with confirmed=True to actually send.
    """
    # Validate email addresses
    to_list = [e.strip() for e in to.split(",") if e.strip()]
    for email in to_list:
        if not _is_valid_email(email):
            return {"error": f"Invalid email address: {email}"}

    cc_list = []
    if cc:
        cc_list = [e.strip() for e in cc.split(",") if e.strip()]
        for email in cc_list:
            if not _is_valid_email(email):
                return {"error": f"Invalid CC email address: {email}"}

    if not confirmed:
        # Create draft and ask for confirmation
        draft = draft_email(to, subject, body, cc)
        return {
            "status": "draft_created",
            "draft_name": draft.get("name"),
            "message": f"📧 Draft email created.\n\nTo: {to}\nSubject: {subject}\n\nPlease confirm to send this email.",
            "requires_confirmation": True,
        }

    # Actually send
    try:
        frappe.sendmail(
            recipients=to_list,
            cc=cc_list if cc_list else None,
            subject=subject,
            message=body,
            now=True,
        )
        return {
            "success": True,
            "message": f"✅ Email sent to {to}",
        }
    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}"}


def draft_email(to, subject, body, cc=None):
    """Create a Communication document as a draft email."""
    doc = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Email",
        "sent_or_received": "Sent",
        "subject": subject,
        "content": body,
        "recipients": to,
        "cc": cc or "",
        "sender": frappe.session.user,
        "email_status": "Draft",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "name": doc.name,
        "message": f"Draft email created: {doc.name}",
    }


def get_recent_emails(limit=10):
    """Fetch recent email Communications."""
    limit = min(int(limit), 50)

    emails = frappe.get_all(
        "Communication",
        filters={
            "communication_medium": "Email",
            "communication_type": "Communication",
        },
        fields=["name", "subject", "sender", "recipients", "sent_or_received",
                "creation", "email_status", "content"],
        order_by="creation DESC",
        limit_page_length=limit,
    )

    # Truncate content for readability
    for e in emails:
        if e.get("content"):
            e["content"] = e["content"][:500]

    return {
        "count": len(emails),
        "emails": emails,
    }


def search_emails(query, limit=10):
    """Search in Communication doctype for emails."""
    limit = min(int(limit), 50)
    if not query:
        return {"error": "Query is required"}

    emails = frappe.get_all(
        "Communication",
        filters={
            "communication_medium": "Email",
            "communication_type": "Communication",
        },
        or_filters={
            "subject": ["like", f"%{query}%"],
            "content": ["like", f"%{query}%"],
            "sender": ["like", f"%{query}%"],
            "recipients": ["like", f"%{query}%"],
        },
        fields=["name", "subject", "sender", "recipients", "sent_or_received",
                "creation", "email_status"],
        order_by="creation DESC",
        limit_page_length=limit,
    )

    return {
        "count": len(emails),
        "query": query,
        "emails": emails,
    }


def _is_valid_email(email):
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))
