"""API Builder for Niv AI Dev Mode 3.0.

Creates whitelisted API endpoints as Frappe Server Scripts.
User describes API in chat → Niv generates code → preview → create Server Script.

Usage via run_python_code MCP tool:
    from niv_ai.niv_core.tools.api_builder import create_api, list_apis, test_api, delete_api
"""
import frappe
import json
from typing import Optional


def create_api(
    api_name: str,
    description: str,
    code: str,
    method: str = "GET",
    allow_guest: bool = False,
    dry_run: bool = True
) -> dict:
    """Create a whitelisted API endpoint as a Server Script.
    
    Args:
        api_name: API method name (e.g., 'get_overdue_loans'). 
                  Accessible at /api/method/{api_name}
        description: What this API does
        code: Python code for the API. Use frappe.form_dict for params.
              Set frappe.response["message"] = result to return data.
        method: HTTP method — GET, POST, PUT, DELETE
        allow_guest: If True, no login required
        dry_run: If True, only preview without creating
    
    Returns:
        dict with status, preview, script details
    """
    if not api_name or not code:
        return {"status": "error", "message": "api_name and code are required"}
    
    # Clean api_name
    api_name = api_name.strip().replace(" ", "_").lower()
    
    # Check if already exists
    existing = frappe.db.exists("Server Script", {"api_method": api_name})
    if existing:
        return {
            "status": "error", 
            "message": f"API '{api_name}' already exists as Server Script '{existing}'. Delete it first or use a different name."
        }
    
    # Build the full script
    full_script = _build_api_script(code, description)
    
    # Validate syntax
    syntax_error = _validate_python(full_script)
    if syntax_error:
        return {"status": "error", "message": f"Syntax error in code: {syntax_error}"}
    
    script_name = f"Niv API: {api_name}"
    
    preview = {
        "name": script_name,
        "api_method": api_name,
        "api_url": f"/api/method/{api_name}",
        "http_method": method,
        "allow_guest": allow_guest,
        "description": description,
        "script": full_script,
    }
    
    if dry_run:
        return {
            "status": "preview",
            "message": f"API '{api_name}' ready to create.\nEndpoint: /api/method/{api_name}\nMethod: {method}\n\nCall with dry_run=False to create.",
            "preview": preview
        }
    
    # Create Server Script
    try:
        doc = frappe.get_doc({
            "doctype": "Server Script",
            "name": script_name,
            "script_type": "API",
            "api_method": api_name,
            "allow_guest": 1 if allow_guest else 0,
            "script": full_script,
            "disabled": 0,
        })
        doc.flags.ignore_permissions = True
        doc.insert()
        frappe.db.commit()
        
        return {
            "status": "success",
            "message": f"✅ API created!\n\nEndpoint: /api/method/{api_name}\nMethod: {method}\nServer Script: {script_name}",
            "api_url": f"/api/method/{api_name}",
            "script_name": script_name
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to create: {str(e)[:300]}"}


def list_apis() -> dict:
    """List all API Server Scripts created by Niv AI.
    
    Returns:
        dict with list of APIs
    """
    scripts = frappe.get_all(
        "Server Script",
        filters={"script_type": "API"},
        fields=["name", "api_method", "allow_guest", "disabled", "modified"],
        order_by="modified desc",
        limit=50
    )
    
    if not scripts:
        return {"status": "empty", "message": "No API Server Scripts found.", "apis": []}
    
    apis = []
    for s in scripts:
        apis.append({
            "name": s.name,
            "endpoint": f"/api/method/{s.api_method}",
            "allow_guest": bool(s.allow_guest),
            "disabled": bool(s.disabled),
            "modified": str(s.modified)
        })
    
    return {
        "status": "success",
        "message": f"Found {len(apis)} API endpoints",
        "apis": apis
    }


def test_api(api_name: str, params: Optional[dict] = None) -> dict:
    """Test an API endpoint by calling it internally.
    
    Args:
        api_name: API method name (e.g., 'get_overdue_loans')
        params: Optional dict of parameters to pass
    
    Returns:
        dict with API response or error
    """
    # Check if exists
    if not frappe.db.exists("Server Script", {"api_method": api_name}):
        return {"status": "error", "message": f"API '{api_name}' not found"}
    
    try:
        # Simulate API call
        if params:
            frappe.form_dict.update(params)
        
        # Get the script and execute
        script_doc = frappe.get_doc("Server Script", {"api_method": api_name})
        
        if script_doc.disabled:
            return {"status": "error", "message": f"API '{api_name}' is disabled"}
        
        # Execute in safe context
        _locals = {"frappe": frappe}
        safe_exec(script_doc.script, _globals=None, _locals=_locals)
        
        result = frappe.response.get("message", "No response set")
        
        return {
            "status": "success",
            "message": f"API test successful",
            "response": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"API test failed: {str(e)[:300]}"
        }


def delete_api(api_name: str, confirm: bool = False) -> dict:
    """Delete an API Server Script.
    
    Args:
        api_name: API method name
        confirm: Must be True to actually delete
    
    Returns:
        dict with status
    """
    script = frappe.db.get_value("Server Script", {"api_method": api_name}, "name")
    if not script:
        return {"status": "error", "message": f"API '{api_name}' not found"}
    
    if not confirm:
        return {
            "status": "confirm",
            "message": f"Are you sure you want to delete API '{api_name}' (Server Script: {script})?\nCall with confirm=True to delete."
        }
    
    try:
        frappe.delete_doc("Server Script", script, force=True)
        frappe.db.commit()
        return {"status": "success", "message": f"✅ API '{api_name}' deleted"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to delete: {str(e)[:200]}"}


# ============================================================
# Helpers
# ============================================================

def _build_api_script(code: str, description: str = "") -> str:
    """Wrap user code with standard API boilerplate."""
    header = f"# Niv AI Generated API\n# {description}\n\n" if description else ""
    
    # If code doesn't set frappe.response, wrap it
    if "frappe.response" not in code:
        return f"""{header}try:
{_indent(code)}
    frappe.response["message"] = result
except Exception as e:
    frappe.response["message"] = {{"error": str(e)}}"""
    
    return f"{header}{code}"


def _indent(code: str, spaces: int = 4) -> str:
    """Indent code block."""
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in code.split("\n"))


def _validate_python(code: str) -> Optional[str]:
    """Check Python syntax. Returns error message or None."""
    try:
        compile(code, "<api>", "exec")
        return None
    except SyntaxError as e:
        return f"Line {e.lineno}: {e.msg}"


def safe_exec(script, _globals=None, _locals=None):
    """Execute script in Frappe safe context."""
    from frappe.utils.safe_exec import safe_exec as frappe_safe_exec
    frappe_safe_exec(script, _globals, _locals)
