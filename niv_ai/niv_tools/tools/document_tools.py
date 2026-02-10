import frappe
import json


def create_document(doctype, values):
    """Create a new document in ERPNext"""
    frappe.has_permission(doctype, "create", throw=True)

    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert()
    frappe.db.commit()

    return {
        "success": True,
        "doctype": doctype,
        "name": doc.name,
        "message": f"Created {doctype} '{doc.name}' successfully",
    }


def get_document(doctype, name, fields=None):
    """Read a document"""
    frappe.has_permission(doctype, "read", throw=True)

    doc = frappe.get_doc(doctype, name)

    if fields:
        result = {"name": doc.name, "doctype": doctype}
        for f in fields:
            result[f] = doc.get(f)
        return result

    # Return safe dict (exclude internal fields)
    data = doc.as_dict()
    exclude = {"docstatus", "idx", "doctype", "_user_tags", "_comments",
               "_assign", "_liked_by", "__onload"}
    return {k: v for k, v in data.items() if k not in exclude and not k.startswith("_")}


def update_document(doctype, name, values):
    """Update fields of an existing document"""
    frappe.has_permission(doctype, "write", throw=True)

    doc = frappe.get_doc(doctype, name)
    doc.update(values)
    doc.save()
    frappe.db.commit()

    return {
        "success": True,
        "doctype": doctype,
        "name": doc.name,
        "message": f"Updated {doctype} '{doc.name}' successfully",
    }


def delete_document(doctype, name):
    """Delete a document"""
    frappe.has_permission(doctype, "delete", throw=True)

    frappe.delete_doc(doctype, name)
    frappe.db.commit()

    return {
        "success": True,
        "message": f"Deleted {doctype} '{name}' successfully",
    }


def submit_document(doctype, name):
    """Submit a submittable document"""
    frappe.has_permission(doctype, "submit", throw=True)

    doc = frappe.get_doc(doctype, name)
    doc.submit()
    frappe.db.commit()

    return {
        "success": True,
        "doctype": doctype,
        "name": doc.name,
        "message": f"Submitted {doctype} '{doc.name}' successfully",
    }


def list_documents(doctype, filters=None, fields=None, order_by=None, limit=20):
    """List documents with filters"""
    frappe.has_permission(doctype, "read", throw=True)

    if not fields:
        fields = ["name", "creation", "modified"]
        # Try to add common fields
        meta = frappe.get_meta(doctype)
        for f in ["title", "subject", "customer", "supplier", "status",
                   "grand_total", "posting_date", "transaction_date"]:
            if meta.has_field(f):
                fields.append(f)

    result = frappe.get_list(
        doctype,
        filters=filters,
        fields=fields,
        order_by=order_by or "creation DESC",
        limit_page_length=min(int(limit), 100),
    )

    return {
        "doctype": doctype,
        "count": len(result),
        "data": result,
    }
