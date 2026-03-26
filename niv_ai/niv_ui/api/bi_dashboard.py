"""
AI-First Business Dashboard API.
All data comes from AI agent using MCP tools.
No hardcoded SQL — AI decides what to query.
"""
import json
import frappe


@frappe.whitelist()
def get_bi_data(period="this_year"):
    """Get ALL dashboard data via AI agent."""
    from niv_ai.niv_core.langchain.agent import run_agent
    
    prompt = f"""You are a business data analyst. I need a complete business dashboard for period: {period}.

Use the run_database_query tool to execute SQL queries and gather ALL this data. Return a single JSON object.

IMPORTANT: 
- Use proper SQL with correct Frappe table names (e.g. tabLoan, `tabSales Invoice`, `tabGL Entry`)
- For period "{period}", calculate appropriate date ranges
- Execute MULTIPLE tool calls to gather all sections

Sections needed:

1. "financial" - Query GL Entry for:
   - total income (SUM credit) and expense (SUM debit) for the period
   - Calculate profit and margin

2. "loan_summary" - Query tabLoan:
   - total_loans, total_sanctioned (SUM loan_amount), total_disbursed (SUM disbursed_amount)
   - active_loans (status IN Disbursed, Partially Disbursed), closed, closure_requested counts
   - total_collected (SUM total_amount_paid)

3. "loan_status" - Query tabLoan GROUP BY status:
   - Each status with count and total amount

4. "disbursement_trend" - Query `tabLoan Disbursement`:
   - Monthly count and SUM(disbursed_amount) for last 12 months

5. "branch_performance" - Query tabLoan GROUP BY branch:
   - Each branch with loan count, disbursed amount, collected amount

6. "pending_approvals" - Query `tabWorkflow Action` WHERE status='Open':
   - COUNT by reference_doctype

7. "team_activity" - Query tabVersion for last 24 hours:
   - User activity counts

8. "receivables" - Query `tabSales Invoice` WHERE outstanding_amount > 0:
   - Ageing buckets: 0-30 days, 31-60, 61-90, 90+ days amounts

9. "collection_today" - Query `tabLoan Repayment`:
   - Today's total collections
   - This week's collections
   - Average daily collection (last 30 days)

10. "npa_warning" - Query tabLoan WHERE status='Disbursed':
    - Loans where total_amount_paid < 50% of total_payment (risky loans)
    - Top 5 by outstanding amount

11. "predictions" - Based on the data you gathered:
    - Predict next 3 months revenue trend (increase/decrease/stable)
    - Identify seasonal patterns
    - Give 3-5 key business insights as text

12. "top_doctypes" - Most used document types by record count

Return ONLY valid JSON. No markdown. No explanation. Just the JSON object with all 12 keys above."""

    try:
        response = run_agent(
            message=prompt,
            conversation_id="ai-dashboard-" + (period or "default"),
            user=frappe.session.user,
            system_prompt="You are a data analyst AI. Use run_database_query tool to fetch real data from the database. Execute multiple queries. Return results as clean JSON only. No markdown formatting."
        )
        
        # Parse JSON from response
        import re
        if response:
            # Try to find JSON block
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return {"source": "ai", "status": "ok", "data": data, "period": period}
                except json.JSONDecodeError:
                    pass
            
            # If no valid JSON, return raw text
            return {"source": "ai", "status": "text", "data": None, "raw": response, "period": period}
        
        return {"source": "ai", "status": "empty", "data": None, "raw": "No response from AI", "period": period}
    
    except Exception as e:
        frappe.log_error(f"AI Dashboard error: {e}")
        return {"source": "error", "status": "error", "data": None, "raw": str(e), "period": period}


@frappe.whitelist()
def get_ai_analysis():
    """Quick AI analysis of current business state."""
    from niv_ai.niv_core.langchain.agent import run_agent
    
    try:
        response = run_agent(
            message="Give me a quick 5-point business health analysis. Query key metrics from database using tools, then provide insights in bullet points.",
            conversation_id="ai-analysis-quick",
            user=frappe.session.user,
        )
        return {"analysis": response}
    except Exception as e:
        return {"analysis": f"Analysis failed: {e}"}
