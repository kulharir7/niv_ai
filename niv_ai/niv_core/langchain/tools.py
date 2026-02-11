"""
MCP Tools → LangChain Tools wrapper.
Reuses existing mcp_client.py — no changes to MCP layer.

Per-user permission isolation:
  When user_api_key is set via set_current_user_api_key(),
  all MCP tool calls use the user's own ERPNext API credentials.
  This means tool results respect the user's roles/permissions —
  e.g., a Sales User only sees their own Sales Orders.
"""
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
    Called before agent.invoke/stream, cleared in finally block."""
    _thread_local.user_api_key = api_key


def get_current_user_api_key() -> Optional[str]:
    """Get the current request user's API key (if set)."""
    return getattr(_thread_local, "user_api_key", None)


def _build_pydantic_model(name: str, parameters: dict):
    """Convert OpenAI function parameters JSON schema → Pydantic model. Cached."""
    cache_key = f"{name}_{hash(json.dumps(parameters, sort_keys=True))}"
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
            return f"Error: '{field}' field zaroori hai (required) for tool '{tool_name}'"

    # Check types
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
            return (f"Error: '{field}' ka type galat hai — expected {expected_type}, "
                    f"got {type(value).__name__} for tool '{tool_name}'")

    return None


def _make_mcp_executor(tool_name: str, input_schema: dict = None):
    """Create a closure that calls MCP tool by name.

    Uses find_tool_server → call_tool_fast.
    Automatically uses per-user API key if set (thread-local).
    Validates arguments against inputSchema before calling.
    """
    def execute(**kwargs):
        # Remove None values — MCP servers don't expect them
        clean_args = {k: v for k, v in kwargs.items() if v is not None}

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

            if isinstance(result, dict):
                return json.dumps(result, default=str, ensure_ascii=False)
            return str(result)

        except Exception as e:
            frappe.log_error(f"MCP tool '{tool_name}' failed: {e}", "Niv AI MCP")
            return json.dumps({"error": f"Tool execution failed: {str(e)}"})

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

        description = func_def.get("description", "")[:1024]
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
