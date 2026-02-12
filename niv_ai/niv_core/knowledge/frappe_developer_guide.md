# Frappe Developer RAG Knowledge Base
# Complete Reference for create_document Tool
# ============================================

This document is the comprehensive knowledge base for an AI chatbot that creates
Frappe/ERPNext documents using the `create_document(doctype, data)` tool.
All examples use EXACT field names and values that Frappe expects.

---

# ============================================================
# 1. DOCTYPE CREATION
# ============================================================

## 1.1 Basic DocType Structure

```python
create_document(doctype="DocType", data={
    "name": "Loan Application",
    "module": "Custom",
    "naming_rule": "By \"Naming Series\" field",
    "autoname": "naming_series:",
    "title_field": "applicant_name",
    "search_fields": "applicant_name, loan_type",
    "sort_field": "modified",
    "sort_order": "DESC",
    "image_field": "",
    "is_submittable": 0,
    "istable": 0,
    "is_tree": 0,
    "is_virtual": 0,
    "editable_grid": 1,
    "track_changes": 1,
    "allow_rename": 1,
    "custom": 1,
    "fields": [...],
    "permissions": [...]
})
```

## 1.2 All Field Types Reference

### Data Fields (Text Input)

| fieldtype | Description | options |
|-----------|-------------|---------|
| Data | Single-line text | options="Email", "Phone", "URL", "Barcode" for validation |
| Small Text | Multi-line, small | — |
| Text | Multi-line text | — |
| Long Text | Large text area | — |
| Text Editor | Rich text (HTML) | — |
| Code | Code editor | options="Python", "JavaScript", "HTML", "CSS", "JSON", "Markdown" |
| HTML | Static HTML display | — |
| HTML Editor | HTML editing | — |
| Markdown Editor | Markdown editing | — |
| Password | Masked input | — |
| Read Only | Display only | — |

### Number Fields

| fieldtype | Description | options |
|-----------|-------------|---------|
| Int | Integer | — |
| Float | Decimal number | — |
| Currency | Currency amount | options=fieldname_of_currency_field OR "Company:company:default_currency" |
| Percent | Percentage | — |
| Rating | Star rating (0-1) | — |
| Duration | Time duration | — |

### Date/Time Fields

| fieldtype | Description |
|-----------|-------------|
| Date | Date only |
| Datetime | Date and time |
| Time | Time only |

### Selection Fields

| fieldtype | Description | options |
|-----------|-------------|---------|
| Select | Dropdown | options="Option1\nOption2\nOption3" (newline separated) |
| Link | Foreign key reference | options="DocType Name" (e.g., "Customer", "Item") |
| Dynamic Link | Dynamic foreign key | options=fieldname_of_link_type_field |
| Table | Child table | options="Child DocType Name" |
| Table MultiSelect | Multi-select via child table | options="Child DocType Name" |
| Check | Boolean checkbox | — |
| Autocomplete | Text with autocomplete | options="Option1\nOption2" |

### File Fields

| fieldtype | Description |
|-----------|-------------|
| Attach | File attachment | 
| Attach Image | Image attachment |
| Image | Display image (from Attach Image field) |

### Layout Fields (no database column)

| fieldtype | Description |
|-----------|-------------|
| Section Break | Start new section |
| Column Break | Start new column within section |
| Tab Break | Start new tab |

### Special Fields

| fieldtype | Description | options |
|-----------|-------------|---------|
| Color | Color picker | — |
| Geolocation | Map coordinates | — |
| Signature | Signature pad | — |
| Heading | Display heading | — |
| Table MultiSelect | Multi-select link | options="Child DocType" |
| Icon | Icon picker | — |

## 1.3 Field Definition Structure

Every field in the `fields` array uses this structure:

```python
{
    "fieldname": "applicant_name",      # Snake_case, unique within DocType
    "fieldtype": "Data",                 # One of the types above
    "label": "Applicant Name",           # Display label
    "options": "",                        # Depends on fieldtype (see above)
    "reqd": 1,                           # 1 = mandatory, 0 = optional
    "read_only": 0,                      # 1 = read only
    "hidden": 0,                         # 1 = hidden
    "default": "",                       # Default value
    "description": "",                   # Help text below field
    "in_list_view": 1,                   # Show in list view
    "in_standard_filter": 1,             # Show in filter sidebar
    "in_preview": 0,                     # Show in preview
    "in_global_search": 0,              # Include in global search
    "bold": 0,                           # Bold in list view
    "unique": 0,                         # Unique constraint
    "no_copy": 0,                        # Don't copy on duplicate
    "allow_in_quick_entry": 0,           # Show in quick entry dialog
    "translatable": 0,                   # Allow translation
    "print_hide": 0,                     # Hide in print
    "report_hide": 0,                    # Hide in report
    "search_index": 0,                   # Database index
    "depends_on": "",                    # Conditional display: "eval:doc.status=='Active'"
    "mandatory_depends_on": "",          # Conditional mandatory
    "read_only_depends_on": "",          # Conditional read-only
    "fetch_from": "",                    # Auto-fetch: "customer.customer_name"
    "fetch_if_empty": 0,                 # Only fetch if field is empty
    "permlevel": 0,                      # Permission level (0-9)
    "columns": 0,                        # Column width in grid (1-10)
    "length": 0,                         # Max characters
    "precision": "",                     # Decimal precision for float/currency
    "non_negative": 0,                   # Prevent negative numbers
    "collapsible": 0,                    # For Section Break: collapsible
    "collapsible_depends_on": "",        # Conditional collapsible
    "is_virtual": 0                      # Virtual (computed) field
}
```

## 1.4 Naming Rules (autoname)

```python
# 1. Naming Series - User selects prefix
"naming_rule": "By \"Naming Series\" field",
"autoname": "naming_series:",
# Requires a naming_series field:
{"fieldname": "naming_series", "fieldtype": "Select", "label": "Series",
 "options": "LA-.YYYY.-.####\nLOAN-.####", "default": "LA-.YYYY.-.####",
 "reqd": 1, "no_copy": 1, "print_hide": 1}

# 2. Field value - name = value of a field
"naming_rule": "By fieldname",
"autoname": "field:employee_id",

# 3. Format string
"naming_rule": "Expression",
"autoname": "format:LA-{applicant_name}-{####}",

# 4. Expression (Python)
"naming_rule": "Expression",
"autoname": "format:LOAN-{YYYY}-{MM}-{####}",

# 5. Hash (random)
"naming_rule": "Random",
"autoname": "hash",

# 6. Autoincrement
"naming_rule": "Autoincrement",
"autoname": "autoincrement",

# 7. Prompt (user enters name)
"naming_rule": "Set by user",
"autoname": "Prompt",

# Naming series format codes:
# .YYYY. = 4-digit year     .YY. = 2-digit year
# .MM.   = 2-digit month    .DD. = 2-digit day
# .####  = 4-digit counter  .#####  = 5-digit counter
# Example: "INV-.YYYY.-.MM.-.#####" → INV-2024-01-00001
```

## 1.5 DocType Flags

```python
# Submittable DocType (has Submit/Cancel workflow, docstatus field)
"is_submittable": 1,
# doc_status: 0=Draft, 1=Submitted, 2=Cancelled

# Child Table DocType (embedded in parent)
"istable": 1,

# Tree DocType (hierarchical with parent-child)
"is_tree": 1,
# Automatically adds parent_doctype, lft, rgt, old_parent fields

# Virtual DocType (no database table, data from code)
"is_virtual": 1,

# Single DocType (only one record, like Settings)
"issingle": 1,
```

## 1.6 Permissions Structure

```python
"permissions": [
    {
        "role": "System Manager",
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "submit": 0,     # Only for is_submittable
        "cancel": 0,     # Only for is_submittable
        "amend": 0,      # Only for is_submittable
        "print": 1,
        "email": 1,
        "report": 1,
        "import": 1,
        "export": 1,
        "share": 1,
        "set_user_permissions": 0,
        "permlevel": 0    # Permission level this applies to
    },
    {
        "role": "Loan Manager",
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 0,
        "permlevel": 0
    }
]
```

## 1.7 Child DocType Creation

Child DocTypes MUST be created BEFORE the parent. They have `istable: 1`.

```python
# Step 1: Create the child DocType
create_document(doctype="DocType", data={
    "name": "Loan Guarantor",
    "module": "Custom",
    "custom": 1,
    "istable": 1,
    "editable_grid": 1,
    "fields": [
        {
            "fieldname": "guarantor_name",
            "fieldtype": "Data",
            "label": "Guarantor Name",
            "reqd": 1,
            "in_list_view": 1,
            "columns": 3
        },
        {
            "fieldname": "relationship",
            "fieldtype": "Select",
            "label": "Relationship",
            "options": "Spouse\nParent\nSibling\nFriend\nOther",
            "in_list_view": 1,
            "columns": 2
        },
        {
            "fieldname": "phone",
            "fieldtype": "Data",
            "label": "Phone",
            "options": "Phone",
            "in_list_view": 1,
            "columns": 2
        },
        {
            "fieldname": "guarantee_amount",
            "fieldtype": "Currency",
            "label": "Guarantee Amount",
            "options": "currency",
            "in_list_view": 1,
            "columns": 2
        },
        {
            "fieldname": "currency",
            "fieldtype": "Link",
            "label": "Currency",
            "options": "Currency",
            "hidden": 1
        },
        {
            "fieldname": "id_document",
            "fieldtype": "Attach",
            "label": "ID Document"
        }
    ]
})

# Step 2: Use in parent DocType
# In parent's fields array:
{
    "fieldname": "guarantors",
    "fieldtype": "Table",
    "label": "Guarantors",
    "options": "Loan Guarantor",    # Name of child DocType
    "reqd": 0
}
```

## 1.8 Section Break, Column Break, Tab Break

```python
# Tab Break - creates a new tab at the top
{
    "fieldname": "details_tab",
    "fieldtype": "Tab Break",
    "label": "Details"
}

# Section Break - horizontal section divider
{
    "fieldname": "personal_info_section",
    "fieldtype": "Section Break",
    "label": "Personal Information",
    "collapsible": 0     # 1 to make collapsible
}

# Column Break - splits section into columns
{
    "fieldname": "column_break_1",
    "fieldtype": "Column Break"
}

# Typical layout pattern:
# Tab Break → Section Break → Field, Field → Column Break → Field, Field
#           → Section Break → Field → Column Break → Field
# Tab Break → Section Break → Table field
```

## 1.9 COMPLETE EXAMPLE: Loan Application DocType

```python
# Step 1: Create child DocType for guarantors
create_document(doctype="DocType", data={
    "name": "Loan Application Guarantor",
    "module": "Custom",
    "custom": 1,
    "istable": 1,
    "editable_grid": 1,
    "fields": [
        {"fieldname": "guarantor_name", "fieldtype": "Data", "label": "Guarantor Name", "reqd": 1, "in_list_view": 1, "columns": 3},
        {"fieldname": "relationship", "fieldtype": "Select", "label": "Relationship", "options": "Spouse\nParent\nSibling\nFriend\nOther", "in_list_view": 1, "columns": 2},
        {"fieldname": "contact_number", "fieldtype": "Data", "label": "Contact Number", "options": "Phone", "in_list_view": 1, "columns": 2},
        {"fieldname": "guarantee_amount", "fieldtype": "Currency", "label": "Guarantee Amount", "in_list_view": 1, "columns": 2},
        {"fieldname": "id_proof", "fieldtype": "Attach", "label": "ID Proof"}
    ]
})

# Step 2: Create child DocType for repayment schedule
create_document(doctype="DocType", data={
    "name": "Loan Repayment Schedule",
    "module": "Custom",
    "custom": 1,
    "istable": 1,
    "editable_grid": 1,
    "fields": [
        {"fieldname": "payment_date", "fieldtype": "Date", "label": "Payment Date", "reqd": 1, "in_list_view": 1, "columns": 2},
        {"fieldname": "principal_amount", "fieldtype": "Currency", "label": "Principal Amount", "in_list_view": 1, "columns": 2},
        {"fieldname": "interest_amount", "fieldtype": "Currency", "label": "Interest Amount", "in_list_view": 1, "columns": 2},
        {"fieldname": "total_payment", "fieldtype": "Currency", "label": "Total Payment", "in_list_view": 1, "columns": 2},
        {"fieldname": "balance_amount", "fieldtype": "Currency", "label": "Balance", "in_list_view": 1, "columns": 2},
        {"fieldname": "is_paid", "fieldtype": "Check", "label": "Paid", "in_list_view": 1, "columns": 1}
    ]
})

# Step 3: Create the main DocType
create_document(doctype="DocType", data={
    "name": "Loan Application",
    "module": "Custom",
    "custom": 1,
    "naming_rule": "By \"Naming Series\" field",
    "autoname": "naming_series:",
    "title_field": "applicant_name",
    "search_fields": "applicant_name, loan_type, status",
    "sort_field": "modified",
    "sort_order": "DESC",
    "is_submittable": 1,
    "track_changes": 1,
    "fields": [
        # --- Tab 1: Application Details ---
        {"fieldname": "application_tab", "fieldtype": "Tab Break", "label": "Application"},

        # --- Naming and Type Section ---
        {"fieldname": "naming_section", "fieldtype": "Section Break", "label": ""},
        {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "LA-.YYYY.-.####\nLOAN-.####", "default": "LA-.YYYY.-.####", "reqd": 1, "no_copy": 1, "print_hide": 1},
        {"fieldname": "loan_type", "fieldtype": "Select", "label": "Loan Type", "options": "\nPersonal Loan\nHome Loan\nVehicle Loan\nBusiness Loan\nEducation Loan", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
        {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "\nDraft\nPending Approval\nApproved\nRejected\nDisbursed\nClosed", "default": "Draft", "in_list_view": 1, "in_standard_filter": 1, "read_only": 1, "no_copy": 1},
        {"fieldname": "column_break_01", "fieldtype": "Column Break"},
        {"fieldname": "application_date", "fieldtype": "Date", "label": "Application Date", "default": "Today", "reqd": 1},
        {"fieldname": "company", "fieldtype": "Link", "label": "Company", "options": "Company", "reqd": 1, "in_standard_filter": 1},
        {"fieldname": "branch", "fieldtype": "Link", "label": "Branch", "options": "Branch"},

        # --- Applicant Information Section ---
        {"fieldname": "applicant_section", "fieldtype": "Section Break", "label": "Applicant Information"},
        {"fieldname": "applicant_type", "fieldtype": "Select", "label": "Applicant Type", "options": "Customer\nEmployee\nMember", "default": "Customer", "reqd": 1},
        {"fieldname": "applicant", "fieldtype": "Dynamic Link", "label": "Applicant", "options": "applicant_type", "reqd": 1},
        {"fieldname": "applicant_name", "fieldtype": "Data", "label": "Applicant Name", "fetch_from": "applicant.customer_name", "read_only": 1, "in_list_view": 1},
        {"fieldname": "column_break_02", "fieldtype": "Column Break"},
        {"fieldname": "email", "fieldtype": "Data", "label": "Email", "options": "Email"},
        {"fieldname": "phone", "fieldtype": "Data", "label": "Phone", "options": "Phone"},
        {"fieldname": "date_of_birth", "fieldtype": "Date", "label": "Date of Birth"},
        {"fieldname": "applicant_photo", "fieldtype": "Attach Image", "label": "Photo"},

        # --- Loan Details Section ---
        {"fieldname": "loan_details_section", "fieldtype": "Section Break", "label": "Loan Details"},
        {"fieldname": "currency", "fieldtype": "Link", "label": "Currency", "options": "Currency", "default": "INR", "reqd": 1},
        {"fieldname": "loan_amount", "fieldtype": "Currency", "label": "Loan Amount", "options": "currency", "reqd": 1, "non_negative": 1},
        {"fieldname": "interest_rate", "fieldtype": "Float", "label": "Interest Rate (%)", "precision": "2", "reqd": 1},
        {"fieldname": "column_break_03", "fieldtype": "Column Break"},
        {"fieldname": "repayment_method", "fieldtype": "Select", "label": "Repayment Method", "options": "\nRepay Fixed Amount per Period\nRepay Over Number of Periods", "reqd": 1},
        {"fieldname": "repayment_periods", "fieldtype": "Int", "label": "Repayment Periods (Months)", "depends_on": "eval:doc.repayment_method=='Repay Over Number of Periods'"},
        {"fieldname": "monthly_repayment_amount", "fieldtype": "Currency", "label": "Monthly Repayment Amount", "options": "currency", "depends_on": "eval:doc.repayment_method=='Repay Fixed Amount per Period'"},
        {"fieldname": "total_payable_amount", "fieldtype": "Currency", "label": "Total Payable Amount", "options": "currency", "read_only": 1},
        {"fieldname": "total_payable_interest", "fieldtype": "Currency", "label": "Total Interest", "options": "currency", "read_only": 1},

        # --- Collateral Section ---
        {"fieldname": "collateral_section", "fieldtype": "Section Break", "label": "Collateral", "collapsible": 1, "depends_on": "eval:doc.loan_type=='Home Loan' || doc.loan_type=='Vehicle Loan'"},
        {"fieldname": "collateral_type", "fieldtype": "Select", "label": "Collateral Type", "options": "\nProperty\nVehicle\nFixed Deposit\nGold\nOther"},
        {"fieldname": "collateral_value", "fieldtype": "Currency", "label": "Collateral Value", "options": "currency"},
        {"fieldname": "column_break_04", "fieldtype": "Column Break"},
        {"fieldname": "collateral_description", "fieldtype": "Small Text", "label": "Description"},

        # --- Tab 2: Guarantors & Schedule ---
        {"fieldname": "guarantors_tab", "fieldtype": "Tab Break", "label": "Guarantors & Schedule"},

        {"fieldname": "guarantors_section", "fieldtype": "Section Break", "label": "Guarantors"},
        {"fieldname": "guarantors", "fieldtype": "Table", "label": "Guarantors", "options": "Loan Application Guarantor"},

        {"fieldname": "schedule_section", "fieldtype": "Section Break", "label": "Repayment Schedule"},
        {"fieldname": "repayment_schedule", "fieldtype": "Table", "label": "Repayment Schedule", "options": "Loan Repayment Schedule", "read_only": 1},

        # --- Tab 3: Notes & Attachments ---
        {"fieldname": "notes_tab", "fieldtype": "Tab Break", "label": "Notes"},
        {"fieldname": "notes_section", "fieldtype": "Section Break", "label": ""},
        {"fieldname": "remarks", "fieldtype": "Text Editor", "label": "Remarks"},
        {"fieldname": "credit_score", "fieldtype": "Rating", "label": "Credit Score"},
        {"fieldname": "internal_notes", "fieldtype": "Long Text", "label": "Internal Notes", "permlevel": 1},

        # --- Amended From (required for submittable) ---
        {"fieldname": "amended_from", "fieldtype": "Link", "label": "Amended From", "options": "Loan Application", "read_only": 1, "no_copy": 1, "print_hide": 1}
    ],
    "permissions": [
        {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1, "print": 1, "email": 1, "report": 1, "import": 1, "export": 1, "share": 1},
        {"role": "Loan Manager", "read": 1, "write": 1, "create": 1, "delete": 0, "submit": 1, "cancel": 1, "amend": 1, "print": 1, "email": 1, "report": 1},
        {"role": "Loan User", "read": 1, "write": 1, "create": 1, "delete": 0, "submit": 0, "cancel": 0, "print": 1, "email": 1}
    ]
})
```

---

# ============================================================
# 2. CUSTOM FIELD CREATION
# ============================================================

## 2.1 Basic Structure

```python
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",                    # Target DocType
    "fieldname": "custom_delivery_priority",
    "fieldtype": "Select",
    "label": "Delivery Priority",
    "options": "Low\nMedium\nHigh\nUrgent",
    "insert_after": "delivery_date",        # Field after which to insert
    "reqd": 0,
    "read_only": 0,
    "hidden": 0,
    "default": "Medium",
    "description": "Priority level for delivery",
    "depends_on": "",
    "mandatory_depends_on": "",
    "read_only_depends_on": "",
    "fetch_from": "",
    "fetch_if_empty": 0,
    "in_list_view": 1,
    "in_standard_filter": 1,
    "in_preview": 0,
    "in_global_search": 0,
    "bold": 0,
    "unique": 0,
    "no_copy": 0,
    "print_hide": 0,
    "report_hide": 0,
    "allow_in_quick_entry": 0,
    "translatable": 0,
    "permlevel": 0
})
```

## 2.2 Custom Field Name Convention

Custom field names are auto-prefixed with `custom_` by Frappe. When specifying `fieldname`, use the `custom_` prefix.
The `name` of the Custom Field document is auto-set to `{DocType}-{fieldname}`, e.g., `Sales Order-custom_delivery_priority`.

## 2.3 Common Custom Field Examples

### Link Field with fetch_from

```python
# Add a custom "Account Manager" field to Sales Order that fetches from Customer
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_account_manager",
    "fieldtype": "Link",
    "label": "Account Manager",
    "options": "Employee",
    "insert_after": "customer_name",
    "fetch_from": "customer.account_manager",
    "fetch_if_empty": 1,
    "in_list_view": 0,
    "in_standard_filter": 1
})
```

### Currency Field

```python
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_insurance_amount",
    "fieldtype": "Currency",
    "label": "Insurance Amount",
    "options": "currency",
    "insert_after": "grand_total",
    "in_list_view": 0,
    "print_hide": 0,
    "bold": 1,
    "non_negative": 1
})
```

### Conditional Field (depends_on)

```python
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_rejection_reason",
    "fieldtype": "Small Text",
    "label": "Rejection Reason",
    "insert_after": "status",
    "depends_on": "eval:doc.status=='Cancelled'",
    "mandatory_depends_on": "eval:doc.status=='Cancelled'",
    "in_list_view": 0
})
```

### Section Break and Multiple Fields

```python
# Add a section break first
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_logistics_section",
    "fieldtype": "Section Break",
    "label": "Logistics Information",
    "insert_after": "terms",
    "collapsible": 1
})

# Then add fields inside it
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_shipping_carrier",
    "fieldtype": "Link",
    "label": "Shipping Carrier",
    "options": "Supplier",
    "insert_after": "custom_logistics_section"
})

create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_tracking_number",
    "fieldtype": "Data",
    "label": "Tracking Number",
    "insert_after": "custom_shipping_carrier"
})
```

### Table (Child Table) Custom Field

```python
# First create the child DocType if it doesn't exist
create_document(doctype="DocType", data={
    "name": "Sales Order Checklist",
    "module": "Custom",
    "custom": 1,
    "istable": 1,
    "fields": [
        {"fieldname": "task", "fieldtype": "Data", "label": "Task", "reqd": 1, "in_list_view": 1, "columns": 4},
        {"fieldname": "completed", "fieldtype": "Check", "label": "Completed", "in_list_view": 1, "columns": 1},
        {"fieldname": "completed_by", "fieldtype": "Link", "label": "Completed By", "options": "User", "in_list_view": 1, "columns": 3},
        {"fieldname": "completion_date", "fieldtype": "Date", "label": "Date", "in_list_view": 1, "columns": 2}
    ]
})

# Then add the Table field
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_checklist",
    "fieldtype": "Table",
    "label": "Checklist",
    "options": "Sales Order Checklist",
    "insert_after": "custom_tracking_number"
})
```

### Check (Boolean) Field

```python
create_document(doctype="Custom Field", data={
    "dt": "Sales Order",
    "fieldname": "custom_is_priority_order",
    "fieldtype": "Check",
    "label": "Priority Order",
    "insert_after": "customer_name",
    "default": "0",
    "in_list_view": 1,
    "bold": 1
})
```

---

# ============================================================
# 3. CLIENT SCRIPT CREATION
# ============================================================

## 3.1 Basic Structure

```python
create_document(doctype="Client Script", data={
    "name": "Sales Order - Auto Calculate",    # Descriptive name
    "dt": "Sales Order",                       # Target DocType
    "script_type": "Form",                     # "Form" or "List"
    "enabled": 1,
    "script": """
frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        // Called when form loads or refreshes
    },
    validate(frm) {
        // Called before saving
    },
    onload(frm) {
        // Called once when form first loads
    },
    before_save(frm) {
        // Called before save
    },
    after_save(frm) {
        // Called after save
    },
    before_submit(frm) {
        // Called before submit
    },
    on_submit(frm) {
        // Called after submit
    },
    before_cancel(frm) {
        // Called before cancel
    },
    after_cancel(frm) {
        // Called after cancel
    }
});
"""
})
```

## 3.2 script_type Values

- `"Form"` — Runs on Form view of the DocType
- `"List"` — Runs on List view of the DocType

## 3.3 Common Client Script Patterns

### Field Change Handler

```python
create_document(doctype="Client Script", data={
    "dt": "Sales Order",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Sales Order', {
    // Triggered when custom_discount_percent changes
    custom_discount_percent(frm) {
        if (frm.doc.custom_discount_percent > 0) {
            let discount = frm.doc.grand_total * frm.doc.custom_discount_percent / 100;
            frm.set_value('discount_amount', discount);
        }
    },

    customer(frm) {
        // Triggered when customer field changes
        if (frm.doc.customer) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Customer',
                    filters: { name: frm.doc.customer },
                    fieldname: ['credit_limit', 'customer_group']
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('custom_credit_limit', r.message.credit_limit);
                    }
                }
            });
        }
    }
});
"""
})
```

### Conditional Field Visibility

```python
create_document(doctype="Client Script", data={
    "dt": "Loan Application",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Loan Application', {
    refresh(frm) {
        // Toggle field visibility
        frm.toggle_display('collateral_type', frm.doc.loan_type === 'Home Loan' || frm.doc.loan_type === 'Vehicle Loan');
        frm.toggle_display('collateral_value', frm.doc.loan_type === 'Home Loan' || frm.doc.loan_type === 'Vehicle Loan');

        // Toggle required
        frm.toggle_reqd('collateral_type', frm.doc.loan_type === 'Home Loan');

        // Set field as read only
        frm.set_df_property('applicant_name', 'read_only', 1);

        // Add custom button
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Approved') {
            frm.add_custom_button(__('Disburse'), function() {
                frappe.call({
                    method: 'your_app.api.disburse_loan',
                    args: { loan: frm.doc.name },
                    callback: function(r) {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }
    },

    loan_type(frm) {
        // Re-evaluate visibility when loan_type changes
        frm.trigger('refresh');
    }
});
"""
})
```

### Validation Script

```python
create_document(doctype="Client Script", data={
    "dt": "Loan Application",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Loan Application', {
    validate(frm) {
        // Validate loan amount
        if (frm.doc.loan_amount <= 0) {
            frappe.throw(__('Loan Amount must be greater than zero'));
        }

        // Validate interest rate
        if (frm.doc.interest_rate < 1 || frm.doc.interest_rate > 36) {
            frappe.throw(__('Interest Rate must be between 1% and 36%'));
        }

        // Validate at least one guarantor for high-value loans
        if (frm.doc.loan_amount > 500000 && (!frm.doc.guarantors || frm.doc.guarantors.length === 0)) {
            frappe.throw(__('At least one guarantor is required for loans above 5,00,000'));
        }

        // Calculate total guarantor amount
        let total_guarantee = 0;
        (frm.doc.guarantors || []).forEach(row => {
            total_guarantee += row.guarantee_amount || 0;
        });

        if (total_guarantee > 0 && total_guarantee < frm.doc.loan_amount * 0.5) {
            frappe.msgprint(__('Warning: Total guarantee amount is less than 50% of loan amount'));
        }
    }
});
"""
})
```

### Set Query (Filter Link Fields)

```python
create_document(doctype="Client Script", data={
    "dt": "Sales Order",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        // Filter Item link to show only enabled selling items
        frm.set_query('item_code', 'items', function(doc, cdt, cdn) {
            return {
                filters: {
                    'is_sales_item': 1,
                    'disabled': 0
                }
            };
        });

        // Filter warehouse by company
        frm.set_query('set_warehouse', function() {
            return {
                filters: {
                    'company': frm.doc.company,
                    'is_group': 0
                }
            };
        });
    },

    // Dynamic filter based on another field
    customer_group(frm) {
        frm.set_query('customer', function() {
            if (frm.doc.customer_group) {
                return {
                    filters: { 'customer_group': frm.doc.customer_group }
                };
            }
        });
    }
});
"""
})
```

### Child Table Events

```python
create_document(doctype="Client Script", data={
    "dt": "Sales Order",
    "script_type": "Form",
    "enabled": 1,
    "script": """
// Parent form events
frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        calculate_totals(frm);
    }
});

// Child table events (Sales Order Item)
frappe.ui.form.on('Sales Order Item', {
    // When qty changes in child table
    qty(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'amount', row.qty * row.rate);
        calculate_totals(frm);
    },

    rate(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'amount', row.qty * row.rate);
        calculate_totals(frm);
    },

    // When a row is added
    items_add(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'warehouse', frm.doc.set_warehouse);
    },

    // When a row is removed
    items_remove(frm, cdt, cdn) {
        calculate_totals(frm);
    }
});

function calculate_totals(frm) {
    let total = 0;
    (frm.doc.items || []).forEach(row => {
        total += row.amount || 0;
    });
    frm.set_value('total', total);
}
"""
})
```

### frappe.call to Server

```python
create_document(doctype="Client Script", data={
    "dt": "Loan Application",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Loan Application', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status === 'Draft') {
            frm.add_custom_button(__('Calculate EMI'), function() {
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Loan Application',
                        filters: {
                            applicant: frm.doc.applicant,
                            status: ['in', ['Approved', 'Disbursed']],
                            name: ['!=', frm.doc.name]
                        },
                        fields: ['name', 'loan_amount', 'status']
                    },
                    callback: function(r) {
                        if (r.message && r.message.length > 0) {
                            let existing = r.message.map(d => d.name + ': ' + d.loan_amount).join('\\n');
                            frappe.msgprint(__('Existing Loans:\\n' + existing));
                        }
                    }
                });
            });
        }
    }
});
"""
})
```

### List View Script

```python
create_document(doctype="Client Script", data={
    "dt": "Loan Application",
    "script_type": "List",
    "enabled": 1,
    "script": """
frappe.listview_settings['Loan Application'] = {
    // Add indicator colors based on status
    get_indicator: function(doc) {
        if (doc.status === 'Draft') return [__('Draft'), 'grey', 'status,=,Draft'];
        if (doc.status === 'Pending Approval') return [__('Pending'), 'orange', 'status,=,Pending Approval'];
        if (doc.status === 'Approved') return [__('Approved'), 'green', 'status,=,Approved'];
        if (doc.status === 'Rejected') return [__('Rejected'), 'red', 'status,=,Rejected'];
        if (doc.status === 'Disbursed') return [__('Disbursed'), 'blue', 'status,=,Disbursed'];
        if (doc.status === 'Closed') return [__('Closed'), 'darkgrey', 'status,=,Closed'];
    },

    // Hide sidebar filters
    hide_name_column: true,

    // Format list row
    formatters: {
        loan_amount(val) {
            return format_currency(val);
        }
    },

    // Button in list view
    onload: function(listview) {
        listview.page.add_inner_button(__('Export Summary'), function() {
            frappe.msgprint('Export triggered');
        });
    }
};
"""
})
```

### Dialog and Prompt

```python
create_document(doctype="Client Script", data={
    "dt": "Loan Application",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Loan Application', {
    refresh(frm) {
        if (frm.doc.status === 'Pending Approval') {
            frm.add_custom_button(__('Approve'), function() {
                let d = new frappe.ui.Dialog({
                    title: 'Approve Loan',
                    fields: [
                        {
                            label: 'Approved Amount',
                            fieldname: 'approved_amount',
                            fieldtype: 'Currency',
                            default: frm.doc.loan_amount,
                            reqd: 1
                        },
                        {
                            label: 'Remarks',
                            fieldname: 'remarks',
                            fieldtype: 'Small Text'
                        }
                    ],
                    primary_action_label: 'Approve',
                    primary_action(values) {
                        frm.set_value('status', 'Approved');
                        frm.set_value('loan_amount', values.approved_amount);
                        frm.set_value('remarks', values.remarks);
                        frm.save();
                        d.hide();
                    }
                });
                d.show();
            }, __('Actions'));
        }
    }
});
"""
})
```

---

# ============================================================
# 4. SERVER SCRIPT CREATION
# ============================================================

## 4.1 Basic Structure

```python
create_document(doctype="Server Script", data={
    "name": "Loan Application - Before Save",
    "script_type": "DocType Event",        # DocType Event | API | Permission Query | Scheduled
    "reference_doctype": "Loan Application",  # Required for DocType Event
    "doctype_event": "Before Save",        # Event type
    "disabled": 0,
    "script": """
# 'doc' is available for DocType Event scripts
if doc.loan_amount > 1000000:
    doc.status = 'Pending Approval'
"""
})
```

## 4.2 script_type Values

| script_type | Required Fields | Description |
|-------------|----------------|-------------|
| DocType Event | reference_doctype, doctype_event | Triggers on document events |
| API | api_method | Creates a whitelisted API endpoint |
| Permission Query | reference_doctype | Adds permission conditions |
| Scheduled | event_frequency OR cron_format | Runs on schedule |

## 4.3 doctype_event Values

- `"Before Insert"` — Before first save (new doc)
- `"After Insert"` — After first save
- `"Before Validate"` — Before validation
- `"Before Save"` — Before save
- `"After Save"` — After save
- `"Before Submit"` — Before submit
- `"After Submit"` — After submit (for submittable)
- `"Before Cancel"` — Before cancel
- `"After Cancel"` — After cancel
- `"Before Delete"` — Before delete
- `"After Delete"` — After delete
- `"Before Rename"` — Before rename
- `"After Rename"` — After rename
- `"On Change"` — When any value changes (via set_value)
- `"On Update"` — After save (alias)

## 4.4 DocType Event Examples

### Before Save - Calculations and Validations

```python
create_document(doctype="Server Script", data={
    "name": "Loan Application - Calculate Interest",
    "script_type": "DocType Event",
    "reference_doctype": "Loan Application",
    "doctype_event": "Before Save",
    "disabled": 0,
    "script": """
# Calculate total payable interest
if doc.loan_amount and doc.interest_rate and doc.repayment_periods:
    monthly_rate = doc.interest_rate / 12 / 100
    n = doc.repayment_periods

    if monthly_rate > 0:
        emi = doc.loan_amount * monthly_rate * ((1 + monthly_rate) ** n) / (((1 + monthly_rate) ** n) - 1)
        doc.monthly_repayment_amount = emi
        doc.total_payable_amount = emi * n
        doc.total_payable_interest = doc.total_payable_amount - doc.loan_amount
    else:
        doc.monthly_repayment_amount = doc.loan_amount / n
        doc.total_payable_amount = doc.loan_amount
        doc.total_payable_interest = 0

# Validate
if doc.loan_amount <= 0:
    frappe.throw('Loan Amount must be greater than zero')

if doc.interest_rate > 36:
    frappe.throw('Interest Rate cannot exceed 36%')
"""
})
```

### After Save - Create Related Documents

```python
create_document(doctype="Server Script", data={
    "name": "Loan Application - After Save Create Activity",
    "script_type": "DocType Event",
    "reference_doctype": "Loan Application",
    "doctype_event": "After Save",
    "disabled": 0,
    "script": """
# Create a ToDo for loan officer on new application
if doc.is_new() or doc.has_value_changed('status'):
    if doc.status == 'Pending Approval':
        todo = frappe.get_doc({
            'doctype': 'ToDo',
            'allocated_to': 'admin@example.com',
            'reference_type': 'Loan Application',
            'reference_name': doc.name,
            'description': f'Review Loan Application {doc.name} for {doc.applicant_name} - Amount: {doc.loan_amount}',
            'priority': 'High' if doc.loan_amount > 500000 else 'Medium'
        })
        todo.insert(ignore_permissions=True)
"""
})
```

### Before Submit - Final Validations

```python
create_document(doctype="Server Script", data={
    "name": "Loan Application - Before Submit",
    "script_type": "DocType Event",
    "reference_doctype": "Loan Application",
    "doctype_event": "Before Submit",
    "disabled": 0,
    "script": """
# Only approved loans can be submitted
if doc.status != 'Approved':
    frappe.throw('Only Approved Loan Applications can be submitted. Current status: ' + doc.status)

# Ensure guarantors exist for large loans
if doc.loan_amount > 500000:
    if not doc.guarantors or len(doc.guarantors) == 0:
        frappe.throw('At least one guarantor is required for loans above 5,00,000')

# Set status to Disbursed on submit
doc.status = 'Disbursed'
"""
})
```

### After Submit

```python
create_document(doctype="Server Script", data={
    "name": "Loan Application - After Submit",
    "script_type": "DocType Event",
    "reference_doctype": "Loan Application",
    "doctype_event": "After Submit",
    "disabled": 0,
    "script": """
# Send email notification
frappe.sendmail(
    recipients=[doc.email],
    subject=f'Loan Application {doc.name} - Disbursed',
    message=f'Dear {doc.applicant_name},<br><br>Your loan of {doc.loan_amount} has been disbursed.<br><br>Regards'
)
"""
})
```

## 4.5 API Server Script

```python
create_document(doctype="Server Script", data={
    "name": "Get Loan Summary",
    "script_type": "API",
    "api_method": "get_loan_summary",     # Accessible at /api/method/get_loan_summary
    "allow_guest": 0,
    "disabled": 0,
    "script": """
# Access via: frappe.call({ method: 'get_loan_summary', args: { applicant: 'CUST-001' } })
# Parameters come from frappe.form_dict
applicant = frappe.form_dict.get('applicant')

if not applicant:
    frappe.throw('Applicant is required')

loans = frappe.get_all('Loan Application',
    filters={'applicant': applicant, 'docstatus': ['<', 2]},
    fields=['name', 'loan_type', 'loan_amount', 'status', 'interest_rate', 'monthly_repayment_amount']
)

total_outstanding = sum(l.loan_amount for l in loans if l.status in ['Approved', 'Disbursed'])

frappe.response['message'] = {
    'loans': loans,
    'total_outstanding': total_outstanding,
    'loan_count': len(loans)
}
"""
})
```

## 4.6 Permission Query Server Script

```python
create_document(doctype="Server Script", data={
    "name": "Loan Application - Permission Query",
    "script_type": "Permission Query",
    "reference_doctype": "Loan Application",
    "disabled": 0,
    "script": """
# Restrict users to see only their branch's loans
# 'user' and 'conditions' are available
if user != 'Administrator':
    branch = frappe.db.get_value('Employee', {'user_id': user}, 'branch')
    if branch:
        conditions = f"(`tabLoan Application`.branch = '{branch}')"
    else:
        conditions = "1=0"  # No access if no branch assigned
"""
})
```

## 4.7 Scheduled Server Script

```python
create_document(doctype="Server Script", data={
    "name": "Loan - Send Repayment Reminders",
    "script_type": "Scheduled",
    "event_frequency": "Cron",
    "cron_format": "0 9 * * *",           # Every day at 9 AM
    "disabled": 0,
    "script": """
# Send repayment reminders 3 days before due date
from datetime import date, timedelta

reminder_date = date.today() + timedelta(days=3)

# Find loans with upcoming payments
loans = frappe.get_all('Loan Application',
    filters={
        'status': 'Disbursed',
        'docstatus': 1
    },
    fields=['name', 'applicant_name', 'email', 'monthly_repayment_amount']
)

for loan in loans:
    # Check repayment schedule
    due_payments = frappe.get_all('Loan Repayment Schedule',
        filters={
            'parent': loan.name,
            'payment_date': reminder_date,
            'is_paid': 0
        },
        fields=['payment_date', 'total_payment']
    )

    for payment in due_payments:
        frappe.sendmail(
            recipients=[loan.email],
            subject=f'Repayment Reminder - {loan.name}',
            message=f'Dear {loan.applicant_name},<br><br>Your payment of {payment.total_payment} is due on {payment.payment_date}.<br><br>Regards'
        )

frappe.log_error('Repayment reminders sent', 'Loan Reminders')
"""
})
```

### event_frequency Values

- `"All"` — Every minute (not recommended)
- `"Hourly"` — Every hour
- `"Hourly Long"` — Every 6 hours
- `"Daily"` — Once daily
- `"Daily Long"` — Once daily (long running)
- `"Weekly"` — Once weekly
- `"Weekly Long"` — Once weekly (long running)
- `"Monthly"` — Once monthly
- `"Monthly Long"` — Once monthly (long running)
- `"Yearly"` — Once yearly
- `"Cron"` — Custom cron format (use `cron_format` field)

### Cron Format Examples

```
"0 9 * * *"        # Every day at 9:00 AM
"0 9 * * 1"        # Every Monday at 9:00 AM
"0 */2 * * *"      # Every 2 hours
"0 9 1 * *"        # First day of every month at 9 AM
"*/30 * * * *"     # Every 30 minutes
"0 18 * * 1-5"     # Weekdays at 6 PM
```

## 4.8 Useful Server Script APIs

```python
# Get a single value
value = frappe.db.get_value("Customer", "CUST-001", "customer_name")

# Get multiple values
values = frappe.db.get_value("Customer", "CUST-001", ["customer_name", "email_id"], as_dict=True)

# Get document
doc = frappe.get_doc("Customer", "CUST-001")

# Get list with filters
records = frappe.get_all("Sales Order",
    filters={"customer": "CUST-001", "status": "To Deliver and Bill"},
    fields=["name", "grand_total", "delivery_date"],
    order_by="creation desc",
    limit_page_length=10
)

# SQL query
results = frappe.db.sql("""
    SELECT name, loan_amount, status
    FROM `tabLoan Application`
    WHERE applicant = %s AND docstatus = 1
""", (doc.applicant,), as_dict=True)

# Set value directly in database
frappe.db.set_value("Loan Application", "LA-2024-0001", "status", "Closed")

# Check existence
exists = frappe.db.exists("Customer", "CUST-001")

# Count
count = frappe.db.count("Loan Application", {"status": "Pending Approval"})

# Throw error (stops execution)
frappe.throw("Error message")

# Show message (non-blocking)
frappe.msgprint("Info message")

# Log error
frappe.log_error("Error details", "Error Title")

# Enqueue long-running task
frappe.enqueue('your_method', queue='long', timeout=600, arg1='value')

# Get current user
current_user = frappe.session.user

# Check permission
frappe.has_permission("Loan Application", "write", doc=doc.name)
```

---

# ============================================================
# 5. WORKFLOW CREATION
# ============================================================

## 5.1 Basic Structure

```python
create_document(doctype="Workflow", data={
    "name": "Loan Application Approval",
    "document_type": "Loan Application",      # Target DocType
    "workflow_name": "Loan Application Approval",
    "is_active": 1,
    "override_status": 0,                     # 1 = workflow state replaces status field
    "send_email_alert": 1,
    "workflow_state_field": "workflow_state",  # Field to store current state
    "states": [
        {
            "state": "Draft",
            "doc_status": "0",
            "is_optional_state": 0,
            "allow_edit": "Loan User",
            "update_field": "status",
            "update_value": "Draft"
        },
        {
            "state": "Pending Approval",
            "doc_status": "0",
            "is_optional_state": 0,
            "allow_edit": "Loan Manager",
            "update_field": "status",
            "update_value": "Pending Approval"
        },
        {
            "state": "Approved",
            "doc_status": "1",               # 1 = Submitted
            "is_optional_state": 0,
            "allow_edit": "Loan Manager",
            "update_field": "status",
            "update_value": "Approved"
        },
        {
            "state": "Rejected",
            "doc_status": "1",
            "is_optional_state": 0,
            "allow_edit": "Loan Manager",
            "update_field": "status",
            "update_value": "Rejected"
        },
        {
            "state": "Cancelled",
            "doc_status": "2",               # 2 = Cancelled
            "is_optional_state": 0,
            "allow_edit": "Loan Manager",
            "update_field": "status",
            "update_value": "Cancelled"
        }
    ],
    "transitions": [
        {
            "state": "Draft",
            "action": "Submit for Approval",
            "next_state": "Pending Approval",
            "allowed": "Loan User",
            "allow_self_approval": 1,
            "condition": "doc.loan_amount > 0"
        },
        {
            "state": "Pending Approval",
            "action": "Approve",
            "next_state": "Approved",
            "allowed": "Loan Manager",
            "allow_self_approval": 0,
            "condition": ""
        },
        {
            "state": "Pending Approval",
            "action": "Reject",
            "next_state": "Rejected",
            "allowed": "Loan Manager",
            "allow_self_approval": 0,
            "condition": ""
        },
        {
            "state": "Pending Approval",
            "action": "Send Back",
            "next_state": "Draft",
            "allowed": "Loan Manager",
            "allow_self_approval": 1
        },
        {
            "state": "Approved",
            "action": "Cancel",
            "next_state": "Cancelled",
            "allowed": "Loan Manager",
            "allow_self_approval": 1
        }
    ]
})
```

## 5.2 State Properties

```python
{
    "state": "Pending Approval",    # State name (shown to user)
    "doc_status": "0",              # "0" = Draft, "1" = Submitted, "2" = Cancelled
    "is_optional_state": 0,         # 1 = can be skipped
    "allow_edit": "Role Name",      # Role that can edit in this state
    "update_field": "status",       # Field to update when entering state
    "update_value": "Pending"       # Value to set in update_field
}
```

## 5.3 Transition Properties

```python
{
    "state": "Draft",                    # From state
    "action": "Submit for Approval",     # Button label shown
    "next_state": "Pending Approval",    # To state
    "allowed": "Loan User",             # Role allowed to perform this
    "allow_self_approval": 1,            # 1 = user can transition their own doc
    "condition": "doc.loan_amount > 0"   # Python condition (optional)
}
```

## 5.4 Important Notes for Workflows

- The `workflow_state_field` must exist on the DocType (add as Custom Field if needed)
- If not using `override_status`, add a `workflow_state` field to the DocType:

```python
create_document(doctype="Custom Field", data={
    "dt": "Loan Application",
    "fieldname": "workflow_state",
    "fieldtype": "Link",
    "label": "Workflow State",
    "options": "Workflow State",
    "hidden": 1,
    "read_only": 1,
    "no_copy": 1,
    "allow_on_submit": 1,
    "insert_after": "status"
})
```

- Workflow States are auto-created if they don't exist, or create them:

```python
create_document(doctype="Workflow State", data={
    "workflow_state_name": "Pending Approval",
    "style": "Warning",         # Primary, Warning, Success, Danger, Inverse, Info
    "icon": "question-sign"
})
```

- Workflow Actions are auto-created if they don't exist, or create them:

```python
create_document(doctype="Workflow Action Master", data={
    "workflow_action_name": "Approve"
})
```

---

# ============================================================
# 6. PRINT FORMAT CREATION
# ============================================================

## 6.1 Basic Structure

```python
create_document(doctype="Print Format", data={
    "name": "Loan Application Print",
    "doc_type": "Loan Application",
    "module": "Custom",
    "print_format_type": "Jinja",       # "Jinja" or "JS"
    "standard": "No",
    "custom_format": 1,
    "default_print_language": "en",
    "disabled": 0,
    "html": """
<style>
    .print-format {
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 12px;
        color: #333;
    }
    .header-section {
        border-bottom: 3px solid #2c3e50;
        padding-bottom: 15px;
        margin-bottom: 20px;
    }
    .company-name {
        font-size: 24px;
        font-weight: bold;
        color: #2c3e50;
    }
    .doc-title {
        font-size: 18px;
        color: #e74c3c;
        margin-top: 5px;
    }
    .info-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    .info-table td {
        padding: 6px 10px;
        border: 1px solid #ddd;
    }
    .info-table .label {
        font-weight: bold;
        background: #f8f9fa;
        width: 30%;
    }
    .section-title {
        font-size: 14px;
        font-weight: bold;
        color: #2c3e50;
        border-bottom: 1px solid #2c3e50;
        padding-bottom: 5px;
        margin: 20px 0 10px;
    }
    .items-table {
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0;
    }
    .items-table th {
        background: #2c3e50;
        color: white;
        padding: 8px;
        text-align: left;
    }
    .items-table td {
        padding: 6px 8px;
        border-bottom: 1px solid #ddd;
    }
    .items-table tr:nth-child(even) {
        background: #f8f9fa;
    }
    .totals-section {
        text-align: right;
        margin-top: 15px;
    }
    .total-row {
        font-size: 14px;
        margin: 5px 0;
    }
    .grand-total {
        font-size: 16px;
        font-weight: bold;
        color: #e74c3c;
        border-top: 2px solid #333;
        padding-top: 8px;
    }
    .footer {
        margin-top: 40px;
        border-top: 1px solid #ddd;
        padding-top: 10px;
        font-size: 10px;
        color: #999;
    }
    .signature-section {
        margin-top: 60px;
        display: flex;
        justify-content: space-between;
    }
    .signature-box {
        width: 200px;
        text-align: center;
    }
    .signature-line {
        border-top: 1px solid #333;
        margin-top: 50px;
        padding-top: 5px;
    }
</style>

<div class="print-format">
    <!-- Header -->
    <div class="header-section">
        <div class="company-name">{{ doc.company }}</div>
        <div class="doc-title">LOAN APPLICATION - {{ doc.name }}</div>
        <div>Date: {{ doc.application_date | default("", true) }}</div>
        <div>Status: <strong>{{ doc.status }}</strong></div>
    </div>

    <!-- Applicant Information -->
    <div class="section-title">Applicant Information</div>
    <table class="info-table">
        <tr>
            <td class="label">Applicant Name</td>
            <td>{{ doc.applicant_name }}</td>
            <td class="label">Applicant Type</td>
            <td>{{ doc.applicant_type }}</td>
        </tr>
        <tr>
            <td class="label">Email</td>
            <td>{{ doc.email or '' }}</td>
            <td class="label">Phone</td>
            <td>{{ doc.phone or '' }}</td>
        </tr>
        <tr>
            <td class="label">Date of Birth</td>
            <td>{{ frappe.utils.formatdate(doc.date_of_birth) if doc.date_of_birth else '' }}</td>
            <td class="label">Branch</td>
            <td>{{ doc.branch or '' }}</td>
        </tr>
    </table>

    <!-- Loan Details -->
    <div class="section-title">Loan Details</div>
    <table class="info-table">
        <tr>
            <td class="label">Loan Type</td>
            <td>{{ doc.loan_type }}</td>
            <td class="label">Currency</td>
            <td>{{ doc.currency }}</td>
        </tr>
        <tr>
            <td class="label">Loan Amount</td>
            <td>{{ frappe.utils.fmt_money(doc.loan_amount, currency=doc.currency) }}</td>
            <td class="label">Interest Rate</td>
            <td>{{ doc.interest_rate }}%</td>
        </tr>
        <tr>
            <td class="label">Repayment Periods</td>
            <td>{{ doc.repayment_periods }} months</td>
            <td class="label">Monthly EMI</td>
            <td>{{ frappe.utils.fmt_money(doc.monthly_repayment_amount, currency=doc.currency) }}</td>
        </tr>
        <tr>
            <td class="label">Total Payable Amount</td>
            <td>{{ frappe.utils.fmt_money(doc.total_payable_amount, currency=doc.currency) }}</td>
            <td class="label">Total Interest</td>
            <td>{{ frappe.utils.fmt_money(doc.total_payable_interest, currency=doc.currency) }}</td>
        </tr>
    </table>

    <!-- Guarantors -->
    {% if doc.guarantors %}
    <div class="section-title">Guarantors</div>
    <table class="items-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Guarantor Name</th>
                <th>Relationship</th>
                <th>Contact</th>
                <th>Guarantee Amount</th>
            </tr>
        </thead>
        <tbody>
            {% for row in doc.guarantors %}
            <tr>
                <td>{{ row.idx }}</td>
                <td>{{ row.guarantor_name }}</td>
                <td>{{ row.relationship }}</td>
                <td>{{ row.contact_number or '' }}</td>
                <td>{{ frappe.utils.fmt_money(row.guarantee_amount, currency=doc.currency) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}

    <!-- Repayment Schedule -->
    {% if doc.repayment_schedule %}
    <div class="section-title">Repayment Schedule</div>
    <table class="items-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Date</th>
                <th>Principal</th>
                <th>Interest</th>
                <th>Total</th>
                <th>Balance</th>
                <th>Paid</th>
            </tr>
        </thead>
        <tbody>
            {% for row in doc.repayment_schedule %}
            <tr>
                <td>{{ row.idx }}</td>
                <td>{{ frappe.utils.formatdate(row.payment_date) }}</td>
                <td>{{ frappe.utils.fmt_money(row.principal_amount, currency=doc.currency) }}</td>
                <td>{{ frappe.utils.fmt_money(row.interest_amount, currency=doc.currency) }}</td>
                <td>{{ frappe.utils.fmt_money(row.total_payment, currency=doc.currency) }}</td>
                <td>{{ frappe.utils.fmt_money(row.balance_amount, currency=doc.currency) }}</td>
                <td>{{ '✓' if row.is_paid else '✗' }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}

    <!-- Remarks -->
    {% if doc.remarks %}
    <div class="section-title">Remarks</div>
    <div>{{ doc.remarks }}</div>
    {% endif %}

    <!-- Signatures -->
    <div class="signature-section">
        <div class="signature-box">
            <div class="signature-line">Applicant Signature</div>
        </div>
        <div class="signature-box">
            <div class="signature-line">Authorized Signatory</div>
        </div>
    </div>

    <!-- Footer -->
    <div class="footer">
        <p>This is a computer-generated document. Printed on {{ frappe.utils.now_datetime().strftime('%Y-%m-%d %H:%M') }}</p>
    </div>
</div>
"""
})
```

## 6.2 Useful Jinja Helpers in Print Formats

```jinja2
{# Format date #}
{{ frappe.utils.formatdate(doc.posting_date) }}
{{ doc.posting_date | frappe.utils.formatdate }}

{# Format currency #}
{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}

{# Format number #}
{{ frappe.utils.flt(doc.quantity, 2) }}

{# Number to words #}
{{ frappe.utils.money_in_words(doc.grand_total, doc.currency) }}

{# Current datetime #}
{{ frappe.utils.now_datetime() }}

{# Get linked doc value #}
{{ frappe.db.get_value("Company", doc.company, "phone_no") }}

{# Conditional display #}
{% if doc.discount_amount > 0 %}
    Discount: {{ doc.discount_amount }}
{% endif %}

{# Loop child table #}
{% for item in doc.items %}
    {{ item.idx }}. {{ item.item_name }} - {{ item.qty }}
{% endfor %}

{# Get image URL #}
{% if doc.image %}
    <img src="{{ doc.image }}" style="max-width: 150px;">
{% endif %}

{# Barcode #}
<svg class="barcode" data-barcode-value="{{ doc.name }}"></svg>

{# QR Code (if available) #}
{{ frappe.utils.get_url() }}/app/{{ doc.doctype | lower | replace(" ", "-") }}/{{ doc.name }}
```

---

# ============================================================
# 7. NOTIFICATION CREATION
# ============================================================

## 7.1 Basic Structure

```python
create_document(doctype="Notification", data={
    "name": "Loan Application Approved",
    "subject": "Loan Application {{ doc.name }} - {{ doc.status }}",
    "document_type": "Loan Application",
    "event": "Value Change",             # Event trigger
    "value_changed": "status",           # For Value Change event
    "condition": "doc.status == 'Approved'",
    "channel": "Email",                  # Email, Slack, System Notification
    "enabled": 1,
    "recipients": [
        {
            "receiver_by_document_field": "email"   # Field containing email
        }
    ],
    "message": """
<h3>Loan Application {{ doc.status }}</h3>
<p>Dear {{ doc.applicant_name }},</p>
<p>Your loan application <strong>{{ doc.name }}</strong> has been <strong>{{ doc.status }}</strong>.</p>

<table style="border-collapse: collapse; width: 100%;">
    <tr>
        <td style="border: 1px solid #ddd; padding: 8px;"><strong>Loan Type</strong></td>
        <td style="border: 1px solid #ddd; padding: 8px;">{{ doc.loan_type }}</td>
    </tr>
    <tr>
        <td style="border: 1px solid #ddd; padding: 8px;"><strong>Loan Amount</strong></td>
        <td style="border: 1px solid #ddd; padding: 8px;">{{ frappe.utils.fmt_money(doc.loan_amount, currency=doc.currency) }}</td>
    </tr>
    <tr>
        <td style="border: 1px solid #ddd; padding: 8px;"><strong>Monthly EMI</strong></td>
        <td style="border: 1px solid #ddd; padding: 8px;">{{ frappe.utils.fmt_money(doc.monthly_repayment_amount, currency=doc.currency) }}</td>
    </tr>
</table>

<p>Please contact us for any queries.</p>
<p>Regards,<br>{{ doc.company }}</p>
"""
})
```

## 7.2 Event Types

```python
# Document events
"event": "New",              # When document is created
"event": "Save",             # When document is saved
"event": "Submit",           # When document is submitted
"event": "Cancel",           # When document is cancelled
"event": "Value Change",     # When specific field value changes
    "value_changed": "status",   # Required: which field to watch
"event": "Days After",       # X days after a date field
    "days_in_advance": 3,
    "date_changed": "due_date",
"event": "Days Before",      # X days before a date field
    "days_in_advance": 3,
    "date_changed": "due_date",
"event": "Custom",           # Triggered manually via frappe.publish_realtime
```

## 7.3 Recipient Types

```python
"recipients": [
    # From a field in the document
    {"receiver_by_document_field": "email"},
    {"receiver_by_document_field": "contact_email"},

    # From a role
    {"receiver_by_role": "Loan Manager"},

    # Specific email
    {"cc": "manager@example.com"},
    {"bcc": "audit@example.com"}
]
```

## 7.4 System Notification

```python
create_document(doctype="Notification", data={
    "name": "Loan Pending Approval Alert",
    "document_type": "Loan Application",
    "event": "Value Change",
    "value_changed": "status",
    "condition": "doc.status == 'Pending Approval'",
    "channel": "System Notification",
    "enabled": 1,
    "recipients": [
        {"receiver_by_role": "Loan Manager"}
    ],
    "subject": "New Loan Application Pending: {{ doc.name }}",
    "message": "{{ doc.applicant_name }} has submitted a loan application for {{ frappe.utils.fmt_money(doc.loan_amount) }}. Please review."
})
```

---

# ============================================================
# 8. WEB FORM CREATION
# ============================================================

## 8.1 Basic Structure

```python
create_document(doctype="Web Form", data={
    "name": "apply-for-loan",              # URL slug
    "title": "Apply for Loan",
    "doc_type": "Loan Application",        # Target DocType
    "module": "Custom",
    "published": 1,
    "login_required": 1,                   # 0 = guest access
    "allow_edit": 1,                       # Allow editing submitted forms
    "allow_multiple": 0,                   # Allow multiple submissions
    "allow_delete": 0,
    "allow_comments": 1,
    "allow_print": 1,
    "allow_incomplete": 0,
    "show_sidebar": 1,
    "show_attachments": 1,
    "max_attachment_size": 5,              # MB
    "is_standard": 0,
    "introduction_text": "<h3>Loan Application Form</h3><p>Please fill in all required fields to apply for a loan.</p>",
    "success_message": "Thank you! Your loan application has been submitted successfully. Our team will review it shortly.",
    "success_url": "/loan-status",
    "banner_image": "",
    "breadcrumbs": [{"label": "Home", "route": "/"}, {"label": "Apply for Loan", "route": ""}],
    "web_form_fields": [
        {
            "fieldname": "loan_type",
            "fieldtype": "Select",
            "label": "Loan Type",
            "options": "\nPersonal Loan\nHome Loan\nVehicle Loan\nBusiness Loan\nEducation Loan",
            "reqd": 1
        },
        {
            "fieldname": "applicant_name",
            "fieldtype": "Data",
            "label": "Full Name",
            "reqd": 1
        },
        {
            "fieldname": "email",
            "fieldtype": "Data",
            "label": "Email Address",
            "options": "Email",
            "reqd": 1
        },
        {
            "fieldname": "phone",
            "fieldtype": "Data",
            "label": "Phone Number",
            "options": "Phone",
            "reqd": 1
        },
        {
            "fieldname": "date_of_birth",
            "fieldtype": "Date",
            "label": "Date of Birth"
        },
        {
            "fieldname": "",
            "fieldtype": "Section Break",
            "label": "Loan Details"
        },
        {
            "fieldname": "loan_amount",
            "fieldtype": "Currency",
            "label": "Requested Loan Amount",
            "reqd": 1,
            "description": "Enter the amount you wish to borrow"
        },
        {
            "fieldname": "repayment_periods",
            "fieldtype": "Int",
            "label": "Repayment Period (Months)",
            "reqd": 1,
            "description": "Number of months to repay"
        },
        {
            "fieldname": "",
            "fieldtype": "Section Break",
            "label": "Additional Information"
        },
        {
            "fieldname": "remarks",
            "fieldtype": "Text",
            "label": "Additional Remarks",
            "max_length": 500
        },
        {
            "fieldname": "applicant_photo",
            "fieldtype": "Attach Image",
            "label": "Photo ID"
        }
    ]
})
```

---

# ============================================================
# 9. PROPERTY SETTER
# ============================================================

## 9.1 Basic Structure

Property Setter changes properties of existing fields in standard DocTypes without modifying core code.

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",         # "DocField" for field props, "DocType" for doctype props
    "doc_type": "Sales Order",              # Target DocType
    "field_name": "delivery_date",          # Target field (empty for DocType properties)
    "property": "reqd",                     # Property to change
    "property_type": "Check",              # Data type of property
    "value": "1",                          # New value (always string)
    "is_system_generated": 0
})
```

## 9.2 Common Property Setter Examples

### Make a field mandatory

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "po_no",
    "property": "reqd",
    "property_type": "Check",
    "value": "1"
})
```

### Hide a field

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "tax_id",
    "property": "hidden",
    "property_type": "Check",
    "value": "1"
})
```

### Make a field read-only

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "customer_name",
    "property": "read_only",
    "property_type": "Check",
    "value": "1"
})
```

### Change default value

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "delivery_date",
    "property": "default",
    "property_type": "Text",
    "value": "Today"
})
```

### Change Select options

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Lead",
    "field_name": "source",
    "property": "options",
    "property_type": "Text",
    "value": "Website\nPhone Call\nEmail\nReferral\nSocial Media\nAdvertisement\nExhibition\nCold Call"
})
```

### Change field label

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "po_no",
    "property": "label",
    "property_type": "Data",
    "value": "Purchase Order Number"
})
```

### Change description

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "delivery_date",
    "property": "description",
    "property_type": "Text",
    "value": "Expected delivery date (must be at least 3 business days from today)"
})
```

### Change DocType-level property (sort field)

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocType",
    "doc_type": "Sales Order",
    "field_name": "",
    "property": "sort_field",
    "property_type": "Data",
    "value": "modified"
})
```

### Allow rename on a DocType

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocType",
    "doc_type": "Item",
    "field_name": "",
    "property": "allow_rename",
    "property_type": "Check",
    "value": "1"
})
```

### Set in_list_view

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "customer_name",
    "property": "in_list_view",
    "property_type": "Check",
    "value": "1"
})
```

### Set depends_on

```python
create_document(doctype="Property Setter", data={
    "doctype_or_field": "DocField",
    "doc_type": "Sales Order",
    "field_name": "po_no",
    "property": "depends_on",
    "property_type": "Data",
    "value": "eval:doc.customer"
})
```

## 9.3 Property Types Reference

| property | property_type | value examples |
|----------|--------------|----------------|
| reqd | Check | "0" or "1" |
| hidden | Check | "0" or "1" |
| read_only | Check | "0" or "1" |
| in_list_view | Check | "0" or "1" |
| in_standard_filter | Check | "0" or "1" |
| bold | Check | "0" or "1" |
| unique | Check | "0" or "1" |
| allow_on_submit | Check | "0" or "1" |
| print_hide | Check | "0" or "1" |
| no_copy | Check | "0" or "1" |
| default | Text | any string |
| label | Data | any string |
| description | Text | any string |
| options | Text | varies by fieldtype |
| depends_on | Data | "eval:doc.field == 'value'" |
| mandatory_depends_on | Data | "eval:doc.field == 'value'" |
| read_only_depends_on | Data | "eval:doc.field == 'value'" |
| fetch_from | Data | "link_field.remote_field" |
| precision | Data | "2", "3", etc. |
| length | Int | number |
| columns | Int | 1-10 |
| sort_field | Data | fieldname |
| sort_order | Data | "ASC" or "DESC" |
| allow_rename | Check | "0" or "1" |
| track_changes | Check | "0" or "1" |
| search_fields | Data | comma-separated fieldnames |

---

# ============================================================
# 10. REPORT CREATION (SCRIPT REPORT)
# ============================================================

## 10.1 Basic Structure

```python
create_document(doctype="Report", data={
    "name": "Loan Application Summary",
    "report_name": "Loan Application Summary",
    "ref_doctype": "Loan Application",     # Primary DocType
    "report_type": "Script Report",         # "Script Report", "Query Report"
    "module": "Custom",
    "is_standard": "No",
    "disabled": 0,
    "roles": [
        {"role": "System Manager"},
        {"role": "Loan Manager"}
    ],
    "columns": [
        {"fieldname": "name", "label": "Application ID", "fieldtype": "Link", "options": "Loan Application", "width": 150},
        {"fieldname": "applicant_name", "label": "Applicant", "fieldtype": "Data", "width": 200},
        {"fieldname": "loan_type", "label": "Loan Type", "fieldtype": "Data", "width": 120},
        {"fieldname": "loan_amount", "label": "Loan Amount", "fieldtype": "Currency", "width": 140},
        {"fieldname": "interest_rate", "label": "Interest %", "fieldtype": "Float", "width": 100},
        {"fieldname": "monthly_repayment_amount", "label": "Monthly EMI", "fieldtype": "Currency", "width": 140},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 120},
        {"fieldname": "application_date", "label": "Date", "fieldtype": "Date", "width": 110}
    ],
    "filters": [
        {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nDraft\nPending Approval\nApproved\nRejected\nDisbursed\nClosed", "default": "", "width": 120},
        {"fieldname": "loan_type", "label": "Loan Type", "fieldtype": "Select", "options": "\nPersonal Loan\nHome Loan\nVehicle Loan\nBusiness Loan\nEducation Loan", "width": 120},
        {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "to_date", "label": "To Date", "fieldtype": "Date", "width": 100},
        {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "width": 150}
    ],
    "query": """
SELECT
    la.name,
    la.applicant_name,
    la.loan_type,
    la.loan_amount,
    la.interest_rate,
    la.monthly_repayment_amount,
    la.status,
    la.application_date
FROM `tabLoan Application` la
WHERE la.docstatus < 2
    {% if filters.status %} AND la.status = %(status)s {% endif %}
    {% if filters.loan_type %} AND la.loan_type = %(loan_type)s {% endif %}
    {% if filters.from_date %} AND la.application_date >= %(from_date)s {% endif %}
    {% if filters.to_date %} AND la.application_date <= %(to_date)s {% endif %}
    {% if filters.company %} AND la.company = %(company)s {% endif %}
ORDER BY la.application_date DESC
"""
})
```

## 10.2 Query Report (SQL-based)

```python
create_document(doctype="Report", data={
    "name": "Loan Portfolio Analysis",
    "report_name": "Loan Portfolio Analysis",
    "ref_doctype": "Loan Application",
    "report_type": "Query Report",
    "module": "Custom",
    "is_standard": "No",
    "disabled": 0,
    "roles": [{"role": "System Manager"}],
    "query": """
SELECT
    la.loan_type AS 'Loan Type:Data:150',
    COUNT(*) AS 'Count:Int:80',
    SUM(la.loan_amount) AS 'Total Amount:Currency:150',
    AVG(la.interest_rate) AS 'Avg Interest:Float:100',
    SUM(la.total_payable_interest) AS 'Total Interest:Currency:150',
    SUM(CASE WHEN la.status = 'Disbursed' THEN la.loan_amount ELSE 0 END) AS 'Disbursed:Currency:150',
    SUM(CASE WHEN la.status = 'Pending Approval' THEN 1 ELSE 0 END) AS 'Pending:Int:80'
FROM `tabLoan Application` la
WHERE la.docstatus < 2
GROUP BY la.loan_type
ORDER BY SUM(la.loan_amount) DESC
"""
})
```

### Query Report Column Format

In Query Reports, columns are defined in the SQL alias with format:
`'Label:FieldType:Width'`

Examples:
- `'Customer Name:Data:200'`
- `'Amount:Currency:150'`
- `'Date:Date:100'`
- `'Sales Order:Link/Sales Order:150'`
- `'Quantity:Float:80'`
- `'Count:Int:60'`

---

# ============================================================
# 11. ROLE AND PERMISSION
# ============================================================

## 11.1 Create a Role

```python
create_document(doctype="Role", data={
    "role_name": "Loan Manager",
    "desk_access": 1,
    "is_custom": 1,
    "disabled": 0
})

create_document(doctype="Role", data={
    "role_name": "Loan User",
    "desk_access": 1,
    "is_custom": 1,
    "disabled": 0
})
```

## 11.2 Custom DocPerm (Add Permission to DocType)

```python
create_document(doctype="Custom DocPerm", data={
    "parent": "Loan Application",    # DocType name
    "parenttype": "DocType",
    "parentfield": "permissions",
    "role": "Loan Manager",
    "permlevel": 0,
    "read": 1,
    "write": 1,
    "create": 1,
    "delete": 0,
    "submit": 1,
    "cancel": 1,
    "amend": 1,
    "print": 1,
    "email": 1,
    "report": 1,
    "import": 0,
    "export": 1,
    "share": 1,
    "set_user_permissions": 0,
    "if_owner": 0                   # 1 = only own documents
})
```

## 11.3 Higher Permission Levels

```python
# Level 0 = default fields, Level 1 = restricted fields
# First, give read access at permlevel 1
create_document(doctype="Custom DocPerm", data={
    "parent": "Loan Application",
    "parenttype": "DocType",
    "parentfield": "permissions",
    "role": "Loan Manager",
    "permlevel": 1,
    "read": 1,
    "write": 1
})

# Regular users can only read permlevel 1 fields
create_document(doctype="Custom DocPerm", data={
    "parent": "Loan Application",
    "parenttype": "DocType",
    "parentfield": "permissions",
    "role": "Loan User",
    "permlevel": 1,
    "read": 1,
    "write": 0
})
```

## 11.4 User Permission (Row-Level Security)

```python
# Restrict user to specific records
create_document(doctype="User Permission", data={
    "user": "user@example.com",
    "allow": "Company",              # DocType to restrict
    "for_value": "My Company",       # Allowed value
    "applicable_for": "Loan Application",  # Apply only to this DocType (optional)
    "is_default": 1,
    "apply_to_all_doctypes": 0       # 1 = restrict across all DocTypes
})
```

---

# ============================================================
# 12. COMMON PATTERNS & BEST PRACTICES
# ============================================================

## 12.1 fetch_from Pattern

Auto-fill fields from a linked document when a Link field is selected.

```python
# When customer is selected, auto-fill customer_name, email, phone
{
    "fieldname": "customer",
    "fieldtype": "Link",
    "label": "Customer",
    "options": "Customer",
    "reqd": 1
},
{
    "fieldname": "customer_name",
    "fieldtype": "Data",
    "label": "Customer Name",
    "fetch_from": "customer.customer_name",   # Format: link_field.remote_field
    "read_only": 1
},
{
    "fieldname": "customer_email",
    "fieldtype": "Data",
    "label": "Email",
    "fetch_from": "customer.email_id",
    "fetch_if_empty": 1        # Only fetch if field is empty
},
{
    "fieldname": "customer_phone",
    "fieldtype": "Data",
    "label": "Phone",
    "fetch_from": "customer.mobile_no"
}
```

## 12.2 depends_on Pattern

Show/hide fields based on conditions.

```python
# Show field only when condition is met
{
    "fieldname": "cheque_no",
    "fieldtype": "Data",
    "label": "Cheque Number",
    "depends_on": "eval:doc.mode_of_payment == 'Cheque'"
}

# Common depends_on expressions:
"depends_on": "eval:doc.status == 'Active'"
"depends_on": "eval:doc.loan_amount > 500000"
"depends_on": "eval:doc.is_approved == 1"
"depends_on": "eval:doc.loan_type == 'Home Loan' || doc.loan_type == 'Vehicle Loan'"
"depends_on": "eval:doc.applicant_type == 'Customer'"
"depends_on": "eval:doc.docstatus == 0"          # Draft only
"depends_on": "eval:doc.docstatus == 1"          # Submitted only
"depends_on": "eval:!doc.__islocal"              # Saved (not new)
"depends_on": "eval:doc.__islocal"               # New (unsaved)
"depends_on": "customer"                          # Simple: if customer has value

# Mandatory conditionally
"mandatory_depends_on": "eval:doc.loan_type == 'Home Loan'"

# Read-only conditionally
"read_only_depends_on": "eval:doc.docstatus == 1"
```

## 12.3 Dynamic Link Pattern

```python
# The "type selector" field
{
    "fieldname": "party_type",
    "fieldtype": "Link",
    "label": "Party Type",
    "options": "DocType",
    "reqd": 1
},
# The dynamic link that changes based on party_type
{
    "fieldname": "party",
    "fieldtype": "Dynamic Link",
    "label": "Party",
    "options": "party_type",    # Points to the field containing the DocType name
    "reqd": 1
}
# If party_type = "Customer", the party field becomes a Link to Customer
# If party_type = "Supplier", the party field becomes a Link to Supplier
```

## 12.4 Naming Conventions

```
# DocType names: Title Case with spaces
"Loan Application", "Sales Order Item", "Loan Repayment Schedule"

# Field names: snake_case
"applicant_name", "loan_amount", "total_payable_interest"

# Module names: Title Case
"Custom", "Accounts", "Selling"

# Naming Series: PREFIX-.YYYY.-.####
"LA-.YYYY.-.####", "SO-.YYYY.-.####", "INV-.YYYY.-.####"

# Custom field prefix: custom_
"custom_delivery_priority", "custom_shipping_carrier"

# Child table DocType: Parent Name + Description
"Sales Order Item", "Loan Application Guarantor"
```

## 12.5 Child Table Aggregation in Server Script

```python
create_document(doctype="Server Script", data={
    "name": "Sales Order - Calculate Custom Totals",
    "script_type": "DocType Event",
    "reference_doctype": "Sales Order",
    "doctype_event": "Before Save",
    "disabled": 0,
    "script": """
# Sum child table values
total_qty = 0
total_weight = 0
for item in doc.items:
    total_qty += item.qty or 0
    total_weight += (item.total_weight or 0)

doc.total_qty = total_qty
doc.custom_total_weight = total_weight

# Find max/min in child table
if doc.items:
    max_rate = max(item.rate for item in doc.items)
    doc.custom_highest_rate = max_rate
"""
})
```

## 12.6 Dashboard (DocType Links)

To show linked documents in a DocType's dashboard, create a "DocType Link" or use the dashboard_fields approach via Custom Field:

```python
# Method: Use Client Script to add dashboard links
create_document(doctype="Client Script", data={
    "dt": "Customer",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Customer', {
    refresh(frm) {
        // Add a dashboard link to show Loan Applications
        frm.dashboard.add_transactions({
            'label': __('Loans'),
            'items': ['Loan Application']
        });
    }
});
"""
})
```

## 12.7 Workspace Creation

```python
create_document(doctype="Workspace", data={
    "name": "Loan Management",
    "label": "Loan Management",
    "module": "Custom",
    "icon": "bank",
    "is_hidden": 0,
    "public": 1,
    "for_user": "",
    "links": [
        {
            "type": "DocType",
            "label": "Loan Application",
            "link_to": "Loan Application",
            "link_type": "DocType",
            "onboard": 1,
            "is_query_report": 0
        },
        {
            "type": "DocType",
            "label": "Loan Settings",
            "link_to": "Loan Settings",
            "link_type": "DocType"
        },
        {
            "type": "Report",
            "label": "Loan Summary",
            "link_to": "Loan Application Summary",
            "link_type": "Report",
            "is_query_report": 1,
            "dependencies": "Loan Application"
        }
    ],
    "shortcuts": [
        {
            "type": "DocType",
            "label": "New Loan Application",
            "link_to": "Loan Application",
            "doc_view": "New"
        },
        {
            "type": "Report",
            "label": "Pending Approvals",
            "link_to": "Loan Application",
            "doc_view": "List",
            "filters_json": "{\"status\": \"Pending Approval\"}"
        }
    ]
})
```

## 12.8 Module Def

```python
create_document(doctype="Module Def", data={
    "module_name": "Loan Management",
    "app_name": "frappe",
    "custom": 1
})
```

## 12.9 Letter Head

```python
create_document(doctype="Letter Head", data={
    "letter_head_name": "Company Letterhead",
    "source": "HTML",
    "content": """
<div style="text-align: center; padding: 10px 0; border-bottom: 2px solid #2c3e50;">
    <h2 style="margin: 0; color: #2c3e50;">My Company Ltd.</h2>
    <p style="margin: 5px 0; color: #666;">123 Business Street, City, Country</p>
    <p style="margin: 2px 0; color: #666;">Phone: +1-234-567-8900 | Email: info@company.com</p>
</div>
""",
    "footer": """
<div style="text-align: center; border-top: 1px solid #ddd; padding-top: 10px; font-size: 10px; color: #999;">
    <p>Registered Office: 123 Business Street | CIN: U12345MH2020PTC123456 | GSTIN: 27XXXXX1234X1ZX</p>
</div>
""",
    "is_default": 1,
    "disabled": 0
})
```

## 12.10 Translation

```python
create_document(doctype="Translation", data={
    "language": "hi",
    "source_text": "Loan Application",
    "translated_text": "ऋण आवेदन"
})
```

## 12.11 Number Card (Dashboard Widget)

```python
create_document(doctype="Number Card", data={
    "name": "Pending Loan Applications",
    "label": "Pending Loans",
    "document_type": "Loan Application",
    "function": "Count",
    "aggregate_function_based_on": "",
    "filters_json": "[['Loan Application', 'status', '=', 'Pending Approval']]",
    "is_public": 1,
    "show_percentage_stats": 1,
    "stats_time_interval": "Monthly",
    "color": "#FF6B6B"
})
```

---

# ============================================================
# 13. DEBUGGING & TESTING PATTERNS
# ============================================================

## 13.1 Verify DocType Creation

```python
# Server Script or bench console
doc = frappe.get_doc("DocType", "Loan Application")
print(f"DocType: {doc.name}")
print(f"Module: {doc.module}")
print(f"Fields: {len(doc.fields)}")
for f in doc.fields:
    print(f"  {f.fieldname} ({f.fieldtype}) - required: {f.reqd}")

# Check if DocType exists
if frappe.db.exists("DocType", "Loan Application"):
    print("DocType exists")
```

## 13.2 Test Client Scripts

```javascript
// In browser console (F12):

// Check if client script is loaded
console.log(cur_frm.script_manager.scripts);

// Manually trigger refresh
cur_frm.trigger('refresh');

// Check field properties
console.log(cur_frm.fields_dict.loan_amount.df);

// Check field value
console.log(cur_frm.doc.loan_amount);

// Test set_value
cur_frm.set_value('status', 'Approved');

// Check if field is visible
console.log(cur_frm.fields_dict.collateral_type.disp_status);
```

## 13.3 Test Server Scripts

```python
# Check if server script exists and is enabled
scripts = frappe.get_all("Server Script",
    filters={"reference_doctype": "Loan Application", "disabled": 0},
    fields=["name", "script_type", "doctype_event"]
)
print(scripts)

# Test API-type server script
import requests
response = requests.post(
    "https://your-site.com/api/method/get_loan_summary",
    json={"applicant": "CUST-001"},
    headers={"Authorization": "token api_key:api_secret"}
)
print(response.json())

# Check error log for server script errors
errors = frappe.get_all("Error Log",
    filters={"method": ["like", "%Server Script%"]},
    fields=["name", "error", "creation"],
    order_by="creation desc",
    limit=5
)
```

## 13.4 Common Errors and Fixes

### Error: "Value missing for required field: X"

```python
# Cause: A required field is not being set
# Fix: Ensure all reqd=1 fields have values in data
# Common missing fields: naming_series, company, currency

# For DocType creation, ensure:
data = {
    "naming_series": "LA-.YYYY.-.####",  # If naming_rule uses naming_series
    "company": "Your Company",            # If company field is reqd
    # ... all other reqd fields
}
```

### Error: "Permission Denied"

```python
# Cause: Current user doesn't have permission
# Fix: Check permissions
frappe.has_permission("Loan Application", "create")  # Returns True/False

# Or create with ignore_permissions
doc = frappe.get_doc({...})
doc.insert(ignore_permissions=True)

# Or add permission
create_document(doctype="Custom DocPerm", data={
    "parent": "Loan Application",
    "parenttype": "DocType",
    "parentfield": "permissions",
    "role": "System Manager",
    "read": 1, "write": 1, "create": 1
})
```

### Error: "Duplicate Name"

```python
# Cause: Document with that name already exists
# Fix: Check existence before creating
if not frappe.db.exists("DocType", "Loan Application"):
    create_document(doctype="DocType", data={...})

# Or use a unique naming pattern
"autoname": "hash"  # Random hash, always unique
```

### Error: "Link Field options must be a valid DocType"

```python
# Cause: Link field options points to non-existent DocType
# Fix: Create the target DocType first, or use correct name
# Wrong:
{"fieldtype": "Link", "options": "Customers"}  # Wrong - not a DocType
# Right:
{"fieldtype": "Link", "options": "Customer"}    # Correct DocType name
```

### Error: "Child table DocType not found"

```python
# Cause: Table field references a child DocType that doesn't exist
# Fix: Create child DocType (istable=1) BEFORE parent DocType
# Step 1: create_document(doctype="DocType", data={"name": "My Child", "istable": 1, ...})
# Step 2: create_document(doctype="DocType", data={"name": "My Parent", fields: [{"fieldtype": "Table", "options": "My Child"}]})
```

### Error: "Cannot edit standard fields"

```python
# Cause: Trying to modify a standard DocType's field directly
# Fix: Use Property Setter or Custom Field instead
# Don't modify Sales Order DocType directly
# Use Property Setter to change field properties
# Use Custom Field to add new fields
```

### Error: "Workflow not applicable"

```python
# Cause: Workflow state field doesn't exist on DocType
# Fix: Add workflow_state field to DocType
create_document(doctype="Custom Field", data={
    "dt": "Loan Application",
    "fieldname": "workflow_state",
    "fieldtype": "Link",
    "label": "Workflow State",
    "options": "Workflow State",
    "hidden": 1,
    "no_copy": 1,
    "allow_on_submit": 1,
    "insert_after": "amended_from"
})
```

## 13.5 Debugging via Error Log

```python
# Create server script to check error logs
create_document(doctype="Server Script", data={
    "name": "Check Recent Errors",
    "script_type": "API",
    "api_method": "check_errors",
    "allow_guest": 0,
    "script": """
errors = frappe.get_all('Error Log',
    fields=['name', 'error', 'method', 'creation'],
    order_by='creation desc',
    limit=10
)
frappe.response['message'] = errors
"""
})
```

## 13.6 Bench Console Commands

```bash
# Open bench console
bench console

# Inside console:
import frappe

# Check DocType
frappe.get_meta("Loan Application").as_dict()

# List all custom DocTypes
frappe.get_all("DocType", filters={"custom": 1}, pluck="name")

# List all Client Scripts
frappe.get_all("Client Script", fields=["name", "dt", "script_type", "enabled"])

# List all Server Scripts
frappe.get_all("Server Script", fields=["name", "script_type", "reference_doctype", "disabled"])

# Execute a server script manually
doc = frappe.get_doc("Loan Application", "LA-2024-0001")
doc.run_method("before_save")

# Clear cache
frappe.clear_cache()

# Rebuild DocType
frappe.reload_doctype("Loan Application")
```

---

# ============================================================
# 14. ADDITIONAL DOCTYPES & PATTERNS
# ============================================================

## 14.1 Single DocType (Settings Page)

```python
create_document(doctype="DocType", data={
    "name": "Loan Settings",
    "module": "Custom",
    "custom": 1,
    "issingle": 1,
    "fields": [
        {"fieldname": "default_interest_rate", "fieldtype": "Float", "label": "Default Interest Rate (%)", "default": "12"},
        {"fieldname": "max_loan_amount", "fieldtype": "Currency", "label": "Maximum Loan Amount"},
        {"fieldname": "min_loan_amount", "fieldtype": "Currency", "label": "Minimum Loan Amount", "default": "10000"},
        {"fieldname": "section_break_1", "fieldtype": "Section Break", "label": "Notification Settings"},
        {"fieldname": "send_approval_notification", "fieldtype": "Check", "label": "Send Approval Notification", "default": "1"},
        {"fieldname": "notification_email", "fieldtype": "Data", "label": "Notification Email", "options": "Email", "depends_on": "eval:doc.send_approval_notification"},
        {"fieldname": "section_break_2", "fieldtype": "Section Break", "label": "Loan Types"},
        {"fieldname": "enabled_loan_types", "fieldtype": "Small Text", "label": "Enabled Loan Types", "description": "One per line"}
    ],
    "permissions": [
        {"role": "System Manager", "read": 1, "write": 1, "create": 1}
    ]
})

# Access single DocType values:
# frappe.db.get_single_value("Loan Settings", "default_interest_rate")
```

## 14.2 Tree DocType

```python
create_document(doctype="DocType", data={
    "name": "Loan Category",
    "module": "Custom",
    "custom": 1,
    "is_tree": 1,
    "naming_rule": "By fieldname",
    "autoname": "field:category_name",
    "nsm_parent_field": "parent_loan_category",
    "fields": [
        {"fieldname": "category_name", "fieldtype": "Data", "label": "Category Name", "reqd": 1},
        {"fieldname": "parent_loan_category", "fieldtype": "Link", "label": "Parent Category", "options": "Loan Category"},
        {"fieldname": "description", "fieldtype": "Small Text", "label": "Description"},
        {"fieldname": "max_amount", "fieldtype": "Currency", "label": "Maximum Amount"},
        {"fieldname": "default_interest_rate", "fieldtype": "Float", "label": "Default Interest Rate"}
    ],
    "permissions": [
        {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}
    ]
})
```

## 14.3 Amendment Pattern (for Submittable DocTypes)

When creating a submittable DocType, always include the `amended_from` field:

```python
{
    "fieldname": "amended_from",
    "fieldtype": "Link",
    "label": "Amended From",
    "options": "Your DocType Name",  # Same as parent DocType
    "read_only": 1,
    "no_copy": 1,
    "print_hide": 1
}
```

## 14.4 Common ERPNext DocTypes to Link To

| DocType | Common Fields |
|---------|--------------|
| Customer | customer_name, email_id, mobile_no, customer_group, territory |
| Supplier | supplier_name, email_id, mobile_no, supplier_group |
| Item | item_name, item_group, stock_uom, standard_rate |
| Employee | employee_name, department, designation, branch, company |
| Company | company_name, default_currency, country |
| User | full_name, email |
| Sales Order | customer, grand_total, delivery_date, status |
| Purchase Order | supplier, grand_total, schedule_date, status |
| Sales Invoice | customer, grand_total, due_date, status |
| Purchase Invoice | supplier, grand_total, due_date, status |
| Journal Entry | voucher_type, total_debit, total_credit |
| Payment Entry | payment_type, party_type, party, paid_amount |
| Project | project_name, status, expected_start_date, expected_end_date |
| Task | subject, project, status, priority |
| Lead | lead_name, email_id, mobile_no, source, status |
| Opportunity | opportunity_from, party_name, opportunity_type, status |
| Address | address_line1, city, state, country, pincode |
| Contact | first_name, last_name, email_id, mobile_no |
| Territory | territory_name, parent_territory |
| Branch | branch |
| Department | department_name, company |
| Designation | designation_name |
| Currency | currency_name, symbol, enabled |
| Warehouse | warehouse_name, company, is_group |
| Cost Center | cost_center_name, company, is_group |
| Account | account_name, company, root_type, account_type, is_group |

## 14.5 Dynamic Link Setup Pattern

For scenarios where the link target changes based on another field:

```python
# Common pattern: Party Type + Party
{"fieldname": "party_type", "fieldtype": "Link", "label": "Party Type", "options": "DocType",
 "reqd": 1},
{"fieldname": "party", "fieldtype": "Dynamic Link", "label": "Party", "options": "party_type",
 "reqd": 1},
{"fieldname": "party_name", "fieldtype": "Data", "label": "Party Name", "read_only": 1}

# With Client Script to fetch name:
create_document(doctype="Client Script", data={
    "dt": "Your DocType",
    "script_type": "Form",
    "enabled": 1,
    "script": """
frappe.ui.form.on('Your DocType', {
    party(frm) {
        if (frm.doc.party && frm.doc.party_type) {
            frappe.db.get_value(frm.doc.party_type, frm.doc.party, 'name', (r) => {
                // For Customer: fetch customer_name
                // For Supplier: fetch supplier_name
                let name_field = frm.doc.party_type === 'Customer' ? 'customer_name' : 'supplier_name';
                frappe.db.get_value(frm.doc.party_type, frm.doc.party, name_field, (r) => {
                    frm.set_value('party_name', r[name_field]);
                });
            });
        }
    }
});
"""
})
```

## 14.6 Table MultiSelect Pattern

```python
# Child DocType for multi-select
create_document(doctype="DocType", data={
    "name": "Loan Application Tag",
    "module": "Custom",
    "custom": 1,
    "istable": 1,
    "fields": [
        {"fieldname": "tag", "fieldtype": "Link", "label": "Tag", "options": "Tag",
         "in_list_view": 1, "reqd": 1}
    ]
})

# In parent DocType fields:
{
    "fieldname": "tags",
    "fieldtype": "Table MultiSelect",
    "label": "Tags",
    "options": "Loan Application Tag"
}
```

---

# ============================================================
# 15. QUICK REFERENCE: create_document CHEAT SHEET
# ============================================================

```python
# DocType
create_document(doctype="DocType", data={"name": "...", "module": "Custom", "custom": 1, "fields": [...], "permissions": [...]})

# Custom Field
create_document(doctype="Custom Field", data={"dt": "Target DocType", "fieldname": "custom_xxx", "fieldtype": "Data", "label": "...", "insert_after": "field_name"})

# Client Script
create_document(doctype="Client Script", data={"dt": "Target DocType", "script_type": "Form", "enabled": 1, "script": "..."})

# Server Script (DocType Event)
create_document(doctype="Server Script", data={"script_type": "DocType Event", "reference_doctype": "...", "doctype_event": "Before Save", "script": "..."})

# Server Script (API)
create_document(doctype="Server Script", data={"script_type": "API", "api_method": "method_name", "script": "..."})

# Server Script (Scheduled)
create_document(doctype="Server Script", data={"script_type": "Scheduled", "event_frequency": "Daily", "script": "..."})

# Workflow
create_document(doctype="Workflow", data={"document_type": "...", "is_active": 1, "workflow_state_field": "workflow_state", "states": [...], "transitions": [...]})

# Print Format
create_document(doctype="Print Format", data={"doc_type": "...", "print_format_type": "Jinja", "custom_format": 1, "html": "..."})

# Notification
create_document(doctype="Notification", data={"document_type": "...", "event": "Value Change", "value_changed": "status", "channel": "Email", "recipients": [...], "subject": "...", "message": "..."})

# Web Form
create_document(doctype="Web Form", data={"doc_type": "...", "title": "...", "published": 1, "web_form_fields": [...]})

# Property Setter
create_document(doctype="Property Setter", data={"doctype_or_field": "DocField", "doc_type": "...", "field_name": "...", "property": "hidden", "property_type": "Check", "value": "1"})

# Report
create_document(doctype="Report", data={"ref_doctype": "...", "report_type": "Query Report", "query": "SELECT ..."})

# Role
create_document(doctype="Role", data={"role_name": "...", "desk_access": 1, "is_custom": 1})

# Custom DocPerm
create_document(doctype="Custom DocPerm", data={"parent": "DocType Name", "parenttype": "DocType", "parentfield": "permissions", "role": "...", "read": 1, "write": 1, "create": 1})

# Workspace
create_document(doctype="Workspace", data={"name": "...", "label": "...", "module": "Custom", "links": [...], "shortcuts": [...]})

# Number Card
create_document(doctype="Number Card", data={"document_type": "...", "function": "Count", "filters_json": "...", "label": "..."})

# User Permission
create_document(doctype="User Permission", data={"user": "user@example.com", "allow": "Company", "for_value": "My Company"})

# Translation
create_document(doctype="Translation", data={"language": "hi", "source_text": "...", "translated_text": "..."})

# Letter Head
create_document(doctype="Letter Head", data={"letter_head_name": "...", "source": "HTML", "content": "...", "is_default": 1})

# Workflow State
create_document(doctype="Workflow State", data={"workflow_state_name": "...", "style": "Success"})

# Workflow Action Master
create_document(doctype="Workflow Action Master", data={"workflow_action_name": "Approve"})

# Module Def
create_document(doctype="Module Def", data={"module_name": "...", "app_name": "frappe", "custom": 1})
```

---

# END OF FRAPPE DEVELOPER RA