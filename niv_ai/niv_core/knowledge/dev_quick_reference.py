"""
Quick reference knowledge that gets injected directly into system prompt.
No embeddings needed — this is the condensed essential knowledge.
"""

DEV_QUICK_REFERENCE = """
=== CREATE_DOCUMENT QUICK REFERENCE ===

1. CUSTOM FIELD:
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",  # target DocType
    "fieldname": "custom_priority_level",  # MUST start with custom_
    "label": "Priority Level",
    "fieldtype": "Select",  # Data|Select|Link|Int|Currency|Date|Check|Text|Table|etc
    "options": "Low\\nMedium\\nHigh",  # \\n separated for Select
    "insert_after": "naming_series",  # position after this field
    "reqd": 0, "hidden": 0, "read_only": 0, "default": "Medium"
})
For Link: "fieldtype": "Link", "options": "Customer"  (options = target DocType)
For Table: "fieldtype": "Table", "options": "Child DocType Name"

2. CLIENT SCRIPT:
create_document(doctype="Client Script", data={
    "dt": "Sales Order",
    "script_type": "Form",  # Form|List
    "enabled": 1,
    "script": "frappe.ui.form.on('Sales Order', {\\n  refresh(frm) {\\n    // your code\\n  }\\n});"
})
Events: refresh, onload, validate, before_save, after_save, before_submit
frm.add_custom_button(), frm.set_query(), frm.set_value(), frappe.call()

3. SERVER SCRIPT:
create_document(doctype="Server Script", data={
    "script_type": "DocEvent",  # DocEvent|API|Scheduler Event
    "reference_doctype": "Sales Order",
    "doctype_event": "Before Save",  # Before Save|After Save|Before Submit|After Submit|Before Cancel|After Cancel|Before Delete
    "script": "if doc.grand_total > 100000:\\n    doc.flags.high_value = True",
    "enabled": 1
})
For API: script_type="API", api_method="custom_api_name"
Available in script: doc, frappe

4. PROPERTY SETTER (modify existing field):
create_document(doctype="Property Setter", data={
    "doc_type": "Sales Order",
    "field_name": "delivery_date",
    "property": "reqd",  # reqd|hidden|read_only|default|label|options|description
    "property_type": "Check",  # Check for 0/1, Data for text, Small Text for large
    "value": "1",  # always string
    "doctype_or_field": "DocField"  # DocField for field props, DocType for DocType props
})

5. WORKFLOW:
create_document(doctype="Workflow", data={
    "workflow_name": "SO Approval",
    "document_type": "Sales Order",
    "is_active": 1,
    "send_email_alert": 0,
    "states": [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Sales User"},
        {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Sales Manager"},
        {"state": "Approved", "doc_status": "1", "allow_edit": "Sales Manager"}
    ],
    "transitions": [
        {"state": "Draft", "action": "Submit for Approval", "next_state": "Pending Approval", "allowed": "Sales User"},
        {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Sales Manager"},
        {"state": "Pending Approval", "action": "Reject", "next_state": "Draft", "allowed": "Sales Manager"}
    ]
})

6. PRINT FORMAT:
create_document(doctype="Print Format", data={
    "name": "Custom SO Print",
    "doc_type": "Sales Order",
    "module": "Selling",
    "print_format_type": "Jinja",
    "custom_format": 1,
    "html": "<h1>{{ doc.name }}</h1>\\n<p>Customer: {{ doc.customer }}</p>\\n{% for item in doc.items %}\\n<p>{{ item.item_code }} - {{ item.qty }}</p>\\n{% endfor %}"
})

7. DOCTYPE (new):
create_document(doctype="DocType", data={
    "name": "Loan Application",
    "module": "Custom",
    "custom": 1,
    "naming_rule": "By fieldname",
    "autoname": "field:applicant_name",
    "fields": [
        {"fieldname": "applicant_name", "fieldtype": "Data", "label": "Applicant Name", "reqd": 1, "in_list_view": 1},
        {"fieldname": "loan_amount", "fieldtype": "Currency", "label": "Loan Amount", "reqd": 1},
        {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Open\\nApproved\\nRejected", "default": "Open"}
    ],
    "permissions": [
        {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
    ]
})
After DocType creation: bench migrate needed (creates DB table)

8. NOTIFICATION:
create_document(doctype="Notification", data={
    "name": "SO High Value Alert",
    "document_type": "Sales Order",
    "event": "Value Change",  # New|Save|Submit|Cancel|Days Before|Days After|Value Change|Method|Custom
    "value_changed": "grand_total",
    "condition": "doc.grand_total > 100000",
    "channel": "Email",  # Email|Slack|System Notification
    "recipients": [{"receiver_by_document_field": "owner"}],
    "subject": "High Value SO: {{ doc.name }}",
    "message": "Sales Order {{ doc.name }} has grand_total {{ doc.grand_total }}"
})

=== FIELD TYPES ===
Data, Select, Link, Int, Float, Currency, Date, Datetime, Time, Check (boolean),
Text, Small Text, Long Text, Text Editor, Code, HTML, Markdown Editor,
Table (child), Table MultiSelect, Attach, Attach Image, Color, Rating,
Geolocation, Duration, Password, Read Only, Section Break, Column Break, Tab Break

=== NAMING RULES ===
- "By fieldname": autoname="field:fieldname"
- "By Naming Series": autoname="naming_series:", add Naming Series field
- "Expression": autoname="format:PREFIX-{####}"
- "Hash": autoname="hash" (random)
- "Prompt": autoname="prompt" (user enters name)

=== NO MIGRATE NEEDED ===
Custom Field, Property Setter, Client Script, Server Script, Workflow,
Print Format, Notification — all apply INSTANTLY.
Only new DocType creation needs bench migrate.
"""
