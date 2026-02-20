"""Script Templates for Niv AI Dev Mode.

Common Frappe Client Script and Server Script patterns.
LLM can use these as reference when generating scripts.

Usage in run_python_code:
    from niv_ai.niv_core.tools.script_templates import get_template, list_templates
"""

# Client Script templates
CLIENT_SCRIPTS = {
    "field_validation": {
        "title": "Field Validation",
        "description": "Validate a field value on save/change",
        "script_type": "Client Script",
        "dt": "",  # User specifies DocType
        "template": '''frappe.ui.form.on('{doctype}', {{
    validate: function(frm) {{
        if (frm.doc.{field} && !{validation}) {{
            frappe.throw(__('{error_message}'));
        }}
    }}
}});''',
        "example_args": {"doctype": "Customer", "field": "mobile_no", "validation": "/^[0-9]{10}$/.test(frm.doc.mobile_no)", "error_message": "Mobile number must be 10 digits"}
    },

    "auto_fetch": {
        "title": "Auto Fetch Field Value",
        "description": "Auto-fill a field when another field changes",
        "script_type": "Client Script",
        "template": '''frappe.ui.form.on('{doctype}', {{
    {trigger_field}: function(frm) {{
        if (frm.doc.{trigger_field}) {{
            frappe.db.get_value('{link_doctype}', frm.doc.{trigger_field}, '{fetch_field}', (r) => {{
                if (r) frm.set_value('{target_field}', r.{fetch_field});
            }});
        }}
    }}
}});''',
        "example_args": {"doctype": "Sales Order", "trigger_field": "customer", "link_doctype": "Customer", "fetch_field": "customer_group", "target_field": "customer_group"}
    },

    "hide_show_field": {
        "title": "Conditional Field Visibility",
        "description": "Show/hide fields based on another field value",
        "script_type": "Client Script",
        "template": '''frappe.ui.form.on('{doctype}', {{
    refresh: function(frm) {{
        frm.toggle_display('{target_field}', frm.doc.{condition_field} === '{condition_value}');
    }},
    {condition_field}: function(frm) {{
        frm.toggle_display('{target_field}', frm.doc.{condition_field} === '{condition_value}');
    }}
}});'''
    },

    "add_custom_button": {
        "title": "Custom Button on Form",
        "description": "Add a custom action button to a form",
        "script_type": "Client Script",
        "template": '''frappe.ui.form.on('{doctype}', {{
    refresh: function(frm) {{
        if (!frm.is_new()) {{
            frm.add_custom_button(__('{button_label}'), function() {{
                {action_code}
            }}, __('{group_label}'));
        }}
    }}
}});'''
    },

    "child_table_total": {
        "title": "Calculate Child Table Total",
        "description": "Auto-calculate total from child table rows",
        "script_type": "Client Script",
        "template": '''frappe.ui.form.on('{child_doctype}', {{
    {amount_field}: function(frm, cdt, cdn) {{
        _calculate_total(frm);
    }},
    {child_table}_remove: function(frm) {{
        _calculate_total(frm);
    }}
}});

function _calculate_total(frm) {{
    let total = 0;
    (frm.doc.{child_table} || []).forEach(row => {{
        total += flt(row.{amount_field});
    }});
    frm.set_value('{total_field}', total);
}}'''
    }
}

# Server Script templates
SERVER_SCRIPTS = {
    "before_save_validation": {
        "title": "Before Save Validation",
        "description": "Validate document before saving",
        "script_type": "Server Script",
        "event": "Before Save",
        "template": '''# Server Script: Before Save on {doctype}
if doc.{field} {condition}:
    frappe.throw("{error_message}")
'''
    },

    "after_insert_action": {
        "title": "After Insert Action",
        "description": "Perform action after new document is created",
        "script_type": "Server Script",
        "event": "After Insert",
        "template": '''# Server Script: After Insert on {doctype}
# Example: Send notification, create linked document, update counter
{action_code}
frappe.db.commit()
'''
    },

    "api_endpoint": {
        "title": "Custom API Endpoint",
        "description": "Create a whitelisted API endpoint",
        "script_type": "Server Script",
        "event": "API",
        "template": '''# API Server Script
# Access via: /api/method/{api_name}
{api_code}
frappe.response["message"] = result
'''
    },

    "scheduled_task": {
        "title": "Scheduled Task (Cron)",
        "description": "Run a task on schedule",
        "script_type": "Server Script",
        "event": "Cron",
        "template": '''# Cron Server Script: {description}
# Frequency: {frequency}
{task_code}
frappe.db.commit()
'''
    }
}


def list_templates() -> dict:
    """List all available script templates."""
    result = {"client_scripts": {}, "server_scripts": {}}
    for key, tpl in CLIENT_SCRIPTS.items():
        result["client_scripts"][key] = {"title": tpl["title"], "description": tpl["description"]}
    for key, tpl in SERVER_SCRIPTS.items():
        result["server_scripts"][key] = {"title": tpl["title"], "description": tpl["description"]}
    return result


def get_template(template_name: str, **kwargs) -> dict:
    """Get a script template with optional variable substitution.
    
    Args:
        template_name: Template key (e.g., 'field_validation', 'auto_fetch')
        **kwargs: Template variables to substitute
    
    Returns:
        dict with 'script', 'script_type', 'title'
    """
    tpl = CLIENT_SCRIPTS.get(template_name) or SERVER_SCRIPTS.get(template_name)
    if not tpl:
        return {"error": f"Template '{template_name}' not found. Available: {list(CLIENT_SCRIPTS.keys()) + list(SERVER_SCRIPTS.keys())}"}
    
    script = tpl["template"]
    if kwargs:
        try:
            script = script.format(**kwargs)
        except KeyError as e:
            return {"error": f"Missing template variable: {e}", "required": [k for k in script.split('{') if '}' in k]}
    
    return {
        "title": tpl["title"],
        "script_type": tpl.get("script_type", "Client Script"),
        "event": tpl.get("event", ""),
        "script": script,
        "example_args": tpl.get("example_args", {})
    }
