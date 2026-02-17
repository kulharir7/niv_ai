"""
MCP Tool Loader
Load MCP tools from Frappe Assistant Core (FAC)
"""
import frappe
from typing import List, Dict, Any, Callable
from dataclasses import dataclass
import json

@dataclass
class MCPTool:
    """MCP Tool definition"""
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Callable

def load_mcp_tools(user: str = None) -> List[MCPTool]:
    """
    Load all MCP tools available to user from FAC.
    Tools are registered via assistant_tools hook.
    """
    tools = []
    user = user or frappe.session.user
    
    # Get tools from all apps via hook
    all_tool_paths = frappe.get_hooks("assistant_tools") or []
    
    for tool_path in all_tool_paths:
        try:
            # Get tool definition function
            tool_fn = frappe.get_attr(tool_path)
            tool_defs = tool_fn()
            
            # Can return single tool or list of tools
            if isinstance(tool_defs, dict):
                tool_defs = [tool_defs]
            elif not isinstance(tool_defs, list):
                continue
                
            for tool_def in tool_defs:
                # Check user permission if needed
                if not _has_tool_permission(user, tool_def.get("name", "")):
                    continue
                    
                tools.append(MCPTool(
                    name=tool_def.get("name", ""),
                    description=tool_def.get("description", ""),
                    parameters=tool_def.get("parameters", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }),
                    execute=tool_def.get("function") or tool_def.get("execute")
                ))
                
        except Exception as e:
            frappe.log_error(
                f"Error loading tool from {tool_path}: {str(e)}",
                "MCP Tool Loader"
            )
            
    return tools

def _has_tool_permission(user: str, tool_name: str) -> bool:
    """
    Check if user has permission to use a tool.
    Returns True by default if no permission system configured.
    """
    # Check if FAC permission system exists
    if frappe.db.exists("DocType", "Assistant Tool Permission"):
        # Check specific permission
        has_perm = frappe.db.exists("Assistant Tool Permission", {
            "user": user,
            "tool_name": tool_name,
            "enabled": 1
        })
        if has_perm:
            return True
            
        # Check if user has wildcard permission
        has_all = frappe.db.exists("Assistant Tool Permission", {
            "user": user,
            "tool_name": "*",
            "enabled": 1
        })
        return bool(has_all)
        
    # No permission system - allow all
    return True

async def execute_tool(tool: MCPTool, arguments: Dict[str, Any]) -> str:
    """
    Execute an MCP tool and return result as string.
    Handles both sync and async tool functions.
    """
    try:
        result = tool.execute(**arguments)
        
        # Handle async functions
        if hasattr(result, "__await__"):
            result = await result
            
        # Convert result to string
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, default=str)
        return str(result)
        
    except Exception as e:
        frappe.log_error(
            f"Tool execution error [{tool.name}]: {str(e)}",
            "MCP Tool Executor"
        )
        return f"Error executing tool: {str(e)}"

def get_tool_definitions_for_prompt(tools: List[MCPTool]) -> str:
    """
    Generate tool descriptions for system prompt.
    Used to help LLM understand available tools.
    """
    if not tools:
        return "No tools available."
        
    lines = ["## Available Tools\n"]
    
    for tool in tools:
        lines.append(f"### {tool.name}")
        lines.append(f"{tool.description}\n")
        
        # Add parameters
        props = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])
        
        if props:
            lines.append("Parameters:")
            for param_name, param_def in props.items():
                req_marker = " (required)" if param_name in required else ""
                param_type = param_def.get("type", "any")
                param_desc = param_def.get("description", "")
                lines.append(f"  - {param_name}: {param_type}{req_marker} - {param_desc}")
        lines.append("")
        
    return "\n".join(lines)
