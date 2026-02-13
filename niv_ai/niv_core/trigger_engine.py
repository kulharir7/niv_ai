# Copyright (c) 2026, Niv AI
# Trigger Engine — runs AI agent when document events fire

import json
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from frappe.utils import now_datetime

try:
    from frappe.utils.safe_exec import safe_eval, get_safe_globals
except ImportError:
    # Frappe v14 fallback
    from frappe import safe_eval
    from frappe.utils.safe_exec import get_safe_globals


def run_triggers(doc, event):
    """Called from hooks.py doc_events. Checks all matching triggers and enqueues AI runs."""
    from niv_ai.niv_core.doctype.niv_trigger.niv_trigger import get_triggers_for_event
    
    triggers = get_triggers_for_event(doc.doctype, event)
    if not triggers:
        return
    
    for trigger in triggers:
        try:
            _process_trigger(doc, trigger, event)
        except Exception as e:
            frappe.log_error(
                "Niv Trigger Error: {} - {}".format(trigger.get("name"), str(e)),
                "Niv AI Trigger"
            )


def _process_trigger(doc, trigger, event):
    """Process a single trigger — check condition, build prompt, enqueue."""
    # Check condition if set
    condition = trigger.get("condition")
    if condition:
        try:
            safe_globals = get_safe_globals()
            safe_globals["doc"] = doc
            result = safe_eval(condition, safe_globals)
            if not result:
                return  # Condition not met
        except Exception as e:
            frappe.log_error(
                "Trigger condition error: {} - {}".format(trigger.get("name"), str(e)),
                "Niv AI Trigger"
            )
            return
    
    # Prevent duplicate runs (lock for 30 seconds)
    lock_key = "niv_trigger:{}:{}:{}:{}".format(
        trigger.get("name"), doc.doctype, doc.name, event
    )
    if frappe.cache().get_value(lock_key):
        return
    frappe.cache().set_value(lock_key, "1", expires_in_sec=30)
    
    # Build prompt from template
    prompt = _build_prompt(doc, trigger)
    
    # Enqueue background job
    frappe.enqueue(
        _execute_trigger,
        queue="long",
        job_name="niv-trigger-{}-{}-{}".format(trigger.get("name"), doc.doctype, doc.name),
        trigger_name=trigger.get("name"),
        doctype=doc.doctype,
        docname=doc.name,
        prompt=prompt,
        system_prompt_name=trigger.get("system_prompt"),
        model=trigger.get("model"),
        user=frappe.session.user,
    )


def _build_prompt(doc, trigger):
    """Build the AI prompt from template + document data."""
    template = trigger.get("prompt_template", "")
    
    # Simple {doc.fieldname} replacement
    try:
        doc_dict = doc.as_dict() if hasattr(doc, "as_dict") else doc
        
        # Replace {doc.fieldname} patterns
        import re
        def replace_field(match):
            field = match.group(1)
            val = doc_dict.get(field, "")
            return str(val) if val is not None else ""
        
        prompt = re.sub(r'\{doc\.(\w+)\}', replace_field, template)
    except Exception:
        prompt = template
    
    # Append document JSON if enabled
    if trigger.get("include_document_data"):
        try:
            clean_doc = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
            # Remove internal fields
            for key in ["_user_tags", "_comments", "_assign", "_liked_by", "docstatus", "password"]:
                clean_doc.pop(key, None)
            prompt += "\n\nDocument Data:\n```json\n{}\n```".format(
                json.dumps(clean_doc, indent=2, default=str)
            )
        except Exception:
            pass
    
    return prompt


def _execute_trigger(trigger_name, doctype, docname, prompt, system_prompt_name=None, model=None, user=None):
    """Background job: Run AI agent for a trigger."""
    try:
        frappe.set_user(user or "Administrator")
        
        # Get or create a trigger conversation
        conv_name = _get_trigger_conversation(trigger_name, doctype, docname)
        
        # Build system prompt
        system_prompt = None
        if system_prompt_name:
            try:
                sp_doc = frappe.get_doc("Niv System Prompt", system_prompt_name)
                system_prompt = sp_doc.prompt
            except Exception:
                pass
        
        if not system_prompt:
            system_prompt = (
                "You are Niv AI running as an automated trigger. "
                "A document event has fired and you need to process it. "
                "Use your available tools to inspect, validate, or act on the document. "
                "Be concise in your response. If you find issues, explain them clearly."
            )
        
        # Run agent directly (non-streaming for background)
        settings = get_niv_settings()
        provider_name = settings.default_provider
        model_name = model or settings.default_model
        
        from niv_ai.niv_core.langchain.agent import run_agent
        response = run_agent(
            message=prompt,
            conversation_id=conv_name,
            provider_name=provider_name,
            model=model_name,
            user=user or "Administrator",
            system_prompt=system_prompt,
        )
        result = {"response": response}
        
        # Update trigger stats
        frappe.db.set_value("Niv Trigger", trigger_name, {
            "last_triggered": now_datetime(),
            "trigger_count": frappe.db.get_value("Niv Trigger", trigger_name, "trigger_count") + 1
        })
        frappe.db.commit()
        
        # Add AI response as Comment on the document
        response = result.get("response", "") if isinstance(result, dict) else str(result)
        if response:
            try:
                frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Info",
                    "reference_doctype": doctype,
                    "reference_name": docname,
                    "content": "<b>🤖 Niv AI Trigger ({}):</b><br>{}".format(
                        trigger_name, response[:500]
                    ),
                }).insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                pass
        
    except Exception as e:
        frappe.log_error(
            "Trigger execution failed: {} - {}".format(trigger_name, str(e)),
            "Niv AI Trigger"
        )


def _get_trigger_conversation(trigger_name, doctype, docname):
    """Get or create a conversation for trigger runs."""
    conv_title = "Trigger: {} - {} {}".format(trigger_name, doctype, docname)
    
    # Check if conversation exists
    existing = frappe.db.get_value(
        "Niv Conversation",
        {"title": conv_title, "owner": "Administrator"},
        "name"
    )
    if existing:
        return existing
    
    # Create new conversation
    conv = frappe.get_doc({
        "doctype": "Niv Conversation",
        "title": conv_title,
    })
    conv.insert(ignore_permissions=True)
    frappe.db.commit()
    return conv.name
