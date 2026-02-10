import frappe
import json


@frappe.whitelist()
def get_tools():
    """Get all available tools for the current user"""
    from niv_ai.niv_core.langchain.tools import get_langchain_tools
    lc_tools = get_langchain_tools()
    return [{"name": t.name, "description": t.description} for t in lc_tools]


@frappe.whitelist()
def register_tool(tool_name, display_name, description, category, function_path, parameters_json, requires_admin=0):
    """Register a new tool (admin only)"""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can register tools")

    if frappe.db.exists("Niv Tool", tool_name):
        # Update existing
        doc = frappe.get_doc("Niv Tool", tool_name)
        doc.display_name = display_name
        doc.description = description
        doc.category = category
        doc.function_path = function_path
        doc.parameters_json = parameters_json if isinstance(parameters_json, str) else json.dumps(parameters_json)
        doc.requires_admin = requires_admin
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "Niv Tool",
            "tool_name": tool_name,
            "display_name": display_name,
            "description": description,
            "category": category,
            "function_path": function_path,
            "parameters_json": parameters_json if isinstance(parameters_json, str) else json.dumps(parameters_json),
            "requires_admin": requires_admin,
            "is_active": 1,
            "log_execution": 1,
        })
        doc.insert(ignore_permissions=True)

    return {"status": "ok", "tool": tool_name}


def register_builtin_tools():
    """Register all built-in tools. Called during install."""
    tools = _get_builtin_tool_definitions()
    for tool in tools:
        try:
            register_tool(**tool)
        except Exception as e:
            frappe.log_error(f"Failed to register tool {tool.get('tool_name')}: {e}")
    frappe.db.commit()


def _get_builtin_tool_definitions():
    """All 23 built-in tool definitions"""
    base = "niv_ai.niv_tools.tools"
    return [
        # Document Tools (6)
        {
            "tool_name": "create_document",
            "display_name": "Create Document",
            "description": "Create a new document/record in ERPNext. Specify the DocType and field values.",
            "category": "document",
            "function_path": f"{base}.document_tools.create_document",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name (e.g. 'Sales Invoice', 'Customer')"},
                    "values": {"type": "object", "description": "Field name-value pairs for the new document"}
                },
                "required": ["doctype", "values"]
            }),
        },
        {
            "tool_name": "get_document",
            "display_name": "Get Document",
            "description": "Read/fetch a specific document by DocType and name. Optionally specify which fields to return.",
            "category": "document",
            "function_path": f"{base}.document_tools.get_document",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name"},
                    "name": {"type": "string", "description": "The document name/ID"},
                    "fields": {"type": "array", "items": {"type": "string"}, "description": "Specific fields to return (optional)"}
                },
                "required": ["doctype", "name"]
            }),
        },
        {
            "tool_name": "update_document",
            "display_name": "Update Document",
            "description": "Update fields of an existing document.",
            "category": "document",
            "function_path": f"{base}.document_tools.update_document",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name"},
                    "name": {"type": "string", "description": "The document name/ID"},
                    "values": {"type": "object", "description": "Field name-value pairs to update"}
                },
                "required": ["doctype", "name", "values"]
            }),
        },
        {
            "tool_name": "delete_document",
            "display_name": "Delete Document",
            "description": "Delete a document from ERPNext.",
            "category": "document",
            "function_path": f"{base}.document_tools.delete_document",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name"},
                    "name": {"type": "string", "description": "The document name/ID"}
                },
                "required": ["doctype", "name"]
            }),
        },
        {
            "tool_name": "submit_document",
            "display_name": "Submit Document",
            "description": "Submit a submittable document (e.g. Sales Invoice, Purchase Order).",
            "category": "document",
            "function_path": f"{base}.document_tools.submit_document",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name"},
                    "name": {"type": "string", "description": "The document name/ID"}
                },
                "required": ["doctype", "name"]
            }),
        },
        {
            "tool_name": "list_documents",
            "display_name": "List Documents",
            "description": "List documents of a DocType with optional filters, fields, ordering, and pagination.",
            "category": "document",
            "function_path": f"{base}.document_tools.list_documents",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name"},
                    "filters": {"type": "object", "description": "Filter conditions as key-value pairs or list of [field, operator, value]"},
                    "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to return"},
                    "order_by": {"type": "string", "description": "Order by clause (e.g. 'creation DESC')"},
                    "limit": {"type": "integer", "description": "Number of records to return (default 20)"}
                },
                "required": ["doctype"]
            }),
        },
        # Search Tools (4)
        {
            "tool_name": "search_documents",
            "display_name": "Search Documents",
            "description": "Full-text search across documents. Searches in document names, titles, and content.",
            "category": "search",
            "function_path": f"{base}.search_tools.search_documents",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "doctype": {"type": "string", "description": "Limit search to specific DocType (optional)"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"}
                },
                "required": ["query"]
            }),
        },
        {
            "tool_name": "search_doctype",
            "display_name": "Search DocType",
            "description": "Find a DocType by name or description. Useful to discover what DocTypes exist.",
            "category": "search",
            "function_path": f"{base}.search_tools.search_doctype",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term for DocType name"}
                },
                "required": ["query"]
            }),
        },
        {
            "tool_name": "search_link",
            "display_name": "Search Link",
            "description": "Search for values in a Link field. Useful to find document names for linking.",
            "category": "search",
            "function_path": f"{base}.search_tools.search_link",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType to search in"},
                    "query": {"type": "string", "description": "Search text"},
                    "filters": {"type": "object", "description": "Additional filters"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"}
                },
                "required": ["doctype", "query"]
            }),
        },
        {
            "tool_name": "search",
            "display_name": "Global Search",
            "description": "Global search across all DocTypes in ERPNext.",
            "category": "search",
            "function_path": f"{base}.search_tools.global_search",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"}
                },
                "required": ["query"]
            }),
        },
        # Report Tools (4)
        {
            "tool_name": "generate_report",
            "display_name": "Generate Report",
            "description": "Run a Script Report or Query Report and return results.",
            "category": "report",
            "function_path": f"{base}.report_tools.generate_report",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "report_name": {"type": "string", "description": "Name of the report"},
                    "filters": {"type": "object", "description": "Report filter values"},
                    "limit": {"type": "integer", "description": "Max rows (default 100)"}
                },
                "required": ["report_name"]
            }),
        },
        {
            "tool_name": "report_list",
            "display_name": "List Reports",
            "description": "List available reports, optionally filtered by module or DocType.",
            "category": "report",
            "function_path": f"{base}.report_tools.report_list",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "Filter by module (optional)"},
                    "doctype": {"type": "string", "description": "Filter by reference DocType (optional)"}
                }
            }),
        },
        {
            "tool_name": "report_requirements",
            "display_name": "Report Requirements",
            "description": "Get the required filters/parameters for a report before running it.",
            "category": "report",
            "function_path": f"{base}.report_tools.report_requirements",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "report_name": {"type": "string", "description": "Name of the report"}
                },
                "required": ["report_name"]
            }),
        },
        {
            "tool_name": "analyze_business_data",
            "display_name": "Analyze Business Data",
            "description": "Run custom analytics queries on business data. Provide a description of what you want to analyze.",
            "category": "report",
            "function_path": f"{base}.report_tools.analyze_business_data",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "Primary DocType to analyze"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "Metrics to calculate (e.g. 'sum', 'count', 'avg')"},
                    "measure_field": {"type": "string", "description": "Field to measure (e.g. 'grand_total')"},
                    "group_by": {"type": "string", "description": "Field to group by (optional)"},
                    "filters": {"type": "object", "description": "Filter conditions"},
                    "period": {"type": "string", "description": "Time period: 'today', 'week', 'month', 'quarter', 'year'"}
                },
                "required": ["doctype"]
            }),
        },
        # Workflow Tools (1)
        {
            "tool_name": "run_workflow",
            "display_name": "Run Workflow Action",
            "description": "Trigger a workflow action on a document (e.g. Approve, Reject, Submit).",
            "category": "workflow",
            "function_path": f"{base}.workflow_tools.run_workflow",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType"},
                    "name": {"type": "string", "description": "Document name"},
                    "action": {"type": "string", "description": "Workflow action to trigger"}
                },
                "required": ["doctype", "name", "action"]
            }),
        },
        # Database Tools (2) - admin only
        {
            "tool_name": "run_python_code",
            "display_name": "Run Python Code",
            "description": "Execute arbitrary Python code on the server. ADMIN ONLY. Use frappe module. Return results via 'result' variable.",
            "category": "database",
            "function_path": f"{base}.database_tools.run_python_code",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute. Use 'result' variable to return data."}
                },
                "required": ["code"]
            }),
            "requires_admin": 1,
        },
        {
            "tool_name": "run_database_query",
            "display_name": "Run Database Query",
            "description": "Execute a SQL query on the database. ADMIN ONLY. Only SELECT queries allowed.",
            "category": "database",
            "function_path": f"{base}.database_tools.run_database_query",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL SELECT query to execute"},
                    "limit": {"type": "integer", "description": "Max rows (default 100)"}
                },
                "required": ["query"]
            }),
            "requires_admin": 1,
        },
        # Utility Tools (6)
        {
            "tool_name": "get_doctype_info",
            "display_name": "Get DocType Info",
            "description": "Get schema/field information about a DocType. Shows all fields, their types, and options.",
            "category": "utility",
            "function_path": f"{base}.utility_tools.get_doctype_info",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "doctype": {"type": "string", "description": "The DocType name"}
                },
                "required": ["doctype"]
            }),
        },
        {
            "tool_name": "fetch_url",
            "display_name": "Fetch URL",
            "description": "Fetch content from a URL and return the text.",
            "category": "utility",
            "function_path": f"{base}.utility_tools.fetch_url",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"}
                },
                "required": ["url"]
            }),
        },
        {
            "tool_name": "extract_file_content",
            "display_name": "Extract File Content",
            "description": "Extract text content from an uploaded file (PDF, image, Excel, Word, etc.)",
            "category": "utility",
            "function_path": f"{base}.utility_tools.extract_file_content",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "file_url": {"type": "string", "description": "The file URL from Frappe file manager"}
                },
                "required": ["file_url"]
            }),
        },
        {
            "tool_name": "create_dashboard",
            "display_name": "Create Dashboard",
            "description": "Create a new Dashboard in ERPNext.",
            "category": "utility",
            "function_path": f"{base}.utility_tools.create_dashboard",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "dashboard_name": {"type": "string", "description": "Name for the dashboard"},
                    "module": {"type": "string", "description": "Module (optional)"}
                },
                "required": ["dashboard_name"]
            }),
        },
        {
            "tool_name": "create_dashboard_chart",
            "display_name": "Create Dashboard Chart",
            "description": "Create a chart for a Dashboard.",
            "category": "utility",
            "function_path": f"{base}.utility_tools.create_dashboard_chart",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {
                    "chart_name": {"type": "string", "description": "Name for the chart"},
                    "chart_type": {"type": "string", "description": "Type: Count, Sum, Average, Group By"},
                    "doctype": {"type": "string", "description": "Source DocType"},
                    "based_on": {"type": "string", "description": "Date field for time series"},
                    "value_based_on": {"type": "string", "description": "Field to aggregate (for Sum/Average)"},
                    "group_by_type": {"type": "string", "description": "Group By field type"},
                    "group_by_based_on": {"type": "string", "description": "Field to group by"},
                    "time_interval": {"type": "string", "description": "Daily, Weekly, Monthly, Quarterly, Yearly"},
                    "timespan": {"type": "string", "description": "Last Month, Last Quarter, Last Year, etc."},
                    "filters_json": {"type": "string", "description": "JSON filters"}
                },
                "required": ["chart_name", "chart_type", "doctype"]
            }),
        },
        {
            "tool_name": "list_user_dashboards",
            "display_name": "List User Dashboards",
            "description": "List all dashboards available to the current user.",
            "category": "utility",
            "function_path": f"{base}.utility_tools.list_user_dashboards",
            "parameters_json": json.dumps({
                "type": "object",
                "properties": {}
            }),
        },
    ]
