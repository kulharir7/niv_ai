"""Import/Export Customizations Helper for Niv AI.

Export and import Custom Fields, Property Setters, Client Scripts, etc.
Usage in run_python_code:
    from niv_ai.niv_core.tools.customization_io import export_customizations, import_customizations
"""
import frappe
import json
from typing import Optional


CUSTOMIZATION_DOCTYPES = [
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Server Script",
    "Custom DocPerm",
]


def export_customizations(doctype: str = None, include_types: list = None) -> dict:
    """Export all customizations for a DocType or all DocTypes.
    
    Args:
        doctype: Specific DocType to export customizations for (optional)
        include_types: List of customization types to include (default: all)
    
    Returns:
        dict with exported customizations, ready to be saved as JSON
    """
    types_to_export = include_types or CUSTOMIZATION_DOCTYPES
    result = {"exported_at": str(frappe.utils.now()), "customizations": {}}
    
    for ctype in types_to_export:
        if ctype not in CUSTOMIZATION_DOCTYPES:
            continue
        
        filters = {}
        if doctype:
            # Each customization type has a different field for the parent DocType
            if ctype == "Custom Field":
                filters["dt"] = doctype
            elif ctype == "Property Setter":
                filters["doc_type"] = doctype
            elif ctype in ("Client Script", "Server Script"):
                filters["dt"] = doctype
            elif ctype == "Custom DocPerm":
                filters["parent"] = doctype
        
        try:
            docs = frappe.get_all(ctype, filters=filters, fields=["name"])
            items = []
            for d in docs:
                full_doc = frappe.get_doc(ctype, d.name)
                # Convert to dict, remove internal fields
                doc_dict = full_doc.as_dict()
                for key in ["creation", "modified", "modified_by", "owner", "docstatus", "idx"]:
                    doc_dict.pop(key, None)
                items.append(doc_dict)
            
            if items:
                result["customizations"][ctype] = items
        except Exception as e:
            result["customizations"][ctype] = {"error": str(e)}
    
    total = sum(len(v) for v in result["customizations"].values() if isinstance(v, list))
    result["total_items"] = total
    result["doctype_filter"] = doctype or "All"
    
    return result


def import_customizations(data: dict, dry_run: bool = True) -> dict:
    """Import customizations from exported JSON.
    
    Args:
        data: Dict from export_customizations()
        dry_run: If True, only validate without importing
    
    Returns:
        dict with import results
    """
    customizations = data.get("customizations", {})
    if not customizations:
        return {"status": "error", "message": "No customizations found in data"}
    
    results = {"imported": 0, "skipped": 0, "errors": [], "details": []}
    
    for ctype, items in customizations.items():
        if not isinstance(items, list):
            continue
        
        for item in items:
            name = item.get("name", "")
            
            if dry_run:
                exists = frappe.db.exists(ctype, name)
                results["details"].append({
                    "type": ctype,
                    "name": name,
                    "action": "update" if exists else "create"
                })
                results["imported"] += 1
                continue
            
            try:
                if frappe.db.exists(ctype, name):
                    # Update existing
                    doc = frappe.get_doc(ctype, name)
                    doc.update(item)
                    doc.save(ignore_permissions=True)
                    results["details"].append({"type": ctype, "name": name, "action": "updated"})
                else:
                    # Create new
                    item["doctype"] = ctype
                    doc = frappe.get_doc(item)
                    doc.insert(ignore_permissions=True)
                    results["details"].append({"type": ctype, "name": doc.name, "action": "created"})
                results["imported"] += 1
            except Exception as e:
                results["errors"].append({"type": ctype, "name": name, "error": str(e)})
    
    if not dry_run:
        frappe.db.commit()
    
    results["status"] = "preview" if dry_run else "success"
    results["message"] = f"{'Would import' if dry_run else 'Imported'} {results['imported']} customizations"
    
    return results


def list_customizations(doctype: str = None) -> dict:
    """Quick summary of customizations for a DocType.
    
    Args:
        doctype: DocType to check (optional, shows all if not specified)
    
    Returns:
        dict with counts per customization type
    """
    result = {}
    for ctype in CUSTOMIZATION_DOCTYPES:
        filters = {}
        if doctype:
            if ctype == "Custom Field":
                filters["dt"] = doctype
            elif ctype == "Property Setter":
                filters["doc_type"] = doctype
            elif ctype in ("Client Script", "Server Script"):
                filters["dt"] = doctype
            elif ctype == "Custom DocPerm":
                filters["parent"] = doctype
        
        try:
            count = frappe.db.count(ctype, filters)
            if count:
                result[ctype] = count
        except Exception:
            pass
    
    result["total"] = sum(result.values())
    result["doctype"] = doctype or "All"
    return result
