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


# Type mapping from JSON Schema → Python types
_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _build_pydantic_model(name: str, parameters: dict):
    """Convert OpenAI function parameters JSON schema → Pydantic model."""
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    
    fields = {}
    for field_name, field_schema in properties.items():
        field_type = _TYPE_MAP.get(field_schema.get("type", "string"), Any)
        description = field_schema.get("description", "")
        
        if field_name in required:
            fields[field_name] = (field_type, Field(description=description))
        else:
            fields[field_name] = (Optional[field_type], Field(default=None, description=description))
    
    if not fields:
        # Empty params — add a dummy so Pydantic doesn't complain
        return None
    
    return create_model(f"{name}_Schema", **fields)


def _make_mcp_executor(tool_name: str):
    """Create a closure that calls MCP tool by name."""
    def execute(**kwargs):
        server = find_tool_server(tool_name)
        if not server:
            return json.dumps({"error": f"No MCP server found for tool: {tool_name}"})
        
        result = call_tool_fast(
            server_name=server["server_name"],
            server_url=server["server_url"],
            api_key=server["api_key"],
            tool_name=tool_name,
            arguments=kwargs,
        )
        
        if isinstance(result, dict):
            return json.dumps(result, default=str, ensure_ascii=False)
        return str(result)
    
    return execute


def get_langchain_tools() -> list:
    """Get all MCP tools as LangChain StructuredTool objects.
    
    Uses existing mcp_client.py (cached, no extra API calls).
    """
    mcp_tools = get_all_mcp_tools_cached()
    lc_tools = []
    
    for tool_def in mcp_tools:
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        description = func_def.get("description", "")[:1024]  # LangChain limit
        parameters = func_def.get("parameters", {})
        
        if not name:
            continue
        
        # Build args schema
        args_schema = _build_pydantic_model(name, parameters)
        executor = _make_mcp_executor(name)
        
        tool = StructuredTool.from_function(
            func=executor,
            name=name,
            description=description,
            args_schema=args_schema,
            return_direct=False,
        )
        lc_tools.append(tool)
    
    return lc_tools
