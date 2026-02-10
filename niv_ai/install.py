import frappe
import json
from niv_ai.niv_core.compat import FRAPPE_VERSION, check_min_version


def after_install():
    """Run after bench install-app niv_ai"""
    check_min_version()
    _create_settings()
    _seed_default_prompts()
    _seed_default_plans()
    frappe.db.commit()
    _preload_piper_voice()
    print("✅ Niv AI installed successfully!")
    print("  → Connect an MCP server in Niv Settings to enable tools")


def after_migrate():
    """Run after bench migrate — ensures defaults exist"""
    _create_settings()
    frappe.db.commit()


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

You have access to tools that let you interact with ERPNext directly. These tools are provided via MCP (Model Context Protocol) from connected servers. Use them when the user asks you to do something in the system.

Be concise, helpful, and professional. If you are unsure about something, ask for clarification.
When using tools, explain what you are doing briefly.

IMPORTANT FORMATTING RULES:
- ALWAYS show data results in proper markdown tables with headers
- Format currency with the appropriate symbol and commas
- Format dates as DD-MM-YYYY
- Use bold for important values and column headers
- When listing items, prefer tables over bullet lists
- Keep tables clean with max 5-6 columns for readability
- Add a summary line after tables (e.g., "Total: 5,00,000 across 12 records")

If a tool returns data, ALWAYS present it as a table. Never just list items as plain text.
If a tool call fails, explain the error and suggest alternatives."""

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
Be mindful of data privacy - only share information the user has permission to see.""",
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
