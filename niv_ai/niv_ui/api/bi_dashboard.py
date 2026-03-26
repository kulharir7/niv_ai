"""
AI Business Intelligence API — 100% Dynamic.
Auto-discovers financial DocTypes, amounts, dates.
Works on ANY Frappe site without hardcoding.
"""
import json
import frappe
from datetime import datetime, timedelta
from collections import defaultdict


# ═══════════════════════════════════════════
# SMART DISCOVERY — Find financial DocTypes
# ═══════════════════════════════════════════

_SKIP_MODULES = ("Core", "Email", "Printing", "Website", "Desk", "Custom",
                 "Integrations", "Data Migration", "Niv Core", "Niv Billing", "Niv UI")

_SKIP_DT = ("DocType", "DocField", "DocPerm", "Module Def", "Translation",
            "File", "Comment", "Activity Log", "Error Log", "Scheduled Job Log",
            "Session Default", "Navbar Item", "Block Module", "Has Role",
            "DefaultValue", "Version", "Communication", "Email Queue",
            "Prepared Report", "Dashboard Chart", "Number Card",
            "Niv Conversation", "Niv Message", "Niv AI Provider",
            "Niv Settings", "Niv MCP Server", "Niv Token Ledger",
            "Niv Billing Plan", "Niv Recharge")

# Common money field names across any Frappe app
_MONEY_FIELDS = ("grand_total", "total", "net_total", "amount", "paid_amount",
                 "outstanding_amount", "base_grand_total", "total_amount",
                 "loan_amount", "disbursement_amount", "sanctioned_amount",
                 "invoice_amount", "payment_amount", "base_total",
                 "rounded_total", "total_debit", "total_credit")

_INCOME_HINTS = ("sales", "invoice", "receipt", "income", "revenue", "collection",
                 "payment received", "disbursement", "recharge")
_EXPENSE_HINTS = ("purchase", "expense", "payment entry", "salary", "payroll",
                  "bill", "debit note", "repayment")
_CUSTOMER_HINTS = ("customer", "client", "member", "subscriber", "borrower",
                   "applicant", "lead", "contact", "patient", "student")
_STATUS_FIELDS = ("status", "docstatus", "workflow_state")


def _get_business_doctypes():
    """Discover all business-relevant DocTypes with their money/date fields."""
    cache_key = "niv_bi_doctypes"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    all_dts = frappe.get_all("DocType",
        filters={
            "istable": 0, "issingle": 0,
            "module": ("not in", _SKIP_MODULES),
            "name": ("not in", _SKIP_DT),
        },
        fields=["name", "module"],
        limit_page_length=300,
    )

    results = []
    for dt in all_dts:
        try:
            count = frappe.db.count(dt["name"])
            if count == 0:
                continue

            # Get fields
            fields = frappe.get_meta(dt["name"]).fields
            field_names = [f.fieldname for f in fields]
            field_map = {f.fieldname: f for f in fields}

            # Find money fields
            money = []
            for fn in _MONEY_FIELDS:
                if fn in field_names:
                    money.append(fn)
            # Also check Currency type fields
            for f in fields:
                if f.fieldtype == "Currency" and f.fieldname not in money:
                    money.append(f.fieldname)

            # Classify: income or expense?
            dt_lower = dt["name"].lower()
            category = "other"
            if any(h in dt_lower for h in _INCOME_HINTS):
                category = "income"
            elif any(h in dt_lower for h in _EXPENSE_HINTS):
                category = "expense"
            elif any(h in dt_lower for h in _CUSTOMER_HINTS):
                category = "customer"

            # Has status?
            status_field = None
            for sf in _STATUS_FIELDS:
                if sf in field_names:
                    status_field = sf
                    break

            # Has date?
            date_field = None
            for df in ("posting_date", "transaction_date", "date", "creation"):
                if df in field_names or df == "creation":
                    date_field = df
                    break

            results.append({
                "doctype": dt["name"],
                "module": dt["module"],
                "count": count,
                "money_fields": money,
                "category": category,
                "status_field": status_field,
                "date_field": date_field or "creation",
            })
        except Exception:
            pass

    results.sort(key=lambda x: x["count"], reverse=True)
    frappe.cache().set_value(cache_key, results, expires_in_sec=300)
    return results


# ═══════════════════════════════════════════
# FINANCIAL APIs
# ═══════════════════════════════════════════

@frappe.whitelist()
def get_bi_data():
    """Master BI endpoint."""
    return {
        "financial": get_financial_summary(),
        "trend": get_monthly_trend(),
        "top_doctypes": get_top_doctypes_smart(),
        "risk": get_risk_analysis(),
        "customers": get_customer_insights(),
        "recent": get_recent_high_value(),
        "status_breakdown": get_status_breakdown(),
        "system_info": get_system_info(),
        "loan_portfolio": _get_loan_portfolio(),
    }


@frappe.whitelist()
def get_financial_summary():
    """Auto-detect income/expense DocTypes and sum amounts."""
    dts = _get_business_doctypes()
    
    today = datetime.now()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    year_start = today.replace(month=1, day=1).strftime("%Y-%m-%d")
    
    income_month = 0
    income_year = 0
    expense_month = 0
    expense_year = 0
    income_sources = []
    expense_sources = []
    
    for dt in dts:
        if not dt["money_fields"]:
            continue
        mf = dt["money_fields"][0]  # primary money field
        df = dt["date_field"]
        
        try:
            if dt["category"] == "income":
                m_sum = frappe.db.sql(
                    f"SELECT COALESCE(SUM(`{mf}`), 0) FROM `tab{dt['doctype']}` WHERE `{df}` >= %s",
                    month_start
                )[0][0] or 0
                y_sum = frappe.db.sql(
                    f"SELECT COALESCE(SUM(`{mf}`), 0) FROM `tab{dt['doctype']}` WHERE `{df}` >= %s",
                    year_start
                )[0][0] or 0
                income_month += float(m_sum)
                income_year += float(y_sum)
                if float(y_sum) > 0:
                    income_sources.append({"name": dt["doctype"], "amount": float(y_sum), "field": mf})
                    
            elif dt["category"] == "expense":
                m_sum = frappe.db.sql(
                    f"SELECT COALESCE(SUM(`{mf}`), 0) FROM `tab{dt['doctype']}` WHERE `{df}` >= %s",
                    month_start
                )[0][0] or 0
                y_sum = frappe.db.sql(
                    f"SELECT COALESCE(SUM(`{mf}`), 0) FROM `tab{dt['doctype']}` WHERE `{df}` >= %s",
                    year_start
                )[0][0] or 0
                expense_month += float(m_sum)
                expense_year += float(y_sum)
                if float(y_sum) > 0:
                    expense_sources.append({"name": dt["doctype"], "amount": float(y_sum), "field": mf})
        except Exception:
            pass
    
    # Also try GL Entry if available (most accurate)
    try:
        gl_month = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(debit), 0) as total_debit,
                COALESCE(SUM(credit), 0) as total_credit
            FROM `tabGL Entry` WHERE posting_date >= %s AND is_cancelled = 0
        """, month_start, as_dict=True)
        if gl_month:
            if gl_month[0]["total_credit"] > income_month:
                income_month = float(gl_month[0]["total_credit"])
            if gl_month[0]["total_debit"] > expense_month:
                expense_month = float(gl_month[0]["total_debit"])
    except Exception:
        pass
    
    profit_month = income_month - expense_month
    profit_year = income_year - expense_year
    
    return {
        "income_month": income_month,
        "income_year": income_year,
        "expense_month": expense_month,
        "expense_year": expense_year,
        "profit_month": profit_month,
        "profit_year": profit_year,
        "margin_pct": round((profit_month / income_month * 100) if income_month > 0 else 0, 1),
        "income_sources": sorted(income_sources, key=lambda x: x["amount"], reverse=True)[:5],
        "expense_sources": sorted(expense_sources, key=lambda x: x["amount"], reverse=True)[:5],
    }


@frappe.whitelist()
def get_monthly_trend(months=6):
    """Monthly income/expense trend — auto-detected."""
    months = int(months)
    dts = _get_business_doctypes()
    data = []
    
    today = datetime.now()
    
    for i in range(months - 1, -1, -1):
        m_date = today.replace(day=1) - timedelta(days=i * 30)
        m_start = m_date.replace(day=1).strftime("%Y-%m-%d")
        if m_date.month == 12:
            m_end = m_date.replace(year=m_date.year + 1, month=1, day=1).strftime("%Y-%m-%d")
        else:
            m_end = m_date.replace(month=m_date.month + 1, day=1).strftime("%Y-%m-%d")
        
        m_income = 0
        m_expense = 0
        
        for dt in dts:
            if not dt["money_fields"]:
                continue
            mf = dt["money_fields"][0]
            df = dt["date_field"]
            try:
                s = frappe.db.sql(
                    f"SELECT COALESCE(SUM(`{mf}`), 0) FROM `tab{dt['doctype']}` WHERE `{df}` >= %s AND `{df}` < %s",
                    (m_start, m_end)
                )[0][0] or 0
                if dt["category"] == "income":
                    m_income += float(s)
                elif dt["category"] == "expense":
                    m_expense += float(s)
            except Exception:
                pass
        
        data.append({
            "month": m_date.strftime("%b %y"),
            "income": m_income,
            "expense": m_expense,
            "profit": m_income - m_expense,
        })
    
    return data


@frappe.whitelist()
def get_top_doctypes_smart(limit=8):
    """Top DocTypes by record count + today's new."""
    dts = _get_business_doctypes()
    today = datetime.now().strftime("%Y-%m-%d")
    
    results = []
    for dt in dts[:20]:  # check top 20
        try:
            today_count = frappe.db.count(dt["doctype"], {dt["date_field"]: (">=", today)}) if dt["date_field"] != "creation" else frappe.db.count(dt["doctype"], {"creation": (">=", today)})
        except Exception:
            today_count = 0
        results.append({
            "doctype": dt["doctype"],
            "module": dt["module"],
            "count": dt["count"],
            "today": today_count,
            "category": dt["category"],
            "has_money": len(dt["money_fields"]) > 0,
        })
    
    return results[:int(limit)]


@frappe.whitelist()
def get_risk_analysis():
    """AI Risk Detection — find overdue, pending, stale records."""
    dts = _get_business_doctypes()
    risks = []
    
    for dt in dts:
        if not dt["status_field"]:
            continue
        try:
            meta = frappe.get_meta(dt["doctype"])
            field_names = [f.fieldname for f in meta.fields]
            
            # Check for overdue items
            has_due_date = "due_date" in field_names
            if has_due_date:
                overdue = frappe.db.count(dt["doctype"], {
                    "due_date": ("<", datetime.now().strftime("%Y-%m-%d")),
                    dt["status_field"]: ("not in", ("Paid", "Completed", "Closed", "Cancelled", "Settled")),
                })
                if overdue > 0:
                    total_overdue_amt = 0
                    if dt["money_fields"]:
                        try:
                            total_overdue_amt = float(frappe.db.sql(
                                f"SELECT COALESCE(SUM(`{dt['money_fields'][0]}`), 0) FROM `tab{dt['doctype']}` WHERE due_date < %s AND `{dt['status_field']}` NOT IN ('Paid','Completed','Closed','Cancelled','Settled')",
                                datetime.now().strftime("%Y-%m-%d")
                            )[0][0] or 0)
                        except Exception:
                            pass
                    risks.append({
                        "type": "overdue",
                        "doctype": dt["doctype"],
                        "count": overdue,
                        "amount": total_overdue_amt,
                        "severity": "high" if overdue > 50 else "medium" if overdue > 10 else "low",
                    })
            
            # Check for draft/pending items
            pending_statuses = ("Draft", "Pending", "Pending Approval", "Open", "Unpaid", "Overdue")
            for ps in pending_statuses:
                try:
                    pending = frappe.db.count(dt["doctype"], {dt["status_field"]: ps})
                    if pending > 5:
                        risks.append({
                            "type": "pending",
                            "doctype": dt["doctype"],
                            "count": pending,
                            "status": ps,
                            "severity": "medium" if pending > 50 else "low",
                        })
                        break  # one status per doctype
                except Exception:
                    pass
        except Exception:
            pass
    
    risks.sort(key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["severity"], 0), reverse=True)
    return risks[:10]


@frappe.whitelist()
def get_customer_insights():
    """Auto-find customer-like DocTypes and analyze."""
    dts = _get_business_doctypes()
    customer_dts = [dt for dt in dts if dt["category"] == "customer"]
    
    insights = []
    for dt in customer_dts[:3]:
        try:
            total = dt["count"]
            today = datetime.now().strftime("%Y-%m-%d")
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            new_week = frappe.db.count(dt["doctype"], {"creation": (">=", week_ago)})
            new_month = frappe.db.count(dt["doctype"], {"creation": (">=", month_ago)})
            
            insights.append({
                "doctype": dt["doctype"],
                "total": total,
                "new_this_week": new_week,
                "new_this_month": new_month,
                "growth_pct": round((new_month / max(total - new_month, 1)) * 100, 1),
            })
        except Exception:
            pass
    
    return insights


@frappe.whitelist()
def get_recent_high_value(limit=8):
    """Recent high-value transactions across all money DocTypes."""
    dts = _get_business_doctypes()
    records = []
    
    for dt in dts:
        if not dt["money_fields"] or dt["category"] not in ("income", "expense"):
            continue
        mf = dt["money_fields"][0]
        try:
            rows = frappe.db.sql(f"""
                SELECT name, `{mf}` as amount, {dt['date_field']} as date, creation
                FROM `tab{dt['doctype']}`
                WHERE `{mf}` > 0
                ORDER BY creation DESC
                LIMIT 3
            """, as_dict=True)
            for r in rows:
                records.append({
                    "doctype": dt["doctype"],
                    "name": r["name"],
                    "amount": float(r["amount"]),
                    "date": str(r.get("date") or r.get("creation", "")),
                    "category": dt["category"],
                    "time_ago": frappe.utils.pretty_date(r.get("creation")),
                })
        except Exception:
            pass
    
    records.sort(key=lambda x: x["amount"], reverse=True)
    return records[:int(limit)]


@frappe.whitelist()
def get_status_breakdown():
    """Status distribution for top DocTypes that have status field."""
    dts = _get_business_doctypes()
    breakdowns = []
    
    for dt in dts[:10]:
        if not dt["status_field"]:
            continue
        try:
            rows = frappe.db.sql(f"""
                SELECT `{dt['status_field']}` as status, COUNT(*) as cnt
                FROM `tab{dt['doctype']}`
                WHERE `{dt['status_field']}` IS NOT NULL AND `{dt['status_field']}` != ''
                GROUP BY `{dt['status_field']}`
                ORDER BY cnt DESC
                LIMIT 6
            """, as_dict=True)
            if rows:
                breakdowns.append({
                    "doctype": dt["doctype"],
                    "statuses": [{"status": r["status"], "count": r["cnt"]} for r in rows],
                })
        except Exception:
            pass
    
    return breakdowns[:5]


@frappe.whitelist()
def get_system_info():
    """System health info."""
    dts = _get_business_doctypes()
    total_docs = sum(dt["count"] for dt in dts)
    
    income_dts = [dt for dt in dts if dt["category"] == "income"]
    expense_dts = [dt for dt in dts if dt["category"] == "expense"]
    customer_dts = [dt for dt in dts if dt["category"] == "customer"]
    
    try:
        total_users = frappe.db.count("User", {"enabled": 1, "user_type": "System User"})
    except Exception:
        total_users = 0
    
    # Get installed apps
    try:
        from frappe.utils.change_log import get_versions
        apps = list(get_versions().keys())
    except Exception:
        apps = []
    
    return {
        "total_documents": total_docs,
        "total_doctypes": len(dts),
        "total_users": total_users,
        "income_doctypes": len(income_dts),
        "expense_doctypes": len(expense_dts),
        "customer_doctypes": len(customer_dts),
        "installed_apps": apps,
        "discovered": [{"doctype": dt["doctype"], "category": dt["category"], "count": dt["count"]} for dt in dts[:15]],
    }


@frappe.whitelist()


# ═══════════════════════════════════════════
# LOAN PORTFOLIO DATA
# ═══════════════════════════════════════════

def _get_loan_portfolio():
    """Get comprehensive loan portfolio data for NBFC dashboard."""
    data = {
        "summary": {},
        "status_breakdown": [],
        "disbursement_trend": [],
        "collection_data": {},
        "npa_data": {},
    }
    
    try:
        if not frappe.db.table_exists("Loan"):
            return data
        
        # Portfolio summary
        total = frappe.db.sql("""
            SELECT COUNT(*) cnt, IFNULL(SUM(loan_amount),0) total_sanctioned,
                   IFNULL(SUM(disbursed_amount),0) total_disbursed,
                   IFNULL(SUM(total_amount_paid),0) total_collected,
                   IFNULL(SUM(total_principal_paid),0) principal_collected,
                   IFNULL(SUM(total_interest_payable),0) interest_expected,
                   IFNULL(SUM(written_off_amount),0) written_off
            FROM tabLoan WHERE docstatus=1
        """, as_dict=True)[0]
        
        active = frappe.db.sql("""
            SELECT COUNT(*) cnt, IFNULL(SUM(loan_amount),0) amount,
                   IFNULL(SUM(disbursed_amount),0) disbursed
            FROM tabLoan WHERE docstatus=1 AND status IN ('Disbursed','Partially Disbursed')
        """, as_dict=True)[0]
        
        data["summary"] = {
            "total_loans": total.cnt,
            "total_sanctioned": total.total_sanctioned,
            "total_disbursed": total.total_disbursed,
            "total_collected": total.total_collected,
            "principal_collected": total.principal_collected,
            "interest_expected": total.interest_expected,
            "written_off": total.written_off,
            "active_loans": active.cnt,
            "active_amount": active.amount,
            "active_disbursed": active.disbursed,
        }
        
        # Status breakdown
        statuses = frappe.db.sql("""
            SELECT status, COUNT(*) cnt, IFNULL(SUM(loan_amount),0) amount
            FROM tabLoan WHERE docstatus=1 GROUP BY status ORDER BY cnt DESC
        """, as_dict=True)
        data["status_breakdown"] = [{"status": s.status, "count": s.cnt, "amount": s.amount} for s in statuses]
        
        # Disbursement trend (last 12 months)
        try:
            trend = frappe.db.sql(
                "SELECT DATE_FORMAT(disbursement_date, '%b %y') as month, "
                "DATE_FORMAT(disbursement_date, '%Y-%m') as sort_key, "
                "COUNT(*) cnt, IFNULL(SUM(disbursed_amount),0) amount "
                "FROM `tabLoan Disbursement` WHERE docstatus=1 "
                "AND disbursement_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH) "
                "GROUP BY month, sort_key ORDER BY sort_key",
                as_dict=True)
            data["disbursement_trend"] = [{"month": t.month, "count": t.cnt, "amount": t.amount} for t in trend]
        except:
            pass
        
        # New applications this month
        try:
            new_apps = frappe.db.sql("""
                SELECT COUNT(*) cnt FROM `tabLoan Application`
                WHERE creation >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01')
            """, as_dict=True)[0]
            data["summary"]["new_applications_month"] = new_apps.cnt
        except:
            data["summary"]["new_applications_month"] = 0
        
        # Closure requests
        try:
            closures = frappe.db.sql("""
                SELECT COUNT(*) cnt FROM tabLoan WHERE status='Loan Closure Requested'
            """, as_dict=True)[0]
            data["summary"]["closure_requests"] = closures.cnt
        except:
            data["summary"]["closure_requests"] = 0
    
    except Exception as e:
        frappe.log_error(f"Loan portfolio error: {e}")
    
    return data

def get_ai_analysis():
    """AI analyzes entire business state — on-demand."""
    fin = get_financial_summary()
    risk = get_risk_analysis()
    cust = get_customer_insights()
    info = get_system_info()
    
    context = f"""Business Financial Summary:
- This Month Income: ₹{fin['income_month']:,.0f}
- This Month Expense: ₹{fin['expense_month']:,.0f}
- This Month Profit: ₹{fin['profit_month']:,.0f} ({fin['margin_pct']}% margin)
- This Year Income: ₹{fin['income_year']:,.0f}
- This Year Expense: ₹{fin['expense_year']:,.0f}
- This Year Profit: ₹{fin['profit_year']:,.0f}

Income Sources: {json.dumps(fin['income_sources'][:3], default=str)}
Expense Sources: {json.dumps(fin['expense_sources'][:3], default=str)}

Risks Detected ({len(risk)} items):
"""
    for r in risk[:5]:
        context += f"- {r['type'].upper()}: {r['doctype']} — {r['count']} items"
        if r.get("amount"):
            context += f" (₹{r['amount']:,.0f})"
        context += f" [{r['severity']}]\n"
    
    context += f"""
Customer Insights:
"""
    for c in cust:
        context += f"- {c['doctype']}: {c['total']} total, +{c['new_this_month']} this month ({c['growth_pct']}% growth)\n"
    
    context += f"""
System: {info['total_documents']:,} documents across {info['total_doctypes']} types, {info['total_users']} users
Apps: {', '.join(info['installed_apps'][:10])}
"""
    
    prompt = f"""You are a senior business analyst AI. Analyze this data and provide:

1. 📊 **Executive Summary** (2-3 lines)
2. 💰 **Financial Health** — rating (Excellent/Good/Average/Poor) + reason
3. ⚠️ **Top 3 Risks** — what needs immediate attention
4. 📈 **Growth Opportunities** — 2-3 actionable suggestions
5. 🎯 **Recommendation** — #1 priority action for management

Be concise, use ₹ for amounts, use emojis. Respond in English + Hindi mix if the data suggests an Indian business.

{context}"""
    
    try:
        from niv_ai.niv_core.langchain.llm import get_llm
        llm = get_llm(streaming=False)
        response = llm.invoke(prompt)
        return {"analysis": response.content}
    except Exception as e:
        return {"analysis": f"AI analysis unavailable: {str(e)}"}
