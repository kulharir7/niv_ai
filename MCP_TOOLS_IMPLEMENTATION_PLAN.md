# MCP Tools Enterprise Implementation Plan — Niv AI v0.8.0

**Created:** 2026-02-18
**Status:** READY FOR IMPLEMENTATION
**Goal:** Make Niv AI's tool system stable, efficient, and NBFC-ready

---

## Overview

5 Phases, 32 tasks. Har task ka exact file path, kya change karna hai, aur full production-ready code hai. Koi shortcut nahi.

---

## Phase 1: Tool Descriptions & Schema Fix (Day 1-2) 🔴 CRITICAL

### Task 1.1: Create Tool Description Enhancement File

**File:** `niv_ai/niv_core/tools/tool_descriptions.py` (NEW FILE)
**What:** Central place for all enhanced tool descriptions and parameter schemas
**Why:** FAC ke tools ki descriptions bahut short hain — LLM galat tool choose karta hai

```python
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
                    "Always include 'name'. Use ['*'] for all fields (expensive). "
                    "Example: [\"name\", \"status\", \"loan_amount\", \"posting_date\"]"
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
            "- Field names use snake_case (e.g., loan_amount, posting_date)\n"
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
```

---

### Task 1.2: Apply Enhanced Descriptions in tools.py

**File:** `niv_ai/niv_core/langchain/tools.py`
**What:** Use enhanced descriptions when building LangChain tools
**Where:** Inside `get_langchain_tools()` function

**Change in `get_langchain_tools()`:**

Find this code block:
```python
    for tool_def in mcp_tools:
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        if not name:
            continue

        description = func_def.get("description", "")[:4096]
        parameters = func_def.get("parameters", {})
```

Replace with:
```python
    from niv_ai.niv_core.tools.tool_descriptions import (
        get_enhanced_description, enhance_tool_schema
    )

    for tool_def in mcp_tools:
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "")
        if not name:
            continue

        # Use enhanced descriptions if available (much better for LLM tool selection)
        enhanced_desc = get_enhanced_description(name)
        description = (enhanced_desc or func_def.get("description", ""))[:4096]
        
        # Enhance parameter schemas with better descriptions and examples
        parameters = enhance_tool_schema(name, func_def.get("parameters", {}))
```

**Also create `__init__.py`:**

**File:** `niv_ai/niv_core/tools/__init__.py` (NEW FILE)
```python
# MCP Tools utilities for Niv AI
```

---

### Task 1.3: Add Tool Usage Guidelines to System Prompt

**File:** `niv_ai/niv_core/langchain/memory.py`
**What:** Add tool usage decision tree and efficiency rules to system prompt
**Where:** Add a new constant and append to `get_system_prompt()`

Add this constant at the top of the file (after imports):

```python
TOOL_USAGE_GUIDELINES = """
## Tool Usage Guidelines (MANDATORY — Follow These Rules)

### Tool Selection Decision Tree
- Need a single document by name/ID? → get_document
- Need a list with simple filters? → list_documents
- Need SQL-level analytics (JOIN, GROUP BY, SUM, AVG, COUNT)? → run_database_query
- Don't know the DocType name? → search_doctype
- Don't know field names for a DocType? → get_doctype_info
- Need to create/update/delete? → create_document / update_document / delete_document
- Need a pre-built report? → report_requirements FIRST, then generate_report
- Need full-text search across fields? → search_documents
- Need to find an exact linked record name? → search_link

### Efficiency Rules (CRITICAL)
1. MAXIMUM 4 tool calls per user question. If you need more, summarize and ask to continue.
2. For "how many X" questions → use run_database_query with SELECT COUNT(*), NOT list_documents.
3. For "total/sum/average" questions → use run_database_query with SUM/AVG, NOT list_documents.
4. If you know the DocType fields already, do NOT call get_doctype_info first.
5. If a tool fails, try ONE different approach. If that also fails, explain the issue to the user.
6. NEVER call the same tool with the same arguments twice.
7. After getting tool results, ALWAYS write a text summary. Never end with just tool calls.

### Common Mistakes to Avoid
- Using list_documents to count records → Use run_database_query with COUNT(*)
- Calling get_doctype_info for well-known DocTypes (Customer, Item, Sales Invoice, Loan)
- Calling list_documents + get_document for the same record → Just use get_document directly
- Using run_python_code for simple math → Calculate it yourself
"""
```

Then in `get_system_prompt()`, append it to the default prompt. Find:
```python
    if discovery_ctx:
        return default_prompt + "\n\n" + discovery_ctx
    return default_prompt
```

Replace with:
```python
    # Always append tool usage guidelines
    full_prompt = default_prompt + "\n\n" + TOOL_USAGE_GUIDELINES
    if discovery_ctx:
        full_prompt += "\n\n" + discovery_ctx
    return full_prompt
```

---

### Task 1.4: Embed NBFC DocType Schemas in Agent Router

**File:** `niv_ai/niv_core/langchain/agent_router.py`
**What:** Add common DocType field info to NBFC agent prompt so it doesn't need get_doctype_info calls
**Where:** Update `AGENT_REGISTRY["nbfc"]["prompt_suffix"]`

Replace the nbfc prompt_suffix with:

```python
        "prompt_suffix": """\n\nYou are specialized in NBFC and lending operations. You understand:
- Loan Application lifecycle (Lead → Application → Sanction → Disbursement)
- NPA Classification (SMA-0, SMA-1, SMA-2, Sub-standard, Doubtful, Loss)
- Collection and Recovery processes
- Co-lending and Balance Transfer
- Regulatory compliance (RBI guidelines)

Always show financial data in proper tables with formatted numbers (₹ symbol, Indian number format).

## Key DocTypes & Fields (USE DIRECTLY — no need to call get_doctype_info)

### Loan Application
- Fields: name, applicant, applicant_name, loan_amount, loan_type, status, posting_date, company, rate_of_interest, repayment_method, repayment_periods
- Status values: Open, Approved, Rejected, Sanctioned, Disbursed, Closed
- Table name: `tabLoan Application`

### Loan
- Fields: name, applicant, applicant_name, loan_amount, loan_type, status, disbursement_date, repayment_start_date, total_payment, total_interest_payable, total_amount_paid, monthly_repayment_amount, rate_of_interest, company
- Status values: Sanctioned, Partially Disbursed, Disbursed, Loan Closure Requested, Closed
- Table name: `tabLoan`

### Loan Repayment
- Fields: name, against_loan, applicant, payment_type, amount_paid, posting_date, principal_amount, interest_amount, penalty_amount
- Table name: `tabLoan Repayment`

### Loan Disbursement
- Fields: name, against_loan, applicant, disbursed_amount, posting_date, disbursement_date
- Table name: `tabLoan Disbursement`

### Journal Entry
- Fields: name, voucher_type, posting_date, total_debit, total_credit, company, remark
- Table name: `tabJournal Entry`

### Customer
- Fields: name, customer_name, customer_type, customer_group, territory, default_currency
- Table name: `tabCustomer`

## Common SQL Patterns for NBFC
- Overdue loans: SELECT * FROM `tabLoan` WHERE status='Disbursed' AND name IN (SELECT parent FROM `tabRepayment Schedule` WHERE payment_date < CURDATE() AND is_paid=0)
- Loan count by status: SELECT status, COUNT(*) as count, SUM(loan_amount) as total FROM `tabLoan` GROUP BY status
- Total AUM: SELECT SUM(loan_amount) as total_aum, COUNT(*) as loan_count FROM `tabLoan` WHERE docstatus=1 AND status IN ('Disbursed', 'Partially Disbursed')
""",
```

---

### Task 1.5: Delete Dead mcp_loader.py

**File:** `niv_ai/niv_core/tools/mcp_loader.py` — CHECK IF EXISTS
**What:** This file is dead code (never imported). Verify and delete.

Check: `niv_ai/niv_core/tools/mcp_loader.py` — if it exists and is not imported anywhere, delete it.
Also check for any file at the old v0.7.0 location if it was created there.

---

## Phase 2: Tool Result Optimization (Day 3-5) 🟡 HIGH

### Task 2.1: Create Tool Result Summarizer

**File:** `niv_ai/niv_core/tools/result_processor.py` (NEW FILE)
**What:** Post-process tool results to reduce token waste
**Why:** list_documents returns 50KB+ JSON that floods context window

```python
"""
Tool Result Post-Processor for Niv AI.

Problem: MCP tools return raw JSON that can be 50KB+, flooding the LLM context window.
Solution: Intelligently summarize/truncate results while preserving essential information.

Usage: Called by langchain/tools.py in _make_mcp_executor() after getting tool result.
"""
import json
from typing import Optional


# Maximum characters to allow in a tool result before summarization kicks in
MAX_RESULT_CHARS = 4000

# Tools whose results should never be truncated (schema/metadata tools)
_NO_TRUNCATE_TOOLS = {
    "get_doctype_info", "search_doctype", "report_requirements",
    "report_list", "search_link"
}

# Read-only tools whose results can be cached
READ_ONLY_TOOLS = {
    "get_doctype_info", "search_doctype", "report_list",
    "report_requirements", "search_link"
}


def post_process_result(tool_name: str, result_text: str) -> str:
    """Post-process a tool result to reduce token usage.
    
    Strategy:
    1. Small results (< MAX_RESULT_CHARS) → pass through unchanged
    2. JSON list results → keep first N records + summary
    3. Large text → truncate with indicator
    4. Schema tools → never truncate
    
    Args:
        tool_name: Name of the tool that produced this result
        result_text: Raw result string from MCP tool
        
    Returns:
        Processed result string (may be shorter than input)
    """
    if not result_text:
        return result_text
    
    # Small results → pass through
    if len(result_text) <= MAX_RESULT_CHARS:
        return result_text
    
    # Schema/metadata tools → don't truncate (they're reference data)
    if tool_name in _NO_TRUNCATE_TOOLS:
        # Still apply a generous limit
        if len(result_text) > 8000:
            return result_text[:8000] + "\n\n[... truncated. Use specific filters for smaller results.]"
        return result_text
    
    # Try to parse as JSON for intelligent summarization
    try:
        data = json.loads(result_text)
        return _summarize_json_result(tool_name, data)
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Plain text → hard truncate with indicator
    return _truncate_text(result_text)


def _summarize_json_result(tool_name: str, data) -> str:
    """Summarize a JSON tool result intelligently."""
    
    # Case 1: Dict with "data" list (list_documents pattern)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return _summarize_list_result(tool_name, data)
    
    # Case 2: Dict with "result" that contains data
    if isinstance(data, dict) and "result" in data:
        result_val = data["result"]
        if isinstance(result_val, dict) and "data" in result_val and isinstance(result_val["data"], list):
            return _summarize_list_result(tool_name, result_val)
        if isinstance(result_val, list):
            return _summarize_list_result(tool_name, {"data": result_val})
    
    # Case 3: Plain list
    if isinstance(data, list):
        return _summarize_list_result(tool_name, {"data": data})
    
    # Case 4: Dict with large string values
    if isinstance(data, dict):
        return _summarize_dict_result(data)
    
    # Fallback: convert back to JSON string and truncate
    text = json.dumps(data, default=str, ensure_ascii=False)
    return _truncate_text(text)


def _summarize_list_result(tool_name: str, data: dict) -> str:
    """Summarize a list-type result (most common for list_documents)."""
    records = data.get("data", [])
    total_count = data.get("total_count", len(records))
    message = data.get("message", "")
    
    if not records:
        return json.dumps({"data": [], "total_count": 0, "message": message or "No records found"}, 
                         default=str, ensure_ascii=False)
    
    # Determine how many records to keep
    # For small lists, keep all; for large lists, keep first 10
    max_records = 10 if len(records) > 10 else len(records)
    
    summary = {
        "total_records_in_database": total_count,
        "records_returned": len(records),
        "showing_first": max_records,
        "data": records[:max_records],
    }
    
    if message:
        summary["message"] = message
    
    if len(records) > max_records:
        summary["note"] = (
            f"Showing {max_records} of {len(records)} returned records "
            f"({total_count} total in database). "
            "Add more specific filters or use get_document for details on a specific record."
        )
    
    result = json.dumps(summary, default=str, ensure_ascii=False)
    
    # If still too large after keeping 10 records, reduce further
    if len(result) > MAX_RESULT_CHARS and max_records > 5:
        summary["data"] = records[:5]
        summary["showing_first"] = 5
        summary["note"] = (
            f"Showing 5 of {len(records)} returned records "
            f"({total_count} total in database). "
            "Results were large — add more specific filters or ask about specific records."
        )
        result = json.dumps(summary, default=str, ensure_ascii=False)
    
    # Last resort: truncate individual records
    if len(result) > MAX_RESULT_CHARS:
        # Keep only key fields from each record
        slim_records = []
        for record in records[:5]:
            if isinstance(record, dict):
                # Keep name + up to 5 most important fields
                slim = {}
                priority_fields = ["name", "status", "title", "subject", "customer_name", 
                                  "applicant_name", "loan_amount", "amount", "total", 
                                  "posting_date", "creation"]
                for f in priority_fields:
                    if f in record:
                        slim[f] = record[f]
                # Add remaining fields up to limit
                for k, v in record.items():
                    if k not in slim and len(slim) < 8:
                        val = str(v)
                        slim[k] = val[:200] if len(val) > 200 else v
                slim_records.append(slim)
            else:
                slim_records.append(record)
        
        summary["data"] = slim_records
        result = json.dumps(summary, default=str, ensure_ascii=False)
    
    return result


def _summarize_dict_result(data: dict) -> str:
    """Summarize a dict result by truncating large values."""
    slim = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 500:
            slim[key] = value[:500] + "...[truncated]"
        elif isinstance(value, list) and len(value) > 10:
            slim[key] = value[:10]
            slim[f"_{key}_note"] = f"Showing 10 of {len(value)} items"
        elif isinstance(value, dict):
            # Recursively handle nested dicts
            val_str = json.dumps(value, default=str)
            if len(val_str) > 1000:
                slim[key] = json.loads(val_str[:1000] + "}")  # Attempt to keep valid JSON
            else:
                slim[key] = value
        else:
            slim[key] = value
    
    return json.dumps(slim, default=str, ensure_ascii=False)


def _truncate_text(text: str) -> str:
    """Truncate plain text with indicator."""
    if len(text) <= MAX_RESULT_CHARS:
        return text
    
    truncated = text[:MAX_RESULT_CHARS]
    remaining = len(text) - MAX_RESULT_CHARS
    return f"{truncated}\n\n[... {remaining} characters truncated. Ask for specific details if needed.]"


def add_next_steps(tool_name: str, result_text: str) -> str:
    """Append contextual next-step hints to tool results.
    
    Guides the LLM on what to do after getting this result.
    """
    hints = {
        "list_documents": (
            "\n\n💡 Next steps: Use get_document(doctype, name) to see full details "
            "of a specific record. Use run_database_query for aggregations (SUM, COUNT, AVG)."
        ),
        "get_doctype_info": (
            "\n\n💡 Now you know the fields. Use list_documents with correct field names, "
            "or create_document with all required fields."
        ),
        "report_requirements": (
            "\n\n💡 Now call generate_report with the required filters listed above."
        ),
        "search_doctype": (
            "\n\n💡 Now use list_documents or get_document with the correct DocType name."
        ),
        "report_list": (
            "\n\n💡 To generate a report, first call report_requirements(report_name) to get required filters, "
            "then call generate_report(report_name, filters)."
        ),
    }
    
    hint = hints.get(tool_name)
    if hint and len(result_text) < MAX_RESULT_CHARS:  # Don't add hints to already large results
        return result_text + hint
    return result_text
```

---

### Task 2.2: Integrate Result Processor into tools.py

**File:** `niv_ai/niv_core/langchain/tools.py`
**What:** Call post_process_result() and add_next_steps() after every tool call
**Where:** Inside `_make_mcp_executor()`, after getting the result

Find the existing result processing block in `_make_mcp_executor()` (the try/except around `call_tool_fast`):

After the line:
```python
            return str(result)
```
(the final return inside the try block)

**The entire try block** should be wrapped to include post-processing. Replace the try/except in the execute() function (after the confirmation check and validation) with:

```python
        server_name = find_tool_server(tool_name)
        if not server_name:
            return json.dumps({"error": f"No MCP server found for tool: {tool_name}"})

        try:
            # Use per-user API key if available (permission isolation)
            user_key = get_current_user_api_key()

            result = call_tool_fast(
                server_name=server_name,
                tool_name=tool_name,
                arguments=clean_args,
                user_api_key=user_key,
            )

            # MCP returns {"content": [{"type": "text", "text": "..."}]}
            result_text = None
            if isinstance(result, dict) and "content" in result:
                contents = result["content"]
                if isinstance(contents, list):
                    text_parts = []
                    for c in contents:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text_parts.append(c.get("text", ""))
                        elif isinstance(c, dict):
                            text_parts.append(json.dumps(c, default=str))
                        else:
                            text_parts.append(str(c))
                    result_text = "\n".join(text_parts)

            if result_text is None:
                # BUG-012: Ensure result is always a string for the LLM
                if isinstance(result, (dict, list)):
                    result_text = json.dumps(result, default=str, ensure_ascii=False)
                else:
                    result_text = str(result)

            # ── Post-process: Summarize large results + add next-step hints ──
            from niv_ai.niv_core.tools.result_processor import post_process_result, add_next_steps
            result_text = post_process_result(tool_name, result_text)
            result_text = add_next_steps(tool_name, result_text)

            return result_text

        except Exception as e:
            frappe.log_error(f"MCP tool '{tool_name}' failed: {e}", "Niv AI MCP")
            # Return actionable error — guides LLM to self-correct
            err_str = str(e)
            hint = _get_recovery_hint(tool_name, clean_args, err_str)
            return json.dumps({
                "error": f"Tool '{tool_name}' failed: {err_str}",
                "recovery_hint": hint,
            })
```

---

### Task 2.3: Add Consecutive Failure Detection

**File:** `niv_ai/niv_core/langchain/tools.py`
**What:** Stop LLM from retrying the same failed tool 3+ times
**Where:** Add tracking in `_make_mcp_executor()`

Add this at the top of `tools.py` (after existing imports):

```python
import time as _time

# Track consecutive failures per conversation to prevent retry loops
# Key: (conversation_id, tool_name, args_hash) → count
_failure_tracker = {}
_FAILURE_TRACKER_TTL = 300  # 5 min
_MAX_CONSECUTIVE_FAILURES = 2
```

Add this function after the existing `_get_recovery_hint()`:

```python
def _check_failure_limit(tool_name: str, arguments: dict) -> str:
    """Check if this tool+args combo has failed too many times.
    
    Returns error message if limit exceeded, None otherwise.
    Prevents the LLM from retrying the same failed operation in a loop.
    """
    conv_id = get_active_dev_conv_id()
    if not conv_id:
        return None
    
    args_hash = hashlib.md5(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()[:8]
    key = f"{conv_id}:{tool_name}:{args_hash}"
    
    # Clean old entries
    now = _time.time()
    stale_keys = [k for k, v in _failure_tracker.items() if v.get("expires", 0) < now]
    for k in stale_keys:
        _failure_tracker.pop(k, None)
    
    entry = _failure_tracker.get(key)
    if entry and entry.get("count", 0) >= _MAX_CONSECUTIVE_FAILURES:
        return (
            f"STOP: Tool '{tool_name}' has already failed {entry['count']} times with similar arguments. "
            "Do NOT retry. Use a completely different approach or tell the user you cannot complete this request. "
            "Try: (1) a different tool, (2) simpler arguments, or (3) explain to the user what went wrong."
        )
    return None


def _record_tool_failure(tool_name: str, arguments: dict):
    """Record a tool failure for consecutive failure tracking."""
    conv_id = get_active_dev_conv_id()
    if not conv_id:
        return
    
    args_hash = hashlib.md5(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()[:8]
    key = f"{conv_id}:{tool_name}:{args_hash}"
    
    entry = _failure_tracker.get(key, {"count": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["expires"] = _time.time() + _FAILURE_TRACKER_TTL
    _failure_tracker[key] = entry


def _clear_tool_failures(tool_name: str, arguments: dict):
    """Clear failure tracking on success."""
    conv_id = get_active_dev_conv_id()
    if not conv_id:
        return
    
    args_hash = hashlib.md5(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()[:8]
    key = f"{conv_id}:{tool_name}:{args_hash}"
    _failure_tracker.pop(key, None)
```

Then in `_make_mcp_executor()`, add failure check at the start of `execute()` (after cleaning None args, before confirmation flow):

```python
        # ── Check consecutive failure limit ──
        failure_msg = _check_failure_limit(tool_name, clean_args)
        if failure_msg:
            return json.dumps({"error": failure_msg})
```

And in the except block, add failure recording:

```python
        except Exception as e:
            frappe.log_error(f"MCP tool '{tool_name}' failed: {e}", "Niv AI MCP")
            _record_tool_failure(tool_name, clean_args)  # Track failure
            err_str = str(e)
            hint = _get_recovery_hint(tool_name, clean_args, err_str)
            return json.dumps({
                "error": f"Tool '{tool_name}' failed: {err_str}",
                "recovery_hint": hint,
            })
```

And after successful result, clear failures:

```python
            # ── Post-process: Summarize large results + add next-step hints ──
            from niv_ai.niv_core.tools.result_processor import post_process_result, add_next_steps
            result_text = post_process_result(tool_name, result_text)
            result_text = add_next_steps(tool_name, result_text)
            
            _clear_tool_failures(tool_name, clean_args)  # Clear on success

            return result_text
```

---

### Task 2.4: Improve Agent Router with Weighted Scoring

**File:** `niv_ai/niv_core/langchain/agent_router.py`
**What:** Better keyword matching with multi-word keyword bonus + ambiguity detection
**Where:** Replace `classify()` method in `AgentRouter` class

Replace the `classify()` method with:

```python
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
```

---

### Task 2.5: Add Tool Result Caching for Read-Only Tools

**File:** `niv_ai/niv_core/tools/result_cache.py` (NEW FILE)
**What:** Cache results of read-only tools (get_doctype_info, report_list, etc.)
**Why:** Same get_doctype_info("Customer") call returns identical data every time

```python
"""
Tool Result Cache for read-only MCP tools.

Problem: get_doctype_info, search_doctype, report_list return the same data every time,
but are called fresh on every request (wastes ~200ms per call).

Solution: Short-lived worker-memory cache for read-only tools.
Cache keys include tool_name + args hash. TTL = 2 minutes.

Usage: Called by langchain/tools.py in _make_mcp_executor()
"""
import hashlib
import json
import time
import threading


# Read-only tools safe to cache (no side effects)
CACHEABLE_TOOLS = {
    "get_doctype_info",
    "search_doctype",
    "report_list",
    "report_requirements",
    "search_link",
}

# Cache storage: {cache_key: (result_string, expires_timestamp)}
_result_cache = {}
_cache_lock = threading.Lock()

# Cache configuration
CACHE_TTL = 120  # 2 minutes
MAX_CACHE_SIZE = 200  # Maximum entries before cleanup


def get_cached_result(tool_name: str, arguments: dict) -> str:
    """Get a cached result for a read-only tool call.
    
    Returns:
        Cached result string, or None if not cached or expired.
    """
    if tool_name not in CACHEABLE_TOOLS:
        return None
    
    key = _make_key(tool_name, arguments)
    
    with _cache_lock:
        entry = _result_cache.get(key)
        if entry is None:
            return None
        
        result, expires = entry
        if time.time() > expires:
            # Expired — remove and return None
            _result_cache.pop(key, None)
            return None
        
        return result


def set_cached_result(tool_name: str, arguments: dict, result: str):
    """Cache a result for a read-only tool call.
    
    Only caches if:
    - Tool is in CACHEABLE_TOOLS
    - Result is not an error
    - Result is not too large (< 10KB)
    """
    if tool_name not in CACHEABLE_TOOLS:
        return
    
    # Don't cache errors
    if '"error"' in result[:100]:
        return
    
    # Don't cache very large results (schema tools should be small)
    if len(result) > 10000:
        return
    
    key = _make_key(tool_name, arguments)
    
    with _cache_lock:
        # Cleanup if cache is getting too large
        if len(_result_cache) >= MAX_CACHE_SIZE:
            _evict_expired()
        
        _result_cache[key] = (result, time.time() + CACHE_TTL)


def clear_cache():
    """Clear all cached results. Call when tools change."""
    with _cache_lock:
        _result_cache.clear()


def _make_key(tool_name: str, arguments: dict) -> str:
    """Generate a cache key from tool name + arguments."""
    args_str = json.dumps(arguments, sort_keys=True, default=str)
    args_hash = hashlib.md5(args_str.encode()).hexdigest()
    return f"{tool_name}:{args_hash}"


def _evict_expired():
    """Remove expired entries from cache. Called with lock held."""
    now = time.time()
    expired_keys = [k for k, (_, exp) in _result_cache.items() if exp < now]
    for k in expired_keys:
        _result_cache.pop(k, None)
    
    # If still too large after removing expired, remove oldest entries
    if len(_result_cache) >= MAX_CACHE_SIZE:
        # Sort by expiry and remove oldest half
        sorted_entries = sorted(_result_cache.items(), key=lambda x: x[1][1])
        to_remove = len(_result_cache) // 2
        for key, _ in sorted_entries[:to_remove]:
            _result_cache.pop(key, None)
```

**Integrate into tools.py** — In `_make_mcp_executor()`, before calling `call_tool_fast()`:

```python
        # ── Check result cache for read-only tools ──
        from niv_ai.niv_core.tools.result_cache import get_cached_result, set_cached_result
        cached = get_cached_result(tool_name, clean_args)
        if cached is not None:
            return cached

        server_name = find_tool_server(tool_name)
        # ... existing code ...
```

And after getting the successful result (before the final return):

```python
            # Cache read-only tool results
            set_cached_result(tool_name, clean_args, result_text)
            
            _clear_tool_failures(tool_name, clean_args)
            return result_text
```

---

## Phase 3: NBFC-Specific Tools (Week 2-3) 🟡 HIGH

> **Note:** These tools are FAC BaseTool subclasses installed via hooks.
> They run on the same server as FAC, so they get the direct Python call path.

### Task 3.1: Create NBFC Tools Package

**File:** `niv_ai/niv_core/tools/nbfc/__init__.py` (NEW)

```python
"""
NBFC-specific compound tools for Niv AI.

These tools combine multiple database queries into single, domain-optimized
operations. Each tool replaces 3-5 individual tool calls.

Registration: Via hooks.py → assistant_tools hook → FAC picks them up.
"""
```

### Task 3.2: Loan Portfolio Summary Tool

**File:** `niv_ai/niv_core/tools/nbfc/loan_summary.py` (NEW)

```python
"""
NBFC Loan Portfolio Summary Tool.

Replaces: 3-4 calls to list_documents + run_database_query
Returns: Complete portfolio overview with NPA classification, DPD buckets, and key metrics.
"""
import json
import frappe
from datetime import datetime, timedelta


def nbfc_loan_summary(company: str = None, as_of_date: str = None, include_details: bool = False) -> str:
    """Get comprehensive NBFC loan portfolio summary.
    
    Args:
        company: Filter by company name. Leave empty for all companies.
        as_of_date: Report date in YYYY-MM-DD format. Default: today.
        include_details: If True, include individual loan records. Default: False.
    
    Returns:
        JSON string with portfolio metrics, NPA classification, and DPD analysis.
    """
    as_of_date = as_of_date or frappe.utils.today()
    
    # Build company filter
    company_filter = f"AND l.company = {frappe.db.escape(company)}" if company else ""
    
    # ── 1. Portfolio Overview ──
    overview_query = f"""
        SELECT 
            COUNT(*) as total_loans,
            COUNT(CASE WHEN l.status IN ('Disbursed', 'Partially Disbursed') THEN 1 END) as active_loans,
            COALESCE(SUM(l.loan_amount), 0) as total_sanctioned,
            COALESCE(SUM(CASE WHEN l.status IN ('Disbursed', 'Partially Disbursed') 
                         THEN l.loan_amount ELSE 0 END), 0) as total_aum,
            COALESCE(SUM(l.total_amount_paid), 0) as total_collected,
            COALESCE(SUM(l.total_payment - l.total_amount_paid), 0) as total_outstanding,
            COALESCE(AVG(l.rate_of_interest), 0) as avg_interest_rate,
            COUNT(DISTINCT l.applicant) as unique_borrowers
        FROM `tabLoan` l
        WHERE l.docstatus = 1 {company_filter}
    """
    
    overview = frappe.db.sql(overview_query, as_dict=True)
    overview_data = overview[0] if overview else {}
    
    # ── 2. Status Distribution ──
    status_query = f"""
        SELECT 
            l.status,
            COUNT(*) as count,
            COALESCE(SUM(l.loan_amount), 0) as total_amount
        FROM `tabLoan` l
        WHERE l.docstatus = 1 {company_filter}
        GROUP BY l.status
        ORDER BY total_amount DESC
    """
    status_data = frappe.db.sql(status_query, as_dict=True)
    
    # ── 3. Loan Type Distribution ──
    type_query = f"""
        SELECT 
            l.loan_type,
            COUNT(*) as count,
            COALESCE(SUM(l.loan_amount), 0) as total_amount,
            COALESCE(AVG(l.rate_of_interest), 0) as avg_rate
        FROM `tabLoan` l
        WHERE l.docstatus = 1 {company_filter}
        GROUP BY l.loan_type
        ORDER BY total_amount DESC
    """
    type_data = frappe.db.sql(type_query, as_dict=True)
    
    # ── 4. DPD (Days Past Due) Analysis ──
    # Get overdue repayment schedules for active loans
    dpd_query = f"""
        SELECT 
            l.name as loan_name,
            l.applicant_name,
            l.loan_amount,
            MIN(rs.payment_date) as first_overdue_date,
            DATEDIFF('{as_of_date}', MIN(rs.payment_date)) as dpd_days,
            COUNT(rs.name) as overdue_installments,
            COALESCE(SUM(rs.total_payment), 0) as overdue_amount
        FROM `tabLoan` l
        JOIN `tabRepayment Schedule` rs ON rs.parent = l.name
        WHERE l.docstatus = 1 
            AND l.status IN ('Disbursed', 'Partially Disbursed')
            AND rs.is_paid = 0
            AND rs.payment_date < '{as_of_date}'
            {company_filter}
        GROUP BY l.name, l.applicant_name, l.loan_amount
        ORDER BY dpd_days DESC
    """
    
    try:
        overdue_loans = frappe.db.sql(dpd_query, as_dict=True)
    except Exception:
        # Repayment Schedule might not exist or have different structure
        overdue_loans = []
    
    # Classify into DPD buckets
    dpd_buckets = {
        "0_days": {"count": 0, "amount": 0, "label": "Current (0 DPD)"},
        "1_30_days": {"count": 0, "amount": 0, "label": "1-30 Days"},
        "31_60_days": {"count": 0, "amount": 0, "label": "31-60 Days"},
        "61_90_days": {"count": 0, "amount": 0, "label": "61-90 Days (SMA-2)"},
        "91_180_days": {"count": 0, "amount": 0, "label": "91-180 Days (Sub-standard/NPA)"},
        "181_365_days": {"count": 0, "amount": 0, "label": "181-365 Days (Doubtful)"},
        "365_plus_days": {"count": 0, "amount": 0, "label": "365+ Days (Loss)"},
    }
    
    npa_loans = []
    for loan in overdue_loans:
        dpd = loan.get("dpd_days", 0) or 0
        amount = float(loan.get("loan_amount", 0) or 0)
        
        if dpd <= 0:
            dpd_buckets["0_days"]["count"] += 1
            dpd_buckets["0_days"]["amount"] += amount
        elif dpd <= 30:
            dpd_buckets["1_30_days"]["count"] += 1
            dpd_buckets["1_30_days"]["amount"] += amount
        elif dpd <= 60:
            dpd_buckets["31_60_days"]["count"] += 1
            dpd_buckets["31_60_days"]["amount"] += amount
        elif dpd <= 90:
            dpd_buckets["61_90_days"]["count"] += 1
            dpd_buckets["61_90_days"]["amount"] += amount
        elif dpd <= 180:
            dpd_buckets["91_180_days"]["count"] += 1
            dpd_buckets["91_180_days"]["amount"] += amount
            npa_loans.append(loan)
        elif dpd <= 365:
            dpd_buckets["181_365_days"]["count"] += 1
            dpd_buckets["181_365_days"]["amount"] += amount
            npa_loans.append(loan)
        else:
            dpd_buckets["365_plus_days"]["count"] += 1
            dpd_buckets["365_plus_days"]["amount"] += amount
            npa_loans.append(loan)
    
    # Add current (non-overdue) active loans to 0 DPD bucket
    active_count = int(overview_data.get("active_loans", 0))
    overdue_count = len(overdue_loans)
    current_count = max(0, active_count - overdue_count)
    dpd_buckets["0_days"]["count"] += current_count
    
    # ── 5. NPA Summary ──
    total_npa_count = sum(1 for l in overdue_loans if (l.get("dpd_days", 0) or 0) > 90)
    total_npa_amount = sum(float(l.get("loan_amount", 0) or 0) for l in overdue_loans if (l.get("dpd_days", 0) or 0) > 90)
    total_aum = float(overview_data.get("total_aum", 0) or 0)
    
    npa_summary = {
        "total_npa_count": total_npa_count,
        "total_npa_amount": total_npa_amount,
        "npa_percentage": round((total_npa_amount / total_aum * 100), 2) if total_aum > 0 else 0,
        "gross_npa_ratio": round((total_npa_amount / total_aum * 100), 2) if total_aum > 0 else 0,
    }
    
    # ── Build Response ──
    result = {
        "as_of_date": as_of_date,
        "company": company or "All Companies",
        "portfolio_overview": {
            "total_loans": int(overview_data.get("total_loans", 0)),
            "active_loans": int(overview_data.get("active_loans", 0)),
            "unique_borrowers": int(overview_data.get("unique_borrowers", 0)),
            "total_sanctioned": float(overview_data.get("total_sanctioned", 0)),
            "total_aum": total_aum,
            "total_collected": float(overview_data.get("total_collected", 0)),
            "total_outstanding": float(overview_data.get("total_outstanding", 0)),
            "avg_interest_rate": round(float(overview_data.get("avg_interest_rate", 0)), 2),
            "currency": "INR",
        },
        "status_distribution": [
            {"status": s["status"], "count": int(s["count"]), "amount": float(s["total_amount"])}
            for s in status_data
        ],
        "loan_type_distribution": [
            {"loan_type": t["loan_type"], "count": int(t["count"]), 
             "amount": float(t["total_amount"]), "avg_rate": round(float(t["avg_rate"]), 2)}
            for t in type_data
        ],
        "dpd_analysis": {
            bucket_key: {
                "label": bucket["label"],
                "count": bucket["count"],
                "amount": bucket["amount"],
            }
            for bucket_key, bucket in dpd_buckets.items()
            if bucket["count"] > 0 or bucket_key == "0_days"
        },
        "npa_summary": npa_summary,
    }
    
    # Include top overdue loans if details requested
    if include_details and npa_loans:
        result["top_npa_loans"] = [
            {
                "loan": l["loan_name"],
                "borrower": l.get("applicant_name", ""),
                "amount": float(l.get("loan_amount", 0) or 0),
                "dpd_days": int(l.get("dpd_days", 0) or 0),
                "overdue_installments": int(l.get("overdue_installments", 0) or 0),
                "overdue_amount": float(l.get("overdue_amount", 0) or 0),
            }
            for l in npa_loans[:20]
        ]
    
    return json.dumps(result, default=str, ensure_ascii=False)
```

### Task 3.3: EMI Calculator Tool

**File:** `niv_ai/niv_core/tools/nbfc/emi_calculator.py` (NEW)

```python
"""
EMI Calculator Tool for NBFC operations.

Pure calculation — no database access needed.
Replaces: LLM trying to use run_python_code for EMI calculations.
"""
import json
import math


def calculate_emi(
    principal: float,
    annual_rate: float,
    tenure_months: int,
    method: str = "flat",
    start_date: str = None,
) -> str:
    """Calculate EMI, total interest, and generate amortization schedule.
    
    Args:
        principal: Loan principal amount in INR.
        annual_rate: Annual interest rate as percentage (e.g., 12.5 for 12.5%).
        tenure_months: Loan tenure in months.
        method: 'flat' for flat rate, 'reducing' for reducing balance. Default: flat.
        start_date: Optional start date (YYYY-MM-DD) for amortization schedule.
    
    Returns:
        JSON with EMI amount, total interest, total payment, and amortization schedule.
    """
    if principal <= 0:
        return json.dumps({"error": "Principal must be greater than 0"})
    if annual_rate < 0:
        return json.dumps({"error": "Interest rate cannot be negative"})
    if tenure_months <= 0:
        return json.dumps({"error": "Tenure must be greater than 0 months"})
    
    monthly_rate = annual_rate / 12 / 100
    
    if method == "reducing":
        # Reducing Balance EMI: P * r * (1+r)^n / ((1+r)^n - 1)
        if monthly_rate == 0:
            emi = principal / tenure_months
        else:
            emi = principal * monthly_rate * math.pow(1 + monthly_rate, tenure_months) / \
                  (math.pow(1 + monthly_rate, tenure_months) - 1)
        
        total_payment = emi * tenure_months
        total_interest = total_payment - principal
        
        # Generate amortization schedule
        schedule = []
        balance = principal
        for month in range(1, tenure_months + 1):
            interest_component = balance * monthly_rate
            principal_component = emi - interest_component
            balance = max(0, balance - principal_component)
            
            schedule.append({
                "month": month,
                "emi": round(emi, 2),
                "principal": round(principal_component, 2),
                "interest": round(interest_component, 2),
                "balance": round(balance, 2),
            })
    
    else:  # flat rate
        total_interest = principal * (annual_rate / 100) * (tenure_months / 12)
        total_payment = principal + total_interest
        emi = total_payment / tenure_months
        
        # Flat rate schedule (equal principal, decreasing interest)
        schedule = []
        principal_per_month = principal / tenure_months
        interest_per_month = total_interest / tenure_months
        balance = principal
        
        for month in range(1, tenure_months + 1):
            balance -= principal_per_month
            schedule.append({
                "month": month,
                "emi": round(emi, 2),
                "principal": round(principal_per_month, 2),
                "interest": round(interest_per_month, 2),
                "balance": round(max(0, balance), 2),
            })
    
    # Only show first 12 + last 3 months in schedule (to keep response small)
    if len(schedule) > 15:
        display_schedule = schedule[:12] + [{"month": "...", "note": f"Months 13-{tenure_months-3} omitted"}] + schedule[-3:]
    else:
        display_schedule = schedule
    
    result = {
        "loan_details": {
            "principal": principal,
            "annual_rate_percent": annual_rate,
            "tenure_months": tenure_months,
            "method": method,
            "currency": "INR",
        },
        "calculations": {
            "emi_amount": round(emi, 2),
            "total_interest": round(total_interest, 2),
            "total_payment": round(total_payment, 2),
            "effective_rate": round((total_interest / principal) * 100, 2),
        },
        "amortization_schedule": display_schedule,
    }
    
    return json.dumps(result, default=str, ensure_ascii=False)
```

### Task 3.4: Register NBFC Tools via Hooks

**File:** `niv_ai/niv_ai/hooks.py`
**What:** Register NBFC tools so FAC discovers them
**Where:** Add `assistant_tools` hook

Add this to hooks.py:

```python
# MCP Tools — registered with FAC via assistant_tools hook
assistant_tools = [
    "niv_ai.niv_core.tools.nbfc.register_tools"
]
```

**File:** `niv_ai/niv_core/tools/nbfc/__init__.py` — Update:

```python
"""
NBFC-specific compound tools for Niv AI.
"""


def register_tools():
    """Register NBFC tools with FAC. Called by assistant_tools hook."""
    from niv_ai.niv_core.tools.nbfc.loan_summary import nbfc_loan_summary
    from niv_ai.niv_core.tools.nbfc.emi_calculator import calculate_emi
    
    return [
        {
            "name": "nbfc_loan_summary",
            "description": (
                "Get comprehensive NBFC loan portfolio summary with NPA classification, "
                "DPD buckets, status distribution, and key metrics.\n\n"
                "USE THIS WHEN:\n"
                "- 'What is our loan book status?' or 'Portfolio overview'\n"
                "- 'How many NPAs do we have?' or 'NPA summary'\n"
                "- 'What is the collection efficiency?'\n"
                "- Any question about overall lending portfolio health\n\n"
                "Returns: Portfolio overview, status distribution, loan type distribution, "
                "DPD analysis, and NPA summary — all in one call.\n\n"
                "NOTE: For individual loan details, use get_document('Loan', loan_name) instead."
            ),
            "function": nbfc_loan_summary,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name to filter by. Leave empty for all companies.",
                    },
                    "as_of_date": {
                        "type": "string",
                        "description": "Report date in YYYY-MM-DD format. Default: today.",
                    },
                    "include_details": {
                        "type": "boolean",
                        "description": "If true, include individual NPA loan records. Default: false.",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
        {
            "name": "calculate_emi",
            "description": (
                "Calculate EMI (Equated Monthly Installment), total interest, total payment, "
                "and generate amortization schedule for a loan.\n\n"
                "USE THIS WHEN:\n"
                "- User asks 'What will be the EMI for X loan?'\n"
                "- Loan comparison calculations\n"
                "- Amortization schedule generation\n\n"
                "Supports: Flat rate and Reducing balance methods.\n"
                "NO database access needed — pure calculation."
            ),
            "function": calculate_emi,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "principal": {
                        "type": "number",
                        "description": "Loan principal amount in INR (e.g., 500000 for 5 lakh).",
                    },
                    "annual_rate": {
                        "type": "number",
                        "description": "Annual interest rate as percentage (e.g., 12.5 for 12.5%).",
                    },
                    "tenure_months": {
                        "type": "integer",
                        "description": "Loan tenure in months (e.g., 36 for 3 years).",
                    },
                    "method": {
                        "type": "string",
                        "description": "Calculation method: 'flat' or 'reducing'. Default: 'flat'.",
                        "enum": ["flat", "reducing"],
                        "default": "flat",
                    },
                },
                "required": ["principal", "annual_rate", "tenure_months"],
            },
        },
    ]
```

> **⚠️ IMPORTANT:** The `register_tools()` hook format depends on FAC's `assistant_tools` implementation.
> If FAC expects `BaseTool` subclasses instead of dicts, these will need to be adapted.
> Check FAC's `plugin_manager.py` for the exact format it expects from hooks.

---

## Phase 4: Architecture Improvements (Week 3-4) 🟢 MEDIUM

### Task 4.1: Add Per-User Rate Limiting on Tool Calls

**File:** `niv_ai/niv_core/langchain/tools.py`
**What:** Limit tool calls per user per minute
**Where:** In `_make_mcp_executor()`, before executing

```python
# Add at top of tools.py
_RATE_LIMIT_WINDOW = 60  # 1 minute
_RATE_LIMIT_MAX_CALLS = 50  # max 50 tool calls per minute per user


def _check_tool_rate_limit() -> str:
    """Check per-user tool call rate limit. Returns error message or None."""
    try:
        user = frappe.session.user
        key = f"niv_tool_rate:{user}"
        count = frappe.cache().get_value(key)
        
        if count is None:
            frappe.cache().set_value(key, 1, expires_in_sec=_RATE_LIMIT_WINDOW)
            return None
        
        count = int(count)
        if count >= _RATE_LIMIT_MAX_CALLS:
            return (
                f"Rate limit exceeded: {count} tool calls in the last minute. "
                "Please wait before making more requests."
            )
        
        frappe.cache().set_value(key, count + 1, expires_in_sec=_RATE_LIMIT_WINDOW)
        return None
    except Exception:
        return None  # Don't block on rate limit errors
```

Add to `_make_mcp_executor()` execute(), at the top after clean_args:

```python
        # ── Rate limit check ──
        rate_error = _check_tool_rate_limit()
        if rate_error:
            return json.dumps({"error": rate_error})
```

---

### Task 4.2: Add Cache Warming on Startup

**File:** `niv_ai/niv_ai/hooks.py`
**What:** Pre-load tool cache on worker start
**Where:** Add `after_migrate` hook

```python
after_migrate = ["niv_ai.niv_core.mcp_client.warm_cache"]
```

**File:** `niv_ai/niv_core/mcp_client.py`
**What:** Add warm_cache function

Add at the bottom of the file:

```python
def warm_cache():
    """Pre-load tool cache. Called by after_migrate hook."""
    try:
        tools = get_all_mcp_tools_cached()
        frappe.logger().info(f"Niv MCP: Cache warmed with {len(tools)} tools")
    except Exception as e:
        frappe.logger().warning(f"Niv MCP: Cache warming failed: {e}")
```

---

### Task 4.3: Sanitize Tool Error Messages

**File:** `niv_ai/niv_core/langchain/tools.py`
**What:** Remove internal details (SQL, tracebacks) from tool errors shown to LLM
**Where:** New function + integrate in _make_mcp_executor

```python
def _sanitize_tool_error(error_str: str) -> str:
    """Remove internal details from tool errors before passing to LLM.
    
    Strips: SQL queries, file paths, Python tracebacks, internal module names.
    Keeps: The core error message that helps the LLM correct its approach.
    """
    import re
    
    sanitized = error_str
    
    # Remove file paths
    sanitized = re.sub(r'File ".*?"', 'File "..."', sanitized)
    
    # Remove line numbers from tracebacks
    sanitized = re.sub(r', line \d+', '', sanitized)
    
    # Remove SQL query bodies (keep just "SQL query failed")
    if "mariadb" in sanitized.lower() or "mysql" in sanitized.lower():
        sanitized = re.sub(r'SELECT.*?(?:FROM|$)', '[SQL query]', sanitized, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove Python module paths
    sanitized = re.sub(r'[\w.]+\.py', '...', sanitized)
    
    # Remove Traceback blocks
    if "Traceback" in sanitized:
        # Keep only the last line (the actual error)
        lines = sanitized.strip().split('\n')
        # Find the last meaningful error line
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith(('Traceback', 'File', 'at ', '  ')):
                sanitized = line
                break
    
    # Limit length
    if len(sanitized) > 500:
        sanitized = sanitized[:500] + "..."
    
    return sanitized
```

Use in the except block of `_make_mcp_executor()`:

```python
        except Exception as e:
            frappe.log_error(f"MCP tool '{tool_name}' failed: {e}", "Niv AI MCP")
            _record_tool_failure(tool_name, clean_args)
            err_str = _sanitize_tool_error(str(e))
            hint = _get_recovery_hint(tool_name, clean_args, str(e))  # Use raw error for hint matching
            return json.dumps({
                "error": f"Tool '{tool_name}' failed: {err_str}",
                "recovery_hint": hint,
            })
```

---

## Phase 5: Advanced (Month 2+) 🟢 NICE TO HAVE

### Task 5.1: Tool Usage Analytics (Track What Works)

**File:** `niv_ai/niv_core/tools/analytics.py` (NEW)
**What:** Log tool calls, success/failure, duration for optimization
**Priority:** Low — implement after Phase 1-4 are stable

### Task 5.2: Parallel Tool Execution

**What:** Allow LangGraph to call multiple independent tools in parallel
**Requires:** LangGraph configuration change + tool dependency analysis
**Priority:** Low

### Task 5.3: Tool Streaming for Long Operations

**What:** Stream progress for generate_report and run_database_query
**Requires:** MCP protocol streaming support
**Priority:** Low

---

## Implementation Order (Recommended)

```
Day 1:  Task 1.1 → 1.2 → 1.3 → 1.4 → 1.5  (Tool descriptions + system prompt)
Day 2:  Task 2.1 → 2.2                       (Result summarizer)
Day 3:  Task 2.3 → 2.4 → 2.5                (Failure detection + router + cache)
Day 4:  Task 3.1 → 3.2 → 3.3 → 3.4          (NBFC tools)
Day 5:  Task 4.1 → 4.2 → 4.3                (Rate limit + cache warm + error sanitize)
Day 6:  Testing on production server
```

## Expected Stability Improvements

| Metric | Before | After Phase 1-2 | After All |
|--------|--------|-----------------|-----------|
| Avg tool calls per query | 3-5 | 1-3 | 1-2 |
| Wrong tool selection rate | ~30% | ~10% | ~5% |
| Context window waste | High (50KB+) | Low (<4KB) | Minimal |
| Token cost per query | ₹₹₹ | ₹₹ | ₹ |
| NBFC query accuracy | ~60% | ~75% | ~90% |
| Retry loops (same error) | Common | Rare | None |

---

*Plan created by Roma 🔧 — 2026-02-18*
