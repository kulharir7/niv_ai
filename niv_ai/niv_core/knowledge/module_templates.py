"""
Module Templates — Pre-built blueprints for common ERPNext modules.
AI uses these as reference when user asks to create a complete module.
Injected into dev system prompt alongside dev_quick_reference.
"""

MODULE_TEMPLATES = """
=== MODULE TEMPLATES (BLUEPRINTS) ===

When user asks to create a complete module/system, follow this pattern:
1. Show the blueprint FIRST — list all components
2. Get user approval
3. Build step by step, showing progress
4. Test each component after creation

--- TEMPLATE: BASIC CRUD MODULE ---
Use when: User wants a simple master DocType with list/form view.
Components:
- 1 DocType (5-10 fields)
- 1 Print Format
- Permissions (System Manager + custom role)
Example prompt: "Customer Feedback DocType banao"

DocType pattern:
{
    "name": "<ModuleName>",
    "module": "Custom",
    "custom": 1,
    "naming_rule": "By \"Naming Series\" field",
    "autoname": "naming_series:",
    "fields": [
        {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "PREFIX-.#####", "reqd": 1, "hidden": 1, "default": "PREFIX-.#####"},
        {"fieldname": "title_field", "fieldtype": "Data", "label": "Title", "reqd": 1, "in_list_view": 1},
        {"fieldname": "sb_details", "fieldtype": "Section Break", "label": "Details"},
        {"fieldname": "description", "fieldtype": "Text Editor", "label": "Description"},
        {"fieldname": "cb1", "fieldtype": "Column Break"},
        {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Open\\nIn Progress\\nCompleted\\nCancelled", "default": "Open", "in_list_view": 1},
        {"fieldname": "date", "fieldtype": "Date", "label": "Date", "default": "Today"},
        {"fieldname": "assigned_to", "fieldtype": "Link", "label": "Assigned To", "options": "User"}
    ],
    "permissions": [
        {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 0}
    ]
}

--- TEMPLATE: MASTER-DETAIL (Parent + Child Table) ---
Use when: User wants a transactional document with line items.
Components:
- 1 Parent DocType (submittable)
- 1 Child DocType (line items table)
- 1 Workflow (optional)
- 1 Print Format
Example prompts: "Purchase Request banao", "Expense Claim form chahiye"

Parent DocType must have:
- naming_series (auto-numbering)
- Company link (for multi-company)
- Status field
- Total/Grand Total (Currency, read_only, calculated)
- items table (Table field linking to child)
- amended_from (Link to self, for amendment)

Child DocType must have:
- parent, parenttype, parentfield (auto by Frappe)
- item_code or description (Data)
- qty (Float/Int)
- rate (Currency)
- amount (Currency, formula: qty * rate)

Submittable DocType: set "is_submittable": 1
Then states are: Draft(0) → Submitted(1) → Cancelled(2)

--- TEMPLATE: APPROVAL WORKFLOW ---
Use when: User wants maker-checker or multi-level approval.
Components:
- 1 DocType (with status/workflow_state fields)
- 1 Workflow (states + transitions)
- 2-3 Notifications (email alerts)
- Custom roles if needed
Example: "Leave Application with 2-level approval"

Standard approval workflow pattern:
States: Draft → Pending Approval → Approved / Rejected
Roles: Maker (creates), Checker (approves/rejects)

Workflow JSON pattern:
{
    "workflow_name": "<Name> Approval",
    "document_type": "<DocType>",
    "is_active": 1,
    "workflow_state_field": "workflow_state",
    "states": [
        {"state": "Draft", "doc_status": "0", "allow_edit": "<MakerRole>", "is_optional_state": 0},
        {"state": "Pending Approval", "doc_status": "0", "allow_edit": "<CheckerRole>"},
        {"state": "Approved", "doc_status": "1", "allow_edit": "<CheckerRole>", "update_field": "status", "update_value": "Approved"},
        {"state": "Rejected", "doc_status": "0", "allow_edit": "<MakerRole>", "update_field": "status", "update_value": "Rejected"}
    ],
    "transitions": [
        {"state": "Draft", "action": "Submit for Approval", "next_state": "Pending Approval", "allowed": "<MakerRole>"},
        {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "<CheckerRole>", "condition": ""},
        {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "<CheckerRole>"},
        {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "<MakerRole>"}
    ]
}

IMPORTANT: DocType must have a "workflow_state" field (Select type) for workflow to work.
Add it as Custom Field if modifying existing DocType.

--- TEMPLATE: REPORT MODULE ---
Use when: User wants analytics/reports.
Components:
- 1 Script Report (for complex queries)
- OR 1 Report Builder (for simple filters)
- Dashboard Chart (optional)
Example: "Monthly sales report chahiye"

Script Report pattern:
{
    "name": "<Report Name>",
    "report_type": "Script Report",
    "ref_doctype": "<Main DocType>",
    "is_standard": "No",
    "module": "Custom",
    "report_script": "result = frappe.db.sql('''\\n    SELECT name, customer, grand_total, transaction_date\\n    FROM `tabSales Order`\\n    WHERE transaction_date BETWEEN %(from_date)s AND %(to_date)s\\n    ORDER BY grand_total DESC\\n''', filters, as_dict=1)\\ndata = result\\ncolumns = [\\n    {'fieldname': 'name', 'label': 'Sales Order', 'fieldtype': 'Link', 'options': 'Sales Order', 'width': 150},\\n    {'fieldname': 'customer', 'label': 'Customer', 'fieldtype': 'Link', 'options': 'Customer', 'width': 200},\\n    {'fieldname': 'grand_total', 'label': 'Amount', 'fieldtype': 'Currency', 'width': 120},\\n    {'fieldname': 'transaction_date', 'label': 'Date', 'fieldtype': 'Date', 'width': 120}\\n]",
    "filters": [
        {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date", "mandatory": 1, "default": "Today - 30d"},
        {"fieldname": "to_date", "label": "To Date", "fieldtype": "Date", "mandatory": 1, "default": "Today"}
    ]
}

--- TEMPLATE: NOTIFICATION SYSTEM ---
Use when: User wants alerts/emails on events.
Components:
- 1+ Notification records
- Subject template (Jinja)
- Message template (Jinja)
Example: "High value order pe alert chahiye"

Common notification events:
- "New": when document is created
- "Save": when document is saved
- "Submit": when document is submitted
- "Value Change": when specific field changes
- "Days Before/After": scheduled relative to date field

Notification JSON:
{
    "name": "<Alert Name>",
    "document_type": "<DocType>",
    "event": "Save",
    "condition": "doc.grand_total > 100000",
    "channel": "System Notification",
    "recipients": [{"receiver_by_document_field": "owner"}],
    "subject": "Alert: {{ doc.name }} - {{ doc.grand_total }}",
    "message": "Document {{ doc.name }} needs attention.\\nAmount: {{ frappe.utils.fmt_money(doc.grand_total) }}"
}

--- TEMPLATE: API INTEGRATION ---
Use when: User wants external API connection.
Components:
- 1 Server Script (API type)
- 1 DocType for config/logs (optional)
Example: "SMS notification API connect karo"

Server Script (API type):
{
    "script_type": "API",
    "api_method": "send_sms",
    "allow_guest": 0,
    "script": "import requests\\nphone = frappe.form_dict.get('phone')\\nmessage = frappe.form_dict.get('message')\\n# API call here\\nfrappe.response['message'] = {'status': 'sent'}"
}
Call via: /api/method/send_sms?phone=123&message=hello

--- TEMPLATE: DASHBOARD ---
Use when: User wants visual overview.
Components:
- 1 Number Card per metric
- 1-3 Dashboard Charts
- 1 Dashboard (groups charts together)

Number Card:
{
    "name": "Total Sales Orders",
    "document_type": "Sales Order",
    "function": "Count",
    "is_standard": 0,
    "filters_json": "[[\\"Sales Order\\",\\"docstatus\\",\\"=\\",1]]"
}

Dashboard Chart:
{
    "name": "Monthly Sales",
    "chart_type": "Count",
    "document_type": "Sales Order",
    "based_on": "transaction_date",
    "time_interval": "Monthly",
    "timespan": "Last Year",
    "filters_json": "[[\\"Sales Order\\",\\"docstatus\\",\\"=\\",1]]",
    "type": "Bar"
}

=== SMART FIELD SUGGESTIONS ===

When creating a new DocType, ALWAYS suggest these standard fields based on context:

FOR ANY DocType:
- naming_series (if transactional)
- status (Select: Open/In Progress/Completed/Cancelled)
- company (Link: Company) — for multi-company
- amended_from (Link: self) — if submittable

FOR PERSON/CONTACT DocType (Customer, Employee, Applicant):
- full_name (Data, mandatory)
- email (Data, options: Email)
- phone / mobile_no (Data, options: Phone)
- gender (Select: Male/Female/Other)
- date_of_birth (Date)
- address (Link: Address) or address fields inline
- image (Attach Image) — for photo

FOR FINANCIAL DocType (Invoice, Payment, Loan):
- posting_date (Date, default: Today)
- company (Link: Company, mandatory)
- currency (Link: Currency)
- exchange_rate (Float, default: 1)
- total_amount / grand_total (Currency, read_only)
- outstanding_amount (Currency, read_only)
- paid_amount (Currency)
- payment_terms (Link: Payment Terms Template)

FOR INVENTORY DocType (Stock Entry, Delivery):
- item_code (Link: Item, mandatory)
- warehouse (Link: Warehouse)
- qty (Float, mandatory)
- rate (Currency)
- amount (Currency, formula)
- uom (Link: UOM)
- batch_no (Link: Batch)
- serial_no (Small Text)

FOR APPROVAL DocType:
- workflow_state (Select) — required for Workflow
- approval_status (Select: Pending/Approved/Rejected)
- approved_by (Link: User, read_only)
- approval_date (Date, read_only)
- remarks (Small Text)

FOR LINKING TO EXISTING DocTypes:
- customer (Link: Customer)
- supplier (Link: Supplier)
- employee (Link: Employee)
- project (Link: Project)
- cost_center (Link: Cost Center)

=== DOCUMENT FLOW MAP ===

ERPNext standard flows — AI must understand these connections:

SELLING FLOW:
Lead → Opportunity → Quotation → Sales Order → Delivery Note → Sales Invoice → Payment Entry
                                  └→ Sales Invoice (direct)
                                  └→ Work Order (manufacturing)

BUYING FLOW:
Material Request → Supplier Quotation → Purchase Order → Purchase Receipt → Purchase Invoice → Payment Entry

STOCK FLOW:
Purchase Receipt → Stock Entry (Material Receipt)
Delivery Note → Stock Entry (Material Issue)
Stock Reconciliation (adjustments)
Stock Entry types: Material Receipt, Material Issue, Material Transfer, Manufacture, Repack

MANUFACTURING FLOW:
BOM (Bill of Materials) → Work Order → Stock Entry (Manufacture) → Quality Inspection

HR FLOW:
Job Opening → Job Applicant → Employee → Attendance → Salary Structure → Salary Slip → Journal Entry

ACCOUNTING FLOW:
Journal Entry, Payment Entry → GL Entry (auto)
Sales Invoice / Purchase Invoice → GL Entry (auto)
Period Closing Voucher (year end)

PROJECT FLOW:
Project → Task → Timesheet → Salary Slip / Sales Invoice

CRM FLOW:
Lead → Opportunity → Quotation → Sales Order
Lead Source, Campaign, Territory tracking

=== BLUEPRINT OUTPUT FORMAT ===

When showing a blueprint to user, use this format:

📋 BLUEPRINT: <Module Name>

📦 DocTypes (<count>):
├─ <DocType 1> — <brief description>
├─ <DocType 2> — <brief description>
└─ <Child DocType> — (child of <Parent>)

🔄 Workflows (<count>):
├─ <Workflow 1>: <State1> → <State2> → <State3>
└─ <Workflow 2>: <State1> → <State2>

📊 Reports (<count>):
├─ <Report 1> — <what it shows>
└─ <Report 2> — <what it shows>

⚡ Server Scripts (<count>):
├─ <Script 1> — <what it does>
└─ <Script 2> — <what it does>

📧 Notifications (<count>):
└─ <Notification 1> — <trigger>

🖨️ Print Formats (<count>):
└─ <Format 1> — for <DocType>

Estimated build time: ~<X> minutes
Shall I proceed? (yes/no/modify)
"""


FIELD_TYPE_GUIDE = """
=== WHEN TO USE WHICH FIELD TYPE ===

Data: Short text (name, title, code) — max 140 chars
Small Text: Medium text (notes, remarks) — no formatting
Text: Long text — no formatting
Text Editor: Rich text with formatting (HTML)
Long Text: Very long plain text
Code: Source code with syntax highlighting

Int: Whole numbers (quantity in pieces)
Float: Decimal numbers (rates, percentages)  
Currency: Money amounts — auto-formats with currency symbol
Percent: 0-100 percentage values

Date: Date only (posting_date, due_date)
Datetime: Date + Time (exact timestamps)
Time: Time only (check_in_time)
Duration: Time duration (hours:minutes)

Link: Reference to another DocType (most common relationship)
Dynamic Link: Reference where target DocType is variable
Table: Child table (one-to-many relationship)
Table MultiSelect: Many-to-many via link table

Select: Dropdown with fixed options (status, type, category)
Check: Boolean (yes/no, true/false, 0/1)
Rating: Star rating (0-1 decimal, displayed as stars)
Color: Color picker

Attach: File upload (any file)
Attach Image: Image upload (with preview)
Image: Display image from URL/field

Section Break: Visual section divider
Column Break: Start new column (2-column layout)
Tab Break: New tab in form view

Read Only: Display-only field (calculated values)
HTML: Raw HTML content
Geolocation: Map coordinates
Barcode: Barcode/QR display
Password: Encrypted field
"""
