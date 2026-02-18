"""
Agent Router — Simplified. LLM decides tool selection freely.

Previous approach: keyword-based routing → filtered tool subsets
New approach: ALL tools available, few-shot examples as prompt hints

The LLM is smart enough to pick the right tool when given:
1. Good tool descriptions (via tool_descriptions.py)
2. Few-shot examples in system prompt
3. Minimal guidance rules
"""
import frappe
from typing import Dict, Any, Tuple, List
from niv_ai.niv_core.utils import get_niv_settings


# ─── Few-Shot Examples ──────────────────────────────────────────────
# These help the LLM understand HOW to call tools correctly.
# Not routing — just showing patterns.

NBFC_EXAMPLES = """
## TOOL CALLING EXAMPLES (NBFC/Lending):

### "show all loans" / "loan list"
list_documents(doctype="Loan", fields=["name","applicant_name","loan_amount","status","posting_date"], limit=20, order_by="posting_date desc")

### "overdue loans" / "NPA loans"
list_documents(doctype="Loan", filters={"status": ["in", ["Overdue","NPA"]]}, fields=["name","applicant_name","loan_amount","status"], limit=20)

### "loan details LOAN-001"
get_document(doctype="Loan", name="LOAN-001")

### "total disbursed amount" / "loan portfolio"
run_database_query(query="SELECT SUM(loan_amount) as total, COUNT(*) as count FROM `tabLoan` WHERE status='Disbursed'")

### "loan count by status"
run_database_query(query="SELECT status, COUNT(*) as count, SUM(loan_amount) as total FROM `tabLoan` GROUP BY status")
"""

GENERAL_EXAMPLES = """
## TOOL CALLING EXAMPLES:

### "list of [anything]" / "show [records]"
list_documents(doctype="[DocType]", fields=["name","..."], limit=20)

### "details of [record]"
get_document(doctype="[DocType]", name="[Name]")

### "how many" / "total" / "count"
run_database_query(query="SELECT COUNT(*) FROM `tabDocType` WHERE ...")
"""


# ─── DocType Quick Reference ───────────────────────────────────────
# Embedded schema so LLM doesn't need get_doctype_info for common types

COMMON_DOCTYPES = """
## KEY DOCTYPES (no need to call get_doctype_info for these):

### Loan (`tabLoan`)
Fields: name, applicant, applicant_name, loan_amount, loan_type, status, posting_date, rate_of_interest, loan_duration, product, applicant_mobile_number
Status: Sanctioned, Partially Disbursed, Disbursed, Loan Closure Requested, Closed, Cancel

### Loan Application (`tabLoan Application`)  
Fields: name, applicant, first_name, last_name, workflow_state, status, company

### Loan Repayment (`tabLoan Repayment`)
Fields: name, against_loan, applicant, applicant_name, posting_date, repayment_mode

### Customer (`tabCustomer`)
Fields: name, customer_name, customer_type, first_name, last_name, mobile_no
"""


def get_prompt_enhancement(query: str = "") -> str:
    """Get few-shot examples and DocType reference for the system prompt.
    
    No routing, no filtering — just helpful context for the LLM.
    """
    parts = []
    
    # Always include common DocType reference
    parts.append(COMMON_DOCTYPES)
    
    # Detect if NBFC app is installed → add NBFC examples
    try:
        if "nbfc" in frappe.get_installed_apps():
            parts.append(NBFC_EXAMPLES)
        else:
            parts.append(GENERAL_EXAMPLES)
    except Exception:
        parts.append(GENERAL_EXAMPLES)
    
    return "\n".join(parts)


# ─── Backward Compatibility ────────────────────────────────────────
# These functions are called by agent.py — keep the interface but simplify

def classify_query(query: str) -> Tuple[str, Dict[str, Any]]:
    """Always returns 'general' — no routing, LLM decides."""
    return "general", {"method": "llm_decides", "confidence": 1.0}


def get_agent_tools(agent_id: str, all_tools: List[Any]) -> List[Any]:
    """Always returns ALL tools — no filtering."""
    return all_tools


def get_agent_prompt_suffix(agent_id: str) -> str:
    """Returns few-shot examples instead of agent-specific prompts."""
    return get_prompt_enhancement()
