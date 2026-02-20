"""Impact Analysis Helper for Niv AI Dev Mode.

Analyzes dependencies and impacts before making changes to DocTypes, fields, or documents.
Usage in run_python_code:
    from niv_ai.niv_core.tools.impact_analysis import analyze_doctype_impact, analyze_field_impact
"""
import frappe
import json


def analyze_doctype_impact(doctype: str) -> dict:
    """Analyze what depends on a DocType - Links, Child Tables, Scripts, Print Formats, etc.
    
    Args:
        doctype: The DocType to analyze
    
    Returns:
        dict with dependency information
    """
    if not frappe.db.exists("DocType", doctype):
        return {"status": "error", "message": f"DocType '{doctype}' not found"}
    
    result = {
        "doctype": doctype,
        "dependencies": {},
        "total_dependencies": 0
    }
    
    # 1. Link fields pointing to this DocType (other DocTypes that reference this one)
    link_fields = frappe.get_all("DocField", 
        filters={"fieldtype": "Link", "options": doctype, "parent": ["!=", doctype]},
        fields=["parent", "fieldname", "label"],
        limit=50
    )
    if link_fields:
        result["dependencies"]["linked_from"] = [
            {"doctype": f.parent, "field": f.fieldname, "label": f.label or f.fieldname}
            for f in link_fields
        ]
    
    # 2. Dynamic Link fields
    dynamic_links = frappe.db.sql("""
        SELECT parent, fieldname FROM `tabDocField` 
        WHERE fieldtype='Dynamic Link' AND parent != %s
        LIMIT 20
    """, doctype, as_dict=True)
    if dynamic_links:
        result["dependencies"]["dynamic_links"] = [
            {"doctype": d.parent, "field": d.fieldname} for d in dynamic_links[:10]
        ]
    
    # 3. Child Tables
    child_tables = frappe.get_all("DocField",
        filters={"fieldtype": "Table", "options": doctype},
        fields=["parent", "fieldname"],
        limit=20
    )
    if child_tables:
        result["dependencies"]["used_as_child_table_in"] = [
            {"doctype": f.parent, "field": f.fieldname} for f in child_tables
        ]
    
    # 4. Custom Fields on this DocType
    custom_fields = frappe.db.count("Custom Field", {"dt": doctype})
    if custom_fields:
        result["dependencies"]["custom_fields"] = custom_fields
    
    # 5. Property Setters
    property_setters = frappe.db.count("Property Setter", {"doc_type": doctype})
    if property_setters:
        result["dependencies"]["property_setters"] = property_setters
    
    # 6. Client Scripts
    client_scripts = frappe.get_all("Client Script", 
        filters={"dt": doctype}, fields=["name"], limit=10)
    if client_scripts:
        result["dependencies"]["client_scripts"] = [s.name for s in client_scripts]
    
    # 7. Server Scripts
    server_scripts = frappe.get_all("Server Script",
        filters={"reference_doctype": doctype}, fields=["name"], limit=10)
    if server_scripts:
        result["dependencies"]["server_scripts"] = [s.name for s in server_scripts]
    
    # 8. Print Formats
    print_formats = frappe.get_all("Print Format",
        filters={"doc_type": doctype, "standard": "No"}, fields=["name"], limit=10)
    if print_formats:
        result["dependencies"]["print_formats"] = [p.name for p in print_formats]
    
    # 9. Document count
    try:
        doc_count = frappe.db.count(doctype)
        result["document_count"] = doc_count
    except Exception:
        result["document_count"] = "unknown"
    
    # Calculate total
    total = 0
    for key, val in result["dependencies"].items():
        if isinstance(val, list):
            total += len(val)
        elif isinstance(val, int):
            total += val
    result["total_dependencies"] = total
    
    # Risk assessment
    if total > 20 or (isinstance(result.get("document_count"), int) and result["document_count"] > 1000):
        result["risk"] = "HIGH"
        result["warning"] = "This DocType has many dependencies. Changes may have wide impact."
    elif total > 5:
        result["risk"] = "MEDIUM"
    else:
        result["risk"] = "LOW"
    
    return result


def analyze_field_impact(doctype: str, fieldname: str) -> dict:
    """Analyze impact of changing/removing a specific field.
    
    Args:
        doctype: The DocType containing the field
        fieldname: The field to analyze
    
    Returns:
        dict with dependency info for this field
    """
    result = {
        "doctype": doctype,
        "fieldname": fieldname,
        "dependencies": {},
        "total_dependencies": 0
    }
    
    # Get field meta
    try:
        meta = frappe.get_meta(doctype)
        field = meta.get_field(fieldname)
        if not field:
            return {"status": "error", "message": f"Field '{fieldname}' not found in {doctype}"}
        result["field_type"] = field.fieldtype
        result["label"] = field.label
        result["is_custom"] = bool(frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}))
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    # 1. Property Setters on this field
    prop_setters = frappe.get_all("Property Setter",
        filters={"doc_type": doctype, "field_name": fieldname},
        fields=["name", "property", "value"], limit=10)
    if prop_setters:
        result["dependencies"]["property_setters"] = [
            {"name": p.name, "property": p.property, "value": str(p.value)[:50]}
            for p in prop_setters
        ]
    
    # 2. If it's a Link field, what references it
    if field.fieldtype == "Link" and field.options:
        result["links_to"] = field.options
        # Count how many docs use this field
        try:
            used_count = frappe.db.sql(f"""
                SELECT COUNT(*) FROM `tab{doctype}` 
                WHERE `{fieldname}` IS NOT NULL AND `{fieldname}` != ''
            """)[0][0]
            result["values_in_use"] = used_count
        except Exception:
            pass
    
    # 3. Check if field is used in any report
    # (simplified check - look for field name in report queries)
    
    # 4. Check if any fetch_from references this field
    fetch_refs = frappe.get_all("DocField",
        filters={"fetch_from": ["like", f"%{fieldname}%"]},
        fields=["parent", "fieldname", "fetch_from"], limit=10)
    if fetch_refs:
        result["dependencies"]["fetched_by"] = [
            {"doctype": f.parent, "field": f.fieldname, "fetch_from": f.fetch_from}
            for f in fetch_refs
        ]
    
    total = sum(len(v) if isinstance(v, list) else 0 for v in result["dependencies"].values())
    result["total_dependencies"] = total
    
    return result
