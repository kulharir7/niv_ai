import frappe
import json
from frappe import _


@frappe.whitelist()
def get_mcp_servers():
    """List MCP servers from Niv MCP Server DocType."""
    try:
        if frappe.db.exists("DocType", "Niv MCP Server"):
            servers = frappe.get_all(
                "Niv MCP Server",
                filters={},
                fields=["name", "server_name", "is_active", "transport_type", "server_url", "tools_count", "last_connected", "notes"],
                order_by="creation ASC",
            )
            result = []
            for s in servers:
                result.append({
                    "name": s.name,
                    "server_name": s.server_name,
                    "is_active": s.is_active,
                    "status": "Connected" if s.is_active else "Disconnected",
                    "transport_type": s.transport_type or "http",
                    "description": s.notes or f"MCP Server ({s.transport_type})",
                    "tools_count": s.tools_count or 0,
                    "last_connected": str(s.last_connected) if s.last_connected else None,
                })
            if result:
                return result
    except Exception:
        pass
    # Fallback
    return [{
        "name": "default",
        "server_name": "MCP Server",
        "is_active": 1,
        "status": "Connected",
        "transport_type": "direct",
        "description": "Built-in tools",
    }]


@frappe.whitelist()
def toggle_server(server_name, is_active):
    """Toggle MCP server active status. Accepts name or server_name."""
    try:
        if not frappe.db.exists("DocType", "Niv MCP Server"):
            return {"success": False, "error": "Niv MCP Server DocType not found"}

        # Find by name (primary key) first, then by server_name
        doc_name = None
        if frappe.db.exists("Niv MCP Server", server_name):
            doc_name = server_name
        else:
            # Search by server_name field
            found = frappe.db.get_value("Niv MCP Server", {"server_name": server_name}, "name")
            if found:
                doc_name = found

        if doc_name:
            is_active_val = 1 if (is_active and str(is_active) not in ("0", "false", "False")) else 0
            frappe.db.set_value("Niv MCP Server", doc_name, "is_active", is_active_val)
            frappe.db.commit()
            # Clear ALL MCP caches (worker + redis + langchain tools)
            try:
                from niv_ai.niv_core.mcp_client import clear_cache
                clear_cache()
            except Exception:
                pass
            # Clear Redis caches (shared across all workers)
            try:
                import frappe as _f
                for key in ["niv_mcp_tools:openai_tools", "niv_mcp_tools:tool_index"]:
                    _f.cache().delete_value(key)
                # Clear all server-specific caches
                _f.cache().delete_value(f"niv_mcp_tools:tools:{doc_name}")
            except Exception:
                pass
            return {"success": True, "is_active": is_active_val}
        return {"success": False, "error": f"Server '{server_name}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def test_connection(server_name=None):
    """Test MCP tool discovery."""
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
    """Get all tools from MCP servers in OpenAI function calling format."""
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools as _get_all
        return _get_all()
    except Exception as e:
        frappe.logger().error(f"Niv AI MCP: Error getting tools: {e}")
        return []
