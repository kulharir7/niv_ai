"""
Hybrid AI Dashboard API.
- get_bi_data: Instant SQL data (fast)
- start_ai_refresh: Background AI agent fetches + analyzes (slow but smart)
- poll_ai_result: Frontend polls for AI result
"""
import json
import frappe


@frappe.whitelist()
def get_bi_data(period="this_year"):
    """FAST — Direct SQL queries for instant dashboard load."""
    from datetime import datetime, date, timedelta
    
    data = {}
    today = date.today()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    year_start = date(today.year, 1, 1).strftime("%Y-%m-%d")
    
    # Financial
    try:
        gl = frappe.db.sql(
            "SELECT IFNULL(SUM(credit),0) income, IFNULL(SUM(debit),0) expense "
            "FROM `tabGL Entry` WHERE is_cancelled=0 AND posting_date >= %s", year_start, as_dict=True)
        if gl:
            inc, exp = float(gl[0].income), float(gl[0].expense)
            data["financial"] = {"income": inc, "expense": exp, "profit": inc - exp, "margin_pct": round(((inc-exp)/inc*100) if inc else 0, 1)}
    except: pass
    
    # Loan Summary
    try:
        l = frappe.db.sql(
            "SELECT COUNT(*) total, IFNULL(SUM(loan_amount),0) sanctioned, "
            "IFNULL(SUM(disbursed_amount),0) disbursed, IFNULL(SUM(total_amount_paid),0) collected, "
            "SUM(CASE WHEN status IN ('Disbursed','Partially Disbursed') THEN 1 ELSE 0 END) active, "
            "SUM(CASE WHEN status='Loan Closure Requested' THEN 1 ELSE 0 END) closure "
            "FROM tabLoan WHERE docstatus=1", as_dict=True)
        if l:
            data["loan_summary"] = {k: float(v) if isinstance(v, (int, float)) else int(v or 0) for k, v in l[0].items()}
    except: pass
    
    # Loan Status
    try:
        data["loan_status"] = [{"status": r.status, "count": r.cnt, "amount": float(r.amt)} 
            for r in frappe.db.sql("SELECT status, COUNT(*) cnt, IFNULL(SUM(loan_amount),0) amt FROM tabLoan WHERE docstatus=1 GROUP BY status ORDER BY cnt DESC", as_dict=True)]
    except: data["loan_status"] = []
    
    # Disbursement Trend
    try:
        data["disbursement_trend"] = [{"month": r.month, "count": r.cnt, "amount": float(r.amt)}
            for r in frappe.db.sql(
                "SELECT DATE_FORMAT(disbursement_date, '%b %y') month, COUNT(*) cnt, IFNULL(SUM(disbursed_amount),0) amt "
                "FROM `tabLoan Disbursement` WHERE docstatus=1 AND disbursement_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH) "
                "GROUP BY month, DATE_FORMAT(disbursement_date, '%Y-%m') ORDER BY DATE_FORMAT(disbursement_date, '%Y-%m')", as_dict=True)]
    except: data["disbursement_trend"] = []
    
    # Pending Approvals
    try:
        data["pending_approvals"] = [{"doctype": r.dt, "count": r.cnt}
            for r in frappe.db.sql("SELECT reference_doctype dt, COUNT(*) cnt FROM `tabWorkflow Action` WHERE status='Open' GROUP BY dt ORDER BY cnt DESC LIMIT 8", as_dict=True)]
    except: data["pending_approvals"] = []
    
    # Team Activity
    try:
        data["team_activity"] = [{"user": r.user, "count": int(r.cnt)}
            for r in frappe.db.sql(
                "SELECT user, SUM(cnt) cnt FROM ("
                "SELECT owner user, COUNT(*) cnt FROM tabVersion WHERE creation >= DATE_SUB(NOW(), INTERVAL 24 HOUR) AND owner IS NOT NULL GROUP BY owner "
                "UNION ALL SELECT owner user, COUNT(*) cnt FROM `tabActivity Log` WHERE creation >= DATE_SUB(NOW(), INTERVAL 24 HOUR) AND owner IS NOT NULL GROUP BY owner"
                ") t WHERE user NOT IN ('Guest','') GROUP BY user ORDER BY cnt DESC LIMIT 8", as_dict=True)]
    except: data["team_activity"] = []
    
    # Collection Today
    try:
        today_str = today.strftime("%Y-%m-%d")
        tc = frappe.db.sql("SELECT IFNULL(SUM(amount_paid),0) amt FROM `tabLoan Repayment` WHERE docstatus=1 AND posting_date=%s", today_str)
        avg = frappe.db.sql("SELECT IFNULL(AVG(d),0) avg_d FROM (SELECT SUM(amount_paid) d FROM `tabLoan Repayment` WHERE docstatus=1 AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) GROUP BY posting_date) t")
        data["collection_today"] = {"today": float(tc[0][0] if tc else 0), "avg_daily": float(avg[0][0] if avg else 0)}
    except: data["collection_today"] = {}
    
    # NPA Warning
    try:
        data["npa_warning"] = [{"loan": r.name, "applicant": r.applicant or "", "amount": float(r.loan_amount), "paid_pct": round(float(r.total_amount_paid or 0) / float(r.total_payment) * 100, 1) if r.total_payment else 0}
            for r in frappe.db.sql("SELECT name, applicant, loan_amount, total_amount_paid, total_payment FROM tabLoan WHERE docstatus=1 AND status='Disbursed' AND total_payment > 0 AND (total_amount_paid / total_payment) < 0.5 ORDER BY (total_payment - total_amount_paid) DESC LIMIT 5", as_dict=True)]
    except: data["npa_warning"] = []
    
    # Branch Performance
    try:
        data["branch_performance"] = [{"branch": r.branch or "Unassigned", "loans": r.cnt, "disbursed": float(r.disb), "collected": float(r.coll)}
            for r in frappe.db.sql("SELECT IFNULL(branch,'Unassigned') branch, COUNT(*) cnt, IFNULL(SUM(disbursed_amount),0) disb, IFNULL(SUM(total_amount_paid),0) coll FROM tabLoan WHERE docstatus=1 GROUP BY branch ORDER BY disb DESC LIMIT 10", as_dict=True)]
    except: data["branch_performance"] = []
    
    return data


@frappe.whitelist()
def start_ai_refresh(period="this_year"):
    """Start background AI agent to fetch + analyze data."""
    job_key = f"ai_dash_{frappe.session.user}_{period}"
    running_key = f"ai_dash_running_{frappe.session.user}"
    
    if frappe.cache().get_value(running_key):
        return {"status": "already_running"}
    
    frappe.cache().set_value(running_key, "1", expires_in_sec=300)
    frappe.enqueue(
        _run_ai_analysis,
        queue="long",
        job_key=job_key,
        running_key=running_key,
        period=period,
        user=frappe.session.user
    )
    return {"status": "started"}


@frappe.whitelist()
def poll_ai_result(period="this_year"):
    """Poll for AI analysis result."""
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
def clear_ai_cache(period="this_year"):
    """Clear AI cache."""
    frappe.cache().delete_value(f"ai_dash_{frappe.session.user}_{period}")
    frappe.cache().delete_value(f"ai_dash_running_{frappe.session.user}")
    return {"status": "cleared"}


def _run_ai_analysis(job_key, running_key, period, user):
    """Background: AI agent queries + analyzes."""
    import re
    frappe.set_user(user)
    
    prompt = f"""Analyze business data for period: {period}. Use run_database_query tool.

Query these and return JSON:
1. "financial" - GL Entry income/expense totals
2. "loan_summary" - Total loans, sanctioned, disbursed, collected, active count
3. "loan_status" - [{{"status", "count", "amount"}}] GROUP BY status
4. "disbursement_trend" - [{{"month", "count", "amount"}}] last 12 months
5. "predictions" - Based on data: {{"revenue_trend": "up/down/stable", "insights": ["insight1", "insight2", ...]}}
6. "npa_warning" - Risky loans where paid < 50%
7. "collection_today" - Today + weekly + avg daily collections
8. "branch_performance" - [{{"branch", "loans", "disbursed", "collected"}}]

Return ONLY valid JSON."""

    try:
        from niv_ai.niv_core.api.chat import send_message
        response = send_message(
            conversation_id=f"ai-dashboard-{period}",
            message=prompt,
        )
        response_text = response if isinstance(response, str) else str(response)
        
        result = {"source": "ai", "period": period, "raw": response_text, "status": "text"}
        if response_text:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    result["data"] = json.loads(json_match.group())
                    result["status"] = "ok"
                except: pass
        
        frappe.cache().set_value(job_key, json.dumps(result), expires_in_sec=300)
    except Exception as e:
        frappe.log_error(f"AI Dashboard error: {e}")
        frappe.cache().set_value(job_key, json.dumps({"status": "error", "raw": str(e)}), expires_in_sec=60)
    finally:
        frappe.cache().delete_value(running_key)


@frappe.whitelist()
def get_ai_analysis():
    """Quick AI analysis."""
    from niv_ai.niv_core.api.chat import send_message
    try:
        r = send_message(conversation_id="ai-analysis", message="Give 5 business insights by querying the database.")
        return {"analysis": r}
    except Exception as e:
        return {"analysis": str(e)}
