import frappe
import json
from frappe import _


@frappe.whitelist()
def get_mcp_servers():
    """List all MCP servers with their status."""
    servers = frappe.get_all(
        "Niv MCP Server",
        fields=["name", "server_name", "is_active", "status", "transport_type", "description", "last_connected", "tools_count"],
        order_by="server_name asc",
    )
    return servers


@frappe.whitelist()
def toggle_server(server_name, is_active):
    """Enable or disable an MCP server."""
    doc = frappe.get_doc("Niv MCP Server", server_name)
    doc.is_active = int(is_active)
    if not doc.is_active:
        doc.status = "Disconnected"
    doc.save(ignore_permissions=False)
    frappe.db.commit()
    return {"success": True}


def _populate_tools_table(doc, tools):
    """Populate the child table with discovered tools."""
    doc.tools = []
    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "")
        # Truncate description to 200 chars for readability
        if len(desc) > 200:
            desc = desc[:197] + "..."
        doc.append("tools", {
            "tool_name": name,
            "description": desc,
            "enabled": 1
        })
    doc.tools_count = len(tools)
    doc.tools_discovered = json.dumps(tools, indent=2)


@frappe.whitelist()
def test_connection(server_name):
    """Test connectivity to an MCP server and discover tools using the real MCP client."""
    doc = frappe.get_doc("Niv MCP Server", server_name)

    try:
        from niv_ai.niv_core.mcp_client import discover_tools, clear_cache

        # Clear cache to force fresh discovery
        clear_cache(server_name)
        tools = discover_tools(server_name, use_cache=False)

        doc.status = "Connected"
        doc.last_connected = frappe.utils.now()
        _populate_tools_table(doc, tools)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {
            "success": True,
            "status": "Connected",
            "tools_count": len(tools),
            "tools": [{"name": t.get("name"), "description": (t.get("description", "")[:100])} for t in tools],
        }
    except Exception as e:
        doc.status = "Error"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": False, "status": "Error", "error": str(e)}


@frappe.whitelist()
def get_all_mcp_tools():
    """Get all tools from all active MCP servers in OpenAI function calling format."""
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools as _get_all
        return _get_all()
    except Exception as e:
        frappe.logger().error(f"Niv AI MCP: Error getting all MCP tools: {e}")
        return []
