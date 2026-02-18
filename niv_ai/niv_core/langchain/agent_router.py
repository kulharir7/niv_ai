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


# ─── Few-Shot Examples for Tool Calling ─────────────────────────────────────

NBFC_TOOL_EXAMPLES = """
## TOOL CALLING EXAMPLES (Follow these patterns exactly):

### Query: "top 5 loans" / "loan list dikhao" / "show loans"
```
list_documents({
  "doctype": "Loan",
  "fields": ["name", "applicant_name", "loan_amount", "status", "disbursement_date"],
  "limit": 5,
  "order_by": "loan_amount desc"
})
```

### Query: "overdue loans" / "NPA loans" / "defaulted loans"
```
list_documents({
  "doctype": "Loan",
  "fields": ["name", "applicant_name", "loan_amount", "status", "days_past_due"],
  "filters": {"status": ["in", ["Overdue", "NPA", "Written Off"]]},
  "limit": 20
})
```

### Query: "loan details for LOAN-001" / "show loan ABC"
```
get_document({
  "doctype": "Loan",
  "name": "LOAN-001"
})
```

### Query: "total disbursed amount" / "loan portfolio value"
```
run_database_query({
  "query": "SELECT SUM(loan_amount) as total, COUNT(*) as count FROM `tabLoan` WHERE status='Disbursed'"
})
```

### Query: "EMI schedule for loan X"
```
list_documents({
  "doctype": "Repayment Schedule",
  "filters": {"parent": "LOAN-X"},
  "fields": ["idx", "payment_date", "principal_amount", "interest_amount", "total_payment", "balance_loan_amount"],
  "order_by": "idx asc"
})
```

### Query: "customers with loans" / "borrowers list"
```
list_documents({
  "doctype": "Customer",
  "fields": ["name", "customer_name", "mobile_no"],
  "filters": {"customer_group": "Borrower"},
  "limit": 20
})
```

## RULES:
1. ONE tool call is enough for simple queries - don't call multiple tools unnecessarily
2. Always include relevant fields in the fields array
3. Use filters to narrow results instead of fetching everything
4. Use order_by for "top X" queries
5. Use limit to control result size
"""

ACCOUNTS_TOOL_EXAMPLES = """
## TOOL CALLING EXAMPLES:

### Query: "top 5 invoices" / "recent sales"
```
list_documents({
  "doctype": "Sales Invoice",
  "fields": ["name", "customer", "grand_total", "status", "posting_date"],
  "limit": 5,
  "order_by": "posting_date desc"
})
```

### Query: "unpaid invoices" / "outstanding receivables"
```
list_documents({
  "doctype": "Sales Invoice",
  "fields": ["name", "customer", "grand_total", "outstanding_amount"],
  "filters": {"outstanding_amount": [">", 0], "docstatus": 1},
  "limit": 20
})
```

### Query: "account balance" / "ledger for account X"
```
run_database_query({
  "query": "SELECT SUM(debit)-SUM(credit) as balance FROM `tabGL Entry` WHERE account='Cash - ABC'"
})
```

## RULES:
1. ONE tool call for simple queries
2. Include only necessary fields
3. Use filters effectively
"""

GENERAL_TOOL_EXAMPLES = """
## TOOL CALLING EXAMPLES:

### Query: "list of [DocType]" / "show [records]"
```
list_documents({
  "doctype": "[DocType Name]",
  "fields": ["name", "...relevant fields..."],
  "limit": 10
})
```

### Query: "details of [record]"
```
get_document({
  "doctype": "[DocType]",
  "name": "[Record Name]"
})
```

## RULES:
1. ONE tool call is usually enough
2. Don't call get_doctype_info unless you truly don't know the fields
3. Use filters to narrow results
"""


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

Always show financial data in proper tables with formatted numbers (₹ symbol, Indian number format).

## Key DocTypes & Fields (USE DIRECTLY — no need to call get_doctype_info)

### Loan (table: `tabLoan`)
- Key fields: name, applicant, applicant_name, loan_amount, loan_type, status, posting_date (=Sanction Date), company, rate_of_interest, flat_interest_rate, irr, loan_duration, product, product_category, applicant_mobile_number, co_applicant, co_applicant_name, is_unsecured, delinquent_since, interest_type, asset_type
- Status values: Sanctioned, Partially Disbursed, Disbursed, Loan Closure Requested, Closed, Cancel
- NOTE: loan_type is a Link field to "Loan Category". 210+ fields total — use get_doctype_info if you need others.

### Loan Application (table: `tabLoan Application`)
- Key fields: name, applicant, applicant_type, first_name, middle_name, last_name, workflow_state, status, company
- Status values: Open
- NOTE: 341 fields — heavily customized. Use get_doctype_info for specific field discovery.

### Loan Repayment (table: `tabLoan Repayment`)
- Key fields: name, against_loan, applicant, applicant_name, posting_date, receipt_date, repayment_mode, reference_number, product, company, cheque_no
- NOTE: 82 fields.

### Customer (table: `tabCustomer`)
- Key fields: name, customer_name, customer_type, first_name, last_name, date_of_birth, gender, father_name, npa (Check)

## Common SQL Patterns
- Loan list: SELECT name, applicant_name, loan_amount, status, posting_date FROM `tabLoan` ORDER BY posting_date DESC LIMIT 20
- Loan count by status: SELECT status, COUNT(*) as count, SUM(loan_amount) as total FROM `tabLoan` GROUP BY status
- Total AUM: SELECT SUM(loan_amount) as total_aum, COUNT(*) as loan_count FROM `tabLoan` WHERE docstatus=1 AND status IN ('Disbursed', 'Partially Disbursed')
- IMPORTANT: This system has many custom fields. If a field name causes an error, use get_doctype_info or SELECT * FROM `tabX` LIMIT 1 to discover correct field names.

""" + NBFC_TOOL_EXAMPLES,
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
        "prompt_suffix": """

You are specialized in accounting and finance. You understand:
- Chart of Accounts and General Ledger
- Journal Entries and Payment Entries
- Sales and Purchase Invoices
- GST/TDS compliance
- Financial statements (P&L, Balance Sheet, Cash Flow)

""" + ACCOUNTS_TOOL_EXAMPLES + """

Always format amounts with ₹ symbol and proper number formatting (e.g., ₹1,23,456.00).""",
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
        "prompt_suffix": """

You are specialized in HR and payroll. You understand:
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
        "prompt_suffix": """

Developer mode is active. You may perform multi-step implementation with full tools.
Before making broad changes, explain scope and impact. Prefer safe, reversible updates.""",
    },

    "general": {
        "name": "General Agent",
        "description": "Handles general queries with a focused set of core tools",
        "keywords": [],  # Empty keywords — this is the fallback
        # LIMITED tool set for general queries - prevents overwhelming the LLM
        "tools": CORE_TOOLS | READ_TOOLS | REPORT_TOOLS | {"run_python_code", "create_document", "update_document"},
        "prompt_suffix": """

You are a helpful assistant for this ERP system.
Focus on answering the user's question directly and efficiently.

""" + GENERAL_TOOL_EXAMPLES + """

Use the MINIMUM number of tool calls needed to get the answer.""",
    },

    "reporting": {
        "name": "Reporting Agent",
        "description": "Specialized in generating reports and data analysis",
        "keywords": [
            "report", "chart", "dashboard", "graph", "analysis", "statistics",
            "summary", "aggregate", "export", "excel", "pdf", "trend"
        ],
        "tools": CORE_TOOLS | REPORT_TOOLS | DASHBOARD_TOOLS | UTILITY_TOOLS | {"run_python_code"},
        "prompt_suffix": """

You are specialized in reports and data visualization.
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
        
        Uses weighted keyword scoring:
        - Single word match: +1 point
        - Multi-word phrase match: +3 points (more specific = more reliable)
        - If top two agents are within 1 point, falls back to "general" (ambiguous)
        
        Returns: (agent_id, metadata)
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))

        # Step 1: Weighted keyword scoring
        scores = {}
        matched_keywords = {}
        
        for agent_id, config in AGENT_REGISTRY.items():
            if agent_id in ("general", "orchestrator"):
                continue
                
            score = 0
            matches = []
            
            for kw in config.get("keywords", []):
                kw_lower = kw.lower()
                
                # Multi-word keyword (phrase match) — higher weight
                if " " in kw_lower:
                    if kw_lower in query_lower:
                        score += 3
                        matches.append(kw)
                else:
                    # Single word match
                    if kw_lower in query_words:
                        score += 1
                        matches.append(kw)
            
            if score > 0:
                scores[agent_id] = score
                matched_keywords[agent_id] = matches

        if scores:
            # Sort by score descending
            sorted_agents = sorted(scores.keys(), key=lambda a: scores[a], reverse=True)
            best_agent = sorted_agents[0]
            best_score = scores[best_agent]
            
            # Ambiguity detection: if top two are close, fall to general
            if len(sorted_agents) > 1:
                second_score = scores[sorted_agents[1]]
                if best_score - second_score <= 1 and best_score <= 2:
                    # Too close to call — use general agent with all tools
                    return "general", {
                        "method": "ambiguous",
                        "confidence": 0.3,
                        "candidates": {a: scores[a] for a in sorted_agents[:3]},
                        "matched_keywords": matched_keywords,
                    }
            
            confidence = min(1.0, best_score / 4.0)  # 4+ points = 100%
            return best_agent, {
                "method": "keyword",
                "confidence": confidence,
                "score": best_score,
                "matched_keywords": matched_keywords.get(best_agent, []),
            }

        # Step 2: Semantic similarity (slower, more accurate)
        try:
            if self._should_use_embedding():
                return self._classify_by_embedding(query)
        except Exception as e:
            frappe.logger().warning(f"AgentRouter embedding classification failed: {e}")

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
