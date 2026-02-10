import frappe
import json
import time
import importlib


def execute_tool(tool_name, parameters, user, conversation_id=None):
    """
    Execute a tool by name with given parameters.

    Tool resolution order:
    1. Check Niv Tool DocType (custom/registered tools)
    2. Check Frappe Assistant Core tools (if installed)
    """
    start_time = time.time()

    # ── Resolve common tool name aliases (AI hallucinations) ──
    TOOL_ALIASES = {
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
    tool_name = TOOL_ALIASES.get(tool_name, tool_name)

    # ── Try Niv Tool DocType first ──
    if frappe.db.exists("Niv Tool", tool_name):
        tool = frappe.get_doc("Niv Tool", tool_name)

        if not tool.is_active:
            return {"error": f"Tool '{tool_name}' is disabled"}

        # Check permissions
        if tool.requires_admin and "System Manager" not in frappe.get_roles(user):
            return {"error": f"Tool '{tool_name}' requires admin access"}

        if tool.allowed_roles:
            user_roles = set(frappe.get_roles(user))
            allowed = set(r.role for r in tool.allowed_roles)
            if not user_roles.intersection(allowed):
                return {"error": f"You don't have permission to use '{tool_name}'"}

        # Check if this tool delegates to FAC
        if tool.function_path and tool.function_path.startswith("fac:"):
            # Delegate to Frappe Assistant Core
            fac_tool_name = tool.function_path[4:]  # strip "fac:"
            return _execute_fac_tool(fac_tool_name, parameters, user, conversation_id, start_time, tool)

        # Execute native Niv tool
        return _execute_native_tool(tool, parameters, user, conversation_id, start_time)

    # ── Try Frappe Assistant Core ──
    try:
        from niv_ai.niv_tools.fac_adapter import get_fac_tool
        fac_tool = get_fac_tool(tool_name)
        if fac_tool:
            return _execute_fac_tool(tool_name, parameters, user, conversation_id, start_time)
    except ImportError:
        pass

    # ── Try MCP servers ──
    try:
        from niv_ai.niv_core.mcp_client import find_tool_server, execute_mcp_tool
        server = find_tool_server(tool_name)
        if server:
            return _execute_mcp_tool(tool_name, parameters, user, conversation_id, start_time)
    except ImportError:
        pass

    return {"error": f"Tool '{tool_name}' not found"}


def _execute_native_tool(tool, parameters, user, conversation_id, start_time):
    """Execute a native Niv AI tool (Python function)"""
    is_error = False
    error_message = ""
    result = None

    try:
        module_path, func_name = tool.function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        result = func(**parameters)
    except Exception as e:
        is_error = True
        error_message = str(e)
        result = {"error": error_message}
        frappe.log_error(f"Tool execution error: {tool.tool_name}: {e}", "Niv AI Tool Error")

    exec_time = int((time.time() - start_time) * 1000)

    # Log execution
    _log_execution(tool.tool_name, user, conversation_id, parameters, result, exec_time, is_error, error_message, tool.log_execution if hasattr(tool, 'log_execution') else True)

    return result


def _execute_fac_tool(tool_name, parameters, user, conversation_id, start_time, niv_tool=None):
    """Execute a Frappe Assistant Core tool"""
    is_error = False
    error_message = ""
    result = None

    try:
        from niv_ai.niv_tools.fac_adapter import execute_fac_tool
        result = execute_fac_tool(tool_name, parameters, user)

        if isinstance(result, dict) and not result.get("success", True):
            is_error = True
            error_message = result.get("error", "Unknown error")
    except Exception as e:
        is_error = True
        error_message = str(e)
        result = {"error": error_message}
        frappe.log_error(f"FAC tool execution error: {tool_name}: {e}", "Niv AI FAC Tool Error")

    exec_time = int((time.time() - start_time) * 1000)

    # Log execution
    should_log = True
    if niv_tool and hasattr(niv_tool, 'log_execution'):
        should_log = niv_tool.log_execution
    _log_execution(tool_name, user, conversation_id, parameters, result, exec_time, is_error, error_message, should_log)

    return result


def _execute_mcp_tool(tool_name, parameters, user, conversation_id, start_time):
    """Execute a tool via MCP protocol"""
    is_error = False
    error_message = ""
    result = None

    try:
        from niv_ai.niv_core.mcp_client import execute_mcp_tool
        result = execute_mcp_tool(tool_name, parameters)

        if isinstance(result, dict) and result.get("error"):
            is_error = True
            error_message = result["error"]
    except Exception as e:
        is_error = True
        error_message = str(e)
        result = {"error": error_message}
        frappe.log_error(f"MCP tool execution error: {tool_name}: {e}", "Niv AI MCP Tool Error")

    exec_time = int((time.time() - start_time) * 1000)
    _log_execution(tool_name, user, conversation_id, parameters, result, exec_time, is_error, error_message)
    return result


def _log_execution(tool_name, user, conversation_id, parameters, result, exec_time, is_error, error_message, should_log=True):
    """Log tool execution to Niv Tool Log"""
    if not should_log:
        return
    try:
        log = frappe.get_doc({
            "doctype": "Niv Tool Log",
            "tool": tool_name,
            "user": user,
            "conversation": conversation_id,
            "parameters_json": json.dumps(parameters, default=str),
            "result_json": json.dumps(result, default=str)[:65000],
            "execution_time_ms": exec_time,
            "is_error": is_error,
            "error_message": error_message,
        })
        log.insert(ignore_permissions=True)
    except Exception:
        pass  # Don't fail the tool call because of logging


def get_available_tools(user):
    """
    Get all tools available to a user.
    Combines Niv Tools + FAC tools (if installed).
    """
    user_roles = set(frappe.get_roles(user))
    is_admin = "System Manager" in user_roles

    # ── Niv Tools ──
    niv_tools = frappe.get_all(
        "Niv Tool",
        filters={"is_active": 1},
        fields=["name", "tool_name", "display_name", "description",
                "category", "function_path", "parameters_json",
                "requires_admin"],
    )

    available = []
    niv_tool_names = set()

    for tool in niv_tools:
        if tool.requires_admin and not is_admin:
            continue

        # Check role-based access
        allowed_roles = frappe.get_all(
            "Has Role",
            filters={"parent": tool.name, "parenttype": "Niv Tool"},
            fields=["role"],
        )
        if allowed_roles:
            allowed_set = set(r.role for r in allowed_roles)
            if not user_roles.intersection(allowed_set):
                continue

        available.append(tool)
        niv_tool_names.add(tool.tool_name)

    # ── FAC Tools (if installed, and not already registered as Niv Tools) ──
    try:
        from niv_ai.niv_tools.fac_adapter import discover_fac_tools
        fac_tools = discover_fac_tools()

        for name, fac_tool in fac_tools.items():
            if name in niv_tool_names:
                continue  # Already registered as Niv Tool

            # Check admin requirement
            requires_admin = getattr(fac_tool, 'requires_permission', None) == "System Manager"
            if requires_admin and not is_admin:
                continue

            # Create a pseudo tool dict for compatibility
            params_schema = getattr(fac_tool, 'inputSchema', {})
            available.append(frappe._dict({
                "name": name,
                "tool_name": name,
                "display_name": getattr(fac_tool, 'name', name),
                "description": getattr(fac_tool, 'description', ''),
                "category": getattr(fac_tool, 'category', 'Custom'),
                "function_path": f"fac:{name}",
                "parameters_json": json.dumps(params_schema),
                "requires_admin": 1 if requires_admin else 0,
                "source": "frappe_assistant_core",
            }))

    except ImportError:
        pass  # FAC not installed

    # ── MCP Tools (from active MCP servers) ──
    try:
        from niv_ai.niv_core.mcp_client import get_all_active_servers, discover_tools
        existing_names = {t.tool_name for t in available}

        for server_name in get_all_active_servers():
            try:
                tools = discover_tools(server_name)
                for tool in tools:
                    name = tool.get("name", "")
                    if not name or name in niv_tool_names or name in existing_names:
                        continue
                    existing_names.add(name)

                    params_schema = tool.get("inputSchema", {"type": "object", "properties": {}})
                    available.append(frappe._dict({
                        "name": name,
                        "tool_name": name,
                        "display_name": name,
                        "description": tool.get("description", ""),
                        "category": "MCP",
                        "function_path": f"mcp:{server_name}:{name}",
                        "parameters_json": json.dumps(params_schema),
                        "requires_admin": 0,
                        "source": f"mcp:{server_name}",
                    }))
            except Exception:
                pass  # Skip servers that are down
    except ImportError:
        pass

    return available


def tools_to_openai_format(tools):
    """Convert tools to OpenAI function calling format"""
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
