# Niv AI — Tool Accuracy Benchmark
# File: niv_ai/niv_core/tests/tool_benchmark.py
#
# Run: bench --site <site> execute niv_ai.niv_core.tests.tool_benchmark.run_benchmark
# Or:  bench --site <site> execute niv_ai.niv_core.tests.tool_benchmark.run_benchmark --kwargs '{"verbose": true}'

import frappe
import json
import time
from datetime import datetime


# ─── Benchmark Test Cases ──────────────────────────────────────────
# Each case: (query, expected_tools, category)
# expected_tools: list of tool names that SHOULD be called
# If any expected tool is in actual tools called, it's a PASS

BENCHMARK_CASES = [
    # ── Category: Document Listing ──
    ("Show all Sales Orders", ["list_documents"], "listing"),
    ("List overdue loans", ["list_documents", "run_database_query"], "listing"),
    ("Show customers from Mumbai", ["list_documents"], "listing"),
    ("Show all pending Purchase Orders", ["list_documents"], "listing"),
    ("List employees in HR department", ["list_documents"], "listing"),
    ("Show invoices from last month", ["list_documents", "run_database_query"], "listing"),
    ("Show all active loan applications", ["list_documents"], "listing"),

    # ── Category: Document Retrieval ──
    ("Get details of Sales Order SO-00001", ["get_document"], "retrieval"),
    ("Show me customer C-001", ["get_document"], "retrieval"),
    ("What are the details of Invoice INV-001", ["get_document"], "retrieval"),
    ("Open Loan LOAN-0001", ["get_document"], "retrieval"),

    # ── Category: Search ──
    ("Find documents about laptop", ["search_documents"], "search"),
    ("Search for customer Rajesh", ["search_documents", "list_documents"], "search"),
    ("What DocType stores loan data", ["search_doctype"], "search"),
    ("Find the DocType for sales", ["search_doctype"], "search"),
    ("Search for item Mobile Phone", ["search_documents", "search_link"], "search"),

    # ── Category: Database Queries ──
    ("Total sales this month", ["run_database_query", "analyze_business_data"], "analytics"),
    ("Average loan amount", ["run_database_query", "analyze_business_data"], "analytics"),
    ("Count of overdue loans by branch", ["run_database_query", "analyze_business_data"], "analytics"),
    ("Sum of all pending invoices", ["run_database_query", "analyze_business_data"], "analytics"),
    ("Top 10 customers by revenue", ["run_database_query", "analyze_business_data"], "analytics"),
    ("Monthly sales trend", ["run_database_query", "analyze_business_data"], "analytics"),
    ("NPA percentage", ["run_database_query", "analyze_business_data"], "analytics"),
    ("Collection efficiency this month", ["run_database_query", "analyze_business_data"], "analytics"),
    ("PAR 30 report", ["run_database_query", "analyze_business_data"], "analytics"),
    ("WRR of loan portfolio", ["run_database_query", "analyze_business_data"], "analytics"),

    # ── Category: Document Creation ──
    ("Create a new customer named Test Corp", ["create_document"], "creation"),
    ("Add a new task for follow up", ["create_document"], "creation"),
    ("Create a ToDo reminder for tomorrow", ["create_document"], "creation"),

    # ── Category: Document Update ──
    ("Update customer C-001 phone to 9876543210", ["update_document"], "update"),
    ("Mark task TASK-001 as completed", ["update_document"], "update"),
    ("Change status of SO-001 to Cancelled", ["update_document"], "update"),

    # ── Category: Schema / DocType Info ──
    ("What fields does Sales Order have", ["get_doctype_info"], "schema"),
    ("Show me the structure of Customer doctype", ["get_doctype_info"], "schema"),
    ("What are the fields in Loan", ["get_doctype_info"], "schema"),
    ("List all DocTypes in the system", ["search_doctype"], "schema"),

    # ── Category: Reports ──
    ("Show me the General Ledger report", ["generate_report", "report_list"], "reports"),
    ("Run Accounts Receivable report", ["generate_report"], "reports"),
    ("What reports are available", ["report_list"], "reports"),
    ("List all reports for loans", ["report_list"], "reports"),

    # ── Category: Visualization ──
    ("Show a chart of monthly sales", ["create_visualization", "run_database_query"], "visualization"),
    ("Create a pie chart of customers by city", ["create_visualization", "run_database_query"], "visualization"),

    # ── Category: NBFC Specific ──
    ("Show loan disbursement summary", ["run_database_query", "analyze_business_data"], "nbfc"),
    ("EMI collection status today", ["run_database_query", "list_documents"], "nbfc"),
    ("Loan portfolio quality report", ["run_database_query", "analyze_business_data"], "nbfc"),
    ("Show all NPA loans", ["list_documents", "run_database_query"], "nbfc"),
    ("Branch wise collection report", ["run_database_query", "analyze_business_data"], "nbfc"),

    # ── Category: General / No Tools ──
    ("Hello", [], "general"),
    ("What is ERPNext", [], "general"),
    ("Thank you", [], "general"),
]


def _get_tool_selection(query):
    """Use the fast model to get tool selections for a query (no execution)."""
    from niv_ai.niv_core.langchain.agent import _get_fast_model, _build_system_prompt
    from niv_ai.niv_core.langchain.tools import get_langchain_tools
    from niv_ai.niv_core.langchain.llm import get_llm

    tools = get_langchain_tools()
    fast_model = _get_fast_model()

    # get_llm with defaults handles provider resolution
    llm = get_llm(model=fast_model, streaming=False)
    llm_with_tools = llm.bind_tools(tools)

    system_prompt = _build_system_prompt(None)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    try:
        response = llm_with_tools.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None) or []
        return [tc.get("name", "") for tc in tool_calls]
    except Exception as e:
        return [f"ERROR: {e}"]


def run_benchmark(verbose=False):
    """Run tool accuracy benchmark.
    
    Args:
        verbose: If True, print each test case result
    
    Returns dict with results summary.
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "total": len(BENCHMARK_CASES),
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "accuracy": 0,
        "by_category": {},
        "failures": [],
        "duration_seconds": 0,
    }

    start_time = time.time()

    for i, (query, expected_tools, category) in enumerate(BENCHMARK_CASES):
        if category not in results["by_category"]:
            results["by_category"][category] = {"total": 0, "passed": 0}
        results["by_category"][category]["total"] += 1

        try:
            actual_tools = _get_tool_selection(query)

            # Check if any error
            if actual_tools and actual_tools[0].startswith("ERROR:"):
                results["errors"] += 1
                if verbose:
                    print(f"  [{i+1}/{len(BENCHMARK_CASES)}] ⚠️  {query}")
                    print(f"     Error: {actual_tools[0]}")
                continue

            # Determine pass/fail
            if not expected_tools:
                # Expected no tools — pass if no tools called
                passed = len(actual_tools) == 0
            else:
                # Pass if ANY expected tool was selected
                passed = any(t in expected_tools for t in actual_tools)

            if passed:
                results["passed"] += 1
                results["by_category"][category]["passed"] += 1
                if verbose:
                    print(f"  [{i+1}/{len(BENCHMARK_CASES)}] ✅ {query}")
                    if actual_tools:
                        print(f"     Tools: {', '.join(actual_tools)}")
            else:
                results["failed"] += 1
                failure = {
                    "query": query,
                    "expected": expected_tools,
                    "actual": actual_tools,
                    "category": category,
                }
                results["failures"].append(failure)
                if verbose:
                    print(f"  [{i+1}/{len(BENCHMARK_CASES)}] ❌ {query}")
                    print(f"     Expected: {expected_tools}")
                    print(f"     Actual:   {actual_tools}")

        except Exception as e:
            results["errors"] += 1
            if verbose:
                print(f"  [{i+1}/{len(BENCHMARK_CASES)}] ⚠️  {query} — {e}")

    results["duration_seconds"] = round(time.time() - start_time, 2)
    total_valid = results["passed"] + results["failed"]
    results["accuracy"] = round((results["passed"] / total_valid * 100), 1) if total_valid > 0 else 0

    # Category accuracy
    for cat, data in results["by_category"].items():
        data["accuracy"] = round((data["passed"] / data["total"] * 100), 1) if data["total"] > 0 else 0

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Niv AI Tool Accuracy Benchmark")
    print(f"{'='*60}")
    print(f"  Total:    {results['total']}")
    print(f"  Passed:   {results['passed']} ✅")
    print(f"  Failed:   {results['failed']} ❌")
    print(f"  Errors:   {results['errors']} ⚠️")
    print(f"  Accuracy: {results['accuracy']}%")
    print(f"  Duration: {results['duration_seconds']}s")
    print(f"\n  By Category:")
    for cat, data in sorted(results["by_category"].items()):
        status = "✅" if data["accuracy"] >= 85 else "⚠️" if data["accuracy"] >= 70 else "❌"
        print(f"    {status} {cat}: {data['accuracy']}% ({data['passed']}/{data['total']})")
    print(f"{'='*60}")

    # Save results to file
    try:
        results_path = "/home/gws/frappe-bench/apps/niv_ai/benchmark_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Results saved to: {results_path}")
    except Exception:
        pass

    return results
