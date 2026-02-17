"""
Niv AI A2A Configuration — COMPLETE

Centralized configuration for A2A multi-agent system.
Based on official ADK samples patterns.
"""

from datetime import date


# ─────────────────────────────────────────────────────────────────
# AGENT CONFIGURATION
# ─────────────────────────────────────────────────────────────────

# Agent names (must match factory.py)
AGENT_NAMES = {
    "orchestrator": "niv_orchestrator",
    "coder": "frappe_coder",
    "analyst": "data_analyst",
    "nbfc": "nbfc_specialist",
    "discovery": "system_discovery",
}

# Agent display names (for UI)
AGENT_DISPLAY_NAMES = {
    "niv_orchestrator": "🎯 Orchestrator",
    "frappe_coder": "👨‍💻 Frappe Developer",
    "data_analyst": "📊 Data Analyst",
    "nbfc_specialist": "🏦 NBFC Specialist",
    "system_discovery": "🔍 System Discovery",
}

# State keys (output_key values for each agent)
STATE_KEYS = {
    "orchestrator": "orchestrator_result",
    "coder": "coder_result",
    "analyst": "analyst_result",
    "nbfc": "nbfc_result",
    "discovery": "discovery_result",
}


# ─────────────────────────────────────────────────────────────────
# TOOL CATEGORIES
# ─────────────────────────────────────────────────────────────────

# Tools assigned to each agent
AGENT_TOOLS = {
    "coder": [
        "create_document",
        "update_document",
        "delete_document",
        "get_document",
        "get_doctype_info",
        "search_doctype",
        "run_python_code",
    ],
    "analyst": [
        "run_database_query",
        "generate_report",
        "report_list",
        "report_requirements",
        "list_documents",
        "fetch",
        "get_document",
    ],
    "nbfc": [
        "run_database_query",
        "list_documents",
        "get_doctype_info",
        "get_document",
        "search_documents",
    ],
    "discovery": [
        "introspect_system",
        "get_doctype_info",
        "search_doctype",
        "list_documents",
    ],
    "orchestrator": [
        "universal_search",
        "list_documents",
        "get_doctype_info",
    ],
}


# ─────────────────────────────────────────────────────────────────
# SESSION CONFIGURATION
# ─────────────────────────────────────────────────────────────────

SESSION_TTL = 7200  # 2 hours
STATE_TTL = 7200
EVENTS_TTL = 3600  # 1 hour
MAX_EVENTS = 100  # Keep last 100 events per session


# ─────────────────────────────────────────────────────────────────
# TEMPERATURE CONFIGURATION
# ─────────────────────────────────────────────────────────────────

# Based on official samples
TEMPERATURE = {
    "routing": 0.05,   # Very low for consistent routing decisions
    "factual": 0.1,    # Low for data queries
    "creative": 0.3,   # Medium for code generation
}


# ─────────────────────────────────────────────────────────────────
# ROUTING HINTS
# ─────────────────────────────────────────────────────────────────

# Keywords that suggest which agent to use
ROUTING_HINTS = {
    "coder": [
        "doctype", "create", "script", "field", "workflow",
        "print format", "web form", "code", "develop", "build",
        "custom", "hook", "server script", "client script",
        "child table", "report builder",
    ],
    "analyst": [
        "report", "query", "sql", "data", "analytics", "dashboard",
        "aggregate", "count", "sum", "average", "chart", "graph",
        "statistics", "analysis", "trend", "comparison",
    ],
    "nbfc": [
        "loan", "emi", "repayment", "borrower", "disbursement",
        "interest", "due", "overdue", "nbfc", "growth system",
        "lms", "los", "collection", "npa", "default", "sanction",
        "co-lending", "litigation",
    ],
    "discovery": [
        "scan", "discover", "explore", "system", "structure",
        "onboard", "learn", "understand", "list doctypes",
        "what modules", "show workflows",
    ],
}


# ─────────────────────────────────────────────────────────────────
# GLOBAL INSTRUCTION
# ─────────────────────────────────────────────────────────────────

GLOBAL_INSTRUCTION = f"""
You are part of Niv AI — an intelligent assistant for Frappe/ERPNext systems.
Today's date: {date.today()}

UNIVERSAL RULES:
1. NEVER hallucinate or invent data. Always use tools to get REAL data.
2. If a tool fails, explain the error and suggest alternatives.
3. Be concise but thorough. Provide actionable answers.
4. For NBFC/Growth System queries, always verify data from the database.
5. When creating DocTypes/Scripts, always verify existing structure first.

USE YOUR BRAIN FOR CALCULATIONS (CRITICAL - MAXIMUM 3 TOOL CALLS):
Use tools ONLY for fetching data. Use YOUR KNOWLEDGE for calculations:
- WRR: WRR = Σ(Loan Amount × Risk Weight) / Σ(Total Loan Amount)
  Risk Weights: Standard=0%, SMA-0=5%, SMA-1=10%, SMA-2=15%, Substandard=25%, Doubtful=50%, Loss=100%
- EMI: EMI = P × r × (1+r)^n / ((1+r)^n - 1)
- NPA: >90 days overdue = NPA
- Interest, DPD, averages, percentages - calculate yourself!

CORRECT: 1 tool call to fetch data → calculate with brain → present result
WRONG: Multiple tools for calculations, run_python_code for simple math
"""


# ─────────────────────────────────────────────────────────────────
# ERROR MESSAGES
# ─────────────────────────────────────────────────────────────────

ERROR_MESSAGES = {
    "no_tools": "No MCP tools loaded. Check MCP server connection.",
    "adk_not_installed": "Google ADK not installed. Run: pip install google-adk",
    "session_error": "Session service error. Check Redis connection.",
    "orchestrator_error": "Failed to create orchestrator agent.",
    "tool_not_found": "Tool not found in any MCP server.",
    "frappe_context": "Frappe context initialization failed.",
}


# ─────────────────────────────────────────────────────────────────
# FEATURE FLAGS
# ─────────────────────────────────────────────────────────────────

FEATURES = {
    "enable_state_logging": True,   # Log state changes
    "enable_transfer_logging": True,  # Log agent transfers
    "enable_tool_result_truncation": True,  # Truncate long tool results
    "max_tool_result_length": 500,  # Max chars for tool result display
}
