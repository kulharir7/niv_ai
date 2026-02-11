"""
Tool Registry — manages Niv Tool DocType entries.

Since v0.3.0, all tools come from MCP servers (FAC).
Only email_tools and image_tools are kept as native Python tools
(unique functionality not available via MCP).

The Niv Tool DocType is reserved for future admin-defined custom tools.
"""
import frappe
import json


@frappe.whitelist()
def get_tools():
    """Get all available tools for the current user.
    
    Returns MCP tools from connected servers + any native tools.
    """
    from niv_ai.niv_core.langchain.tools import get_langchain_tools
    lc_tools = get_langchain_tools()
    return [{"name": t.name, "description": t.description} for t in lc_tools]


@frappe.whitelist()
def register_tool(tool_name, display_name, description, category, function_path, parameters_json, requires_admin=0):
    """Register a custom tool (admin only).
    
    For admin-defined tools that run native Python functions.
    MCP tools are auto-discovered — no registration needed.
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can register tools")

    if frappe.db.exists("Niv Tool", tool_name):
        doc = frappe.get_doc("Niv Tool", tool_name)
        doc.display_name = display_name
        doc.description = description
        doc.category = category
        doc.function_path = function_path
        doc.parameters_json = parameters_json if isinstance(parameters_json, str) else json.dumps(parameters_json)
        doc.requires_admin = requires_admin
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "Niv Tool",
            "tool_name": tool_name,
            "display_name": display_name,
            "description": description,
            "category": category,
            "function_path": function_path,
            "parameters_json": parameters_json if isinstance(parameters_json, str) else json.dumps(parameters_json),
            "requires_admin": requires_admin,
            "is_active": 1,
            "log_execution": 1,
        })
        doc.insert(ignore_permissions=True)

    return {"status": "ok", "tool": tool_name}
