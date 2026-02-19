"""
NBFC Domain Knowledge Pack — Loan lifecycle, RBI compliance, CIBIL integration,
EMI calculations, NPA rules, and complete module blueprints.
Injected into dev system prompt when NBFC/lending context detected.
"""

NBFC_DOMAIN_KNOWLEDGE = """
=== NBFC DOMAIN KNOWLEDGE PACK ===

You are now an NBFC (Non-Banking Financial Company) expert. Use this knowledge
when user asks about loans, lending, NBFC, finance, EMI, NPA, CIBIL, KYC, or
when building for Growth System / lending companies.

--- LOAN LIFECYCLE (Complete Flow) ---

1. LEAD GENERATION
   Lead → Customer walks in / online application / DSA (Direct Selling Agent) referral
   DocType: Lead or Loan Lead
   Fields: name, phone, email, source (Walk-in/Online/DSA/Reference), product_interest

2. KYC (Know Your Customer)
   PAN verification → Aadhaar verification → Address proof → Photo → Video KYC (optional)
   DocType: KYC Application
   Fields: pan_number, aadhaar_number, pan_verified(Check), aadhaar_verified(Check),
           kyc_status(Select: Pending/Verified/Rejected), kyc_date, verified_by,
           address_proof_type(Select: Aadhaar/Passport/Voter ID/Utility Bill),
           address_proof_attachment(Attach), photo(Attach Image),
           video_kyc_done(Check), video_kyc_link(Data)
   Rule: PAN is MANDATORY for any loan. Format: ABCDE1234F (5 alpha + 4 digit + 1 alpha)
   Rule: CKYC (Central KYC) number assigned after verification

3. CREDIT BUREAU CHECK (CIBIL/Equifax/Experian)
   PAN → Bureau API → Credit Score + Credit Report
   DocType: Credit Bureau Check
   Fields: applicant(Link: Customer), pan_number, bureau(Select: CIBIL/Equifax/Experian),
           score(Int), score_date, report_json(Long Text), report_attachment(Attach),
           enquiry_id(Data), status(Select: Pending/Fetched/Failed/Error)
   
   CIBIL SCORE RANGES:
   - 750-900: Excellent — Auto-approve eligible, lowest interest rate
   - 700-749: Good — Approve with standard rate
   - 650-699: Fair — Manual review required, higher rate
   - 600-649: Poor — Reject or approve with very high rate + extra collateral
   - Below 600: Very Poor — Auto-reject
   - -1 or NH: No History — First-time borrower, needs special handling
   
   CIBIL API INTEGRATION:
   - Provider: TransUnion CIBIL
   - API: REST/SOAP based
   - Auth: Member ID + Password + Security Key
   - Input: PAN, Name, DOB, Phone, Address
   - Output: Score (3 digits), DPD (Days Past Due) history, Active loans, Enquiries
   - Cost: Rs 35-50 per pull
   - Rate limit: Check company agreement
   
   Server Script pattern for CIBIL:
   ```
   import requests, json
   
   def fetch_cibil_score(pan, name, dob, phone):
       # API endpoint (varies by provider)
       url = frappe.db.get_single_value("NBFC Settings", "cibil_api_url")
       api_key = frappe.utils.password.get_decrypted_password("NBFC Settings", "NBFC Settings", "cibil_api_key")
       
       payload = {
           "pan": pan,
           "name": name,
           "dob": dob,
           "phone": phone
       }
       headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
       
       response = requests.post(url, json=payload, headers=headers, timeout=30)
       data = response.json()
       
       return {
           "score": data.get("score", 0),
           "report": json.dumps(data),
           "enquiry_id": data.get("enquiry_id", ""),
           "dpd_history": data.get("dpd_history", []),
           "active_loans": data.get("active_loans", 0),
           "total_enquiries_last_30d": data.get("enquiries_30d", 0)
       }
   ```

4. LOAN APPLICATION
   Customer fills application → Document upload → CIBIL check → Eligibility calculation
   DocType: Loan Application (Submittable)
   Fields: 
   - applicant(Link: Customer, mandatory)
   - applicant_name(Data, fetch_from: applicant.customer_name)
   - loan_product(Link: Loan Product, mandatory)
   - applied_amount(Currency, mandatory)
   - loan_purpose(Select: Personal/Business/Education/Home/Vehicle/Gold/Agriculture)
   - tenure_months(Int, mandatory)
   - monthly_income(Currency)
   - existing_emi(Currency) — other loan EMIs
   - cibil_score(Int, read_only, fetched from Credit Bureau Check)
   - eligible_amount(Currency, read_only, calculated)
   - interest_rate(Percent, fetched from Loan Product based on score)
   - processing_fee(Currency, calculated)
   - status(Select: Draft/Submitted/Under Review/Approved/Sanctioned/Rejected/Cancelled)
   - rejection_reason(Small Text)
   - approved_amount(Currency)
   - approved_by(Link: User, read_only)
   - approval_date(Date, read_only)
   
   Child Table: Loan Application Document
   Fields: document_type(Select: PAN Card/Aadhaar/Bank Statement/Salary Slip/ITR/
           Property Papers/Vehicle RC/Gold Valuation), attachment(Attach), verified(Check)
   
   ELIGIBILITY CALCULATION:
   - FOIR (Fixed Obligation to Income Ratio) = (existing_emi + proposed_emi) / monthly_income
   - Max FOIR: 50-60% (company policy)
   - Eligible EMI = monthly_income * max_foir - existing_emi
   - Eligible Amount = EMI_to_Principal(eligible_emi, rate, tenure)
   
   Workflow: Draft → Submitted → Under Review (Credit team) → Approved/Rejected (Manager)
            → Sanctioned (Senior Manager) → Disbursement

5. LOAN SANCTION
   Approved application → Sanction letter generated → Customer accepts terms
   DocType: Loan Sanction (Submittable)
   Fields: loan_application(Link), sanctioned_amount(Currency), interest_rate(Percent),
           tenure_months(Int), emi_amount(Currency), processing_fee(Currency),
           insurance_amount(Currency), net_disbursement(Currency),
           sanction_date(Date), valid_till(Date), 
           terms_accepted(Check), acceptance_date(Date)

6. LOAN DISBURSEMENT
   After sanction → Amount transferred to customer bank account
   DocType: Loan Disbursement (Submittable)
   Fields: loan(Link: Loan), disbursement_date(Date), amount(Currency),
           bank_account(Data), ifsc_code(Data), utr_number(Data),
           payment_mode(Select: NEFT/RTGS/IMPS/Cheque),
           disbursement_type(Select: Full/Partial/Tranche)
   Multiple disbursements possible for construction loans (tranche-based)

7. LOAN (Master Record)
   Created after disbursement — this is the active loan
   DocType: Loan (Submittable)
   Fields: loan_application(Link), borrower(Link: Customer), loan_product(Link),
           disbursed_amount(Currency), interest_rate(Percent), tenure(Int),
           emi_amount(Currency), disbursement_date(Date), first_emi_date(Date),
           maturity_date(Date), outstanding_principal(Currency), outstanding_interest(Currency),
           total_paid(Currency), total_overdue(Currency),
           dpd(Int, Days Past Due), npa_status(Select: Standard/SMA-0/SMA-1/SMA-2/Substandard/Doubtful/Loss),
           loan_status(Select: Active/Closed/Written Off/Restructured/Settled)
   
   Child Table: Repayment Schedule
   Fields: emi_number(Int), due_date(Date), principal(Currency), interest(Currency),
           emi_amount(Currency), outstanding_balance(Currency), 
           paid_amount(Currency), paid_date(Date), status(Select: Upcoming/Due/Paid/Overdue/Partial)

8. REPAYMENT / COLLECTION
   Monthly EMI collection via NACH/ECS/UPI/Cash/Cheque
   DocType: Loan Repayment (Submittable)
   Fields: loan(Link: Loan), repayment_date(Date), amount(Currency),
           principal_component(Currency), interest_component(Currency),
           penalty_amount(Currency), payment_mode(Select: NACH/ECS/UPI/Cash/Cheque/NEFT),
           reference_number(Data), bounce_status(Select: None/Bounced/Represented)
   
   NACH (National Automated Clearing House):
   - Auto-debit from customer bank account on EMI date
   - eMandate registration required
   - Bounce charges: Rs 250-500 per bounce
   - Representation: Retry after 3-5 days

9. NPA (Non-Performing Asset) MANAGEMENT
   RBI NPA Classification Rules:
   - Standard: 0-30 DPD (Days Past Due)
   - SMA-0: 1-30 DPD (Special Mention Account)
   - SMA-1: 31-60 DPD
   - SMA-2: 61-90 DPD
   - Substandard: 91-365 DPD (NPA starts here!)
   - Doubtful: 366-730 DPD (Doubtful 1: 1 year, Doubtful 2: 2 years, Doubtful 3: 3+ years)
   - Loss: When recovery unlikely, to be written off
   
   PROVISIONING (money kept aside for bad loans):
   - Standard: 0.40%
   - Substandard: 15% (secured) / 25% (unsecured)
   - Doubtful 1: 25%
   - Doubtful 2: 40%
   - Doubtful 3: 100%
   - Loss: 100%
   
   DocType: NPA Review
   Fields: loan(Link), review_date, current_dpd, previous_npa_status, new_npa_status,
           provisioning_amount, action_taken(Select: Call/Notice/Legal/Write-off/Restructure)
   
   Scheduler: Daily cron job to update DPD and NPA status for all active loans

10. RECOVERY / COLLECTIONS
    DocType: Collection Activity
    Fields: loan(Link), activity_date, type(Select: Phone Call/SMS/Email/Field Visit/Legal Notice),
            contacted_person, response, next_action_date, collected_amount,
            assigned_to(Link: User/Collection Agent)
    
    Escalation Matrix:
    - 1-30 DPD: SMS + Auto-call
    - 31-60 DPD: Personal call + Email
    - 61-90 DPD: Field visit + Warning notice
    - 91+ DPD: Legal notice + Recovery agent

11. LOAN CLOSURE
    When all EMIs paid → Close loan → Release security/collateral → NOC letter
    DocType: Loan Closure
    Fields: loan(Link), closure_type(Select: Regular/Foreclosure/Settlement/Write-off),
            closure_date, total_paid, waiver_amount, settlement_amount,
            noc_generated(Check), noc_date, security_released(Check)

--- EMI CALCULATION FORMULAS ---

REDUCING BALANCE (most common):
EMI = P * r * (1+r)^n / ((1+r)^n - 1)
Where:
  P = Principal (loan amount)
  r = Monthly interest rate (annual_rate / 12 / 100)
  n = Tenure in months

Example: Loan 5,00,000 at 12% for 36 months
  r = 12 / 12 / 100 = 0.01
  EMI = 500000 * 0.01 * (1.01)^36 / ((1.01)^36 - 1)
  EMI = 16,607

FLAT RATE:
Total Interest = P * annual_rate * years / 100
EMI = (P + Total Interest) / n

Example: Same loan
  Total Interest = 500000 * 12 * 3 / 100 = 180000
  EMI = (500000 + 180000) / 36 = 18,889
  (Flat rate is HIGHER than reducing balance!)

RULE OF 78 (for foreclosure):
Used to calculate interest refund on early closure.
Rebate = Remaining_sum / Total_sum * Total_interest

Server Script for EMI:
```
import math

def calculate_emi(principal, annual_rate, tenure_months):
    if annual_rate == 0:
        return principal / tenure_months
    r = annual_rate / 12 / 100
    n = tenure_months
    emi = principal * r * math.pow(1 + r, n) / (math.pow(1 + r, n) - 1)
    return round(emi, 2)

def generate_schedule(principal, annual_rate, tenure_months, start_date):
    r = annual_rate / 12 / 100
    emi = calculate_emi(principal, annual_rate, tenure_months)
    balance = principal
    schedule = []
    
    for i in range(1, tenure_months + 1):
        interest = round(balance * r, 2)
        principal_component = round(emi - interest, 2)
        balance = round(balance - principal_component, 2)
        
        due_date = frappe.utils.add_months(start_date, i)
        schedule.append({
            "emi_number": i,
            "due_date": due_date,
            "emi_amount": emi,
            "principal": principal_component,
            "interest": interest,
            "outstanding_balance": max(balance, 0)
        })
    
    return schedule
```

--- LOAN PRODUCTS ---

Common NBFC Loan Products:
1. Personal Loan: Unsecured, 10-24% rate, 12-60 months, max 25L
2. Business Loan: Secured/Unsecured, 12-28% rate, 12-84 months
3. Gold Loan: Secured by gold, 7-15% rate, 3-24 months, LTV 75%
4. Vehicle Loan: Secured by vehicle, 8-16% rate, 12-84 months
5. Home Loan: Secured by property, 8-12% rate, up to 360 months
6. Microfinance: Group lending, 20-26% rate, 12-24 months, max 1.25L
7. LAP (Loan Against Property): Secured, 9-16% rate, up to 180 months
8. Education Loan: 10-14% rate, moratorium period
9. Co-Lending: NBFC + Bank partnership, shared risk/return

DocType: Loan Product
Fields: product_name(Data), product_code(Data), loan_type(Select: above list),
        min_amount(Currency), max_amount(Currency),
        min_tenure(Int), max_tenure(Int),
        base_interest_rate(Percent), max_interest_rate(Percent),
        processing_fee_percent(Percent), processing_fee_fixed(Currency),
        min_cibil_score(Int), max_foir(Percent),
        collateral_required(Check), ltv_ratio(Percent),
        insurance_required(Check), insurance_percent(Percent),
        prepayment_allowed(Check), prepayment_charges_percent(Percent),
        foreclosure_allowed(Check), foreclosure_lock_in_months(Int)

--- NBFC SETTINGS DocType ---

DocType: NBFC Settings (Single)
Fields:
  Section: Company Info
  - company_name, rbi_registration_number, company_category(Select: NBFC-D/NBFC-ND/NBFC-MFI/HFC)
  
  Section: Credit Bureau
  - cibil_api_url(Data), cibil_api_key(Password), cibil_member_id(Data)
  - equifax_api_url, equifax_api_key
  - min_cibil_score_auto_approve(Int, default: 750)
  - min_cibil_score_manual_review(Int, default: 650)
  - auto_reject_below_score(Int, default: 600)
  
  Section: NACH/Payment
  - nach_sponsor_bank(Data), nach_utility_code(Data)
  - bounce_charges(Currency, default: 500)
  - penal_interest_rate(Percent, default: 2)
  
  Section: NPA Settings
  - npa_threshold_days(Int, default: 90)
  - sma0_days(Int, default: 30), sma1_days(Int, default: 60), sma2_days(Int, default: 90)
  - auto_npa_marking(Check)
  - provisioning_standard(Percent), provisioning_substandard(Percent)
  
  Section: Communication
  - sms_provider, sms_api_key, sms_sender_id
  - email_templates_for_dunning(Check)

--- COMPLETE NBFC MODULE BLUEPRINT ---

When user asks "NBFC ke liye Loan Management System banao", use this blueprint:

📋 BLUEPRINT: NBFC Loan Management System

📦 DocTypes (12):
├─ NBFC Settings — Global configuration (Single DocType)
├─ Loan Product — Interest rates, tenure, eligibility rules  
├─ KYC Application — PAN/Aadhaar verification
├─ Credit Bureau Check — CIBIL/Equifax score fetch
├─ Loan Application — Customer applies for loan (Submittable)
├─ Loan Application Document — (child) uploaded documents
├─ Loan Sanction — Approved terms & conditions (Submittable)
├─ Loan — Active loan master record (Submittable)
├─ Repayment Schedule — (child) EMI schedule
├─ Loan Disbursement — Money transfer to customer (Submittable)
├─ Loan Repayment — EMI payment received (Submittable)
└─ Loan Closure — Final settlement & NOC

🔄 Workflows (2):
├─ Loan Application: Draft → Under Review → Approved/Rejected → Sanctioned
└─ Loan Closure: Initiated → Verified → NOC Generated → Closed

📊 Reports (5):
├─ Loan Portfolio Summary — Active loans, amounts, product-wise
├─ EMI Collection Report — Due vs collected, bounce rate
├─ NPA Report — DPD-wise classification, provisioning
├─ Disbursement Report — Daily/monthly disbursements
└─ CIBIL Score Distribution — Score ranges of applicants

⚡ Server Scripts (4):
├─ Auto-calculate EMI on Loan Application save
├─ CIBIL Score fetch on KYC completion  
├─ NPA Marker — daily scheduler to update DPD & NPA status
└─ Bounce handler — mark NACH bounces, add penalty

📧 Notifications (3):
├─ Loan Approved — Email + SMS to customer
├─ EMI Due Reminder — 3 days before due date
└─ Overdue Alert — Daily for DPD > 0

--- AGENT BEHAVIOR FOR NBFC (Autonomous Operations) ---

When handling NBFC tasks, be an "Active Agent", not just a "Responder":
1.  AUTONOMOUS VALIDATION: If a user says "Process this loan", don't ask "What is the PAN?". Instead:
    - Search for the applicant's existing records using list_documents.
    - Check if KYC documents are already attached.
    - If missing, then ask. If found, proceed to next step (Credit bureau check) automatically.
2.  PROACTIVE ERROR FIXING: If a CIBIL fetch fails, look at the error. If it's a "Connection timeout", tell the user you'll try once more after a short wait, or check if API credentials in NBFC Settings are missing.
3.  LINKED REASONING: When discussing a loan, always look up the Borrower's history. "This borrower had a bounce in their previous loan, so we should be cautious with the sanction amount."
4.  BULK ANALYSIS: If asked about portfolio health, use run_database_query to get DPD counts and NPA percentages, then present a summary without being asked for specific steps.

Estimated build time: ~2 hours
"""

NBFC_FIELD_SUGGESTIONS = """
=== NBFC-SPECIFIC FIELD SUGGESTIONS ===

When creating DocTypes for NBFC/lending, ALWAYS suggest these fields:

FOR ANY LOAN-RELATED DocType:
- company (Link: Company, mandatory)
- branch (Link: Branch)  
- loan_product (Link: Loan Product)
- fiscal_year (Link: Fiscal Year)

FOR PERSON/BORROWER:
- pan_number (Data, mandatory) — format: ABCDE1234F
- aadhaar_number (Data) — 12 digits
- cibil_score (Int, read_only)
- customer_category (Select: Individual/Corporate/MSME/SHG)
- occupation (Select: Salaried/Self-Employed/Business/Agriculture/Retired)
- monthly_income (Currency)
- employer_name (Data) — if salaried
- business_name (Data) — if self-employed

FOR LOAN AMOUNTS:
- applied_amount (Currency)
- sanctioned_amount (Currency)
- disbursed_amount (Currency)
- outstanding_principal (Currency, read_only)
- outstanding_interest (Currency, read_only)
- total_overdue (Currency, read_only)
- penal_interest (Currency, read_only)

FOR DATES:
- application_date (Date, default: Today)
- sanction_date (Date)
- disbursement_date (Date)
- first_emi_date (Date)
- maturity_date (Date)
- closure_date (Date)
- last_payment_date (Date, read_only)

FOR NPA TRACKING:
- dpd (Int, Days Past Due, read_only)
- npa_status (Select: Standard/SMA-0/SMA-1/SMA-2/Substandard/Doubtful/Loss)
- npa_date (Date) — when it became NPA
- provisioning_amount (Currency, read_only)
"""
"""
NBFC CALCULATIONS KNOWLEDGE - Add to domain_nbfc.py

This section teaches agents NBFC-specific calculations and formulas.
"""

NBFC_CALCULATIONS_KNOWLEDGE = """

--- NBFC PORTFOLIO CALCULATIONS ---

1. WRR (WEIGHTED RISK RATING)
   Purpose: Measures overall portfolio risk weighted by loan exposure
   
   Formula:
   WRR = Σ(Loan Amount × Risk Score) / Σ(Loan Amount)
   
   Where Risk Score can be:
   - CIBIL Score based: Map 300-900 to 1-5 scale
     * 750-900 → 1 (Lowest Risk)
     * 700-749 → 2 (Low Risk)
     * 650-699 → 3 (Medium Risk)
     * 600-649 → 4 (High Risk)
     * Below 600 → 5 (Very High Risk)
   
   - NPA Status based:
     * Standard → 1
     * SMA-0 → 2
     * SMA-1 → 3
     * SMA-2 → 4
     * Substandard/Doubtful/Loss → 5
   
   SQL Example:
   ```sql
   SELECT 
       SUM(loan_amount * CASE 
           WHEN cibil_score >= 750 THEN 1
           WHEN cibil_score >= 700 THEN 2
           WHEN cibil_score >= 650 THEN 3
           WHEN cibil_score >= 600 THEN 4
           ELSE 5 
       END) / SUM(loan_amount) AS wrr
   FROM `tabLoan`
   WHERE docstatus = 1 AND status = 'Disbursed'
   ```
   
   Interpretation:
   - WRR < 2.0 → Excellent portfolio
   - WRR 2.0-2.5 → Good portfolio
   - WRR 2.5-3.0 → Average portfolio
   - WRR 3.0-3.5 → Risky portfolio
   - WRR > 3.5 → Very risky, needs attention

2. PAR (PORTFOLIO AT RISK)
   Purpose: Percentage of portfolio that has overdue payments
   
   Formula:
   PAR(X) = (Outstanding of loans with DPD > X days) / (Total Outstanding) × 100
   
   Common variants:
   - PAR-0: Any overdue (DPD > 0)
   - PAR-30: 30+ days overdue
   - PAR-60: 60+ days overdue
   - PAR-90: 90+ days overdue (NPA threshold)
   
   SQL Example:
   ```sql
   SELECT 
       SUM(CASE WHEN dpd > 30 THEN outstanding_amount ELSE 0 END) * 100.0 / 
       SUM(outstanding_amount) AS par_30
   FROM `tabLoan`
   WHERE docstatus = 1 AND status IN ('Disbursed', 'Active')
   ```
   
   Interpretation:
   - PAR-30 < 3% → Excellent
   - PAR-30 3-5% → Good
   - PAR-30 5-10% → Needs attention
   - PAR-30 > 10% → Critical

3. COLLECTION EFFICIENCY
   Purpose: How much of expected amount was actually collected
   
   Formula:
   Collection Efficiency = (Amount Collected in Period) / (Amount Due in Period) × 100
   
   SQL Example:
   ```sql
   SELECT 
       SUM(paid_amount) * 100.0 / SUM(emi_amount) AS collection_efficiency
   FROM `tabRepayment Schedule`
   WHERE payment_date BETWEEN '2024-01-01' AND '2024-01-31'
   ```
   
   Interpretation:
   - > 95% → Excellent
   - 90-95% → Good
   - 85-90% → Needs improvement
   - < 85% → Critical

4. NPA RATIO
   Purpose: Percentage of total loans classified as NPA
   
   Formula:
   NPA Ratio = (Gross NPA Amount) / (Gross Advances) × 100
   
   Gross NPA = Sum of all loans with DPD > 90 days
   Gross Advances = Total outstanding of all loans
   
   SQL Example:
   ```sql
   SELECT 
       SUM(CASE WHEN dpd > 90 THEN outstanding_amount ELSE 0 END) * 100.0 / 
       SUM(outstanding_amount) AS npa_ratio
   FROM `tabLoan`
   WHERE docstatus = 1
   ```

5. PROVISION COVERAGE RATIO (PCR)
   Purpose: How much provision is kept against NPAs
   
   Formula:
   PCR = (Total Provisions) / (Gross NPA) × 100
   
   RBI Provisioning Norms:
   - Standard Assets: 0.40%
   - SMA-1, SMA-2: 5%
   - Substandard: 15%
   - Doubtful (up to 1 year): 25%
   - Doubtful (1-3 years): 40%
   - Doubtful (> 3 years): 100%
   - Loss: 100%

6. YIELD ON ADVANCES
   Purpose: Average interest rate earned on loan portfolio
   
   Formula:
   Yield = (Interest Income for Period) / (Average Loan Outstanding) × 100
   
7. LOAN-TO-VALUE (LTV) RATIO
   Purpose: Loan amount vs collateral value (for secured loans)
   
   Formula:
   LTV = (Loan Amount / Collateral Value) × 100
   
   Typical limits:
   - Gold Loan: Max 75% LTV
   - Vehicle Loan: Max 85-90% LTV
   - Home Loan: Max 75-80% LTV
   - LAP (Loan Against Property): Max 60-70% LTV

8. EMI TO INCOME RATIO (FOIR)
   Purpose: Check if borrower can afford the EMI
   
   Formula:
   FOIR = (Total Monthly EMI including new loan) / (Monthly Income) × 100
   
   Typically:
   - FOIR < 40% → Eligible
   - FOIR 40-50% → Marginal
   - FOIR > 50% → Reject

--- USAGE INSTRUCTIONS FOR AGENTS ---

When asked about WRR, PAR, or other NBFC calculations:
1. First identify which fields exist in the system (loan_amount, cibil_score, dpd, outstanding_amount, etc.)
2. Use run_database_query with the appropriate SQL
3. Apply the formula
4. Interpret the result with benchmarks

Example prompt handling:
User: "Calculate WRR for top 10 loans"
Agent should:
1. Get top 10 loans by loan_amount: list_documents or run_database_query
2. Get their risk scores (cibil_score) or NPA status (dpd/npa_status)
3. Apply WRR formula: SUM(amount × risk_weight) / SUM(amount)
4. Return result with interpretation

"""
