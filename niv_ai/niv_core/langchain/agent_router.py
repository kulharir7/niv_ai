"""
Agent Router System — Classifies queries and routes to specialized agents.

Architecture:
  Query → Router (0.2s) → Specialized Agent (6-12 tools) → Response

Benefits:
  - 4-5x faster tool selection (10-12 tools vs 34)
  - Better accuracy (domain-specific prompts)
  - Lower token usage
  - Parallel execution opportunity
"""
import re
import frappe
from typing import Optional, Dict, List, Tuple, Any
from niv_ai.niv_core.utils import get_niv_settings


# ─── Tool Categories ────────────────────────────────────────────────────────

# Core tools every agent needs
CORE_TOOLS = {
    "list_documents",      # Search/list records
    "get_document",        # Get single record
    "search_documents",    # Global search
    "get_doctype_info",    # Schema info
    "run_database_query",  # SQL queries
}

# Extended read tools
READ_TOOLS = {
    *CORE_TOOLS,
    "search_doctype",      # Search within DocType
    "search_link",         # Link field options
    "search",              # Vector search
    "fetch",               # Fetch from vector store
}

# Write tools (need confirmation in dev mode)
WRITE_TOOLS = {
    "create_document",
    "update_document",
    "delete_document",
    "submit_document",
    "run_workflow",
}

# Reporting tools
REPORT_TOOLS = {
    "generate_report",
    "report_list",
    "report_requirements",
    "analyze_business_data",
}

# Dashboard tools
DASHBOARD_TOOLS = {
    "create_dashboard",
    "create_dashboard_chart",
    "list_user_dashboards",
}

# NBFC-specific tools
NBFC_TOOLS = {
    "nbfc_credit_scoring",
    "nbfc_loan_prequalification",
    "cersai_registration",
    "rbi_return_generator",
    "ckyc_updater",
    "aml_screening",
    "fair_practice_compliance",
    "interest_rate_disclosure",
}

# Utility tools
UTILITY_TOOLS = {
    "send_email",
    "excel_generator",
    "pdf_generator",
    "extract_file_content",
}

# Power tools (advanced users)
POWER_TOOLS = {
    "run_python_code",
}


# ─── Agent Registry ────────────────────────────────────────────────────────

AGENT_REGISTRY = {
    "nbfc": {
        "name": "NBFC Agent",
        "description": "Handles loan applications, NPA analysis, collections, and NBFC operations",
        "keywords": [
            "loan", "npa", "overdue", "emi", "collection", "recovery",
            "borrower", "lender", "disbursement", "sanction", "credit",
            "collateral", "interest rate", "principal", "repayment",
            "default", "write-off", "provision", "sma", "wirr", "wrr",
            "co-lending", "los", "lms", "underwriting", "dti", "ltv",
            "mahaveer", "growth system", "nbfc", "cibil", "cersai",
            "rbi return", "nbs", "crilc", "delinquency", "dpd",
            "pre-emi", "moratorium", "foreclosure", "topup"
        ],
        "tools": CORE_TOOLS | REPORT_TOOLS | NBFC_TOOLS | {"run_python_code", "submit_document", "run_workflow"},
        "prompt_suffix": """\n\nYou are specialized in NBFC and lending operations. You understand:
- Loan Application lifecycle (Lead → Application → Sanction → Disbursement)
- NPA Classification (SMA-0, SMA-1, SMA-2, Sub-standard, Doubtful, Loss)
- Collection and Recovery processes
- Co-lending and Balance Transfer
- Regulatory compliance (RBI guidelines)

For calculations, use the NBFC-specific tools (nbfc_credit_scoring, etc.) when available.
Always show financial data in proper tables with formatted numbers.""",
    },

    "accounts": {
        "name": "Accounts Agent",
        "description": "Handles accounting, invoices, payments, and financial reports",
        "keywords": [
            "invoice", "payment", "journal", "ledger", "gl", "trial balance",
            "profit", "loss", "balance sheet", "p&l", "pl", "bs", "gst",
            "tax", "tds", "receivable", "payable", "expense", "income",
            "capital", "asset", "liability", "equity", "depreciation",
            "reconciliation", "bank", "cheque", "neft", "rtgs", "upi",
            "voucher", "fiscal year", "cost center", "budget"
        ],
        "tools": CORE_TOOLS | REPORT_TOOLS | WRITE_TOOLS | {"run_python_code", "analyze_business_data"},
        "prompt_suffix": """\n\nYou are specialized in accounting and finance. You understand:
- Chart of Accounts and General Ledger
- Journal Entries and Payment Entries
- Sales and Purchase Invoices
- GST/TDS compliance
- Financial statements (P&L, Balance Sheet, Cash Flow)

Always format amounts with currency symbols and proper number formatting.""",
    },

    "hr": {
        "name": "HR Agent",
        "description": "Handles employee management, payroll, leave, and attendance",
        "keywords": [
            "employee", "staff", "payroll", "salary", "leave", "attendance",
            "recruitment", "hiring", "joining", "resignation", "exit",
            "performance", "appraisal", "training", "onboarding",
            "shift", "overtime", "bonus", "deduction", "pf", "esi",
            "gratuity", "ctc", "designation", "department", "holiday"
        ],
        "tools": CORE_TOOLS | REPORT_TOOLS | {"run_python_code"},
        "prompt_suffix": """\n\nYou are specialized in HR and payroll. You understand:
- Employee lifecycle (Recruitment → Onboarding → Active → Exit)
- Leave management and attendance tracking
- Payroll processing and salary slips
- Performance appraisals and training

Be mindful of data privacy — only share information the user has permission to see.""",
    },

    "developer": {
        "name": "Developer Agent",
        "description": "Handles full-stack Frappe development tasks with complete tool access",
        "keywords": ["dev", "developer", "doctype", "custom field", "workflow", "script", "report", "api", "hook", "debug"],
        "tools": None,  # Full tool access in dev mode
        "prompt_suffix": """\n\nDeveloper mode is active. You may perform multi-step implementation with full tools.
Before making broad changes, explain scope and impact. Prefer safe, reversible updates.""",
    },

    "general": {
        "name": "General Agent",
        "description": "Handles general queries with a focused set of core tools",
        "keywords": [],  # Empty keywords — this is the fallback
        # LIMITED tool set for general queries - prevents overwhelming the LLM
        "tools": CORE_TOOLS | READ_TOOLS | REPORT_TOOLS | {"run_python_code", "create_document", "update_document"},
        "prompt_suffix": """\n\nYou are a helpful assistant for ERPNext/Frappe. 
Focus on answering the user's question directly and efficiently.
Use the minimum number of tool calls needed to get the answer.""",
    },

    "reporting": {
        "name": "Reporting Agent",
        "description": "Specialized in generating reports and data analysis",
        "keywords": [
            "report", "chart", "dashboard", "graph", "analysis", "statistics",
            "summary", "aggregate", "export", "excel", "pdf", "trend"
        ],
        "tools": CORE_TOOLS | REPORT_TOOLS | DASHBOARD_TOOLS | UTILITY_TOOLS | {"run_python_code"},
        "prompt_suffix": """\n\nYou are specialized in reports and data visualization.
Use generate_report for standard Frappe reports.
Use run_python_code for custom analysis and calculations.
Use excel_generator or pdf_generator for exports.""",
    },
}


# ─── Router Class ──────────────────────────────────────────────────────────

class AgentRouter:
    """Classifies queries and selects the best agent."""

    def __init__(self):
        self._keyword_index = self._build_keyword_index()
        self._embedding_model = None
        self._embedding_cache = {}

    def _build_keyword_index(self) -> Dict[str, List[str]]:
        """Build keyword → agent mapping for O(1) lookup."""
        index = {}
        for agent_id, config in AGENT_REGISTRY.items():
            for kw in config.get("keywords", []):
                kw_lower = kw.lower()
                if kw_lower not in index:
                    index[kw_lower] = []
                index[kw_lower].append(agent_id)
        return index

    def classify(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """
        Classify a query and return the best agent.

        Returns: (agent_id, metadata)
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))

        # Step 1: Exact keyword match (instant)
        matches = {}
        for word in query_words:
            if word in self._keyword_index:
                for agent_id in self._keyword_index[word]:
                    matches[agent_id] = matches.get(agent_id, 0) + 1

        if matches:
            best_agent = max(matches.keys(), key=lambda a: matches[a])
            confidence = min(1.0, matches[best_agent] / 3.0)
            return best_agent, {
                "method": "keyword",
                "confidence": confidence,
                "matched_keywords": matches
            }

        # Step 2: Semantic similarity (if enabled)
        try:
            if self._should_use_embedding():
                return self._classify_by_embedding(query)
        except Exception as e:
            frappe.logger().warning(f"AgentRouter embedding failed: {e}")

        # Step 3: Fallback to general agent
        return "general", {"method": "fallback", "confidence": 0.0}

    def _should_use_embedding(self) -> bool:
        try:
            settings = get_niv_settings()
            return bool(getattr(settings, "enable_knowledge_base", 0))
        except Exception:
            return False

    def _classify_by_embedding(self, query: str) -> Tuple[str, Dict[str, Any]]:
        if self._embedding_model is None:
            try:
                from niv_ai.niv_core.langchain.rag import get_embeddings
                self._embedding_model = get_embeddings()
            except Exception:
                return "general", {"method": "embedding_failed", "confidence": 0.0}

        if self._embedding_model is None:
            return "general", {"method": "embedding_unavailable", "confidence": 0.0}

        query_embedding = self._embedding_model.embed_query(query)
        best_agent = "general"
        best_score = 0.0

        for agent_id, config in AGENT_REGISTRY.items():
            if agent_id == "general":
                continue
            if agent_id not in self._embedding_cache:
                desc = f"{config['name']}: {config['description']}"
                self._embedding_cache[agent_id] = self._embedding_model.embed_query(desc)
            agent_embedding = self._embedding_cache[agent_id]
            score = self._cosine_similarity(query_embedding, agent_embedding)
            if score > best_score:
                best_score = score
                best_agent = agent_id

        if best_score > 0.3:
            return best_agent, {"method": "embedding", "confidence": min(1.0, best_score)}
        return "general", {"method": "embedding_low_confidence", "confidence": best_score}

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        import math
        if len(vec1) != len(vec2):
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def get_agent_config(self, agent_id: str) -> Dict[str, Any]:
        return AGENT_REGISTRY.get(agent_id, AGENT_REGISTRY["general"])

    def get_tools_for_agent(self, agent_id: str, all_tools: List[Any]) -> List[Any]:
        """Filter tools for a specific agent."""
        config = self.get_agent_config(agent_id)
        tool_names = config.get("tools")

        # None = all tools (developer mode only)
        if tool_names is None:
            return all_tools

        # Filter to only allowed tools
        tool_name_set = set(tool_names)
        filtered = [t for t in all_tools if getattr(t, "name", "") in tool_name_set]

        if not filtered:
            frappe.logger().warning(f"AgentRouter: No tools found for {agent_id}, using all tools")
            return all_tools

        return filtered

    def get_system_prompt_suffix(self, agent_id: str) -> str:
        config = self.get_agent_config(agent_id)
        return config.get("prompt_suffix", "")


# ─── Global Router Instance ────────────────────────────────────────────────

_router_instance = None


def get_router() -> AgentRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = AgentRouter()
    return _router_instance


def classify_query(query: str) -> Tuple[str, Dict[str, Any]]:
    return get_router().classify(query)


def get_agent_tools(agent_id: str, all_tools: List[Any]) -> List[Any]:
    return get_router().get_tools_for_agent(agent_id, all_tools)


def get_agent_prompt_suffix(agent_id: str) -> str:
    return get_router().get_system_prompt_suffix(agent_id)


def test_router():
    """Test the router with sample queries."""
    test_queries = [
        "Show me today's loan applications",
        "What's the NPA status?",
        "Show my bank balance",
        "List all employees",
        "Generate profit and loss report",
        "Hello, how are you?",
        "Create a new customer",
    ]

    router = get_router()
    results = []

    for q in test_queries:
        agent_id, meta = router.classify(q)
        config = router.get_agent_config(agent_id)
        tools = config.get("tools")
        tool_count = len(tools) if tools else "ALL"
        results.append({
            "query": q[:40],
            "agent": agent_id,
            "tools": tool_count,
            "confidence": round(meta.get("confidence", 0), 2),
        })

    return results


if __name__ == "__main__":
    import json
    results = test_router()
    print(json.dumps(results, indent=2))
