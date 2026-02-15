"""
Niv AI A2A Configuration

Centralized config for A2A system.
"""

# Agent names (consistent across the system)
AGENT_NAMES = {
    "orchestrator": "niv_orchestrator",
    "coder": "frappe_coder",
    "analyst": "data_analyst",
    "nbfc": "nbfc_specialist",
    "discovery": "system_discovery",
}

# State keys (output_key values)
STATE_KEYS = {
    "orchestrator": "orchestrator_result",
    "coder": "coder_result",
    "analyst": "analyst_result",
    "nbfc": "nbfc_result",
    "discovery": "discovery_result",
}

# Tool categories per agent
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

# Session settings
SESSION_TTL = 7200  # 2 hours
SESSION_MAX_EVENTS = 100  # Max events to keep in history

# Routing keywords (help orchestrator decide which agent to use)
ROUTING_HINTS = {
    "coder": [
        "doctype", "create", "script", "field", "workflow", "print format",
        "web form", "code", "develop", "build", "custom", "hook",
    ],
    "analyst": [
        "report", "query", "sql", "data", "analytics", "dashboard",
        "aggregate", "count", "sum", "average", "chart",
    ],
    "nbfc": [
        "loan", "emi", "repayment", "borrower", "disbursement",
        "interest", "due", "overdue", "nbfc", "growth system",
        "lms", "los", "collection",
    ],
    "discovery": [
        "scan", "discover", "explore", "system", "structure",
        "onboard", "learn", "understand",
    ],
}
