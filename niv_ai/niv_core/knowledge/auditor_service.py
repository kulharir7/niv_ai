
import frappe
import json
from datetime import datetime, timedelta

class NBFCAuditor:
    """
    Autonomous auditing engine for NBFC operations.
    Scans for overdue payments, high-risk loans, and data anomalies.
    """
    
    @staticmethod
    def audit_overdue_loans():
        """Find loans with missed installments."""
        today = datetime.now().date()
        
        # Query Repayment Schedule for 'Pending' installments past due date
        # Note: Using generic field names, will be refined by Discovery Agent
        overdue = frappe.get_all(
            "Repayment Schedule",
            filters={
                "payment_date": ["<", today],
                "status": ["in", ["Pending", "Unpaid", "Overdue"]]
            },
            fields=["parent", "payment_date", "principal_amount", "interest_amount"]
        )
        
        if not overdue:
            return None
            
        summary = f"🚨 AUDIT ALERT: Found {len(overdue)} overdue installments.\n"
        for o in overdue[:5]:  # List top 5
            summary += f"- Loan {o.parent}: Due on {o.payment_date}\n"
            
        return summary

    @staticmethod
    def check_system_health():
        """Generic system anomaly detection."""
        findings = []
        
        # Check 1: Loans with 0 interest (possible data entry error)
        zero_interest = frappe.db.count("Loan", filters={"interest_rate": 0})
        if zero_interest > 0:
            findings.append(f"Found {zero_interest} loans with 0% interest rate.")
            
        # Check 2: Documents stuck in 'Draft' for too long
        old_drafts = frappe.db.count("Loan", filters={
            "docstatus": 0, 
            "creation": ["<", datetime.now() - timedelta(days=7)]
        })
        if old_drafts > 0:
            findings.append(f"Found {old_drafts} loan drafts older than 7 days.")
            
        return findings

def run_daily_audit():
    """Background task to run all audits and notify user."""
    auditor = NBFCAuditor()
    results = []
    
    overdue = auditor.audit_overdue_loans()
    if overdue:
        results.append(overdue)
        
    health = auditor.check_system_health()
    if health:
        results.extend(health)
        
    if results:
        message = "\n".join(results)
        # In a real scenario, this would send a notification via Telegram/Webchat
        frappe.log_error(f"Niv AI Auditor Findings:\n{message}", "Niv AI Auditor")
        return message
    
    return "Audit clean. No issues found."
