"""
AI-First Business Dashboard API.
Uses background job to avoid HTTP timeout.
"""
import json
import frappe


@frappe.whitelist()
def get_bi_data(period="this_year"):
    """Start AI dashboard job and return job ID."""
    job_key = f"ai_dash_{frappe.session.user}_{period}"
    
    # Check if result already cached
    cached = frappe.cache().get_value(job_key)
    if cached:
        return {"status": "ready", "data": json.loads(cached) if isinstance(cached, str) else cached}
    
    # Check if job is already running
    running_key = f"ai_dash_running_{frappe.session.user}"
    if frappe.cache().get_value(running_key):
        return {"status": "processing"}
    
    # Start background job
    frappe.cache().set_value(running_key, "1", expires_in_sec=300)
    frappe.enqueue(
        _run_ai_dashboard,
        queue="long",
        job_key=job_key,
        running_key=running_key,
        period=period,
        user=frappe.session.user,
        now=frappe.conf.developer_mode  # Run immediately in dev mode
    )
    
    return {"status": "started"}


@frappe.whitelist()
def poll_bi_data(period="this_year"):
    """Poll for AI dashboard result."""
    job_key = f"ai_dash_{frappe.session.user}_{period}"
    
    cached = frappe.cache().get_value(job_key)
    if cached:
        data = json.loads(cached) if isinstance(cached, str) else cached
        return {"status": "ready", "data": data}
    
    running_key = f"ai_dash_running_{frappe.session.user}"
    if frappe.cache().get_value(running_key):
        return {"status": "processing"}
    
    return {"status": "not_started"}


@frappe.whitelist()
def clear_bi_cache(period="this_year"):
    """Clear cached dashboard data to force refresh."""
    job_key = f"ai_dash_{frappe.session.user}_{period}"
    frappe.cache().delete_value(job_key)
    running_key = f"ai_dash_running_{frappe.session.user}"
    frappe.cache().delete_value(running_key)
    return {"status": "cleared"}


def _run_ai_dashboard(job_key, running_key, period, user):
    """Background job — runs AI agent to fetch dashboard data."""
    import re
    
    frappe.set_user(user)
    
    prompt = f"""You are a business data analyst. I need a complete business dashboard for period: {period}.

Use the run_database_query tool to execute SQL queries. Return a single JSON object.

IMPORTANT RULES:
- Use Frappe table names: tabLoan, `tabSales Invoice`, `tabGL Entry`, `tabLoan Disbursement`, `tabLoan Repayment`, `tabWorkflow Action`, tabVersion
- Execute each query separately using the tool
- Return ONLY valid JSON at the end. No markdown.

Get this data:

1. "financial": {{income: total GL credit, expense: total GL debit, profit, margin_pct}}
2. "loan_summary": {{total_loans, total_sanctioned, total_disbursed, total_collected, active_loans, closure_requested}}
3. "loan_status": [{{status, count, amount}}] from tabLoan GROUP BY status
4. "disbursement_trend": [{{month, count, amount}}] monthly from Loan Disbursement last 12 months
5. "pending_approvals": [{{doctype, count}}] from Workflow Action WHERE status=Open
6. "team_activity": [{{user, count}}] from tabVersion last 24h
7. "collection_today": {{today_amount, week_amount, avg_daily}}
8. "npa_warning": [{{loan, applicant, amount, paid_pct}}] risky loans (paid < 50%)
9. "predictions": {{insights: ["insight1", "insight2", ...]}} based on data patterns
10. "branch_performance": [{{branch, loans, disbursed, collected}}]

Return ONLY the JSON object."""

    try:
        from niv_ai.niv_core.langchain.agent import run_agent
        
        response = run_agent(
            message=prompt,
            conversation_id=f"ai-dashboard-{period}-{user}",
            user=user,
            system_prompt="You are a data analyst. Use run_database_query tool. Return clean JSON only."
        )
        
        result = {"source": "ai", "period": period, "raw": response}
        
        if response:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    result["data"] = parsed
                    result["status"] = "ok"
                except:
                    result["status"] = "text"
            else:
                result["status"] = "text"
        else:
            result["status"] = "empty"
        
        # Cache result for 5 minutes
        frappe.cache().set_value(job_key, json.dumps(result), expires_in_sec=300)
    
    except Exception as e:
        frappe.log_error(f"AI Dashboard job error: {e}")
        frappe.cache().set_value(job_key, json.dumps({
            "source": "error", "status": "error", "raw": str(e)
        }), expires_in_sec=60)
    
    finally:
        frappe.cache().delete_value(running_key)


@frappe.whitelist()
def get_ai_analysis():
    """Quick AI analysis."""
    from niv_ai.niv_core.langchain.agent import run_agent
    try:
        response = run_agent(
            message="Give me 5 key business insights by querying the database.",
            conversation_id="ai-analysis-quick",
            user=frappe.session.user,
        )
        return {"analysis": response}
    except Exception as e:
        return {"analysis": f"Failed: {e}"}
