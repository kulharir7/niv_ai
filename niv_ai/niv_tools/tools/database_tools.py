import frappe
import json


def run_python_code(code):
    """Execute Python code on the server. ADMIN ONLY."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        return {"error": "Admin access required"}

    # Safety: basic checks
    dangerous = ["os.system", "subprocess", "eval(", "exec(", "__import__",
                  "shutil.rmtree", "os.remove", "os.unlink"]
    for d in dangerous:
        if d in code:
            return {"error": f"Dangerous operation detected: {d}"}

    try:
        local_vars = {"frappe": frappe, "json": json}
        exec(code, {"__builtins__": __builtins__}, local_vars)

        result = local_vars.get("result", "Code executed successfully (set 'result' variable to return data)")

        # Try to serialize
        try:
            json.dumps(result, default=str)
        except (TypeError, ValueError):
            result = str(result)

        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"Execution error: {str(e)}"}


def run_database_query(query, limit=100):
    """Execute a SQL SELECT query. ADMIN ONLY."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        return {"error": "Admin access required"}

    # Only allow SELECT
    clean = query.strip().upper()
    if not clean.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed"}

    # Block dangerous keywords
    blocked = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
    for b in blocked:
        if f" {b} " in f" {clean} ":
            return {"error": f"'{b}' operations are not allowed"}

    # Add LIMIT if not present
    limit = min(int(limit), 500)
    if "LIMIT" not in clean:
        query = f"{query.rstrip(';')} LIMIT {limit}"

    try:
        result = frappe.db.sql(query, as_dict=True)
        return {
            "success": True,
            "row_count": len(result),
            "data": result,
        }
    except Exception as e:
        return {"error": f"Query error: {str(e)}"}
