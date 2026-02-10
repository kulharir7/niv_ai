import frappe
import json
from frappe.utils import getdate, nowdate, add_days, get_first_day, get_last_day


def generate_report(report_name, filters=None, limit=100):
    """Run a report and return results"""
    if not frappe.db.exists("Report", report_name):
        return {"error": f"Report '{report_name}' not found"}

    report = frappe.get_doc("Report", report_name)
    frappe.has_permission(report.ref_doctype, "read", throw=True)

    filters = filters or {}
    limit = min(int(limit), 500)

    try:
        columns, data = report.get_data(filters=filters, limit=limit, as_dict=True)

        # Format columns
        col_names = []
        for c in columns:
            if isinstance(c, dict):
                col_names.append(c.get("label", c.get("fieldname", "")))
            else:
                col_names.append(str(c))

        return {
            "report": report_name,
            "columns": col_names,
            "row_count": len(data),
            "data": data[:limit],
        }
    except Exception as e:
        return {"error": f"Failed to run report: {str(e)}"}


def report_list(module=None, doctype=None):
    """List available reports"""
    filters = {"disabled": 0}
    if module:
        filters["module"] = module
    if doctype:
        filters["ref_doctype"] = doctype

    reports = frappe.get_list(
        "Report",
        filters=filters,
        fields=["name", "report_name", "report_type", "ref_doctype", "module"],
        order_by="name ASC",
        limit_page_length=100,
    )

    return {"count": len(reports), "reports": reports}


def report_requirements(report_name):
    """Get required filters for a report"""
    if not frappe.db.exists("Report", report_name):
        return {"error": f"Report '{report_name}' not found"}

    report = frappe.get_doc("Report", report_name)

    # Get filter fields from report columns or script
    filters_info = []
    if hasattr(report, "filters") and report.filters:
        try:
            f = json.loads(report.filters) if isinstance(report.filters, str) else report.filters
            filters_info = f
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "report": report_name,
        "ref_doctype": report.ref_doctype,
        "report_type": report.report_type,
        "filters": filters_info,
    }


def analyze_business_data(doctype, metrics=None, measure_field=None, group_by=None, filters=None, period=None):
    """Custom analytics on business data"""
    frappe.has_permission(doctype, "read", throw=True)

    meta = frappe.get_meta(doctype)
    if not meta:
        return {"error": f"DocType '{doctype}' not found"}

    # Build date filter
    date_filters = filters or {}
    date_field = None
    for f in ["posting_date", "transaction_date", "creation"]:
        if meta.has_field(f):
            date_field = f
            break

    if period and date_field:
        today = getdate(nowdate())
        if period == "today":
            date_filters[date_field] = today
        elif period == "week":
            date_filters[date_field] = [">=", add_days(today, -7)]
        elif period == "month":
            date_filters[date_field] = [">=", get_first_day(today)]
        elif period == "quarter":
            date_filters[date_field] = [">=", add_days(today, -90)]
        elif period == "year":
            date_filters[date_field] = [">=", add_days(today, -365)]

    metrics = metrics or ["count"]
    result = {"doctype": doctype, "period": period, "metrics": {}}

    for metric in metrics:
        if metric == "count":
            count = frappe.db.count(doctype, filters=date_filters)
            result["metrics"]["count"] = count

        elif metric == "sum" and measure_field:
            total = frappe.db.sql("""
                SELECT COALESCE(SUM(`{field}`), 0) as total
                FROM `tab{doctype}`
                WHERE {conditions}
            """.format(
                field=measure_field,
                doctype=doctype,
                conditions=_build_conditions(date_filters, doctype),
            ), as_dict=True)
            result["metrics"]["sum"] = total[0].total if total else 0

        elif metric == "avg" and measure_field:
            avg = frappe.db.sql("""
                SELECT COALESCE(AVG(`{field}`), 0) as average
                FROM `tab{doctype}`
                WHERE {conditions}
            """.format(
                field=measure_field,
                doctype=doctype,
                conditions=_build_conditions(date_filters, doctype),
            ), as_dict=True)
            result["metrics"]["avg"] = avg[0].average if avg else 0

    # Group by
    if group_by and meta.has_field(group_by):
        grouped = frappe.get_list(
            doctype,
            filters=date_filters,
            fields=[group_by, "count(name) as count"],
            group_by=group_by,
            order_by="count DESC",
            limit_page_length=20,
        )
        result["grouped_by"] = {group_by: grouped}

    return result


def _build_conditions(filters, doctype):
    """Build SQL WHERE conditions from filters dict"""
    if not filters:
        return "1=1"

    conditions = []
    for field, value in filters.items():
        if isinstance(value, list) and len(value) == 2:
            op, val = value
            conditions.append(f"`{field}` {op} '{val}'")
        else:
            conditions.append(f"`{field}` = '{value}'")

    return " AND ".join(conditions) if conditions else "1=1"
