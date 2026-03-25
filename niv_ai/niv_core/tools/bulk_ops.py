"""Bulk Operations Helper for Niv AI.

Safe bulk operations that run_python_code can import.
Usage in run_python_code:
    from niv_ai.niv_core.tools.bulk_ops import bulk_update, bulk_create, bulk_delete

All operations have safety limits and return detailed results.
"""
import frappe
import json
from typing import Optional


# Safety limits
MAX_BULK_OPS = 50  # Max documents per bulk operation
MAX_PREVIEW = 10   # Max docs to show in preview


def bulk_update(doctype: str, filters: dict, data: dict, limit: int = 50, dry_run: bool = True) -> dict:
    """Bulk update documents matching filters.
    
    Args:
        doctype: Document type (e.g., 'Loan', 'Customer')
        filters: Frappe filters dict (e.g., {'status': 'Active', 'branch': 'Mumbai'})
        data: Fields to update (e.g., {'status': 'Closed'})
        limit: Max documents to update (capped at 50)
        dry_run: If True, only preview changes without applying
    
    Returns:
        dict with 'affected', 'preview', 'status' keys
    """
    limit = min(limit, MAX_BULK_OPS)
    
    if not doctype or not filters or not data:
        return {"status": "error", "message": "doctype, filters, and data are required"}
    
    # Get matching documents
    try:
        docs = frappe.get_all(doctype, filters=filters, fields=["name"] + list(data.keys()), limit=limit)
    except Exception as e:
        return {"status": "error", "message": f"Failed to query: {str(e)}"}
    
    if not docs:
        return {"status": "no_match", "message": f"No {doctype} documents match the given filters", "affected": 0}
    
    # Build preview with old → new values
    preview = []
    for doc in docs[:MAX_PREVIEW]:
        changes = {}
        for field, new_val in data.items():
            old_val = doc.get(field, "N/A")
            if str(old_val) != str(new_val):
                changes[field] = f"{old_val} → {new_val}"
        if changes:
            preview.append({"name": doc.name, "changes": changes})
    
    if dry_run:
        return {
            "status": "preview",
            "message": f"DRY RUN: {len(docs)} {doctype} documents would be updated",
            "affected": len(docs),
            "preview": preview,
            "note": "Call with dry_run=False to apply changes"
        }
    
    # Apply updates
    updated = 0
    errors = []
    for doc in docs:
        try:
            frappe.db.set_value(doctype, doc.name, data, update_modified=True)
            updated += 1
        except Exception as e:
            errors.append({"name": doc.name, "error": str(e)})
    
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": f"Updated {updated}/{len(docs)} {doctype} documents",
        "affected": updated,
        "errors": errors[:5] if errors else [],
        "preview": preview
    }


def bulk_create(doctype: str, records: list, dry_run: bool = True) -> dict:
    """Bulk create documents.
    
    Args:
        doctype: Document type
        records: List of dicts, each containing field values for one document
        dry_run: If True, only validate without creating
    
    Returns:
        dict with 'created', 'status' keys
    """
    if not records:
        return {"status": "error", "message": "records list is empty"}
    
    if len(records) > MAX_BULK_OPS:
        return {"status": "error", "message": f"Max {MAX_BULK_OPS} records per batch. Got {len(records)}."}
    
    if dry_run:
        return {
            "status": "preview",
            "message": f"DRY RUN: Would create {len(records)} {doctype} documents",
            "count": len(records),
            "sample": records[:3],
            "note": "Call with dry_run=False to create"
        }
    
    created = []
    errors = []
    for i, record in enumerate(records):
        try:
            doc = frappe.get_doc({"doctype": doctype, **record})
            doc.insert(ignore_permissions=False)
            created.append(doc.name)
        except Exception as e:
            errors.append({"index": i, "error": str(e)})
    
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": f"Created {len(created)}/{len(records)} {doctype} documents",
        "created": created[:MAX_PREVIEW],
        "errors": errors[:5] if errors else []
    }


def bulk_delete(doctype: str, filters: dict, limit: int = 50, dry_run: bool = True) -> dict:
    """Bulk delete documents matching filters.
    
    Args:
        doctype: Document type
        filters: Frappe filters dict
        limit: Max documents to delete (capped at 50)
        dry_run: If True, only preview without deleting
    
    Returns:
        dict with 'affected', 'status' keys
    """
    limit = min(limit, MAX_BULK_OPS)
    
    if not doctype or not filters:
        return {"status": "error", "message": "doctype and filters are required"}
    
    try:
        docs = frappe.get_all(doctype, filters=filters, fields=["name"], limit=limit)
    except Exception as e:
        return {"status": "error", "message": f"Failed to query: {str(e)}"}
    
    if not docs:
        return {"status": "no_match", "message": f"No {doctype} documents match filters", "affected": 0}
    
    if dry_run:
        return {
            "status": "preview",
            "message": f"DRY RUN: {len(docs)} {doctype} documents would be DELETED",
            "affected": len(docs),
            "names": [d.name for d in docs[:MAX_PREVIEW]],
            "note": "Call with dry_run=False to delete. THIS CANNOT BE UNDONE!"
        }
    
    deleted = 0
    errors = []
    for doc in docs:
        try:
            frappe.delete_doc(doctype, doc.name, ignore_permissions=False, force=0)
            deleted += 1
        except Exception as e:
            errors.append({"name": doc.name, "error": str(e)})
    
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": f"Deleted {deleted}/{len(docs)} {doctype} documents",
        "affected": deleted,
        "errors": errors[:5] if errors else []
    }
