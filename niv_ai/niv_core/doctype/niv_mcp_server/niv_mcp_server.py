# Copyright (c) 2026, Niv AI
# Niv MCP Server DocType

import json
import frappe
from frappe import _
from frappe.utils import now_datetime


class NivMCPServer(frappe.model.document.Document):
    def validate(self):
        if self.transport_type != "stdio" and not self.server_url:
            frappe.throw(_("Server URL is required for {0} transport").format(self.transport_type))
        if self.transport_type == "stdio" and not self.command:
            frappe.throw(_("Command is required for stdio transport"))

    def on_update(self):
        # Clear MCP client cache when server config changes
        try:
            from niv_ai.niv_core.mcp_client import clear_cache
            clear_cache(self.server_name)
        except Exception:
            pass


@frappe.whitelist()
def test_connection(server_name):
    """Test connection to an MCP server and discover tools."""
    doc = frappe.get_doc("Niv MCP Server", server_name)
    if not doc.is_active:
        frappe.throw(_("Server is not active"))

    try:
        from niv_ai.niv_core.mcp_client import discover_tools
        tools = discover_tools(server_name, use_cache=False)

        # Update doc with results
        doc.tools_count = len(tools)
        doc.last_connected = now_datetime()
        doc.tools_discovered_json = json.dumps(
            [{"name": t.get("name", ""), "description": t.get("description", "")[:100]} for t in tools],
            indent=2
        )
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        tool_names = [t.get("name", "") for t in tools]
        return {
            "success": True,
            "tools_count": len(tools),
            "tools": tool_names[:20],  # First 20 for display
            "message": f"Connected! Found {len(tools)} tools.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Connection failed: {str(e)[:200]}",
        }


@frappe.whitelist()
def get_all_active_servers():
    """Get all active MCP server names."""
    servers = frappe.get_all(
        "Niv MCP Server",
        filters={"is_active": 1},
        fields=["server_name"],
        order_by="creation ASC",
    )
    return [s.server_name for s in servers]
