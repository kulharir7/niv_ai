"""
Frappe Assistant Core (FAC) Adapter for Niv AI

Discovers and wraps all tools from frappe_assistant_core plugins
so they can be used with OpenAI function calling format.

This gives Niv AI access to all 23+ battle-tested FAC tools
without reimplementing them.
"""

import frappe
import json
import importlib
import os
from typing import Dict, Any, List, Optional


# Cache for discovered tools
_fac_tools_cache = None


def is_fac_installed() -> bool:
    """Check if frappe_assistant_core is installed"""
    try:
        import frappe_assistant_core
        return True
    except ImportError:
        return False


def discover_fac_tools() -> Dict[str, Any]:
    """
    Discover all tools from frappe_assistant_core plugins.
    Returns dict of {tool_name: tool_instance}
    """
    global _fac_tools_cache
    if _fac_tools_cache is not None:
        return _fac_tools_cache

    if not is_fac_installed():
        _fac_tools_cache = {}
        return _fac_tools_cache

    tools = {}

    try:
        # Discover plugins
        plugins_dir = os.path.join(
            frappe.get_app_path("frappe_assistant_core"), "plugins"
        )

        if not os.path.exists(plugins_dir):
            _fac_tools_cache = {}
            return _fac_tools_cache

        # Iterate through plugin directories
        for plugin_name in os.listdir(plugins_dir):
            plugin_path = os.path.join(plugins_dir, plugin_name)
            if not os.path.isdir(plugin_path) or plugin_name.startswith("_"):
                continue

            tools_dir = os.path.join(plugin_path, "tools")
            if not os.path.exists(tools_dir):
                continue

            # Load each tool module
            for tool_file in os.listdir(tools_dir):
                if not tool_file.endswith(".py") or tool_file.startswith("_"):
                    continue

                module_name = tool_file[:-3]  # remove .py
                try:
                    module = importlib.import_module(
                        f"frappe_assistant_core.plugins.{plugin_name}.tools.{module_name}"
                    )

                    # Find BaseTool subclass in module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and
                            hasattr(attr, 'execute') and
                            hasattr(attr, 'inputSchema') and
                            attr_name not in ('BaseTool',)):
                            try:
                                instance = attr()
                                if hasattr(instance, 'name') and instance.name:
                                    tools[instance.name] = instance
                            except Exception:
                                pass
                        # Also check module-level instances (e.g., document_create = DocumentCreate())
                        elif (hasattr(attr, 'execute') and
                              hasattr(attr, 'inputSchema') and
                              hasattr(attr, 'name') and
                              not isinstance(attr, type)):
                            if attr.name:
                                tools[attr.name] = attr

                except Exception as e:
                    frappe.logger().debug(f"Niv AI: Could not load FAC tool {module_name}: {e}")

    except Exception as e:
        frappe.logger().error(f"Niv AI: Error discovering FAC tools: {e}")

    _fac_tools_cache = tools
    return tools


def get_fac_tool(tool_name: str):
    """Get a specific FAC tool instance by name"""
    tools = discover_fac_tools()
    return tools.get(tool_name)


def execute_fac_tool(tool_name: str, arguments: Dict[str, Any], user: str = None) -> Dict[str, Any]:
    """
    Execute a FAC tool and return the result.
    Uses FAC's own security, validation, and error handling.
    """
    tool = get_fac_tool(tool_name)
    if not tool:
        return {"success": False, "error": f"FAC tool '{tool_name}' not found"}

    # Use _safe_execute if available (includes permission checks, logging)
    if hasattr(tool, '_safe_execute'):
        return tool._safe_execute(arguments)
    else:
        try:
            result = tool.execute(arguments)
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


def fac_tools_to_openai_format(tool_names: List[str] = None) -> List[Dict]:
    """
    Convert FAC tools to OpenAI function calling format.
    If tool_names is None, converts all discovered tools.
    """
    tools = discover_fac_tools()
    result = []

    for name, tool in tools.items():
        if tool_names and name not in tool_names:
            continue

        # Convert FAC inputSchema to OpenAI parameters format
        params = getattr(tool, 'inputSchema', {})
        if not params:
            params = {"type": "object", "properties": {}}

        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": getattr(tool, 'description', name),
                "parameters": params,
            }
        })

    return result


def get_fac_tool_list() -> List[Dict]:
    """Get a summary list of all FAC tools (for admin UI)"""
    tools = discover_fac_tools()
    result = []
    for name, tool in tools.items():
        result.append({
            "name": name,
            "description": getattr(tool, 'description', ''),
            "category": getattr(tool, 'category', 'Custom'),
            "source": "frappe_assistant_core",
            "requires_permission": getattr(tool, 'requires_permission', None),
        })
    return result


def clear_cache():
    """Clear the tool discovery cache (call after app updates)"""
    global _fac_tools_cache
    _fac_tools_cache = None
