"""
MCP Tools → LangChain Tools wrapper.
Reuses existing mcp_client.py — no changes to MCP layer.
"""
import json
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


def _make_mcp_executor(tool_name: str):
    """Create a closure that calls MCP tool by name.

    Uses find_tool_server → call_tool_fast (returns server_name string).
    """
    def execute(**kwargs):
        # Remove None values — MCP servers don't expect them
        clean_args = {k: v for k, v in kwargs.items() if v is not None}

        server_name = find_tool_server(tool_name)
        if not server_name:
            return json.dumps({"error": f"No MCP server found for tool: {tool_name}"})

        try:
            result = call_tool_fast(
                server_name=server_name,
                tool_name=tool_name,
                arguments=clean_args,
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
    lc_tools = []

    for tool_def in mcp_tools:
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        if not name:
            continue

        description = func_def.get("description", "")[:1024]
        parameters = func_def.get("parameters", {})

        args_schema = _build_pydantic_model(name, parameters)
        executor = _make_mcp_executor(name)

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
