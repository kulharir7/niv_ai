"""
Enhanced Tool Descriptions for Niv AI MCP Tools.

Problem: FAC tool descriptions are too short/generic → LLM picks wrong tools.
Solution: Override descriptions at the Niv AI layer before passing to LangChain.

Usage: Called by langchain/tools.py during get_langchain_tools()
"""

# ─── Enhanced Descriptions ─────────────────────────────────────────
# Key = FAC tool name (exact match)
# Value = dict with "description" and optional "parameters" overrides

TOOL_ENHANCEMENTS = {
    "list_documents": {
        "description": (
            "Search and list Frappe/ERPNext documents with filtering, sorting, and pagination.\n\n"
            "USE THIS WHEN:\n"
            "- User wants to find records matching criteria (e.g., 'show all overdue loans')\n"
            "- User wants a list of documents (e.g., 'list all customers in Mumbai')\n"
            "- User wants to browse/explore data\n\n"
            "DO NOT USE WHEN:\n"
            "- You know the exact document name → use get_document instead\n"
            "- You need complex JOINs, GROUP BY, SUM, AVG → use run_database_query instead\n"
            "- You need full-text search across all fields → use search_documents instead\n"
            "- You don't know the DocType name → use search_doctype first\n"
            "- You don't know field names → use get_doctype_info first\n\n"
            "FILTER SYNTAX:\n"
            "- Exact match: {\"status\": \"Active\"}\n"
            "- Operators: {\"creation\": [\">\", \"2024-01-01\"]}\n"
            "- Like: {\"customer_name\": [\"like\", \"%Mahaveer%\"]}\n"
            "- In list: {\"status\": [\"in\", [\"Active\", \"Open\"]]}\n"
            "- Between: {\"creation\": [\"between\", [\"2024-01-01\", \"2024-12-31\"]]}\n"
            "- Operators: =, !=, >, <, >=, <=, like, in, not in, between, is\n\n"
            "COMMON DOCTYPES: Customer, Supplier, Item, Sales Invoice, Purchase Invoice, "
            "Sales Order, Purchase Order, Journal Entry, Payment Entry, Employee, "
            "Loan Application, Loan, Loan Repayment\n\n"
            "TIP: Always include 'name' in fields. Default limit is 20."
        ),
        "parameters": {
            "doctype": {
                "type": "string",
                "description": (
                    "Exact DocType name in Title Case with spaces. "
                    "Examples: 'Sales Invoice', 'Loan Application', 'Journal Entry'. "
                    "Use search_doctype tool if you don't know the exact name."
                ),
            },
            "filters": {
                "type": "object",
                "description": (
                    "Query filters as key-value pairs. Keys are field names, "
                    "values are exact match or [operator, value] pairs. "
                    "Examples: {\"status\": \"Active\"}, {\"creation\": [\">\", \"2024-01-01\"]}, "
                    "{\"customer_name\": [\"like\", \"%search%\"]}"
                ),
            },
            "fields": {
                "type": "array",
                "description": (
                    "Fields to return. Use get_doctype_info to discover available fields. "
                    "Always include 'name'. Use ['*'] for all fields (expensive).\n"
                    "COMMON FIELDS BY DOCTYPE:\n"
                    "- Sales Order: name, customer_name, transaction_date, grand_total, status, delivery_date\n"
                    "- Sales Invoice: name, customer_name, posting_date, grand_total, status\n"
                    "- Purchase Order: name, supplier_name, transaction_date, grand_total, status\n"
                    "- Loan: name, applicant_name, loan_amount, status, posting_date, disbursement_date\n"
                    "- Customer: name, customer_name, customer_type, territory\n"
                    "NOTE: Sales Order uses 'transaction_date' NOT 'posting_date'. Check DocType fields if unsure."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Max records to return. Use 5-10 for previews, 20 for normal lists, "
                    "100+ for exports. Default: 20. Maximum: 1000."
                ),
            },
            "order_by": {
                "type": "string",
                "description": (
                    "Sort order. Format: 'field_name asc' or 'field_name desc'. "
                    "Multiple: 'field1 desc, field2 asc'. Default: 'creation desc'. "
                    "Examples: 'creation desc', 'modified desc', 'name asc', 'loan_amount desc'"
                ),
            },
        },
    },

    "get_document": {
        "description": (
            "Get a single document by its exact name/ID.\n\n"
            "USE THIS WHEN:\n"
            "- You know the exact document name (e.g., 'SAL-INV-0042', 'LOAN-0001')\n"
            "- You need ALL fields of a specific document\n"
            "- User asks about a specific record by name/ID\n\n"
            "DO NOT USE WHEN:\n"
            "- You need to search/filter multiple documents → use list_documents\n"
            "- You don't know the document name → use list_documents with filters first\n\n"
            "Returns: All fields of the document including child tables."
        ),
    },

    "get_doctype_info": {
        "description": (
            "Get DocType metadata: field names, field types, required fields, linked DocTypes.\n\n"
            "USE THIS WHEN:\n"
            "- BEFORE calling list_documents, to discover correct field names for filters\n"
            "- BEFORE calling create_document, to know required fields\n"
            "- User asks about the structure of a DocType\n"
            "- You're unsure which fields exist on a DocType\n\n"
            "DO NOT USE FOR:\n"
            "- Known DocTypes where you already know the fields (Customer, Sales Invoice, etc.)\n\n"
            "IMPORTANT: Call this FIRST when you don't know field names. "
            "It prevents errors from using wrong field names in list_documents or create_document.\n\n"
            "Returns: Field list with names, types, options, required status, and descriptions."
        ),
    },

    "search_documents": {
        "description": (
            "Full-text search across multiple fields of a DocType.\n\n"
            "USE THIS WHEN:\n"
            "- User wants to search by partial text across many fields\n"
            "- You don't know which field contains the search term\n"
            "- Quick fuzzy search (e.g., 'find anything related to Mahaveer')\n\n"
            "DO NOT USE WHEN:\n"
            "- You know the exact field to filter → use list_documents with filters instead\n"
            "- You need structured filtering with operators → use list_documents\n\n"
            "NOTE: This does broad text search. For precise filtered queries, use list_documents."
        ),
    },

    "search_doctype": {
        "description": (
            "Search for DocType NAMES (not documents). Finds which DocTypes exist in the system.\n\n"
            "USE THIS WHEN:\n"
            "- You don't know the exact DocType name\n"
            "- User mentions a concept and you need to find the matching DocType\n"
            "- Example: User says 'invoices' → search to find 'Sales Invoice' vs 'Purchase Invoice'\n\n"
            "DO NOT USE WHEN:\n"
            "- You already know the DocType name → go directly to list_documents/get_document\n\n"
            "Returns: List of matching DocType names."
        ),
    },

    "create_document": {
        "description": (
            "Create a new document in the system.\n\n"
            "USE THIS WHEN:\n"
            "- User explicitly asks to create/add a new record\n"
            "- Creating Custom Fields, Property Setters, Scripts, etc.\n\n"
            "IMPORTANT:\n"
            "- Use get_doctype_info FIRST to discover required fields\n"
            "- All document fields go inside the 'data' parameter\n"
            "- The 'doctype' parameter is separate from 'data'\n"
            "- Example: create_document(doctype='Customer', data={'customer_name': 'ABC Corp', 'customer_type': 'Company'})\n\n"
            "CONFIRMATION: Write operations may require user confirmation. "
            "If the tool returns a confirmation prompt, STOP and wait for user response."
        ),
    },

    "update_document": {
        "description": (
            "Update an existing document's fields.\n\n"
            "USE THIS WHEN:\n"
            "- User asks to change/update/modify a specific record\n"
            "- You know both the DocType and document name\n\n"
            "PARAMETERS:\n"
            "- doctype: The DocType name (e.g., 'Customer')\n"
            "- name: The exact document name/ID\n"
            "- data: Dict of fields to update (only changed fields needed)\n\n"
            "Example: update_document(doctype='Customer', name='CUST-0001', data={'status': 'Active'})"
        ),
    },

    "delete_document": {
        "description": (
            "DELETE a document permanently. ⚠️ DANGEROUS — cannot be undone!\n\n"
            "USE THIS ONLY WHEN:\n"
            "- User explicitly asks to delete a specific record\n"
            "- You have confirmed the exact document name\n\n"
            "ALWAYS requires user confirmation before execution.\n"
            "Never delete without the user's explicit request."
        ),
    },

    "submit_document": {
        "description": (
            "Submit a draft document (changes docstatus from 0 to 1).\n\n"
            "USE THIS WHEN:\n"
            "- User asks to submit/finalize a document\n"
            "- Document is in Draft status (docstatus=0)\n\n"
            "⚠️ Submitted documents cannot be easily modified — they require amendment.\n"
            "Always requires user confirmation."
        ),
    },

    "run_database_query": {
        "description": (
            "Execute a SELECT SQL query directly on the database.\n\n"
            "USE THIS WHEN:\n"
            "- You need JOINs across multiple DocTypes\n"
            "- You need GROUP BY, SUM, AVG, COUNT aggregations\n"
            "- Complex analytics that list_documents cannot handle\n"
            "- 'How many X' questions → SELECT COUNT(*)\n"
            "- 'Total/average/sum of X' questions → SELECT SUM/AVG\n"
            "- Date range analysis across tables\n\n"
            "DO NOT USE WHEN:\n"
            "- Simple list with filters → use list_documents instead (faster, cached)\n"
            "- Single document lookup → use get_document\n\n"
            "RULES:\n"
            "- SELECT queries ONLY (no INSERT/UPDATE/DELETE)\n"
            "- Table names are like `tabDocType Name` (e.g., `tabSales Invoice`, `tabLoan Application`)\n"
            "- Field names use snake_case (e.g., loan_amount, transaction_date, grand_total)\n"
            "- Always add LIMIT to prevent huge result sets\n\n"
            "EXAMPLES:\n"
            "- SELECT COUNT(*) FROM `tabLoan Application` WHERE status='Active'\n"
            "- SELECT status, COUNT(*) as count, SUM(loan_amount) as total FROM `tabLoan` GROUP BY status\n"
            "- SELECT a.name, a.loan_amount, b.amount_paid FROM `tabLoan` a JOIN `tabLoan Repayment` b ON b.against_loan = a.name"
        ),
    },

    "run_python_code": {
        "description": (
            "Execute Python code in the Frappe server context. ⚠️ POWERFUL & DANGEROUS.\n\n"
            "USE THIS ONLY WHEN:\n"
            "- Complex data processing that SQL can't handle\n"
            "- Need to use frappe API methods\n"
            "- Batch operations\n"
            "- Custom calculations requiring Python logic\n\n"
            "DO NOT USE FOR:\n"
            "- Simple queries → use list_documents or run_database_query\n"
            "- Simple math → calculate it yourself\n"
            "- EMI, WRR, NPA calculations → use your own knowledge\n\n"
            "Always requires user confirmation before execution.\n"
            "Available: frappe, json, datetime. No os/subprocess access."
        ),
    },

    "generate_report": {
        "description": (
            "Generate a pre-built report from the system.\n\n"
            "USE THIS WHEN:\n"
            "- User asks for a standard report (Trial Balance, P&L, etc.)\n"
            "- You know the exact report name and required filters\n\n"
            "IMPORTANT: Call report_requirements FIRST to discover required filters.\n"
            "Without correct filters, the report will fail.\n\n"
            "Example flow:\n"
            "1. report_requirements('Trial Balance') → get required filters\n"
            "2. generate_report('Trial Balance', filters={...}) → get report data"
        ),
    },

    "report_list": {
        "description": (
            "List all available reports in the system.\n\n"
            "USE THIS WHEN:\n"
            "- User asks 'what reports are available?'\n"
            "- You need to find the exact report name before generating it\n\n"
            "Returns: List of report names with their types and modules."
        ),
    },

    "report_requirements": {
        "description": (
            "Get required filters/parameters for a specific report.\n\n"
            "USE THIS BEFORE generate_report to discover what filters are needed.\n"
            "Without this, you'll likely pass wrong/missing filters and the report will fail.\n\n"
            "Example: report_requirements('Trial Balance') → tells you that 'company' and 'fiscal_year' are required."
        ),
    },

    "search_link": {
        "description": (
            "Search for link field values (autocomplete-style search).\n\n"
            "USE THIS WHEN:\n"
            "- You need to find the exact name of a linked record\n"
            "- User mentions a partial name and you need the exact match\n"
            "- Example: User says 'Mahaveer company' → search_link to find exact Customer name\n\n"
            "Returns: Matching records with name and description."
        ),
    },

    "analyze_business_data": {
        "description": (
            "Analyze business data with built-in analytics functions.\n\n"
            "USE THIS WHEN:\n"
            "- User needs business intelligence insights\n"
            "- Trend analysis, comparisons, forecasting\n"
            "- Pre-built analytics that go beyond raw SQL\n\n"
            "For simple aggregations, prefer run_database_query instead."
        ),
    },

    "create_visualization": {
        "description": (
            "Create a chart/visualization from data.\n\n"
            "USE THIS WHEN:\n"
            "- User asks for a chart, graph, or visual representation\n"
            "- After fetching data, to present it visually\n\n"
            "Supports: bar, line, pie, donut, and other chart types."
        ),
    },
}


def get_enhanced_description(tool_name: str) -> str:
    """Get enhanced description for a tool, or None if no enhancement exists."""
    enhancement = TOOL_ENHANCEMENTS.get(tool_name)
    if enhancement:
        return enhancement.get("description")
    return None


def get_enhanced_parameters(tool_name: str) -> dict:
    """Get enhanced parameter descriptions for a tool."""
    enhancement = TOOL_ENHANCEMENTS.get(tool_name)
    if enhancement:
        return enhancement.get("parameters", {})
    return {}


def enhance_tool_schema(tool_name: str, original_schema: dict) -> dict:
    """Merge enhanced parameter descriptions into the original schema.
    
    Does NOT change structure — only enriches descriptions and adds examples.
    """
    param_enhancements = get_enhanced_parameters(tool_name)
    if not param_enhancements:
        return original_schema
    
    # Deep copy to avoid mutating cached schemas
    import copy
    schema = copy.deepcopy(original_schema)
    
    properties = schema.get("properties", {})
    for param_name, enhancements in param_enhancements.items():
        if param_name in properties:
            # Only override description, don't change type/required
            if "description" in enhancements:
                properties[param_name]["description"] = enhancements["description"]
    
    return schema
