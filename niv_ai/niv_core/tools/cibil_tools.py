"""
CIBIL/Credit Score Tools for Niv AI NBFC Agent.

Location: niv_ai/niv_core/tools/cibil_tools.py
"""

import json
import frappe
from typing import Optional


def get_cibil_score(
    applicant: str = None,
    loan_application: str = None,
) -> str:
    """
    Get CIBIL/Credit score for a customer or loan application.
    
    Args:
        applicant: Customer/Applicant name or ID
        loan_application: Loan Application ID (e.g., ABPALI1025-0005099)
    
    Returns:
        JSON string with CIBIL score and risk details
    """
    try:
        result = {
            "found": False,
            "source": None,
            "cibil_score": None,
            "risk_category": None,
            "details": {}
        }
        
        # Build filters
        filters = {}
        if loan_application:
            filters["loan_application"] = loan_application
        elif applicant:
            filters["applicant_name"] = ["like", f"%{applicant}%"]
        
        if not filters:
            return json.dumps({"error": "Please provide applicant name or loan_application ID"})
        
        # Try Credit Score Assessment first
        assessments = frappe.get_all(
            "Credit Score Assessment",
            filters=filters,
            fields=[
                "name", "loan_application", "applicant", "applicant_name",
                "cibil_score", "cibil_rating", "overall_score", "risk_category",
                "dti_score", "dti_rating", "collateral_score", "collateral_rating",
                "income_stability_score", "kyc_score", "final_decision",
                "assessment_date"
            ],
            order_by="creation desc",
            limit=1
        )
        
        if assessments:
            a = assessments[0]
            result["found"] = True
            result["source"] = "Credit Score Assessment"
            result["cibil_score"] = a.get("cibil_score")
            result["overall_score"] = a.get("overall_score")
            result["risk_category"] = a.get("risk_category")
            result["details"] = {
                "assessment_id": a.get("name"),
                "applicant_name": a.get("applicant_name"),
                "loan_application": a.get("loan_application"),
                "cibil_rating": a.get("cibil_rating"),
                "dti_score": a.get("dti_score"),
                "collateral_score": a.get("collateral_score"),
                "income_stability_score": a.get("income_stability_score"),
                "kyc_score": a.get("kyc_score"),
                "final_decision": a.get("final_decision"),
            }
            
            # Add recommendation based on score
            score = a.get("cibil_score") or a.get("overall_score")
            if score:
                if score >= 750:
                    result["recommendation"] = "Excellent - Auto approve eligible, lowest interest rate"
                elif score >= 700:
                    result["recommendation"] = "Good - Standard approval with normal rate"
                elif score >= 650:
                    result["recommendation"] = "Fair - Manual review required, higher rate"
                elif score >= 600:
                    result["recommendation"] = "Poor - High risk, extra collateral needed"
                else:
                    result["recommendation"] = "Very Poor - Consider rejection"
            
            return json.dumps(result, indent=2, default=str)
        
        # No data found
        result["message"] = f"No CIBIL/Credit score found for {applicant or loan_application}. Run Credit Score Assessment first."
        return json.dumps(result, indent=2)
        
    except Exception as e:
        frappe.log_error(f"get_cibil_score error: {e}", "Niv AI CIBIL")
        return json.dumps({"error": str(e)})


def check_credit_eligibility(
    cibil_score: int,
    loan_amount: float,
    monthly_income: float,
    existing_emi: float = 0,
) -> str:
    """
    Check loan eligibility based on CIBIL score and income.
    Calculates FOIR and suggests interest rate.
    
    Args:
        cibil_score: CIBIL score (300-900)
        loan_amount: Requested loan amount
        monthly_income: Monthly income of applicant
        existing_emi: Current EMI obligations (default 0)
    
    Returns:
        JSON with eligibility decision, FOIR, and recommendations
    """
    try:
        # EMI estimation (14% for 36 months)
        rate = 14 / 12 / 100
        tenure = 36
        if rate > 0:
            proposed_emi = loan_amount * rate * ((1 + rate) ** tenure) / (((1 + rate) ** tenure) - 1)
        else:
            proposed_emi = loan_amount / tenure
        
        total_emi = existing_emi + proposed_emi
        foir = (total_emi / monthly_income) * 100 if monthly_income > 0 else 100
        
        # Eligibility checks
        eligible = True
        reasons = []
        recommendations = []
        
        # CIBIL check
        if cibil_score < 600:
            eligible = False
            reasons.append(f"CIBIL score {cibil_score} below minimum (600)")
        elif cibil_score < 650:
            recommendations.append("Manual review due to moderate CIBIL")
        
        # FOIR check (max 60%)
        if foir > 60:
            eligible = False
            reasons.append(f"FOIR {foir:.1f}% exceeds limit (60%)")
            recommendations.append("Reduce loan amount or clear existing EMIs")
        
        # Interest rate based on CIBIL
        if cibil_score >= 750:
            rate_range = "12-14%"
            category = "Excellent"
        elif cibil_score >= 700:
            rate_range = "14-16%"
            category = "Good"
        elif cibil_score >= 650:
            rate_range = "16-20%"
            category = "Fair"
        else:
            rate_range = "20%+ or Reject"
            category = "Poor"
        
        # Max eligible amount based on FOIR
        max_emi_allowed = monthly_income * 0.6 - existing_emi
        if max_emi_allowed > 0 and rate > 0:
            max_loan = max_emi_allowed * (((1 + rate) ** tenure) - 1) / (rate * ((1 + rate) ** tenure))
        else:
            max_loan = 0
        
        result = {
            "eligible": eligible,
            "cibil_score": cibil_score,
            "cibil_category": category,
            "requested_amount": loan_amount,
            "max_eligible_amount": round(max_loan, 0),
            "proposed_emi": round(proposed_emi, 2),
            "total_emi": round(total_emi, 2),
            "foir": round(foir, 2),
            "foir_limit": 60,
            "suggested_interest_rate": rate_range,
            "reasons": reasons if not eligible else [],
            "recommendations": recommendations,
            "calculation_basis": "14% interest, 36 months tenure"
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        frappe.log_error(f"check_credit_eligibility error: {e}", "Niv AI CIBIL")
        return json.dumps({"error": str(e)})


def get_credit_history(loan_application: str) -> str:
    """
    Get complete credit assessment history for a loan application.
    
    Args:
        loan_application: Loan Application ID
    
    Returns:
        JSON with all credit assessments and CIBIL records
    """
    try:
        result = {
            "loan_application": loan_application,
            "assessments": [],
            "latest_decision": None,
        }
        
        # Get all assessments
        assessments = frappe.get_all(
            "Credit Score Assessment",
            filters={"loan_application": loan_application},
            fields=["name", "overall_score", "risk_category", "cibil_score", 
                    "final_decision", "assessment_date", "creation"],
            order_by="creation desc"
        )
        
        if assessments:
            result["assessments"] = [
                {
                    "id": a.name,
                    "score": a.overall_score,
                    "cibil": a.cibil_score,
                    "risk": a.risk_category,
                    "decision": a.final_decision,
                    "date": str(a.assessment_date) if a.assessment_date else str(a.creation)
                }
                for a in assessments
            ]
            result["latest_decision"] = assessments[0].final_decision
            result["latest_score"] = assessments[0].overall_score
            result["total_assessments"] = len(assessments)
        else:
            result["message"] = "No credit assessments found for this application"
        
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        frappe.log_error(f"get_credit_history error: {e}", "Niv AI CIBIL")
        return json.dumps({"error": str(e)})
