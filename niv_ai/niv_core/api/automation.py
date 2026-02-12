import frappe
import json
import requests
from datetime import date, datetime


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def on_doc_event(doc, method):
    """Generic doc event handler - called for all doctypes"""
    # Map method name to event type
    event_map = {
        "before_save": "before_save",
        "on_update": "on_update",
        "before_submit": "before_submit",
        "on_submit": "on_submit",
        "before_cancel": "before_cancel",
        "on_cancel": "on_cancel",
        "on_trash": "on_trash",
        "after_insert": "after_insert",
    }

    # Extract event from method path
    event = None
    for key in event_map:
        if key in method:
            event = event_map[key]
            break

    if not event:
        return

    try:
        check_auto_actions(doc, event)
    except Exception as e:
        frappe.log_error(f"Auto action error for {doc.doctype} {doc.name}: {str(e)}", "Niv Auto Action Error")

    # Niv AI Triggers — run AI agent on doc events
    try:
        from niv_ai.niv_core.trigger_engine import run_triggers
        run_triggers(doc, event)
    except Exception as e:
        frappe.log_error(f"Niv Trigger error for {doc.doctype} {doc.name}: {str(e)}", "Niv AI Trigger Error")


def check_auto_actions(doc, event):
    """Check if any auto actions match this doc event"""
    actions = frappe.get_all(
        "Niv Auto Action",
        filters={
            "trigger_doctype": doc.doctype,
            "trigger_event": event,
            "is_active": 1,
        },
        fields=["name", "title", "condition", "ai_prompt", "notification_user"],
    )

    if not actions:
        return

    for action in actions:
        try:
            # Evaluate condition if present
            if action.condition and action.condition.strip():
                # Safe eval context
                context = {"doc": doc, "frappe": frappe}
                condition_result = frappe.safe_eval(action.condition, eval_locals=context)
                if not condition_result:
                    continue

            # Condition matched (or no condition) - execute
            frappe.enqueue(
                "niv_ai.niv_core.api.automation.execute_auto_action",
                queue="short",
                action_name=action.name,
                doctype=doc.doctype,
                docname=doc.name,
            )
        except Exception as e:
            frappe.log_error(
                f"Auto action condition error [{action.name}]: {str(e)}",
                "Niv Auto Action Error",
            )


def execute_auto_action(action_name, doctype, docname):
    """Execute an auto action - sends prompt to AI and creates notification"""
    action = frappe.get_doc("Niv Auto Action", action_name)
    doc = frappe.get_doc(doctype, docname)

    settings = frappe.get_single("Niv Settings")
    provider_name = settings.default_provider
    if not provider_name:
        frappe.log_error("No AI provider configured for auto actions", "Niv Auto Action")
        return

    provider = frappe.get_doc("Niv AI Provider", provider_name)
    model = settings.default_model or provider.default_model

    # Build prompt with doc context
    doc_data = doc.as_dict()
    # Remove internal fields
    clean_data = {k: v for k, v in doc_data.items()
                  if not k.startswith("_") and k not in ("docstatus", "idx", "doctype")}

    prompt = action.ai_prompt or f"Summarize this {doctype} document."
    prompt = prompt.replace("{doctype}", doctype).replace("{name}", docname)

    messages = [
        {
            "role": "system",
            "content": f"You are analyzing a {doctype} document for an automated action. Be concise and actionable.",
        },
        {
            "role": "user",
            "content": f"{prompt}\n\nDocument data:\n```json\n{json.dumps(clean_data, cls=DateTimeEncoder, indent=2)[:4000]}\n```",
        },
    ]

    try:
        headers = {
            "Authorization": f"Bearer {provider.get_password('api_key')}",
            "Content-Type": "application/json",
        }
        if provider.headers_json:
            try:
                headers.update(json.loads(provider.headers_json))
            except json.JSONDecodeError:
                pass

        resp = requests.post(
            f"{provider.base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": 1000,
            },
            timeout=60,
        )

        if resp.status_code != 200:
            frappe.log_error(f"AI API error in auto action: {resp.text[:300]}", "Niv Auto Action")
            return

        result = resp.json()
        ai_response = result["choices"][0]["message"]["content"]

        # Create notification
        notification_user = action.notification_user or "Administrator"
        notification = frappe.get_doc({
            "doctype": "Notification Log",
            "subject": f"🤖 Niv AI: {action.title or 'Auto Action'} - {doctype} {docname}",
            "email_content": ai_response,
            "for_user": notification_user,
            "type": "Alert",
            "document_type": doctype,
            "document_name": docname,
        })
        notification.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Auto action execution error [{action_name}]: {str(e)}", "Niv Auto Action")


@frappe.whitelist()
def run_daily_auto_actions():
    """Run daily scheduled auto actions"""
    actions = frappe.get_all(
        "Niv Auto Action",
        filters={
            "trigger_event": "daily",
            "is_active": 1,
        },
        fields=["name", "title", "trigger_doctype", "condition", "ai_prompt", "notification_user"],
    )

    for action in actions:
        try:
            frappe.enqueue(
                "niv_ai.niv_core.api.automation._execute_daily_action",
                queue="short",
                action_name=action.name,
            )
        except Exception as e:
            frappe.log_error(f"Daily auto action error [{action.name}]: {str(e)}", "Niv Auto Action")


def _execute_daily_action(action_name):
    """Execute a daily auto action"""
    action = frappe.get_doc("Niv Auto Action", action_name)
    settings = frappe.get_single("Niv Settings")
    provider_name = settings.default_provider
    if not provider_name:
        return

    provider = frappe.get_doc("Niv AI Provider", provider_name)
    model = settings.default_model or provider.default_model

    prompt = action.ai_prompt or f"Provide a daily summary for {action.trigger_doctype}."

    messages = [
        {"role": "system", "content": "You are providing a daily automated report. Be concise."},
        {"role": "user", "content": prompt},
    ]

    try:
        headers = {
            "Authorization": f"Bearer {provider.get_password('api_key')}",
            "Content-Type": "application/json",
        }
        if provider.headers_json:
            try:
                headers.update(json.loads(provider.headers_json))
            except json.JSONDecodeError:
                pass

        resp = requests.post(
            f"{provider.base_url}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": 1000},
            timeout=60,
        )

        if resp.status_code != 200:
            return

        ai_response = resp.json()["choices"][0]["message"]["content"]
        notification_user = action.notification_user or "Administrator"

        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": f"🤖 Niv AI Daily: {action.title or action.trigger_doctype}",
            "email_content": ai_response,
            "for_user": notification_user,
            "type": "Alert",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Daily auto action error [{action_name}]: {str(e)}", "Niv Auto Action")
