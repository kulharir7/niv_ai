import frappe
import json
from frappe import _


@frappe.whitelist()
def get_mcp_servers():
    """List MCP servers. FAC is always the server (same Frappe instance)."""
    return [{
        "name": "Frappe Assistant Core",
        "server_name": "Frappe Assistant Core",
        "is_active": 1,
        "status": "Connected",
        "transport_type": "direct",
        "description": "Built-in ERPNext tools via Frappe Assistant Core",
    }]


@frappe.whitelist()
def toggle_server(server_name, is_active):
    """Toggle not needed — FAC is always active."""
    return {"success": True}


@frappe.whitelist()
def test_connection(server_name=None):
    """Test FAC tool discovery."""
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached
        tools = get_all_mcp_tools_cached()
        return {
            "success": True,
            "status": "Connected",
            "tools_count": len(tools),
            "tools": [{"name": t.get("name"), "description": (t.get("description", "")[:100])} for t in tools],
        }
    except Exception as e:
        return {"success": False, "status": "Error", "error": str(e)}


@frappe.whitelist()
def get_all_mcp_tools():
    """Get all tools from FAC in OpenAI function calling format."""
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools as _get_all
        return _get_all()
    except Exception as e:
        frappe.logger().error(f"Niv AI MCP: Error getting tools: {e}")
        return []
