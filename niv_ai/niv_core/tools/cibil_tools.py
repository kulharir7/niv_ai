"""
CIBIL/Credit Score Tools for FAC (frappe_assistant_core) pattern.

Location: niv_ai/niv_core/tools/cibil_tools.py
Register via hooks.py: assistant_tools
"""

import json
import frappe
from typing import Any, Dict


class GetCibilScoreTool:
    """Get CIBIL/Credit score for a customer or loan application."""
    
    def __init__(self):
        self.name = "get_cibil_score"
        self.description = "Get CIBIL/Credit score for a customer or loan application. Returns score, risk category, and recommendation."
        self.category = "NBFC"
        self.source_app = "niv_ai"
        self.requires_permission = "Loan Application"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "applicant": {
                    "type": "string",
                    "description": "Customer/Applicant name to search"
                },
                "loan_application": {
                    "type": "string",
                    "description": "Loan Application ID (e.g., ABPALI1025-0005099)"
                }
            }
        }
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }
    
    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        applicant = arguments.get("applicant")
        loan_application = arguments.get("loan_application")
        
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
            return {"error": "Please provide applicant name or loan_application ID"}
        
        try:
            # Try Credit Score Assessment first
            assessments = frappe.get_all(
                "Credit Score Assessment",
                filters=filters,
                fields=[
                    "name", "loan_application", "applicant", "applicant_name",
                    "cibil_score", "cibil_rating", "overall_score", "risk_category",
                    "dti_score", "dti_rating", "collateral_score",
                    "income_stability_score", "kyc_score", "final_decision",
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
                    "final_decision": a.get("final_decision"),
                }
                
                # Add recommendation
                score = a.get("cibil_score") or a.get("overall_score")
                if score:
                    if score >= 750:
                        result["recommendation"] = "Excellent - Auto approve, lowest rate"
                    elif score >= 700:
                        result["recommendation"] = "Good - Standard approval"
                    elif score >= 650:
                        result["recommendation"] = "Fair - Manual review, higher rate"
                    elif score >= 600:
                        result["recommendation"] = "Poor - High risk"
                    else:
                        result["recommendation"] = "Very Poor - Likely reject"
            else:
                result["message"] = f"No CIBIL score found for {applicant or loan_application}"
                
        except Exception as e:
            frappe.log_error(f"get_cibil_score error: {e}", "Niv AI CIBIL")
            result["error"] = str(e)
        
        return result


class CheckCreditEligibilityTool:
    """Check loan eligibility based on CIBIL score and income."""
    
    def __init__(self):
        self.name = "check_credit_eligibility"
        self.description = "Check loan eligibility based on CIBIL score, income, and existing EMIs. Calculates FOIR and suggests interest rate."
        self.category = "NBFC"
        self.source_app = "niv_ai"
        self.requires_permission = "Loan Application"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "cibil_score": {
                    "type": "integer",
                    "description": "CIBIL score (300-900)"
                },
                "loan_amount": {
                    "type": "number",
                    "description": "Requested loan amount"
                },
                "monthly_income": {
                    "type": "number",
                    "description": "Monthly income of applicant"
                },
                "existing_emi": {
                    "type": "number",
                    "description": "Current EMI obligations (default 0)"
                }
            },
            "required": ["cibil_score", "loan_amount", "monthly_income"]
        }
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }
    
    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cibil_score = arguments.get("cibil_score", 0)
        loan_amount = arguments.get("loan_amount", 0)
        monthly_income = arguments.get("monthly_income", 0)
        existing_emi = arguments.get("existing_emi", 0)
        
        # EMI calculation (14% for 36 months)
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
        
        if cibil_score < 600:
            eligible = False
            reasons.append(f"CIBIL score {cibil_score} below minimum (600)")
        elif cibil_score < 650:
            recommendations.append("Manual review due to moderate CIBIL")
        
        if foir > 60:
            eligible = False
            reasons.append(f"FOIR {foir:.1f}% exceeds limit (60%)")
            recommendations.append("Reduce loan amount or clear existing EMIs")
        
        # Interest rate based on CIBIL
        if cibil_score >= 750:
            rate_range, category = "12-14%", "Excellent"
        elif cibil_score >= 700:
            rate_range, category = "14-16%", "Good"
        elif cibil_score >= 650:
            rate_range, category = "16-20%", "Fair"
        else:
            rate_range, category = "20%+ or Reject", "Poor"
        
        # Max eligible amount
        max_emi_allowed = monthly_income * 0.6 - existing_emi
        if max_emi_allowed > 0 and rate > 0:
            max_loan = max_emi_allowed * (((1 + rate) ** tenure) - 1) / (rate * ((1 + rate) ** tenure))
        else:
            max_loan = 0
        
        return {
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
            "recommendations": recommendations
        }


class GetCreditHistoryTool:
    """Get complete credit assessment history for a loan application."""
    
    def __init__(self):
        self.name = "get_credit_history"
        self.description = "Get complete credit assessment history for a loan application."
        self.category = "NBFC"
        self.source_app = "niv_ai"
        self.requires_permission = "Loan Application"
        self.inputSchema = {
            "type": "object",
            "properties": {
                "loan_application": {
                    "type": "string",
                    "description": "Loan Application ID"
                }
            },
            "required": ["loan_application"]
        }
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }
    
    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        loan_application = arguments.get("loan_application")
        
        result = {
            "loan_application": loan_application,
            "assessments": [],
            "latest_decision": None,
        }
        
        try:
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
                result["message"] = "No credit assessments found"
                
        except Exception as e:
            frappe.log_error(f"get_credit_history error: {e}", "Niv AI CIBIL")
            result["error"] = str(e)
        
        return result


# Tool instances for hook registration
def get_cibil_score_tool():
    return GetCibilScoreTool()

def check_credit_eligibility_tool():
    return CheckCreditEligibilityTool()

def get_credit_history_tool():
    return GetCreditHistoryTool()
