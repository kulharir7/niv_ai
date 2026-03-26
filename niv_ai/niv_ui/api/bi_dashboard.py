"""
AI Business Intelligence API — 100% Dynamic.
Auto-discovers financial DocTypes, amounts, dates.
Works on ANY Frappe site without hardcoding.
"""
import json
import frappe
from datetime import datetime, timedelta
from collections import defaultdict


def _safe_call(fn):
    """Call function safely, return empty dict on error."""
    try:
        return fn()
    except Exception as e:
        frappe.log_error(f"BI Dashboard error in {fn.__name__}: {e}")
        return {}


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


def _get_date_range(period="this_year"):
    """Convert period string to (start_date, end_date)."""
    from datetime import datetime, date
    today = date.today()
    
    if period == "this_month":
        start = today.replace(day=1)
        end = today
    elif period == "last_month":
        first_this = today.replace(day=1)
        end = first_this - __import__("datetime").timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this_quarter":
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)
        end = today
    elif period == "last_quarter":
        q = (today.month - 1) // 3
        if q == 0:
            start = date(today.year - 1, 10, 1)
            end = date(today.year - 1, 12, 31)
        else:
            start = date(today.year, (q - 1) * 3 + 1, 1)
            end = date(today.year, q * 3, 1) - __import__("datetime").timedelta(days=1)
    elif period == "this_year":
        start = date(today.year, 1, 1)
        end = today
    elif period == "last_year":
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
    else:  # all
        start = date(2019, 1, 1)
        end = today
    
    return str(start), str(end)

@frappe.whitelist()
def get_bi_data(period="this_year"):
    """Master BI endpoint."""
    return {
        "financial": get_financial_summary(period=period),
        "trend": get_monthly_trend(),
        "top_doctypes": get_top_doctypes_smart(),
        "risk": get_risk_analysis(),
        "customers": get_customer_insights(),
        "recent": get_recent_high_value(),
        "status_breakdown": get_status_breakdown(),
        "system_info": get_system_info(),
        "loan_portfolio": _safe_call(_get_loan_portfolio),
        "receivables": _safe_call(_get_receivables_ageing),
        "pending": _safe_call(_get_pending_approvals),
        "growth": _safe_call(_get_collection_and_growth),
        "branches": _safe_call(_get_branch_performance),
        "pipeline": _safe_call(_get_tat_and_pipeline),
        "predictions": _safe_call(_get_smart_predictions),
    }


@frappe.whitelist()
def get_financial_summary(period="this_year"):
    """Auto-detect income/expense DocTypes and sum amounts."""
    dts = _get_business_doctypes()
    
    today = datetime.now()
    period_start, period_end = _get_date_range(period)
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    year_start = period_start  # Use period start instead of fixed Jan 1
    
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













def _get_smart_predictions():
    """AI-powered predictions based on historical trends."""
    data = {"revenue_forecast": [], "collection_prediction": {}, "npa_warning": [], "seasonal": []}
    try:
        # --- Revenue Forecast (linear trend from last 6 months → predict next 3) ---
        try:
            hist = frappe.db.sql(
                "SELECT DATE_FORMAT(posting_date, '%Y-%m') as ym, "
                "IFNULL(SUM(CASE WHEN voucher_type IN ('Sales Invoice','Journal Entry') THEN credit ELSE 0 END),0) as income, "
                "IFNULL(SUM(CASE WHEN voucher_type IN ('Purchase Invoice','Journal Entry') THEN debit ELSE 0 END),0) as expense "
                "FROM `tabGL Entry` WHERE is_cancelled=0 "
                "AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) "
                "GROUP BY ym ORDER BY ym",
                as_dict=True)
            
            if len(hist) >= 3:
                incomes = [float(h.income) for h in hist]
                expenses = [float(h.expense) for h in hist]
                
                # Simple linear regression for prediction
                def predict_next(values, n_predict=3):
                    n = len(values)
                    if n < 2: return [values[-1]] * n_predict if values else [0] * n_predict
                    x_mean = (n - 1) / 2
                    y_mean = sum(values) / n
                    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
                    den = sum((i - x_mean) ** 2 for i in range(n))
                    slope = num / den if den else 0
                    intercept = y_mean - slope * x_mean
                    return [max(0, intercept + slope * (n + i)) for i in range(n_predict)]
                
                pred_income = predict_next(incomes)
                pred_expense = predict_next(expenses)
                
                import datetime
                today = datetime.date.today()
                for i in range(3):
                    m = today.month + i + 1
                    y = today.year + (m - 1) // 12
                    m = ((m - 1) % 12) + 1
                    month_label = datetime.date(y, m, 1).strftime('%b %y')
                    data["revenue_forecast"].append({
                        "month": month_label,
                        "predicted_income": round(pred_income[i]),
                        "predicted_expense": round(pred_expense[i]),
                        "predicted_profit": round(pred_income[i] - pred_expense[i]),
                        "confidence": max(40, min(85, 85 - i * 15))
                    })
        except Exception as e:
            frappe.log_error(f"Revenue forecast error: {e}")
        
        # --- Collection Prediction (this week based on daily avg) ---
        try:
            daily = frappe.db.sql(
                "SELECT IFNULL(AVG(daily_total),0) as avg_daily FROM ("
                "  SELECT posting_date, SUM(amount_paid) as daily_total "
                "  FROM `tabLoan Repayment` WHERE docstatus=1 "
                "  AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) "
                "  GROUP BY posting_date"
                ") t", as_dict=True)
            
            avg_daily = float(daily[0].avg_daily) if daily else 0
            import datetime
            today = datetime.date.today()
            days_left = 7 - today.weekday()  # days left this week
            
            this_week = frappe.db.sql(
                "SELECT IFNULL(SUM(amount_paid),0) as collected "
                "FROM `tabLoan Repayment` WHERE docstatus=1 "
                "AND posting_date >= DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)",
                as_dict=True)
            
            collected_so_far = float(this_week[0].collected) if this_week else 0
            predicted_week = collected_so_far + (avg_daily * days_left)
            
            data["collection_prediction"] = {
                "avg_daily": avg_daily,
                "collected_this_week": collected_so_far,
                "predicted_this_week": predicted_week,
                "days_left": days_left
            }
        except Exception as e:
            frappe.log_error(f"Collection prediction error: {e}")
        
        # --- NPA Early Warning (loans with missed payments) ---
        try:
            risky = frappe.db.sql(
                "SELECT l.name, l.applicant, l.loan_amount, l.disbursed_amount, "
                "l.total_amount_paid, l.total_payment, "
                "ROUND((1 - IFNULL(l.total_amount_paid,0) / NULLIF(l.total_payment,0)) * 100, 1) as risk_pct "
                "FROM tabLoan l WHERE l.docstatus=1 AND l.status='Disbursed' "
                "AND l.total_payment > 0 "
                "AND (l.total_amount_paid / l.total_payment) < 0.5 "
                "ORDER BY (l.total_payment - l.total_amount_paid) DESC LIMIT 8",
                as_dict=True)
            data["npa_warning"] = [{
                "loan": r.name, "applicant": r.applicant or "Unknown",
                "amount": float(r.loan_amount), "paid_pct": round(100 - float(r.risk_pct or 100), 1),
                "risk": "high" if float(r.risk_pct or 0) > 70 else "medium"
            } for r in risky]
        except Exception as e:
            frappe.log_error(f"NPA warning error: {e}")
        
        # --- Seasonal Patterns ---
        try:
            seasonal = frappe.db.sql(
                "SELECT MONTH(disbursement_date) as m, MONTHNAME(disbursement_date) as month_name, "
                "COUNT(*) cnt, IFNULL(SUM(disbursed_amount),0) amt "
                "FROM `tabLoan Disbursement` WHERE docstatus=1 "
                "AND disbursement_date >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH) "
                "GROUP BY m, month_name ORDER BY m",
                as_dict=True)
            avg_count = sum(s.cnt for s in seasonal) / max(len(seasonal), 1)
            data["seasonal"] = [{
                "month": s.month_name[:3], "count": s.cnt, "amount": float(s.amt),
                "vs_avg": round((s.cnt / avg_count - 1) * 100) if avg_count else 0
            } for s in seasonal]
        except Exception as e:
            frappe.log_error(f"Seasonal error: {e}")
    
    except Exception as e:
        frappe.log_error(f"Smart predictions error: {e}")
    return data

def _get_tat_and_pipeline():
    """Turnaround time + loan processing pipeline funnel."""
    data = {"tat": {}, "pipeline": []}
    try:
        # TAT: Application to Disbursement (avg days)
        try:
            tat = frappe.db.sql(
                "SELECT AVG(DATEDIFF(ld.disbursement_date, la.creation)) as avg_days, "
                "MIN(DATEDIFF(ld.disbursement_date, la.creation)) as min_days, "
                "MAX(DATEDIFF(ld.disbursement_date, la.creation)) as max_days "
                "FROM `tabLoan Disbursement` ld "
                "INNER JOIN tabLoan l ON ld.against_loan = l.name "
                "INNER JOIN `tabLoan Application` la ON l.loan_application = la.name "
                "WHERE ld.docstatus=1 AND ld.disbursement_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)",
                as_dict=True)
            if tat and tat[0].avg_days is not None:
                data["tat"] = {
                    "avg": round(float(tat[0].avg_days), 1),
                    "min": int(tat[0].min_days or 0),
                    "max": int(tat[0].max_days or 0),
                }
        except:
            pass
        
        # Loan Pipeline Funnel
        try:
            stages = [
                ("Applied", "SELECT COUNT(*) FROM `tabLoan Application`"),
                ("Under Review", "SELECT COUNT(*) FROM `tabLoan Application` WHERE status IN ('Open','Approved')"),
                ("Sanctioned", "SELECT COUNT(*) FROM tabLoan WHERE docstatus=1"),
                ("Disbursed", "SELECT COUNT(*) FROM tabLoan WHERE docstatus=1 AND status IN ('Disbursed','Partially Disbursed','Closed','Loan Closure Requested')"),
                ("Active", "SELECT COUNT(*) FROM tabLoan WHERE docstatus=1 AND status IN ('Disbursed','Partially Disbursed')"),
                ("Closed", "SELECT COUNT(*) FROM tabLoan WHERE docstatus=1 AND status='Closed'"),
            ]
            max_count = 0
            for label, query in stages:
                try:
                    cnt = int(frappe.db.sql(query)[0][0] or 0)
                    data["pipeline"].append({"stage": label, "count": cnt})
                    if cnt > max_count:
                        max_count = cnt
                except:
                    data["pipeline"].append({"stage": label, "count": 0})
            # Calculate percentages
            for p in data["pipeline"]:
                p["pct"] = round(p["count"] / max_count * 100) if max_count else 0
        except:
            pass
    except Exception as e:
        frappe.log_error(f"TAT pipeline error: {e}")
    return data

def _get_branch_performance():
    """Branch-wise loan performance."""
    data = {"branches": [], "quick_stats": {}}
    try:
        # Branch-wise loans
        try:
            branches = frappe.db.sql(
                "SELECT IFNULL(branch, 'Unassigned') as branch, COUNT(*) cnt, "
                "IFNULL(SUM(loan_amount),0) sanctioned, "
                "IFNULL(SUM(disbursed_amount),0) disbursed, "
                "IFNULL(SUM(total_amount_paid),0) collected "
                "FROM tabLoan WHERE docstatus=1 "
                "GROUP BY branch ORDER BY disbursed DESC LIMIT 10",
                as_dict=True)
            data["branches"] = [{
                "name": b.branch, "loans": b.cnt,
                "sanctioned": float(b.sanctioned), "disbursed": float(b.disbursed),
                "collected": float(b.collected),
                "efficiency": round(float(b.collected) / float(b.disbursed) * 100, 1) if b.disbursed else 0
            } for b in branches]
        except:
            pass
        
        # Quick stats
        try:
            today = frappe.utils.nowdate()
            data["quick_stats"] = {
                "today_collections": float(frappe.db.sql(
                    "SELECT IFNULL(SUM(amount_paid),0) FROM `tabLoan Repayment` WHERE docstatus=1 AND posting_date=%s", today)[0][0] or 0),
                "today_disbursements": float(frappe.db.sql(
                    "SELECT IFNULL(SUM(disbursed_amount),0) FROM `tabLoan Disbursement` WHERE docstatus=1 AND disbursement_date=%s", today)[0][0] or 0),
                "active_loans": int(frappe.db.sql(
                    "SELECT COUNT(*) FROM tabLoan WHERE docstatus=1 AND status IN ('Disbursed','Partially Disbursed')")[0][0] or 0),
                "avg_loan_size": float(frappe.db.sql(
                    "SELECT IFNULL(AVG(loan_amount),0) FROM tabLoan WHERE docstatus=1")[0][0] or 0),
            }
        except:
            pass
    except Exception as e:
        frappe.log_error(f"Branch performance error: {e}")
    return data

def _get_collection_and_growth():
    """EMI collection rate + new customer/loan growth trends."""
    data = {"collection": {}, "new_loans_trend": [], "new_customers_trend": []}
    try:
        # EMI Collection this month vs expected
        try:
            month_start = frappe.utils.get_first_day(frappe.utils.nowdate())
            collected = frappe.db.sql(
                "SELECT IFNULL(SUM(amount_paid),0) as paid FROM `tabLoan Repayment` "
                "WHERE docstatus=1 AND posting_date >= %s", month_start, as_dict=True)
            expected = frappe.db.sql(
                "SELECT IFNULL(SUM(total_payment),0) as expected FROM tabLoan "
                "WHERE docstatus=1 AND status IN ('Disbursed','Partially Disbursed')",
                as_dict=True)
            paid = float(collected[0].paid) if collected else 0
            exp = float(expected[0].expected) if expected else 0
            # Monthly expected = total_payment / loan_tenure approx
            data["collection"] = {
                "collected_month": paid,
                "total_outstanding": exp,
                "rate": round(paid / exp * 100, 1) if exp > 0 else 0
            }
        except:
            pass
        
        # New loans per month (last 6 months)
        try:
            loans = frappe.db.sql(
                "SELECT DATE_FORMAT(creation, '%b %y') as month, "
                "DATE_FORMAT(creation, '%Y-%m') as sk, "
                "COUNT(*) cnt, IFNULL(SUM(loan_amount),0) amt "
                "FROM tabLoan WHERE docstatus=1 "
                "AND creation >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) "
                "GROUP BY month, sk ORDER BY sk",
                as_dict=True)
            data["new_loans_trend"] = [{"month": l.month, "count": l.cnt, "amount": float(l.amt)} for l in loans]
        except:
            pass
        
        # New customers (Loan Applications) per month
        try:
            custs = frappe.db.sql(
                "SELECT DATE_FORMAT(creation, '%b %y') as month, "
                "DATE_FORMAT(creation, '%Y-%m') as sk, "
                "COUNT(*) cnt "
                "FROM `tabLoan Application` "
                "WHERE creation >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) "
                "GROUP BY month, sk ORDER BY sk",
                as_dict=True)
            data["new_customers_trend"] = [{"month": c.month, "count": c.cnt} for c in custs]
        except:
            pass
    except Exception as e:
        frappe.log_error(f"Collection growth error: {e}")
    return data

def _get_pending_approvals():
    """Pending workflow approvals and recent team activity."""
    data = {"approvals": [], "team_activity": [], "total_pending": 0}
    try:
        # Pending workflow actions
        pending = frappe.db.sql(
            "SELECT reference_doctype as doctype, status, COUNT(*) cnt "
            "FROM `tabWorkflow Action` WHERE status='Open' "
            "GROUP BY reference_doctype, status ORDER BY cnt DESC LIMIT 8",
            as_dict=True)
        data["approvals"] = [{"doctype": p.doctype, "count": p.cnt} for p in pending]
        data["total_pending"] = sum(p.cnt for p in pending)
        
        # Draft documents (not submitted) - check common doctypes
        draft_doctypes = ["Loan Application", "Sales Order", "Purchase Order", "Sales Invoice", "Purchase Invoice", "Journal Entry", "Payment Entry"]
        draft_list = []
        for dt in draft_doctypes:
            try:
                cnt = frappe.db.count(dt, {"docstatus": 0})
                if cnt > 0:
                    draft_list.append({"doctype": dt, "count": cnt})
            except:
                pass
        data["drafts"] = sorted(draft_list, key=lambda x: x["count"], reverse=True)[:6]
        
        # Recent activity (last 24h) — combine Version + Comment + Activity Log
        activity = frappe.db.sql(
            "SELECT user, SUM(cnt) as total_actions, MAX(last_active) as last_active FROM ("
            "  SELECT owner as user, COUNT(*) cnt, MAX(modified) last_active FROM tabVersion "
            "  WHERE creation >= DATE_SUB(NOW(), INTERVAL 24 HOUR) AND owner IS NOT NULL GROUP BY owner "
            "  UNION ALL "
            "  SELECT owner as user, COUNT(*) cnt, MAX(modified) last_active FROM `tabActivity Log` "
            "  WHERE creation >= DATE_SUB(NOW(), INTERVAL 24 HOUR) AND owner IS NOT NULL GROUP BY owner "
            ") combined WHERE user NOT IN ('Guest', '') "
            "GROUP BY user ORDER BY total_actions DESC LIMIT 8",
            as_dict=True)
        data["team_activity"] = [{"user": a.user.split("@")[0] if "@" in (a.user or "") else (a.user or "Unknown"), "email": a.user, "actions": int(a.total_actions), "last": str(a.last_active)[:16]} for a in activity]
    except Exception as e:
        frappe.log_error(f"Pending approvals error: {e}")
    return data

def _get_receivables_ageing():
    """Outstanding receivables ageing for NBFC."""
    data = {"total_outstanding": 0, "buckets": [], "top_defaulters": []}
    try:
        if not frappe.db.table_exists("Loan"):
            return data
        
        # Outstanding by ageing bucket
        buckets = frappe.db.sql(
            "SELECT "
            "SUM(CASE WHEN DATEDIFF(CURDATE(), posting_date) <= 30 THEN outstanding_amount ELSE 0 END) as d0_30, "
            "SUM(CASE WHEN DATEDIFF(CURDATE(), posting_date) BETWEEN 31 AND 60 THEN outstanding_amount ELSE 0 END) as d31_60, "
            "SUM(CASE WHEN DATEDIFF(CURDATE(), posting_date) BETWEEN 61 AND 90 THEN outstanding_amount ELSE 0 END) as d61_90, "
            "SUM(CASE WHEN DATEDIFF(CURDATE(), posting_date) > 90 THEN outstanding_amount ELSE 0 END) as d90plus, "
            "SUM(outstanding_amount) as total "
            "FROM `tabSales Invoice` WHERE docstatus=1 AND outstanding_amount > 0",
            as_dict=True)
        
        if buckets and buckets[0].total:
            b = buckets[0]
            total = float(b.total or 0)
            data["total_outstanding"] = total
            data["buckets"] = [
                {"label": "0-30 days", "amount": float(b.d0_30 or 0), "color": "#10b981", "pct": round(float(b.d0_30 or 0)/total*100) if total else 0},
                {"label": "31-60 days", "amount": float(b.d31_60 or 0), "color": "#f59e0b", "pct": round(float(b.d31_60 or 0)/total*100) if total else 0},
                {"label": "61-90 days", "amount": float(b.d61_90 or 0), "color": "#f97316", "pct": round(float(b.d61_90 or 0)/total*100) if total else 0},
                {"label": "90+ days", "amount": float(b.d90plus or 0), "color": "#ef4444", "pct": round(float(b.d90plus or 0)/total*100) if total else 0},
            ]
        
        # Top overdue parties
        top = frappe.db.sql(
            "SELECT customer as party, SUM(outstanding_amount) as amount, "
            "COUNT(*) as invoices, MIN(posting_date) as oldest "
            "FROM `tabSales Invoice` WHERE docstatus=1 AND outstanding_amount > 0 "
            "GROUP BY customer ORDER BY amount DESC LIMIT 5",
            as_dict=True)
        data["top_defaulters"] = [{"party": t.party or "Unknown", "amount": float(t.amount), "invoices": t.invoices, "days": (frappe.utils.nowdate() != str(t.oldest)) and (frappe.utils.date_diff(frappe.utils.nowdate(), str(t.oldest))) or 0} for t in top]
    except Exception as e:
        frappe.log_error(f"Receivables ageing error: {e}")
    return data

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



@frappe.whitelist()
def get_ai_dashboard_data():
    """Get dashboard data via AI agent — asks AI to fetch all metrics using tools."""
    import json as _json
    
    prompt = """You are a business intelligence assistant. Generate a complete dashboard report by querying the database.
    
Execute these queries and return the results as a JSON object:

1. **financial**: Run SQL to get this month's total income (credit) and expense (debit) from GL Entry, and year totals
2. **loan_summary**: Run SQL to get total loans count, total sanctioned amount, total disbursed, total collected (total_amount_paid), active loans count (status IN Disbursed,Partially Disbursed), closure requests count
3. **loan_status**: Run SQL to get count and sum(loan_amount) GROUP BY status from Loan table
4. **disbursement_trend**: Run SQL to get monthly disbursement count and sum for last 12 months from Loan Disbursement
5. **branch_performance**: Run SQL to get branch wise loan count, disbursed amount, collected amount from Loan table
6. **pending_approvals**: Run SQL to get pending workflow actions count by doctype, and draft document counts for Loan Application, Sales Order, Purchase Order, Payment Entry
7. **team_activity**: Run SQL to get user activity count from Version table in last 24 hours
8. **receivables**: Run SQL to get outstanding invoice amounts grouped by ageing buckets (0-30, 31-60, 61-90, 90+ days) from Sales Invoice
9. **collection**: Run SQL to get today's total collections from Loan Repayment, today's disbursements from Loan Disbursement
10. **tat**: Run SQL to get average days between Loan Application creation and Loan Disbursement date
11. **pipeline**: Get counts for each stage: total applications, sanctioned loans, disbursed loans, active loans, closed loans

Return ONLY a valid JSON object with all these keys. No markdown, no explanation — just the JSON."""

    from niv_ai.niv_core.langchain.agent import run_agent
    
    try:
        response = run_agent(
            message=prompt,
            conversation_id="ai-dashboard-" + frappe.session.user,
            user=frappe.session.user,
            system_prompt="You are a data analyst. Use run_database_query tool to fetch data. Return results as clean JSON only."
        )
        
        # Try to parse JSON from response
        import re
        # Find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response or "")
        if json_match:
            try:
                data = _json.loads(json_match.group())
                return {"source": "ai", "data": data, "raw": None}
            except:
                pass
        
        # If JSON parse fails, return raw text
        return {"source": "ai", "data": None, "raw": response}
    except Exception as e:
        frappe.log_error(f"AI Dashboard error: {e}")
        return {"source": "error", "data": None, "raw": str(e)}

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
