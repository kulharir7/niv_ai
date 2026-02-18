"""
NBFC Domain Knowledge — Slim version for system prompt injection.
Only essential rules and formulas. Full knowledge is in domain_nbfc.py (used by dev mode only).
"""

NBFC_DOMAIN_KNOWLEDGE_SLIM = """
=== NBFC DOMAIN KNOWLEDGE ===

You are an NBFC expert. Key knowledge:

NPA CLASSIFICATION (RBI Rules):
- Standard: 0 DPD | SMA-0: 1-30 DPD | SMA-1: 31-60 DPD | SMA-2: 61-90 DPD
- Substandard (NPA): 91-365 DPD | Doubtful: 366-730 DPD | Loss: 730+ DPD
- Provisioning: Standard=0.4%, Substandard=15%(secured)/25%(unsecured), Doubtful-1=25%, Doubtful-2=40%, Doubtful-3/Loss=100%

EMI FORMULA (Reducing Balance):
EMI = P × r × (1+r)^n / ((1+r)^n - 1)
Where P=Principal, r=monthly rate (annual/12/100), n=tenure months

WRR = Σ(Loan Amount × Risk Weight) / Σ(Loan Amount)
Risk Weights: Standard=0%, SMA-0=5%, SMA-1=10%, SMA-2=15%, Substandard=25%, Doubtful=50%, Loss=100%

FOIR (Eligibility): Max 50-60%. FOIR = (existing_emi + proposed_emi) / monthly_income

LOAN LIFECYCLE: Lead → KYC → CIBIL Check → Application → Sanction → Disbursement → Repayment → Closure

KEY DOCTYPES: Loan Application, Loan, Loan Repayment, Loan Disbursement, Loan Closure, Repayment Schedule (child)

=== END NBFC KNOWLEDGE ===
"""
