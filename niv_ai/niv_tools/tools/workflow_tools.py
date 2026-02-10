import frappe


def run_workflow(doctype, name, action):
    """Trigger a workflow action on a document"""
    frappe.has_permission(doctype, "write", throw=True)

    doc = frappe.get_doc(doctype, name)

    # Check if workflow exists
    workflow = frappe.get_all(
        "Workflow",
        filters={"document_type": doctype, "is_active": 1},
        limit=1,
    )

    if not workflow:
        return {"error": f"No active workflow found for {doctype}"}

    try:
        from frappe.model.workflow import apply_workflow
        apply_workflow(doc, action)
        frappe.db.commit()

        return {
            "success": True,
            "doctype": doctype,
            "name": doc.name,
            "action": action,
            "new_state": doc.get("workflow_state", ""),
            "message": f"Workflow action '{action}' applied successfully on {doctype} '{name}'",
        }
    except Exception as e:
        return {"error": f"Workflow action failed: {str(e)}"}
