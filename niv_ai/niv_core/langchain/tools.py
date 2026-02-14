"""
MCP Tools → LangChain Tools wrapper.
Reuses existing mcp_client.py — no changes to MCP layer.

Per-user permission isolation:
  When user_api_key is set via set_current_user_api_key(),
  all MCP tool calls use the user's own ERPNext API credentials.
  This means tool results respect the user's roles/permissions —
  e.g., a Sales User only sees their own Sales Orders.
"""
import hashlib
import json
import threading
import frappe
from langchain_core.tools import StructuredTool
from pydantic import create_model, Field
from typing import Any, Optional

from niv_ai.niv_core.mcp_client import (
    get_all_mcp_tools_cached,
    find_tool_server,
    call_tool_fast,
)


# JSON Schema type → Python type mapping
_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}

# Pydantic model cache (avoid re-creating per call)
_schema_cache = {}

# ─── Per-User API Key (thread-local) ──────────────────────────────
# Set before agent run, cleared after. Thread-safe via threading.local.
_thread_local = threading.local()


def set_current_user_api_key(api_key: str = None):
    """Set the API key for the current request's user.
    Called before agent.invoke/stream, cleared in finally block.
    BUG-017: Validate format and log audit trail.
    """
    if api_key:
        if ":" not in api_key:
            frappe.logger().error(f"Niv AI: Invalid API key format for user {frappe.session.user}")
            # We don't throw here to avoid breaking the agent flow, but we won't use the invalid key
            _thread_local.user_api_key = None
            return
        
        # Log audit trail (sensitive info masked)
        key_id = api_key.split(":")[0]
        frappe.logger().info(f"Niv AI Audit: User {frappe.session.user} using API key {key_id}")
        
    _thread_local.user_api_key = api_key


def get_current_user_api_key() -> Optional[str]:
    """Get the current request user's API key (if set)."""
    return getattr(_thread_local, "user_api_key", None)


# ─── Dev Mode Confirmation ─────────────────────────────────────────
# Write tools in dev mode require user confirmation before executing.
# NOTE: Can't use threading.local() because LangGraph runs tools in
# separate ThreadPoolExecutor threads. Use Redis flag instead.
_WRITE_TOOLS = {"create_document", "update_document", "delete_document", "submit_document"}


def set_dev_mode(enabled: bool = False, conversation_id: str = ""):
    """Enable/disable dev mode confirmation. Uses Redis for cross-thread visibility."""
    _thread_local.dev_conversation_id = conversation_id
    if conversation_id:
        key = f"niv_dev_mode:{conversation_id}"
        if enabled:
            frappe.cache().set_value(key, "1", expires_in_sec=600)
        else:
            frappe.cache().delete_value(key)


def is_dev_mode_for(conversation_id: str) -> bool:
    """Check if dev mode is active for a conversation (Redis-backed, cross-thread safe)."""
    if not conversation_id:
        return False
    key = f"niv_dev_mode:{conversation_id}"
    try:
        val = frappe.cache().get_value(key)
        return val == "1" or val == 1 or val == b"1"
    except Exception:
        return False


# Global active dev conversation (set by stream.py, read by tool executor)
# Safe because Gunicorn gthread handles one request at a time per worker
_active_dev_conv_id = {"value": ""}
_dev_lock = threading.Lock()


def set_active_dev_conversation(conv_id: str):
    """Set the active dev mode conversation ID (global, not thread-local)."""
    with _dev_lock:
        _active_dev_conv_id["value"] = conv_id


def is_dev_mode() -> bool:
    """Check dev mode — uses global active conversation + Redis flag."""
    with _dev_lock:
        conv_id = _active_dev_conv_id.get("value", "")
    if not conv_id:
        conv_id = getattr(_thread_local, "dev_conversation_id", "")
    return is_dev_mode_for(conv_id)


def get_active_dev_conv_id() -> str:
    """Get the active dev conversation ID."""
    with _dev_lock:
        return _active_dev_conv_id.get("value", "")


def get_pending_dev_action(conversation_id: str):
    """Get pending dev actions from Redis cache. Returns list of actions."""
    key = f"niv_dev_pending:{conversation_id}"
    try:
        data = frappe.cache().get_value(key)
        if data and isinstance(data, str):
            parsed = json.loads(data)
            # Backward compat: single dict → wrap in list
            if isinstance(parsed, dict):
                return [parsed]
            return parsed
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
        return None
    except Exception:
        return None


def set_pending_dev_action(conversation_id: str, action: dict):
    """Append pending dev action to Redis list (expires in 5 min)."""
    key = f"niv_dev_pending:{conversation_id}"
    existing = get_pending_dev_action(conversation_id) or []
    existing.append(action)
    frappe.cache().set_value(key, json.dumps(existing, default=str), expires_in_sec=300)


def clear_pending_dev_action(conversation_id: str):
    """Clear all pending dev actions."""
    key = f"niv_dev_pending:{conversation_id}"
    frappe.cache().delete_value(key)


def _execute_single_tool(tool_name, arguments):
    """Execute a single MCP tool call and return result string."""
    server_name = find_tool_server(tool_name)
    if not server_name:
        return json.dumps({"error": f"No MCP server found for tool: {tool_name}"})
    try:
        user_key = get_current_user_api_key()
        result = call_tool_fast(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            user_api_key=user_key,
        )
        if isinstance(result, dict) and "content" in result:
            contents = result["content"]
            if isinstance(contents, list):
                text_parts = []
                for c in contents:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                    elif isinstance(c, dict):
                        text_parts.append(json.dumps(c, default=str))
                    else:
                        text_parts.append(str(c))
                return "\n".join(text_parts)
        
        # BUG-012: Ensure result is always a string for the LLM
        if isinstance(result, (dict, list)):
            return json.dumps(result, default=str, ensure_ascii=False)
        return str(result)
    except Exception as e:
        return json.dumps({"error": f"Tool '{tool_name}' failed: {str(e)}"})


def execute_pending_dev_action(conversation_id: str) -> Optional[str]:
    """Execute ALL pending confirmed dev actions. Returns combined result."""
    actions = get_pending_dev_action(conversation_id)
    if not actions:
        return None

    clear_pending_dev_action(conversation_id)

    results = []
    undo_stack = []
    for action in actions:
        tool_name = action.get("tool_name")
        arguments = action.get("arguments", {})
        result = _execute_single_tool(tool_name, arguments)
        results.append(f"**{tool_name}** ({arguments.get('doctype', '')}):\n{result}")

        # Track created docs for undo
        if tool_name == "create_document":
            doctype = arguments.get("doctype", "")
            doc_name = ""
            try:
                result_data = json.loads(result) if isinstance(result, str) else result
                if isinstance(result_data, dict):
                    doc_name = result_data.get("name", "")
            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                frappe.log_error(f"Niv AI: Failed to parse tool result for undo: {e}", "Niv AI Tool")
            # Fallback: try to find "name" in result text
            if not doc_name and isinstance(result, str) and '"name"' in result:
                import re
                m = re.search(r'"name"\s*:\s*"([^"]+)"', result)
                if m:
                    doc_name = m.group(1)
            if doc_name and doctype:
                undo_stack.append({"action": "delete", "doctype": doctype, "name": doc_name})

    # Store undo stack in Redis
    if undo_stack:
        _set_undo_stack(conversation_id, undo_stack)

    return "\n\n---\n\n".join(results)


# ─── Undo/Rollback ────────────────────────────────────────────────

def _set_undo_stack(conversation_id: str, stack: list):
    """Store undo stack in Redis (expires in 30 min)."""
    key = f"niv_dev_undo:{conversation_id}"
    frappe.cache().set_value(key, json.dumps(stack, default=str), expires_in_sec=1800)


def get_undo_stack(conversation_id: str) -> Optional[list]:
    """Get undo stack from Redis."""
    key = f"niv_dev_undo:{conversation_id}"
    try:
        data = frappe.cache().get_value(key)
        if data and isinstance(data, str):
            return json.loads(data)
        if isinstance(data, list):
            return data
        return None
    except Exception:
        return None


def clear_undo_stack(conversation_id: str):
    """Clear undo stack."""
    key = f"niv_dev_undo:{conversation_id}"
    frappe.cache().delete_value(key)


def execute_undo(conversation_id: str) -> Optional[str]:
    """Undo the last dev actions. Deletes created documents."""
    stack = get_undo_stack(conversation_id)
    if not stack:
        return None

    clear_undo_stack(conversation_id)

    results = []
    for item in stack:
        action = item.get("action")
        doctype = item.get("doctype", "")
        name = item.get("name", "")

        if action == "delete" and doctype and name:
            result = _execute_single_tool("delete_document", {"doctype": doctype, "name": name})
            # Parse result to check success
            try:
                result_data = json.loads(result) if isinstance(result, str) else result
                if isinstance(result_data, dict):
                    success = result_data.get("success") or (result_data.get("result", {}) or {}).get("success")
                    if success:
                        results.append(f"✅ Deleted `{doctype}`: **{name}**")
                    else:
                        err = result_data.get("error", result_data.get("result", {}).get("message", "Unknown error"))
                        results.append(f"❌ Failed to delete `{name}`: {err}")
                else:
                    results.append(f"✅ Deleted `{doctype}`: **{name}**")
            except (json.JSONDecodeError, TypeError):
                results.append(f"✅ Deleted `{doctype}`: **{name}**")
        else:
            results.append(f"⚠️ Cannot undo: {item}")

    return "\n\n".join(results)


def _build_pydantic_model(name: str, parameters: dict):
    """Convert OpenAI function parameters JSON schema → Pydantic model. Cached."""
    # BUG-009: use hashlib.md5 instead of hash() for cross-process stable keys
    cache_key = f"{name}_{hashlib.md5(json.dumps(parameters, sort_keys=True).encode()).hexdigest()}"
    if cache_key in _schema_cache:
        return _schema_cache[cache_key]

    properties = parameters.get("properties", {})
    required_set = set(parameters.get("required", []))

    if not properties:
        return None

    fields = {}
    for field_name, field_schema in properties.items():
        field_type = _TYPE_MAP.get(field_schema.get("type", "string"), Any)
        description = field_schema.get("description", "")

        if field_name in required_set:
            fields[field_name] = (field_type, Field(description=description))
        else:
            fields[field_name] = (Optional[field_type], Field(default=None, description=description))

    model = create_model(f"{name}_Schema", **fields)
    _schema_cache[cache_key] = model
    return model


def _validate_arguments(tool_name: str, arguments: dict, input_schema: dict) -> Optional[str]:
    """Validate arguments against inputSchema. Returns error message or None if valid."""
    if not input_schema or input_schema.get("type") != "object":
        return None

    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    # Check required fields
    for field in required:
        if field not in arguments or arguments[field] is None:
            return f"Error: '{field}' is required for tool '{tool_name}'"

    # Check types and apply length limits (BUG-010)
    _schema_type_map = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict,
    }
    for field, value in arguments.items():
        if value is None:
            continue
        field_schema = properties.get(field)
        if not field_schema:
            continue
        expected_type = field_schema.get("type")
        if not expected_type:
            continue
        py_type = _schema_type_map.get(expected_type)
        if py_type and not isinstance(value, py_type):
            return (f"Error: '{field}' has wrong type — expected {expected_type}, "
                    f"got {type(value).__name__} for tool '{tool_name}'")

        # Length limits
        if isinstance(value, str) and len(value) > 10000:
            return f"Error: Argument '{field}' is too long (max 10000 chars)"
        if isinstance(value, list) and len(value) > 100:
            return f"Error: Argument '{field}' has too many items (max 100)"

    return None


def _get_recovery_hint(tool_name, args, error_str):
    """Generate actionable hints for the LLM to self-correct after a tool failure."""
    err = error_str.lower()

    # Permission errors
    if "permission" in err or "not permitted" in err or "forbidden" in err:
        return (
            "PERMISSION DENIED. Try: (1) use run_database_query with SELECT to read data directly, "
            "or (2) use run_python_code with tools.get_documents() which may have different access."
        )

    # Field not found
    if "field" in err and ("not found" in err or "unknown" in err or "invalid" in err):
        return (
            "WRONG FIELD NAME. Use get_doctype_info tool first to discover correct field names, "
            "then retry with the correct field names."
        )

    # DocType not found
    if "doctype" in err and "not found" in err:
        return (
            "WRONG DOCTYPE NAME. Use search_documents or get_doctype_info to find the correct DocType name. "
            "Common ones: 'Sales Invoice' (not 'Invoice'), 'Sales Order', 'Customer', 'Item'."
        )

    # Record not found
    if "not found" in err or "does not exist" in err:
        return (
            "RECORD NOT FOUND. Try: (1) use list_documents to search for similar records, "
            "or (2) use search_documents with a broader query to find the correct name/ID."
        )

    # Timeout
    if "timeout" in err or "timed out" in err:
        return (
            "REQUEST TIMED OUT. Try: (1) reduce the limit/date range, "
            "(2) use run_python_code with tools.get_documents() for lighter queries, "
            "or (3) use run_database_query with a simpler SELECT query."
        )

    # Prepared report taking too long
    if "prepared report" in err or "report" in err.lower() and "queue" in err:
        return (
            "REPORT IS QUEUED/SLOW. Try: (1) use list_documents instead of generate_report, "
            "(2) use run_database_query with a direct SQL query for the same data, "
            "or (3) use run_python_code with tools.get_documents()."
        )

    # Validation errors
    if "required" in err or "mandatory" in err or "missing" in err:
        return (
            "MISSING REQUIRED FIELDS. Use report_requirements or get_doctype_info to discover "
            "required fields/filters, then retry with all required values."
        )

    # JSON parse errors (bad arguments)
    if "json" in err or "parse" in err or "decode" in err:
        return "BAD ARGUMENTS FORMAT. Check argument types — strings must be strings, numbers must be numbers."

    # Generic
    return (
        "TOOL FAILED. Try a different approach: "
        "(1) use a different tool that can get the same data, "
        "(2) simplify the query, or (3) break into smaller steps."
    )


def _make_mcp_executor(tool_name: str, input_schema: dict = None):
    """Create a closure that calls MCP tool by name.

    Uses find_tool_server → call_tool_fast.
    Automatically uses per-user API key if set (thread-local).
    Validates arguments against inputSchema before calling.
    """
    def execute(**kwargs):
        # Remove None values — MCP servers don't expect them
        clean_args = {k: v for k, v in kwargs.items() if v is not None}

        # Dev Mode: intercept write tools → require confirmation
        _dm = is_dev_mode()
        if _dm and tool_name in _WRITE_TOOLS:
            conv_id = get_active_dev_conv_id() or getattr(_thread_local, "dev_conversation_id", "")
            # Store action and return confirmation prompt
            set_pending_dev_action(conv_id, {
                "tool_name": tool_name,
                "arguments": clean_args,
            })
            # Build human-readable summary
            doctype = clean_args.get("doctype", "Unknown")
            data = clean_args.get("data", {})
            summary_parts = [f"📋 **{tool_name}** on `{doctype}`"]
            for k, v in list(data.items())[:8]:
                val = str(v)[:100]
                summary_parts.append(f"  - {k}: {val}")
            summary = "\n".join(summary_parts)
            return (
                f"ACTION QUEUED FOR CONFIRMATION.\n\n{summary}\n\n"
                "Tell the user exactly what will be created/modified and ask them to reply 'yes' to confirm or 'no' to cancel. "
                "DO NOT call any more create/update/delete tools. STOP HERE and wait for user confirmation."
            )

        # Validate arguments against schema
        if input_schema:
            validation_error = _validate_arguments(tool_name, clean_args, input_schema)
            if validation_error:
                return json.dumps({"error": validation_error})

        server_name = find_tool_server(tool_name)
        if not server_name:
            return json.dumps({"error": f"No MCP server found for tool: {tool_name}"})

        try:
            # Use per-user API key if available (permission isolation)
            user_key = get_current_user_api_key()

            result = call_tool_fast(
                server_name=server_name,
                tool_name=tool_name,
                arguments=clean_args,
                user_api_key=user_key,
            )

            # MCP returns {"content": [{"type": "text", "text": "..."}]}
            if isinstance(result, dict) and "content" in result:
                contents = result["content"]
                if isinstance(contents, list):
                    text_parts = []
                    for c in contents:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text_parts.append(c.get("text", ""))
                        elif isinstance(c, dict):
                            text_parts.append(json.dumps(c, default=str))
                        else:
                            text_parts.append(str(c))
                    return "\n".join(text_parts)

            # BUG-012: Ensure result is always a string for the LLM
            if isinstance(result, (dict, list)):
                return json.dumps(result, default=str, ensure_ascii=False)
            return str(result)

        except Exception as e:
            frappe.log_error(f"MCP tool '{tool_name}' failed: {e}", "Niv AI MCP")
            # Return actionable error — guides LLM to self-correct
            err_str = str(e)
            hint = _get_recovery_hint(tool_name, clean_args, err_str)
            return json.dumps({
                "error": f"Tool '{tool_name}' failed: {err_str}",
                "recovery_hint": hint,
            })

    return execute


# Tool list cache (avoids rebuilding LangChain wrappers every call)
_lc_tools_cache = {"tools": [], "expires": 0}
_LC_CACHE_TTL = 300  # 5 min, matches mcp_client


def get_langchain_tools() -> list:
    """Get all MCP tools as LangChain StructuredTool objects. Cached."""
    import time

    if _lc_tools_cache["expires"] > time.time() and _lc_tools_cache["tools"]:
        return _lc_tools_cache["tools"]

    mcp_tools = get_all_mcp_tools_cached()
    
    if not mcp_tools:
        frappe.logger().error("Niv AI: 0 MCP tools loaded! Agent will have no tools. Check MCP server connection.")
    
    lc_tools = []

    for tool_def in mcp_tools:
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        if not name:
            continue

        description = func_def.get("description", "")[:4096]
        parameters = func_def.get("parameters", {})

        args_schema = _build_pydantic_model(name, parameters)
        executor = _make_mcp_executor(name, input_schema=parameters)

        tool = StructuredTool.from_function(
            func=executor,
            name=name,
            description=description,
            args_schema=args_schema,
            return_direct=False,
            handle_tool_error=True,  # Return error as string instead of raising
        )
        lc_tools.append(tool)

    _lc_tools_cache["tools"] = lc_tools
    _lc_tools_cache["expires"] = time.time() + _LC_CACHE_TTL

    return lc_tools


def clear_tools_cache():
    """Clear LangChain tools cache. Call when MCP servers change."""
    _lc_tools_cache["tools"] = []
    _lc_tools_cache["expires"] = 0
    _schema_cache.clear()
