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
    _run_auto_discovery()
    _optimize_mariadb()
    print("✅ Niv AI installed successfully!")
    print("  → Connect an MCP server in Niv Settings to enable tools")


def setup_provider(base_url, api_key, model="mistral-large-latest", fast_model="mistral-small-latest"):
    """Setup AI provider and configure Niv Settings. Called by setup.sh."""
    provider_name = "AI Provider"
    
    if not frappe.db.exists("Niv AI Provider", provider_name):
        doc = frappe.get_doc({
            "doctype": "Niv AI Provider",
            "provider_name": provider_name,
            "base_url": base_url,
            "api_key": api_key,
            "default_model": model,
        })
        doc.insert(ignore_permissions=True)
        print(f"  → Created AI Provider: {provider_name}")
    else:
        doc = frappe.get_doc("Niv AI Provider", provider_name)
        doc.base_url = base_url
        doc.api_key = api_key
        doc.default_model = model
        doc.save(ignore_permissions=True)
        print(f"  → Updated AI Provider: {provider_name}")

    settings = frappe.get_single("Niv Settings")
    settings.default_provider = provider_name
    settings.default_model = model
    settings.fast_model = fast_model
    settings.enable_widget = 1
    settings.widget_title = "Chanakya Ai"
    settings.enable_billing = 1
    settings.billing_mode = "Shared Pool"
    if not settings.shared_pool_balance or int(settings.shared_pool_balance or 0) == 0:
        settings.shared_pool_balance = 10000000
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  → Niv Settings configured (model: {model}, fast: {fast_model})")


def after_migrate():
    """Run after bench migrate — ensures defaults exist, fills missing fields, re-discovers system"""
    _create_settings()
    _ensure_settings_defaults()
    frappe.db.commit()
    _run_auto_discovery()


def _ensure_settings_defaults():
    """Fill missing default values on existing Niv Settings (runs on every migrate).
    Only sets values that are empty/None — never overwrites user's custom values."""
    if not frappe.db.exists("Niv Settings", "Niv Settings"):
        return

    settings = frappe.get_single("Niv Settings")
    changed = False

    # Map of fieldname -> default value (only set if empty)
    defaults = {
        "widget_title": "Chanakya Ai",
        "widget_position": "bottom-right",
        "widget_color": "#7C3AED",
        "auto_open_artifacts": 1,
        "max_tokens_per_message": 4096,
        "max_messages_per_conversation": 50,
        "enable_tools": 1,
        "enable_widget": 1,
        "enable_voice": 1,
        "stt_engine": "auto",
        "tts_engine": "auto",
        "tts_language": "auto",
        "default_voice": "auto",
        "tts_model": "tts-1",
        "voice_base_url": "https://api.openai.com/v1",
        "tool_priority": "MCP First",
        "rate_limit_per_hour": 500,
        "rate_limit_per_day": 5000,
        "rate_limit_message": "You have reached the message limit. Please try again later.",
        "token_cost_input": 1.0,
        "token_cost_output": 3.0,
        "billing_mode": "Shared Pool",
        "enable_vision": 1,
        "vision_model": "gemma3:27b",
        "vision_max_tokens": 2048,
    }

    for field, default in defaults.items():
        current = getattr(settings, field, None)
        # Only set if truly empty (None, empty string, or 0 for non-check fields)
        if current is None or current == "":
            setattr(settings, field, default)
            changed = True

    if changed:
        settings.save(ignore_permissions=True)
        print("  → Niv Settings: filled missing defaults")


def _create_settings():
    """Create Niv Settings singleton if not exists, with comprehensive defaults"""
    if not frappe.db.exists("Niv Settings", "Niv Settings"):
        doc = frappe.get_doc({
            "doctype": "Niv Settings",
            # AI Configuration
            "default_model": "mistral-small-latest",
            "max_tokens_per_message": 4096,
            "max_messages_per_conversation": 50,
            "enable_tools": 1,
            "enable_billing": 0,
            "enable_widget": 1,
            "enable_knowledge_base": 1,
            "tool_priority": "MCP First",
            "system_prompt": DEFAULT_SYSTEM_PROMPT,
            # Rate Limiting
            "rate_limit_per_hour": 500,
            "rate_limit_per_day": 5000,
            "rate_limit_message": "You have reached the message limit. Please try again later.",
            # Widget Settings
            "widget_position": "bottom-right",
            "widget_title": "Chanakya Ai",
            "widget_logo": "/assets/niv_ai/images/niv_logo.png",
            "widget_color": "#7C3AED",
            "auto_open_artifacts": 1,
            # Billing
            "admin_allocation_only": 1,
            "billing_mode": "Shared Pool",
            "shared_pool_balance": 10000000,
            "token_cost_input": 1.0,
            "token_cost_output": 3.0,
            "payment_currency": "INR",
            "currency": "INR",
            # Voice
            "enable_voice": 1,
            "stt_engine": "auto",
            "tts_engine": "auto",
            "tts_language": "auto",
            "default_voice": "auto",
            "tts_model": "tts-1",
            "voice_base_url": "https://api.openai.com/v1",
            # Vision
            "enable_vision": 1,
            "vision_model": "gemma3:27b",
            "vision_max_tokens": 2048,
        })
        doc.insert(ignore_permissions=True)
        print("  → Niv Settings created with all defaults")


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


def _run_auto_discovery():
    """Run auto-discovery to scan and learn the system."""
    try:
        from niv_ai.niv_core.knowledge.unified_discovery import UnifiedDiscovery
        discovery = UnifiedDiscovery()
        data = discovery.run_full_scan()
        doctypes = len(data.get("doctypes", {}))
        print(f"  → System Discovery complete: {doctypes} DocTypes scanned.")
    except Exception as e:
        print("  → System Discovery skipped: {0}".format(str(e)))


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


def _optimize_mariadb():
    """Optimize MariaDB settings for long-running AI streams.
    Creates /etc/mysql/mariadb.conf.d/99-niv-ai.cnf and applies settings live."""
    import subprocess
    import os

    cnf_path = "/etc/mysql/mariadb.conf.d/99-niv-ai.cnf"
    cnf_content = """[mysqld]
# Niv AI — prevent DB connection drops during long SSE streams
net_read_timeout = 300
net_write_timeout = 300
wait_timeout = 86400
interactive_timeout = 86400
max_connections = 300
"""

    try:
        # Write config file (needs sudo)
        if not os.path.exists(cnf_path):
            result = subprocess.run(
                ["sudo", "tee", cnf_path],
                input=cnf_content, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                print("  → MariaDB config created: 99-niv-ai.cnf")
            else:
                print(f"  → MariaDB config skipped (no sudo): {result.stderr.strip()}")
                return
        else:
            print("  → MariaDB config already exists: 99-niv-ai.cnf")

        # Apply live (without restart)
        sql = (
            "SET GLOBAL net_read_timeout=300; "
            "SET GLOBAL net_write_timeout=300; "
            "SET GLOBAL wait_timeout=86400; "
            "SET GLOBAL interactive_timeout=86400; "
            "SET GLOBAL max_connections=300;"
        )
        subprocess.run(
            ["sudo", "mysql", "-e", sql],
            capture_output=True, text=True, timeout=10
        )
        print("  → MariaDB timeouts optimized (net_timeout=300s, wait=24h, max_conn=300)")
    except Exception as e:
        print(f"  → MariaDB optimization skipped: {e}")
        print("    Run manually: sudo mysql -e \"SET GLOBAL net_read_timeout=300; SET GLOBAL net_write_timeout=300; SET GLOBAL wait_timeout=86400; SET GLOBAL interactive_timeout=86400; SET GLOBAL max_connections=300;\"")


# ─── Default Data ────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are Chanakya Ai — the intelligent assistant for THIS business system. You are an NBFC/Lending domain expert.

CRITICAL RULES:
1. You already KNOW this system's domain, modules, workflows, and compliance rules from your training context below. USE THAT KNOWLEDGE DIRECTLY — don't run tools to "figure out" what you already know.
2. Use tools ONLY to fetch live data (counts, records, amounts) or perform actions (create/update docs). NEVER use tools to learn about NPA rules, EMI formulas, loan processes — you already know these.
3. Maximum 3 tool calls per response. After 3 calls, summarize what you have and respond.
4. NEVER invent or fabricate data. If a tool returns no results, say "No data found".
5. NEVER show demo/placeholder names like "John Doe", "Test Customer". Only real data from tools.
6. Respond in the same language the user uses (Hindi/English/Hinglish).
7. Be concise. Tables for data, bullet points for explanations.

BRANDING: NEVER say 'ERPNext' or 'Frappe'. Say 'your system' or 'Chanakya'.

TOOL STRATEGY (follow strictly):
- Knowledge questions (NPA rules, EMI formula, loan process, compliance) → Answer directly from your context. NO tools needed.
- Data questions (how many loans, top customers, overdue amounts) → Use list_documents or run_database_query. ONE call max.
- Document creation → get_doctype_info first, then create_document. TWO calls max.
- Search (find a customer, loan) → search_documents or list_documents. ONE call.

IMPORTANT FORMATTING RULES:
- ALWAYS show data results in proper markdown tables with headers
- Format currency with ₹ symbol and Indian commas (e.g., ₹5,00,000)
- Format dates as DD-MM-YYYY
- Use bold for important values and column headers
- Keep tables clean with max 5-6 columns for readability
- Add a summary line after tables (e.g., "Total: ₹5,00,000 across 12 records")

SPEED: Prefer run_database_query over run_python_code. Prefer list_documents over generate_report. Simpler = faster."""

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
