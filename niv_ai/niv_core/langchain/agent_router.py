"""
Agent Router System — Classifies queries and routes to specialized agents.

Architecture:
  Query → Router (0.2s) → Specialized Agent (6-8 tools) → Response

Benefits:
  - 4-5x faster tool selection (8 tools vs 29)
  - Better accuracy (domain-specific prompts)
  - Lower token usage
  - Parallel execution opportunity
"""
import re
import time
import frappe
from typing import Optional, Dict, List, Tuple, Any
from niv_ai.niv_core.utils import get_niv_settings


# ─── Agent Registry ────────────────────────────────────────────────────────

# Defines specialized agents with their tools, keywords, and prompts
# This can later be moved to a DocType for admin configuration

AGENT_REGISTRY = {
    "nbfc": {
        "name": "NBFC Agent",
        "description": "Handles loan applications, NPA analysis, collections, and NBFC operations",
        "keywords": [
            "loan", "npa", "overdue", "emi", "collection", "recovery",
            "borrower", "lender", "disbursement", "sanction", "credit",
            "collateral", "interest rate", "principal", "repayment",
            "default", "write-off", "provision", "sma", "wirr",
            "co-lending", "los", "lms", "underwriting", "dti", "ltv",
            "mahaveer", "growth system", "nbfc"
        ],
        "tools": [
            "list_documents", "get_document", "search_documents",
            "run_python_code", "run_database_query", "generate_report",
            "submit_document", "run_workflow"
        ],
        "prompt_suffix": """\n\nYou are specialized in NBFC and lending operations. You understand:
- Loan Application lifecycle (Lead → Application → Sanction → Disbursement)
- NPA Classification (SMA-0, SMA-1, SMA-2, Sub-standard, Doubtful, Loss)
- Collection and Recovery processes
- Co-lending and Balance Transfer
- Regulatory compliance (RBI guidelines)

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
            "reconciliation", "bank", "cheque", "neft", "rtgs", "upi"
        ],
        "tools": [
            "list_documents", "get_document", "create_document",
            "run_python_code", "run_database_query", "generate_report",
            "search_documents", "analyze_business_data"
        ],
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
            "gratuity", "ctc", "designation", "department"
        ],
        "tools": [
            "list_documents", "get_document", "search_documents",
            "run_python_code", "run_database_query", "generate_report"
        ],
        "prompt_suffix": """\n\nYou are specialized in HR and payroll. You understand:
- Employee lifecycle (Recruitment → Onboarding → Active → Exit)
- Leave management and attendance tracking
- Payroll processing and salary slips
- Performance appraisals and training

Be mindful of data privacy — only share information the user has permission to see.""",
    },

    "general": {
        "name": "General Agent",
        "description": "Handles general queries, admin tasks, and other operations",
        "keywords": [],  # Empty keywords — this is the fallback
        "tools": None,  # None = all tools
        "prompt_suffix": "",  # No special prompt
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
        - agent_id: "nbfc", "accounts", "hr", or "general"
        - metadata: {"method": "keyword|embedding|fallback", "confidence": 0.0-1.0}
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
            # Get agent with most keyword matches
            best_agent = max(matches.keys(), key=lambda a: matches[a])
            confidence = min(1.0, matches[best_agent] / 3.0)  # 3+ matches = 100%
            return best_agent, {
                "method": "keyword",
                "confidence": confidence,
                "matched_keywords": matches
            }

        # Step 2: Semantic similarity (slower, more accurate)
        # Only if embeddings are enabled and no keyword match
        try:
            if self._should_use_embedding():
                return self._classify_by_embedding(query)
        except Exception as e:
            frappe.logger().warning(f"AgentRouter embedding classification failed: {e}")

        # Step 3: Fallback to general agent
        return "general", {"method": "fallback", "confidence": 0.0}

    def _should_use_embedding(self) -> bool:
        """Check if embedding-based classification should be used."""
        try:
            settings = get_niv_settings()
            # Only use embeddings if RAG is enabled (has embedding pipeline)
            return bool(getattr(settings, "enable_knowledge_base", 0))
        except Exception:
            return False

    def _classify_by_embedding(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """Classify using semantic embeddings (optional, for higher accuracy)."""
        # Lazy load embedding model
        if self._embedding_model is None:
            try:
                from niv_ai.niv_core.langchain.rag import get_embeddings
                self._embedding_model = get_embeddings()
            except Exception:
                return "general", {"method": "embedding_failed", "confidence": 0.0}

        if self._embedding_model is None:
            return "general", {"method": "embedding_unavailable", "confidence": 0.0}

        # Get query embedding
        query_embedding = self._embedding_model.embed_query(query)

        # Compare with agent description embeddings (cached)
        best_agent = "general"
        best_score = 0.0

        for agent_id, config in AGENT_REGISTRY.items():
            if agent_id == "general":
                continue

            # Use description as semantic representation
            if agent_id not in self._embedding_cache:
                desc = f"{config['name']}: {config['description']}"
                self._embedding_cache[agent_id] = self._embedding_model.embed_query(desc)

            agent_embedding = self._embedding_cache[agent_id]
            score = self._cosine_similarity(query_embedding, agent_embedding)

            if score > best_score:
                best_score = score
                best_agent = agent_id

        # Only use embedding result if confidence is high enough
        if best_score > 0.3:
            return best_agent, {
                "method": "embedding",
                "confidence": min(1.0, best_score)
            }

        return "general", {"method": "embedding_low_confidence", "confidence": best_score}

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
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
        """Get full config for an agent."""
        return AGENT_REGISTRY.get(agent_id, AGENT_REGISTRY["general"])

    def get_tools_for_agent(self, agent_id: str, all_tools: List[Any]) -> List[Any]:
        """Filter tools for a specific agent."""
        config = self.get_agent_config(agent_id)

        # None = all tools (general agent)
        if config.get("tools") is None:
            return all_tools

        # Filter tools by name
        tool_names = set(config.get("tools", []))
        filtered = [t for t in all_tools if getattr(t, "name", "") in tool_names]

        # If filtering removed all tools, fall back to all tools
        if not filtered:
            frappe.logger().warning(f"AgentRouter: No tools found for {agent_id}, using all tools")
            return all_tools

        return filtered

    def get_system_prompt_suffix(self, agent_id: str) -> str:
        """Get domain-specific prompt addition for an agent."""
        config = self.get_agent_config(agent_id)
        return config.get("prompt_suffix", "")


# ─── Global Router Instance ────────────────────────────────────────────────

_router_instance = None


def get_router() -> AgentRouter:
    """Get or create the global router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = AgentRouter()
    return _router_instance


def classify_query(query: str) -> Tuple[str, Dict[str, Any]]:
    """
    Quick classification function.
    Returns (agent_id, metadata).
    """
    return get_router().classify(query)


def get_agent_tools(agent_id: str, all_tools: List[Any]) -> List[Any]:
    """Get filtered tools for an agent."""
    return get_router().get_tools_for_agent(agent_id, all_tools)


def get_agent_prompt_suffix(agent_id: str) -> str:
    """Get domain-specific prompt for an agent."""
    return get_router().get_system_prompt_suffix(agent_id)


# ─── Testing / Debugging ───────────────────────────────────────────────────

def test_router():
    """Test the router with sample queries."""
    test_queries = [
        "NPA classification rules batao aur hamare overdue loans dikhao",
        "Top 5 loan applications dikhao",
        "Is employee ki salary kitni hai",
        "Last month ke payments dikhao",
        "General query about the system",
        "Borrower ka credit score check karo",
        "Profit and loss statement generate karo",
        "Staff ke attendance report chahiye",
    ]

    router = get_router()
    results = []

    for q in test_queries:
        agent_id, meta = router.classify(q)
        config = router.get_agent_config(agent_id)
        results.append({
            "query": q[:50] + "..." if len(q) > 50 else q,
            "agent": agent_id,
            "confidence": meta.get("confidence", 0),
            "method": meta.get("method", "unknown"),
            "tool_count": len(config.get("tools") or []),
        })

    return results


if __name__ == "__main__":
    # Run tests
    import json
    results = test_router()
    print(json.dumps(results, indent=2))