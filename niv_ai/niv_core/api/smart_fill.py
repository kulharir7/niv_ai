"""
Niv AI Smart Fill — Auto-suggest field values based on past data.

When user selects a Link field (e.g., Customer on Sales Invoice),
this API looks at the last N similar documents and suggests the most
common values for other fields.

Zero AI cost — pure SQL pattern matching.
"""
import frappe
from frappe import _
from collections import Counter


# Fields to watch on each DocType → which fields to suggest
# Format: { "DocType": { "trigger_field": ["suggest_field1", "suggest_field2"] } }
SMART_FILL_RULES = {
    "Sales Invoice": {
        "customer": [
            "payment_terms_template", "currency", "selling_price_list",
            "taxes_and_charges", "cost_center", "project",
        ],
        "company": ["cost_center", "letter_head"],
    },
    "Sales Order": {
        "customer": [
            "payment_terms_template", "currency", "selling_price_list",
            "taxes_and_charges", "delivery_date", "cost_center",
        ],
    },
    "Purchase Invoice": {
        "supplier": [
            "payment_terms_template", "currency", "buying_price_list",
            "taxes_and_charges", "cost_center",
        ],
    },
    "Purchase Order": {
        "supplier": [
            "payment_terms_template", "currency", "buying_price_list",
            "taxes_and_charges", "cost_center",
        ],
    },
    "Loan": {
        "applicant": [
            "loan_type", "rate_of_interest", "repayment_method",
            "cost_center",
        ],
        "loan_type": [
            "rate_of_interest", "repayment_method", "repayment_periods",
        ],
    },
    "Loan Application": {
        "applicant": ["loan_type", "company"],
        "loan_type": ["rate_of_interest", "repayment_method"],
    },
    "Journal Entry": {
        "company": ["cost_center"],
    },
    "Payment Entry": {
        "party": [
            "paid_from", "paid_to", "cost_center", "mode_of_payment",
        ],
    },
    "Delivery Note": {
        "customer": [
            "taxes_and_charges", "cost_center", "transporter",
        ],
    },
}

# How many past docs to analyze
LOOKBACK_LIMIT = 20

# Minimum confidence (percentage) to suggest a value
MIN_CONFIDENCE = 40  # 40% = at least 40% of past docs had this value


@frappe.whitelist()
def get_suggestions(doctype, trigger_field, trigger_value, existing_values=None):
    """
    Get field suggestions based on past data.

    Args:
        doctype: e.g. "Sales Invoice"
        trigger_field: e.g. "customer"
        trigger_value: e.g. "CUST-001"
        existing_values: JSON string of currently filled fields (to avoid overwriting)

    Returns:
        dict with field suggestions and confidence scores
    """
    import json

    if not doctype or not trigger_field or not trigger_value:
        return {"suggestions": []}

    # Parse existing values
    filled = {}
    if existing_values:
        if isinstance(existing_values, str):
            try:
                filled = json.loads(existing_values)
            except (json.JSONDecodeError, ValueError):
                filled = {}
        elif isinstance(existing_values, dict):
            filled = existing_values

    # Get rules for this DocType + trigger field
    rules = SMART_FILL_RULES.get(doctype, {})
    suggest_fields = rules.get(trigger_field, [])

    if not suggest_fields:
        # Try dynamic discovery — get all Link/Select fields as suggestions
        suggest_fields = _discover_suggest_fields(doctype, trigger_field)
        if not suggest_fields:
            return {"suggestions": []}

    # Filter out already-filled fields
    fields_to_check = [f for f in suggest_fields if not filled.get(f)]
    if not fields_to_check:
        return {"suggestions": []}

    # Query past documents
    suggestions = _analyze_past_data(doctype, trigger_field, trigger_value, fields_to_check)

    return {"suggestions": suggestions}


def _discover_suggest_fields(doctype, trigger_field):
    """Auto-discover which fields could be suggested (non-mandatory Link/Select fields)."""
    try:
        meta = frappe.get_meta(doctype)
        skip_fields = {
            trigger_field, "name", "owner", "creation", "modified",
            "modified_by", "docstatus", "idx", "naming_series",
            "amended_from", "company",  # company usually set first
        }
        skip_types = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table"}

        result = []
        for df in meta.fields:
            if df.fieldname in skip_fields:
                continue
            if df.fieldtype in skip_types:
                continue
            if df.reqd:  # Skip mandatory — user must fill those
                continue
            if df.fieldtype in ("Link", "Select") and not df.hidden:
                result.append(df.fieldname)

        return result[:8]  # Max 8 suggestions
    except Exception:
        return []


def _analyze_past_data(doctype, trigger_field, trigger_value, fields_to_check):
    """Analyze past documents to find common field values."""
    suggestions = []

    # Build field list for query
    all_fields = [f"`{f}`" for f in fields_to_check]
    if not all_fields:
        return suggestions

    field_list = ", ".join(all_fields)

    try:
        # Get past documents with same trigger value
        past_docs = frappe.db.sql("""
            SELECT {fields}
            FROM `tab{doctype}`
            WHERE `{trigger}` = %(trigger_val)s
            AND docstatus < 2
            ORDER BY creation DESC
            LIMIT %(limit)s
        """.format(
            fields=field_list,
            doctype=doctype,
            trigger=trigger_field,
        ), {
            "trigger_val": trigger_value,
            "limit": LOOKBACK_LIMIT,
        }, as_dict=True)

        if not past_docs:
            return suggestions

        total = len(past_docs)

        # For each field, find most common value
        for field in fields_to_check:
            values = [doc.get(field) for doc in past_docs if doc.get(field)]
            if not values:
                continue

            counter = Counter(values)
            most_common_value, count = counter.most_common(1)[0]
            confidence = round((count / total) * 100)

            if confidence >= MIN_CONFIDENCE:
                # Get field label for display
                label = _get_field_label(doctype, field)
                suggestions.append({
                    "fieldname": field,
                    "label": label,
                    "value": most_common_value,
                    "display_value": _get_display_value(doctype, field, most_common_value),
                    "confidence": confidence,
                    "based_on": total,
                })

    except Exception as e:
        frappe.log_error(f"Smart Fill query error: {e}", "Niv Smart Fill")

    # Sort by confidence descending
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    return suggestions[:6]  # Max 6 suggestions


def _get_field_label(doctype, fieldname):
    """Get human-readable field label."""
    try:
        meta = frappe.get_meta(doctype)
        df = meta.get_field(fieldname)
        if df:
            return df.label or fieldname
    except Exception:
        pass
    return fieldname.replace("_", " ").title()


def _get_display_value(doctype, fieldname, value):
    """Get display-friendly value (resolve Link names to titles)."""
    if not value:
        return value
    try:
        meta = frappe.get_meta(doctype)
        df = meta.get_field(fieldname)
        if df and df.fieldtype == "Link" and df.options:
            # Try to get the title/name of the linked doc
            linked_meta = frappe.get_meta(df.options)
            title_field = linked_meta.get_title_field()
            if title_field and title_field != "name":
                title = frappe.db.get_value(df.options, value, title_field)
                if title and title != value:
                    return f"{title} ({value})"
    except Exception:
        pass
    return str(value)


@frappe.whitelist()
def get_smart_fill_config():
    """Return which DocTypes have smart fill enabled."""
    # Return all configured DocTypes + any DocType with >100 docs
    configured = list(SMART_FILL_RULES.keys())

    # Also check if user has custom rules saved (future)
    return {
        "enabled_doctypes": configured,
        "min_confidence": MIN_CONFIDENCE,
    }


@frappe.whitelist()
def add_custom_rule(doctype, trigger_field, suggest_fields):
    """Allow admin to add custom smart fill rules (future feature)."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Manager can modify smart fill rules"))
    # TODO: Save to Niv Settings or separate DocType
    return {"success": True}
