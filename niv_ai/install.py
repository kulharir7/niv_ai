import frappe
import json
from niv_ai.niv_core.compat import FRAPPE_VERSION, check_min_version


def after_install():
    """Run after bench install-app niv_ai"""
    check_min_version()
    _create_settings()
    _seed_default_tools()
    _import_fac_tools()
    _seed_default_prompts()
    _seed_default_plans()
    frappe.db.commit()
    _preload_piper_voice()
    print("✅ Niv AI installed successfully!")


def after_migrate():
    """Run after bench migrate — ensures defaults exist"""
    _create_settings()
    _seed_default_tools()
    _import_fac_tools()
    frappe.db.commit()


def _import_fac_tools():
    """Auto-discover and register Frappe Assistant Core tools"""
    try:
        from niv_ai.niv_tools.fac_adapter import discover_fac_tools
        fac_tools = discover_fac_tools()
    except ImportError:
        print("  → Frappe Assistant Core not installed, skipping FAC tool import")
        return

    count = 0
    for name, tool in fac_tools.items():
        if not frappe.db.exists("Niv Tool", {"tool_name": name}):
            params = getattr(tool, 'inputSchema', {})
            category = getattr(tool, 'category', 'Custom').lower()
            # Map FAC categories to Niv categories
            category_map = {
                'custom': 'custom', 'core': 'document', 'document': 'document',
                'search': 'search', 'report': 'report', 'metadata': 'utility',
                'workflow': 'workflow', 'visualization': 'utility',
                'data_science': 'database', 'data science': 'database',
            }
            mapped_category = category_map.get(category, 'custom')

            requires_admin = getattr(tool, 'requires_permission', None) == "System Manager"

            doc = frappe.get_doc({
                "doctype": "Niv Tool",
                "tool_name": name,
                "display_name": getattr(tool, 'name', name).replace('_', ' ').title(),
                "description": getattr(tool, 'description', ''),
                "category": mapped_category,
                "function_path": f"fac:{name}",
                "parameters_json": json.dumps(params),
                "is_active": 1,
                "is_default": 1,
                "requires_admin": 1 if requires_admin else 0,
                "log_execution": 1,
            })
            doc.insert(ignore_permissions=True)
            count += 1

    if count:
        print(f"  → {count} Frappe Assistant Core tools imported")
    else:
        print(f"  → FAC tools already registered ({len(fac_tools)} found)")


def _create_settings():
    """Create Niv Settings singleton if not exists"""
    if not frappe.db.exists("Niv Settings", "Niv Settings"):
        doc = frappe.get_doc({
            "doctype": "Niv Settings",
            "default_model": "mistral-small-latest",
            "max_tokens_per_message": 4096,
            "max_messages_per_conversation": 50,
            "enable_tools": 1,
            "enable_billing": 0,
            "enable_widget": 1,
            "widget_position": "bottom-right",
            "widget_title": "Niv AI",
            "widget_color": "#5e64ff",
            "admin_allocation_only": 1,
            "token_cost_input": 0.001,
            "token_cost_output": 0.003,
            "system_prompt": DEFAULT_SYSTEM_PROMPT,
        })
        doc.insert(ignore_permissions=True)
        print("  → Niv Settings created")


def _seed_default_tools():
    """Register all 23 built-in tools"""
    for tool in DEFAULT_TOOLS:
        if not frappe.db.exists("Niv Tool", {"tool_name": tool["tool_name"]}):
            doc = frappe.get_doc({
                "doctype": "Niv Tool",
                **tool,
                "is_default": 1,
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)

    count = len(DEFAULT_TOOLS)
    print(f"  → {count} default tools registered")


def _seed_default_prompts():
    """Create default system prompts"""
    for prompt in DEFAULT_PROMPTS:
        if not frappe.db.exists("Niv System Prompt", {"prompt_name": prompt["prompt_name"]}):
            doc = frappe.get_doc({
                "doctype": "Niv System Prompt",
                **prompt,
                "is_default": 1,
            })
            doc.insert(ignore_permissions=True)
    print(f"  → {len(DEFAULT_PROMPTS)} default prompts created")


def _seed_default_plans():
    """Create default credit plans"""
    for plan in DEFAULT_PLANS:
        if not frappe.db.exists("Niv Credit Plan", {"plan_name": plan["plan_name"]}):
            doc = frappe.get_doc({
                "doctype": "Niv Credit Plan",
                **plan,
                "is_default": 1,
            })
            doc.insert(ignore_permissions=True)
    print(f"  → {len(DEFAULT_PLANS)} default credit plans created")


def _preload_piper_voice():
    """Pre-download default Piper voice model during install (optional)"""
    try:
        from niv_ai.niv_core.api.voice import _get_piper_model_path
        model, config = _get_piper_model_path("en_US-lessac-medium")
        if model:
            print("  → Piper voice model pre-downloaded: en_US-lessac-medium")
        else:
            print("  → Piper voice model download skipped")
    except ImportError:
        print("  → Piper TTS not installed (optional), skipping voice pre-download")
    except Exception as e:
        print(f"  → Piper voice pre-download skipped: {e}")


# ─── Default Data ────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are Niv, an AI assistant integrated into ERPNext. You help users with:
- Creating, reading, updating documents
- Searching and finding information
- Running reports and analytics
- Workflow actions
- General questions about their business data

You have access to tools that let you interact with ERPNext directly. Use them when the user asks you to do something in the system.

Be concise, helpful, and professional. If you're unsure about something, ask for clarification.
When using tools, explain what you're doing briefly. Show results in a clean, readable format.
If a tool call fails, explain the error and suggest alternatives."""

DEFAULT_TOOLS = [
    # ── Document Tools ──
    {
        "tool_name": "create_document",
        "display_name": "Create Document",
        "description": "Create a new document in ERPNext (e.g., Sales Order, Customer, Item)",
        "category": "document",
        "function_path": "niv_ai.niv_tools.tools.document_tools.create_document",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "The DocType to create (e.g., 'Customer', 'Sales Order')"},
                "values": {"type": "object", "description": "Field values for the new document"}
            },
            "required": ["doctype", "values"]
        }),
        
    },
    {
        "tool_name": "get_document",
        "display_name": "Get Document",
        "description": "Retrieve a document by DocType and name",
        "category": "document",
        "function_path": "niv_ai.niv_tools.tools.document_tools.get_document",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "name": {"type": "string", "description": "Document name/ID"},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Specific fields to return"}
            },
            "required": ["doctype", "name"]
        }),
        
    },
    {
        "tool_name": "update_document",
        "display_name": "Update Document",
        "description": "Update fields of an existing document",
        "category": "document",
        "function_path": "niv_ai.niv_tools.tools.document_tools.update_document",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "name": {"type": "string", "description": "Document name/ID"},
                "values": {"type": "object", "description": "Fields to update with new values"}
            },
            "required": ["doctype", "name", "values"]
        }),
        
    },
    {
        "tool_name": "delete_document",
        "display_name": "Delete Document",
        "description": "Delete a document from ERPNext",
        "category": "document",
        "function_path": "niv_ai.niv_tools.tools.document_tools.delete_document",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "name": {"type": "string", "description": "Document name/ID"}
            },
            "required": ["doctype", "name"]
        }),
        "requires_admin": 1,
    },
    {
        "tool_name": "submit_document",
        "display_name": "Submit Document",
        "description": "Submit a submittable document (e.g., Sales Invoice, Journal Entry)",
        "category": "document",
        "function_path": "niv_ai.niv_tools.tools.document_tools.submit_document",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "name": {"type": "string", "description": "Document name/ID"}
            },
            "required": ["doctype", "name"]
        }),
        
    },
    {
        "tool_name": "list_documents",
        "display_name": "List Documents",
        "description": "Get a list of documents with filters, ordering, and pagination",
        "category": "document",
        "function_path": "niv_ai.niv_tools.tools.document_tools.list_documents",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType to list"},
                "filters": {"type": "object", "description": "Filter conditions"},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to return"},
                "order_by": {"type": "string", "description": "Sort order (e.g., 'creation desc')"},
                "limit": {"type": "integer", "description": "Max results (default 20)"}
            },
            "required": ["doctype"]
        }),
        
    },
    # ── Search Tools ──
    {
        "tool_name": "search_documents",
        "display_name": "Search Documents",
        "description": "Full-text search across ERPNext documents",
        "category": "search",
        "function_path": "niv_ai.niv_tools.tools.search_tools.search_documents",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"},
                "doctype": {"type": "string", "description": "Limit search to a specific DocType"},
                "limit": {"type": "integer", "description": "Max results (default 20)"}
            },
            "required": ["query"]
        }),
        
    },
    {
        "tool_name": "search_link",
        "display_name": "Search Link Field",
        "description": "Search for link field values (autocomplete-style search)",
        "category": "search",
        "function_path": "niv_ai.niv_tools.tools.search_tools.search_link",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType to search in"},
                "query": {"type": "string", "description": "Search text"},
                "filters": {"type": "object", "description": "Additional filters"}
            },
            "required": ["doctype", "query"]
        }),
        
    },
    {
        "tool_name": "global_search",
        "display_name": "Global Search",
        "description": "Search across all DocTypes in ERPNext",
        "category": "search",
        "function_path": "niv_ai.niv_tools.tools.search_tools.global_search",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "limit": {"type": "integer", "description": "Max results (default 20)"}
            },
            "required": ["query"]
        }),
        
    },
    # ── Report Tools ──
    {
        "tool_name": "generate_report",
        "display_name": "Generate Report",
        "description": "Run a Frappe report and return results",
        "category": "report",
        "function_path": "niv_ai.niv_tools.tools.report_tools.generate_report",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "report_name": {"type": "string", "description": "Report name (e.g., 'General Ledger', 'Stock Balance')"},
                "filters": {"type": "object", "description": "Report filters"},
                "limit": {"type": "integer", "description": "Max rows to return"}
            },
            "required": ["report_name"]
        }),
        
    },
    {
        "tool_name": "list_reports",
        "display_name": "List Reports",
        "description": "List available reports, optionally filtered by module",
        "category": "report",
        "function_path": "niv_ai.niv_tools.tools.report_tools.list_reports",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "Filter by module (e.g., 'Accounts', 'Stock')"}
            }
        }),
        
    },
    {
        "tool_name": "analyze_data",
        "display_name": "Analyze Data",
        "description": "Analyze document data with aggregations (count, sum, avg, etc.)",
        "category": "report",
        "function_path": "niv_ai.niv_tools.tools.report_tools.analyze_data",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType to analyze"},
                "filters": {"type": "object", "description": "Filter conditions"},
                "group_by": {"type": "string", "description": "Field to group by"},
                "aggregate": {"type": "string", "description": "Aggregation: count, sum, avg, min, max"},
                "aggregate_field": {"type": "string", "description": "Field to aggregate on"}
            },
            "required": ["doctype"]
        }),
        
    },
    # ── Workflow Tools ──
    {
        "tool_name": "run_workflow_action",
        "display_name": "Run Workflow Action",
        "description": "Apply a workflow action to a document (approve, reject, etc.)",
        "category": "workflow",
        "function_path": "niv_ai.niv_tools.tools.workflow_tools.run_workflow_action",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "name": {"type": "string", "description": "Document name"},
                "action": {"type": "string", "description": "Workflow action (e.g., 'Approve', 'Reject')"}
            },
            "required": ["doctype", "name", "action"]
        }),
        
    },
    {
        "tool_name": "get_workflow_state",
        "display_name": "Get Workflow State",
        "description": "Get current workflow state and available actions for a document",
        "category": "workflow",
        "function_path": "niv_ai.niv_tools.tools.workflow_tools.get_workflow_state",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "name": {"type": "string", "description": "Document name"}
            },
            "required": ["doctype", "name"]
        }),
        
    },
    # ── Database Tools (Admin Only) ──
    {
        "tool_name": "run_database_query",
        "display_name": "Run Database Query",
        "description": "Execute a read-only SQL query (SELECT only, admin only)",
        "category": "database",
        "function_path": "niv_ai.niv_tools.tools.database_tools.run_database_query",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL SELECT query to execute"}
            },
            "required": ["query"]
        }),
        "requires_admin": 1,
    },
    {
        "tool_name": "run_python_code",
        "display_name": "Run Python Code",
        "description": "Execute Python code in Frappe context (admin only, use with caution)",
        "category": "database",
        "function_path": "niv_ai.niv_tools.tools.database_tools.run_python_code",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"]
        }),
        "requires_admin": 1,
    },
    # ── Utility Tools ──
    {
        "tool_name": "get_doctype_info",
        "display_name": "Get DocType Info",
        "description": "Get metadata about a DocType (fields, permissions, properties)",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.get_doctype_info",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name to inspect"}
            },
            "required": ["doctype"]
        }),
        
    },
    {
        "tool_name": "fetch_url",
        "display_name": "Fetch URL",
        "description": "Fetch content from a URL (web scraping, API calls)",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.fetch_url",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "method": {"type": "string", "description": "HTTP method (GET/POST)", "default": "GET"}
            },
            "required": ["url"]
        }),
        "requires_admin": 1,
    },
    {
        "tool_name": "extract_file_content",
        "display_name": "Extract File Content",
        "description": "Extract text from uploaded files (PDF, Excel, Word, images with OCR)",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.extract_file_content",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "file_url": {"type": "string", "description": "File URL (from ERPNext file manager)"}
            },
            "required": ["file_url"]
        }),
        
    },
    {
        "tool_name": "create_dashboard",
        "display_name": "Create Dashboard",
        "description": "Create a new Number Card or Dashboard in ERPNext",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.create_dashboard",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Dashboard title"},
                "charts": {"type": "array", "description": "List of chart configurations", "items": {"type": "object"}}
            },
            "required": ["title"]
        }),
        "requires_admin": 1,
    },
    {
        "tool_name": "create_number_card",
        "display_name": "Create Number Card",
        "description": "Create a number card (KPI widget) on the dashboard",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.create_number_card",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Card title"},
                "doctype": {"type": "string", "description": "Source DocType"},
                "function": {"type": "string", "description": "Aggregation: Count, Sum, Avg"},
                "aggregate_field": {"type": "string", "description": "Field to aggregate"},
                "filters": {"type": "object", "description": "Filter conditions"}
            },
            "required": ["title", "doctype", "function"]
        }),
        "requires_admin": 1,
    },
    # ── Image Tools ──
    {
        "tool_name": "generate_image",
        "display_name": "Generate Image",
        "description": "Generate an image from a text prompt using DALL-E or compatible API",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.image_tools.generate_image",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text description of the image to generate"},
                "size": {"type": "string", "description": "Image size: 256x256, 512x512, 1024x1024, 1024x1792, 1792x1024", "default": "1024x1024"},
                "style": {"type": "string", "description": "Image style: natural or vivid", "default": "natural"}
            },
            "required": ["prompt"]
        }),
    },
    {
        "tool_name": "describe_image",
        "display_name": "Describe Image",
        "description": "Describe an image using a vision model",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.image_tools.describe_image",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the image to describe"}
            },
            "required": ["image_url"]
        }),
    },
    {
        "tool_name": "get_user_info",
        "display_name": "Get User Info",
        "description": "Get information about the current user or a specified user",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.get_user_info",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "user": {"type": "string", "description": "User email (optional, defaults to current user)"}
            }
        }),
        
    },
    # ── Email Tools ──
    {
        "tool_name": "send_email",
        "display_name": "Send Email",
        "description": "Send an email. Creates a draft first for confirmation, then sends when confirmed.",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.email_tools.send_email",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address(es), comma-separated"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body (HTML supported)"},
                "cc": {"type": "string", "description": "CC email address(es), comma-separated"},
                "confirmed": {"type": "boolean", "description": "Set to true to actually send (after draft confirmation)", "default": False}
            },
            "required": ["to", "subject", "body"]
        }),
    },
    {
        "tool_name": "draft_email",
        "display_name": "Draft Email",
        "description": "Create an email draft without sending",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.email_tools.draft_email",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address(es)"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"},
                "cc": {"type": "string", "description": "CC email address(es)"}
            },
            "required": ["to", "subject", "body"]
        }),
    },
    {
        "tool_name": "get_recent_emails",
        "display_name": "Get Recent Emails",
        "description": "Fetch recent emails from the system",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.email_tools.get_recent_emails",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of emails to fetch (default 10)", "default": 10}
            }
        }),
    },
    {
        "tool_name": "search_emails",
        "display_name": "Search Emails",
        "description": "Search emails by subject, content, sender, or recipients",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.email_tools.search_emails",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10}
            },
            "required": ["query"]
        }),
    },
    {
        "tool_name": "get_system_info",
        "display_name": "Get System Info",
        "description": "Get ERPNext system information (version, installed apps, etc.)",
        "category": "utility",
        "function_path": "niv_ai.niv_tools.tools.utility_tools.get_system_info",
        "parameters_json": json.dumps({
            "type": "object",
            "properties": {}
        }),
        "requires_admin": 1,
    },
]

DEFAULT_PROMPTS = [
    {
        "prompt_name": "Default Assistant",
        "description": "General-purpose ERPNext assistant",
        "prompt": DEFAULT_SYSTEM_PROMPT,
        "category": "general",
    },
    {
        "prompt_name": "Accounts Expert",
        "description": "Specialized in accounting and finance operations",
        "prompt": """You are Niv, an accounting expert AI assistant for ERPNext. You specialize in:
- Journal Entries, Payment Entries, Sales/Purchase Invoices
- General Ledger, Trial Balance, Profit & Loss, Balance Sheet
- Tax calculations and GST compliance
- Bank reconciliation and financial analysis

When users ask about accounting, use the appropriate tools to look up data, create entries, or generate reports.
Always double-check amounts and account names before creating transactions.
Format financial data in clean tables with proper number formatting.""",
        "category": "analysis",
    },
    {
        "prompt_name": "HR Assistant",
        "description": "Specialized in HR and payroll operations",
        "prompt": """You are Niv, an HR assistant for ERPNext. You help with:
- Employee management (attendance, leave, hiring)
- Payroll processing and salary slips
- Leave applications and approvals
- HR reports and analytics

Use tools to access employee data, process leave requests, and generate HR reports.
Be mindful of data privacy — only share information the user has permission to see.""",
        "category": "erp",
    },
]

DEFAULT_PLANS = [
    {
        "plan_name": "Starter",
        "description": "Perfect for trying out Niv AI",
        "tokens": 10000,
        "price": 99,
        "currency": "INR",
        "validity_days": 30,
    },
    {
        "plan_name": "Pro",
        "description": "For regular users who need more power",
        "tokens": 50000,
        "price": 399,
        "currency": "INR",
        "validity_days": 30,
    },
    {
        "plan_name": "Enterprise",
        "description": "For teams and power users",
        "tokens": 200000,
        "price": 999,
        "currency": "INR",
        "validity_days": 30,
    },
]
