"""
Tool Executor — MCP-First Architecture

All tools come from MCP servers (like FAC).
Custom Niv Tools (admin-defined) as fallback only.
No native Python tool implementations.
"""

import frappe
import json
import time


def execute_tool(tool_name, parameters, user, conversation_id=None):
    """
    Execute a tool by name.

    Resolution order:
    1. MCP servers (primary — all tools discovered from connected servers)
    2. Custom Niv Tools (admin-defined with function_path, NOT seed data)
    """
    start_time = time.time()

    # ── Common AI hallucination aliases ──
    ALIASES = {
        "analyze_business_data": "analyze_data",
        "analyse_data": "analyze_data",
        "analyse_business_data": "analyze_data",
        "search": "search_documents",
        "find_documents": "search_documents",
        "get_documents": "list_documents",
        "query_database": "run_database_query",
        "execute_query": "run_database_query",
        "create_doc": "create_document",
        "get_doc": "get_document",
        "update_doc": "update_document",
        "delete_doc": "delete_document",
    }
    tool_name = ALIASES.get(tool_name, tool_name)

    # ── 1. Try MCP servers (primary path) ──
    result = _execute_via_mcp(tool_name, parameters, user, conversation_id, start_time)
    if result is not None:
        return result

    # ── 2. Try custom Niv Tool (admin-defined only) ──
    result = _execute_via_niv_tool(tool_name, parameters, user, conversation_id, start_time)
    if result is not None:
        return result

    return {"error": f"Tool '{tool_name}' not found on any connected MCP server. Make sure an MCP server is connected and active."}


def _execute_via_mcp(tool_name, parameters, user, conversation_id, start_time):
    """Execute tool via MCP. Returns None if tool not found on any server."""
    try:
        from niv_ai.niv_core.mcp_client import find_tool_server, call_tool_fast
        server_name = find_tool_server(tool_name)
        if not server_name:
            return None

        result = call_tool_fast(server_name, tool_name, parameters)

        # MCP returns {content: [{type: "text", text: "..."}]}
        # Normalize to simple dict
        if isinstance(result, dict) and "content" in result:
            contents = result["content"]
            if isinstance(contents, list):
                text_parts = []
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                    elif isinstance(c, dict):
                        text_parts.append(json.dumps(c))
                    else:
                        text_parts.append(str(c))
                result = {"success": True, "result": "\n".join(text_parts)}
            else:
                result = {"success": True, "result": str(contents)}

        is_error = isinstance(result, dict) and (result.get("error") or result.get("isError"))
        exec_time = int((time.time() - start_time) * 1000)
        _log_execution(tool_name, user, conversation_id, parameters, result, exec_time, is_error, result.get("error", "") if is_error else "")
        return result

    except ImportError:
        return None
    except Exception as e:
        exec_time = int((time.time() - start_time) * 1000)
        error_result = {"error": f"MCP tool execution failed: {e}"}
        _log_execution(tool_name, user, conversation_id, parameters, error_result, exec_time, True, str(e))
        frappe.log_error(f"MCP tool error: {tool_name}: {e}", "Niv AI MCP Error")
        return error_result


def _execute_via_niv_tool(tool_name, parameters, user, conversation_id, start_time):
    """Execute custom admin-defined Niv Tool. Returns None if not found."""
    if not frappe.db.exists("Niv Tool", tool_name):
        return None

    tool = frappe.get_doc("Niv Tool", tool_name)

    if not tool.is_active:
        return {"error": f"Tool '{tool_name}' is disabled"}

    if not tool.function_path:
        return {"error": f"Tool '{tool_name}' has no function_path configured"}

    # Permission checks
    if tool.requires_admin and "System Manager" not in frappe.get_roles(user):
        return {"error": f"Tool '{tool_name}' requires admin access"}

    if tool.allowed_roles:
        user_roles = set(frappe.get_roles(user))
        allowed = set(r.role for r in tool.allowed_roles)
        if not user_roles.intersection(allowed):
            return {"error": f"No permission to use '{tool_name}'"}

    # Execute
    try:
        import importlib
        module_path, func_name = tool.function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        result = func(**parameters)
    except Exception as e:
        result = {"error": str(e)}
        frappe.log_error(f"Niv Tool error: {tool_name}: {e}", "Niv AI Tool Error")

    exec_time = int((time.time() - start_time) * 1000)
    is_error = isinstance(result, dict) and "error" in result
    _log_execution(tool_name, user, conversation_id, parameters, result, exec_time, is_error, result.get("error", "") if is_error else "")
    return result


def _log_execution(tool_name, user, conversation_id, parameters, result, exec_time, is_error, error_message):
    """Log tool execution."""
    try:
        frappe.get_doc({
            "doctype": "Niv Tool Log",
            "tool": tool_name,
            "user": user,
            "conversation": conversation_id,
            "parameters_json": json.dumps(parameters, default=str),
            "result_json": json.dumps(result, default=str)[:65000],
            "execution_time_ms": exec_time,
            "is_error": is_error,
            "error_message": error_message,
        }).insert(ignore_permissions=True)
    except Exception:
        pass  # Don't fail tool call because of logging


def get_available_tools(user):
    """
    Get all tools available to a user.
    MCP tools are PRIMARY. Custom Niv Tools as secondary.
    """
    tools = []
    seen_names = set()

    # ── 1. MCP Tools (primary) ──
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached
        mcp_tools = get_all_mcp_tools_cached()
        for tool in mcp_tools:
            name = tool["function"]["name"]
            if name not in seen_names:
                seen_names.add(name)
                tools.append(frappe._dict({
                    "tool_name": name,
                    "display_name": name,
                    "description": tool["function"].get("description", name),
                    "category": "MCP",
                    "parameters_json": json.dumps(tool["function"].get("parameters", {"type": "object", "properties": {}})),
                    "source": "mcp",
                }))
    except ImportError:
        pass
    except Exception as e:
        frappe.logger().error(f"Niv AI: Error loading MCP tools: {e}")

    # ── 2. Custom Niv Tools (admin-defined, non-MCP) ──
    user_roles = set(frappe.get_roles(user))
    is_admin = "System Manager" in user_roles

    niv_tools = frappe.get_all(
        "Niv Tool",
        filters={"is_active": 1},
        fields=["name", "tool_name", "display_name", "description",
                "category", "function_path", "parameters_json", "requires_admin"],
    )

    for tool in niv_tools:
        if tool.tool_name in seen_names:
            continue  # MCP already has this tool
        if tool.requires_admin and not is_admin:
            continue
        # Role check
        allowed_roles = frappe.get_all(
            "Has Role",
            filters={"parent": tool.name, "parenttype": "Niv Tool"},
            fields=["role"],
        )
        if allowed_roles:
            if not user_roles.intersection({r.role for r in allowed_roles}):
                continue

        seen_names.add(tool.tool_name)
        tools.append(tool)

    return tools


def tools_to_openai_format(tools):
    """Convert tools to OpenAI function calling format."""
    result = []
    for tool in tools:
        try:
            params = json.loads(tool.parameters_json) if tool.parameters_json else {}
        except (json.JSONDecodeError, TypeError):
            params = {"type": "object", "properties": {}}

        result.append({
            "type": "function",
            "function": {
                "name": tool.tool_name,
                "description": tool.description or tool.display_name or tool.tool_name,
                "parameters": params,
            },
        })
    return result
