"""
NBFC Domain Knowledge for RAG — Growth System specific.

Indexes NBFC lending workflows, compliance rules, business logic,
and DocType usage guides into the vectorstore.

Usage:
    bench --site <site> execute niv_ai.niv_core.langchain.nbfc_knowledge.index_nbfc_knowledge
    bench --site <site> execute niv_ai.niv_core.langchain.nbfc_knowledge.index_all_nbfc
"""
import frappe


def index_all_nbfc(force=False):
    """Index all NBFC knowledge: workflows + compliance + DocType guides."""
    from .rag import delete_by_source, _reset_vectorstore

    if force:
        for source in ["nbfc_workflow", "nbfc_compliance", "nbfc_doctype_guide", "nbfc_collection", "nbfc_colending"]:
            delete_by_source(source)
        _reset_vectorstore()
        print("[NBFC RAG] Cleared existing NBFC knowledge")

    stats = {}
    stats["workflows"] = index_nbfc_workflows()
    stats["compliance"] = index_nbfc_compliance()
    stats["doctype_guides"] = index_nbfc_doctype_guides()
    stats["collection"] = index_nbfc_collection()
    stats["colending"] = index_nbfc_colending()

    total = sum(stats.values())
    print(f"\n[NBFC RAG] === COMPLETE === Total: {total} NBFC knowledge chunks")
    for key, count in stats.items():
        print(f"  {key}: {count}")
    return stats


def index_nbfc_knowledge():
    """Alias for index_all_nbfc."""
    return index_all_nbfc(force=True)


def index_nbfc_workflows():
    """Index NBFC loan lifecycle workflows."""
    from .rag import add_documents, delete_by_source

    delete_by_source("nbfc_workflow")

    knowledge = [
        {
            "title": "NBFC Complete Loan Lifecycle",
            "content": (
                "NBFC Loan Lifecycle — Full Flow:\n\n"
                "STAGE 1 — LEAD ORIGINATION (LOS):\n"
                "Lead → Lead captured from BC/DSA/Branch/Digital → Lead Source tracking\n"
                "Lead contains: customer name, mobile, loan amount required, loan type, source\n\n"
                "STAGE 2 — LOAN APPLICATION:\n"
                "Lead → Loan Application (DocType: 'Loan Application')\n"
                "Loan Application contains: applicant details, loan amount, loan type, tenure, "
                "customer KYC, income details, co-applicant/guarantor info\n"
                "Required: customer_profile_master (Link), loan_type (Link to Loan Type), "
                "applied_amount, branch\n\n"
                "STAGE 3 — CREDIT ASSESSMENT:\n"
                "Loan Application → Credit Score Assessment → FI Document (Field Investigation)\n"
                "→ PD (Personal Discussion) → TVR (Telephone Verification)\n"
                "Credit Score Assessment checks: CIBIL score, existing obligations, "
                "repayment capacity, LTV ratio\n\n"
                "STAGE 4 — SANCTION & APPROVAL:\n"
                "Credit approved → Loan Application Review (DocType: 'Loan Application Review')\n"
                "Sanction conditions set → Deviations approved/rejected\n"
                "Sanctioned amount may differ from applied amount\n"
                "Approval matrix: Branch Manager → Regional Manager → Credit Head → MD\n\n"
                "STAGE 5 — DISBURSEMENT:\n"
                "Sanction approved → Loan (DocType: 'Loan') created\n"
                "Loan Disbursement (DocType: 'Loan Disbursement') → Bank transfer\n"
                "Pre-disbursement checks: NACH mandate registered, PDC collected, "
                "insurance done, documents verified\n"
                "Disbursement can be: Full or Part (tranche-based)\n\n"
                "STAGE 6 — REPAYMENT (LMS):\n"
                "Loan → Repayment Schedule auto-generated\n"
                "EMI collection via: NACH/eNACH, Cheque (PDC/SPDC), Cash, Bank Transfer\n"
                "Loan Repayment (DocType: 'Loan Repayment') → updates outstanding\n"
                "Receipt (DocType: 'Receipt') → payment confirmation\n\n"
                "STAGE 7 — COLLECTION & NPA:\n"
                "Missed EMI → Bucket classification (SMA-0, SMA-1, SMA-2, NPA)\n"
                "Collection activities: Calling, Field visit, Legal notice\n"
                "NACH bouncing → Re-presentation or cheque collection\n\n"
                "STAGE 8 — CLOSURE/SETTLEMENT:\n"
                "Full repayment → Loan closure\n"
                "Partial settlement → Loan Write Off / Loan Restructure\n"
                "Foreclosure → Pre-payment with charges\n"
                "NPA → Legal action → Repossession → Litigation"
            ),
        },
        {
            "title": "LOS (Loan Origination System) Workflow",
            "content": (
                "LOS — Loan Origination System Workflow:\n\n"
                "1. LEAD CREATION:\n"
                "   DocType: Lead (CRM module)\n"
                "   Sources: BC Partner, DSA, Branch Walk-in, Digital, Referral\n"
                "   Lead → converted to Loan Application\n\n"
                "2. LOAN APPLICATION:\n"
                "   DocType: Loan Application\n"
                "   Key fields: customer_profile_master, loan_type, applied_amount, tenure\n"
                "   Child tables: Customer Details, Professional Details, Bank Details\n"
                "   Status flow: Draft → Submitted → Under Process → Sanctioned/Rejected\n\n"
                "3. KYC & VERIFICATION:\n"
                "   Customer KYC Details: Aadhaar, PAN, Voter ID, Driving License\n"
                "   Digilocker KYC: Digital document verification\n"
                "   FI Document: Field Investigation report (address, business verification)\n"
                "   PD: Personal Discussion with applicant\n"
                "   TVR: Telephone Verification Report\n\n"
                "4. CREDIT ASSESSMENT:\n"
                "   Credit Score Assessment: CIBIL/bureau check\n"
                "   Credit Check: Manual credit evaluation\n"
                "   Underwriting: Risk assessment and loan terms\n"
                "   Deviation handling: Commercial, Credit, Operational deviations\n\n"
                "5. SANCTION:\n"
                "   Loan Application Review: Final approval/rejection\n"
                "   Sanction conditions: Pre-disbursement and post-disbursement\n"
                "   Sanctioned Loan Amount: May differ from applied amount\n"
                "   Security Valuation: Collateral assessment"
            ),
        },
        {
            "title": "LMS (Loan Management System) Workflow",
            "content": (
                "LMS — Loan Management System Workflow:\n\n"
                "1. LOAN CREATION:\n"
                "   DocType: Loan\n"
                "   Created after sanction approval from Loan Application\n"
                "   Key fields: loan_type, loan_amount, rate_of_interest, repayment_method, "
                "repayment_periods, monthly_repayment_amount\n"
                "   Status: Sanctioned → Partially Disbursed → Disbursed → Closed\n\n"
                "2. DISBURSEMENT:\n"
                "   DocType: Loan Disbursement\n"
                "   Can be full or partial (tranche-based)\n"
                "   Creates GL entries: Loan Account Dr, Bank Cr\n"
                "   VAS (Value Added Services) charges added here\n\n"
                "3. REPAYMENT SCHEDULE:\n"
                "   Auto-generated based on loan terms\n"
                "   Methods: Flat, Reducing Balance, Rule of 78\n"
                "   Contains: EMI date, principal, interest, balance\n"
                "   Moratorium period supported\n\n"
                "4. EMI COLLECTION:\n"
                "   NACH/eNACH: Auto-debit from bank (preferred)\n"
                "   PDC: Post-Dated Cheques collected upfront\n"
                "   SPDC: Security PDC\n"
                "   Cash: Daily/Weekly cash collection (DCC)\n"
                "   Receipt: Payment confirmation document\n\n"
                "5. INTEREST ACCRUAL:\n"
                "   Loan Interest Accrual: Monthly interest booking\n"
                "   Process Loan Interest Accrual: Batch processing\n"
                "   GL entries: Interest Receivable Dr, Interest Income Cr\n\n"
                "6. LOAN OPERATIONS:\n"
                "   Loan Restructure: Change EMI/tenure/rate\n"
                "   Loan Moratorium: EMI holiday period\n"
                "   Loan Balance Adjustment: Manual corrections\n"
                "   Loan Write Off: Bad debt write-off\n"
                "   Loan Refund: Excess payment refund"
            ),
        },
        {
            "title": "Disbursement Process Detail",
            "content": (
                "Disbursement Process — Step by Step:\n\n"
                "PRE-DISBURSEMENT CHECKLIST:\n"
                "1. Loan Application sanctioned and approved\n"
                "2. All sanction conditions met\n"
                "3. NACH mandate registered and active\n"
                "4. PDC cheques collected (if applicable)\n"
                "5. Insurance premium paid (Life Cover Insurance, Vehicle Insurance)\n"
                "6. All KYC documents verified\n"
                "7. Security valuation completed\n"
                "8. Legal verification done\n"
                "9. Stamp duty paid (Stamp Duty Activity)\n\n"
                "DISBURSEMENT STEPS:\n"
                "1. Disbursement Activities created\n"
                "2. Disbursal Maker (child table) — breakup of disbursement\n"
                "   - Direct to customer account\n"
                "   - To dealer/vendor (for vehicle/asset loans)\n"
                "   - To insurance company\n"
                "   - VAS charges deduction\n"
                "3. Loan Disbursement submitted → GL entries created\n"
                "4. Repayment Schedule generated\n"
                "5. First EMI date set based on due_date setting\n\n"
                "DISBURSEMENT MODES:\n"
                "- NEFT/RTGS to customer bank account\n"
                "- Demand Draft\n"
                "- Direct to dealer (vehicle loans)\n"
                "- Wallet settlement (for internal transfers)"
            ),
        },
    ]

    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": "nbfc_workflow", "title": k["title"]} for k in knowledge]
    from .rag import add_documents
    count = add_documents(texts, metadatas)
    print(f"[NBFC RAG] Workflows: {count} chunks")
    return count


def index_nbfc_compliance():
    """Index NBFC compliance and regulatory knowledge."""
    from .rag import add_documents, delete_by_source

    delete_by_source("nbfc_compliance")

    knowledge = [
        {
            "title": "NPA Classification & Bucket System",
            "content": (
                "NPA Classification for NBFC (RBI Guidelines):\n\n"
                "BUCKET SYSTEM (Days Past Due - DPD):\n"
                "- Bucket 0 (Current): 0 DPD — EMI paid on time\n"
                "- SMA-0 (Special Mention Account): 1-30 DPD — Early warning\n"
                "- SMA-1: 31-60 DPD — Needs immediate attention\n"
                "- SMA-2: 61-90 DPD — High risk, pre-NPA\n"
                "- NPA (Non-Performing Asset): 90+ DPD — Asset classified as non-performing\n"
                "- Sub-Standard: 90-365 DPD (12 months as NPA)\n"
                "- Doubtful: 365-730 DPD (1-3 years as NPA)\n"
                "- Loss: 730+ DPD (3+ years as NPA)\n\n"
                "PROVISIONING NORMS:\n"
                "- Standard Assets: 0.40% (general)\n"
                "- Sub-Standard: 15%\n"
                "- Doubtful (up to 1 year): 25%\n"
                "- Doubtful (1-3 years): 40%\n"
                "- Doubtful (3+ years): 100%\n"
                "- Loss Assets: 100%\n\n"
                "DocType: Bucket — stores bucket configuration\n"
                "DocType: Bucket Settings (child table) — DPD ranges and actions\n"
                "Credit Shield Activities — tracks account monitoring"
            ),
        },
        {
            "title": "KYC Requirements for NBFC",
            "content": (
                "KYC (Know Your Customer) Requirements:\n\n"
                "MANDATORY DOCUMENTS:\n"
                "1. Identity Proof: Aadhaar Card, PAN Card, Voter ID, Passport, Driving License\n"
                "2. Address Proof: Aadhaar, Utility Bill, Bank Statement, Passport\n"
                "3. Income Proof:\n"
                "   - Salaried: Salary slips (3 months), Form 16, Bank statement (6 months)\n"
                "   - Self-employed: ITR (2 years), P&L, Balance Sheet, Bank statement (12 months)\n"
                "   - Non-income proof: Profession-specific docs\n"
                "4. Photographs: Passport-size photos\n"
                "5. PAN Card: Mandatory for loans above ₹50,000\n\n"
                "DIGITAL KYC:\n"
                "- Digilocker KYC: Aadhaar-based eKYC\n"
                "- Video KYC: For remote verification\n"
                "- CKYC: Central KYC Registry\n\n"
                "DocTypes:\n"
                "- Customer KYC Details: Stores all KYC documents\n"
                "- Customer Document (child table): Individual document records\n"
                "- Digilocker KYC: Digital verification records\n"
                "- FI Document: Field Investigation for address/business verification"
            ),
        },
        {
            "title": "Interest Calculation Methods",
            "content": (
                "Interest Calculation Methods in NBFC:\n\n"
                "1. FLAT RATE:\n"
                "   Interest = Principal × Rate × Tenure\n"
                "   EMI = (Principal + Total Interest) / Number of EMIs\n"
                "   Simple to calculate but effective rate is higher\n\n"
                "2. REDUCING BALANCE (DIMINISHING):\n"
                "   Interest calculated on outstanding principal\n"
                "   EMI = P × r × (1+r)^n / ((1+r)^n - 1)\n"
                "   Where: P=principal, r=monthly rate, n=tenure in months\n"
                "   Lower effective cost for borrower\n\n"
                "3. RULE OF 78:\n"
                "   Front-loaded interest allocation\n"
                "   Used for pre-closure calculations\n"
                "   Higher interest in early months\n\n"
                "REPAYMENT FREQUENCIES:\n"
                "- Monthly (most common)\n"
                "- Weekly\n"
                "- Bi-weekly\n"
                "- Daily (DCC — Daily Cash Collection)\n"
                "- Bullet (interest-only, principal at maturity)\n\n"
                "DocType: Loan Type — defines interest method, rate range, tenure range\n"
                "DocType: Repayment Frequency Type — frequency options\n"
                "DocType: EMI Methods — calculation methodology\n"
                "Repayment Schedule (child table): EMI breakup per installment"
            ),
        },
        {
            "title": "NACH and Collection Mechanisms",
            "content": (
                "NACH (National Automated Clearing House) & Collection:\n\n"
                "NACH/eNACH:\n"
                "- Auto-debit mandate registered with customer's bank\n"
                "- Maximum mandate amount set (usually 1.5x EMI)\n"
                "- Mandate validity: Loan tenure + buffer months\n"
                "- Presentation: Monthly on EMI due date\n"
                "- DocType: Mandate — stores mandate details\n"
                "- DocType: NACH Settlement — settlement after presentation\n"
                "- DocType: Bulk Present NACH — batch presentation\n"
                "- DocType: Bulk Update NACH Status — update after bank response\n\n"
                "CHEQUE COLLECTION:\n"
                "- PDC (Post-Dated Cheque): Collected upfront for full tenure\n"
                "- SPDC (Security Post-Dated Cheque): Security cheques\n"
                "- Presentation on due date\n"
                "- DocType: Cheque Settlement — cheque clearing\n"
                "- DocType: Bulk Present Cheque — batch presentation\n"
                "- Bounce handling: Bounce Reason, re-presentation\n\n"
                "OTHER MODES:\n"
                "- Cash collection (Daily Cash Collection)\n"
                "- Bank transfer (NEFT/RTGS/UPI)\n"
                "- Agent Money Deposit — field agent cash deposit\n"
                "- Wallet — internal wallet for agents\n\n"
                "BOUNCE HANDLING:\n"
                "- Bounce Reason captured (insufficient funds, account closed, etc.)\n"
                "- Bounce charges applied to loan\n"
                "- Re-presentation or alternate mode switch\n"
                "- Repayment Mode Change Request — switch NACH to cheque or vice versa"
            ),
        },
        {
            "title": "Deviation and Approval Matrix",
            "content": (
                "Deviation Handling in NBFC Lending:\n\n"
                "TYPES OF DEVIATIONS:\n"
                "1. Credit Deviations: CIBIL score below threshold, high FOIR, "
                "existing NPAs in bureau\n"
                "2. Commercial Deviations: LTV above limit, rate below minimum, "
                "tenure above maximum\n"
                "3. Operational Deviations: Missing documents, KYC pending, "
                "FI not done\n"
                "4. Loan Details Deviations: Amount above sanctioned, different loan type\n\n"
                "APPROVAL MATRIX:\n"
                "- Level 1: Branch Manager — minor deviations\n"
                "- Level 2: Regional Manager — moderate deviations\n"
                "- Level 3: Credit Head — significant deviations\n"
                "- Level 4: MD/CEO — major deviations\n\n"
                "DocTypes:\n"
                "- Deviation Condition: Master list of deviation rules\n"
                "- Credit Deviations CT: Credit-related deviations in application\n"
                "- Commercial Deviations CT: Commercial deviations\n"
                "- Operational Deviations CT: Process deviations\n"
                "- Assessment Approval Conditions: Approval conditions for assessment\n"
                "- Sanction Approval Condition CT: Conditions for sanction\n"
                "- Assessment Decision Logs: Audit trail of decisions"
            ),
        },
        {
            "title": "Security and Collateral Management",
            "content": (
                "Security & Collateral in NBFC Lending:\n\n"
                "TYPES OF SECURITY:\n"
                "1. Vehicle: Car, Two-wheeler, Commercial vehicle, Tractor\n"
                "   - Vehicle Details CT: Make, model, year, registration, chassis no\n"
                "   - Vehicle Type: Category classification\n"
                "   - Utility Of Vehicle: Usage type\n\n"
                "2. Property: Residential, Commercial, Agricultural land\n"
                "   - Property Titles: Title documents\n"
                "   - Name of Property Owner: Owner details\n"
                "   - Security Valuation: Property valuation report\n\n"
                "3. Gold/Ornaments:\n"
                "   - Ornament Details CT: Weight, purity, value\n"
                "   - Loan Security Pledge: Pledge registration\n\n"
                "4. Fixed Deposit / NCD:\n"
                "   - NCD Subscription: NCD as security\n"
                "   - Deposit: FD as collateral\n\n"
                "LTV (Loan to Value) RATIOS:\n"
                "- New Vehicle: Up to 90-100% of on-road price\n"
                "- Used Vehicle: Up to 70-80% of valuation\n"
                "- Property: Up to 60-70% of market value\n"
                "- Gold: Up to 75% of gold value (RBI norm)\n\n"
                "DocTypes:\n"
                "- Loan Security Type: Master for security categories\n"
                "- Loan Security: Individual security records\n"
                "- Security Valuation: Valuation reports\n"
                "- Asset Group: Asset classification\n"
                "- Asset Documents: Document tracking for assets"
            ),
        },
        {
            "title": "Insurance in NBFC Loans",
            "content": (
                "Insurance Products in NBFC:\n\n"
                "1. LIFE COVER INSURANCE:\n"
                "   - Mandatory for most loans\n"
                "   - Covers outstanding loan on borrower death\n"
                "   - Premium: Age-based (Age Wise Premium table)\n"
                "   - DocType: Life Cover Insurance\n"
                "   - LS Cover Type: Types of life cover\n\n"
                "2. VEHICLE INSURANCE:\n"
                "   - Comprehensive/Third-party\n"
                "   - Required before disbursement\n"
                "   - Hypothecation in favor of NBFC\n\n"
                "3. PROPERTY INSURANCE:\n"
                "   - Fire, earthquake, flood coverage\n"
                "   - Assignment in favor of NBFC\n\n"
                "INSURANCE FLOW:\n"
                "- Insurance Company master maintained\n"
                "- Premium calculated at loan application\n"
                "- Deducted from disbursement or paid separately\n"
                "- Insurance Charge Payment Activity: Premium payment tracking\n"
                "- In House Insurance Activity: Internal insurance processing\n"
                "- Loan Suraksha CT: Insurance protection details on loan\n\n"
                "DocTypes:\n"
                "- Insurance Company: Master list of insurers\n"
                "- Insurer Name: Insurer details\n"
                "- Insurance Table (child): Insurance records on loan\n"
                "- VAS template: Value Added Services including insurance"
            ),
        },
    ]

    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": "nbfc_compliance", "title": k["title"]} for k in knowledge]
    from .rag import add_documents
    count = add_documents(texts, metadatas)
    print(f"[NBFC RAG] Compliance: {count} chunks")
    return count


def index_nbfc_doctype_guides():
    """Index usage guides for critical NBFC DocTypes."""
    from .rag import add_documents, delete_by_source

    delete_by_source("nbfc_doctype_guide")

    guides = [
        {
            "title": "How to create a Loan Application",
            "content": (
                "Creating a Loan Application:\n"
                "DocType: Loan Application\n"
                "Module: Loan Management\n\n"
                "REQUIRED FIELDS:\n"
                "- applicant_type: Individual or Company\n"
                "- applicant: Link to Customer Profile Master\n"
                "- company: NBFC company name\n"
                "- loan_type: Link to Loan Type (defines interest rate, tenure)\n"
                "- applied_amount: Loan amount requested\n"
                "- branch: Branch handling the application\n\n"
                "IMPORTANT CHILD TABLES:\n"
                "- Customer Details: Co-applicant and guarantor info\n"
                "- Professional Details: Employment/business details\n"
                "- Bank Detail CT: Bank account for disbursement\n"
                "- Asset Details: Collateral/security details\n\n"
                "STATUS FLOW:\n"
                "Draft → Submitted → Under Assessment → Sanctioned/Rejected\n\n"
                "AFTER CREATION:\n"
                "1. Submit the application\n"
                "2. Trigger Credit Score Assessment\n"
                "3. Complete FI (Field Investigation)\n"
                "4. Get PD (Personal Discussion) done\n"
                "5. Get approval from Loan Application Review"
            ),
        },
        {
            "title": "How to create a Loan",
            "content": (
                "Creating a Loan (after sanction):\n"
                "DocType: Loan\n"
                "Module: Loan Management\n\n"
                "REQUIRED FIELDS:\n"
                "- applicant_type: Individual or Company\n"
                "- applicant: Link to Customer Profile Master\n"
                "- company: NBFC company name\n"
                "- loan_application: Link to sanctioned Loan Application\n"
                "- loan_type: Link to Loan Type\n"
                "- loan_amount: Sanctioned loan amount\n"
                "- rate_of_interest: Annual interest rate\n"
                "- repayment_method: Repay Fixed Amount per Period / Repay Over Number of Periods\n"
                "- repayment_periods: Number of EMI installments\n"
                "- monthly_repayment_amount: EMI amount\n\n"
                "AUTO-GENERATED:\n"
                "- Repayment Schedule (child table): Full EMI breakup\n"
                "- Total Interest Payable\n"
                "- Total Amount Payable\n\n"
                "STATUS FLOW:\n"
                "Sanctioned → Partially Disbursed → Disbursed → Closed\n\n"
                "AFTER LOAN CREATION:\n"
                "1. Register NACH mandate\n"
                "2. Collect PDC cheques\n"
                "3. Process insurance\n"
                "4. Create Loan Disbursement"
            ),
        },
        {
            "title": "How to create a Loan Disbursement",
            "content": (
                "Creating a Loan Disbursement:\n"
                "DocType: Loan Disbursement\n"
                "Module: Loan Management\n\n"
                "REQUIRED FIELDS:\n"
                "- against_loan: Link to Loan\n"
                "- company: NBFC company name\n"
                "- disbursement_date: Date of disbursement\n"
                "- disbursed_amount: Amount being disbursed\n\n"
                "DISBURSEMENT BREAKUP (Disbursal Maker child table):\n"
                "- Party: Who receives the money\n"
                "- Amount: How much\n"
                "- Mode: NEFT/RTGS/DD/Cash\n\n"
                "PREREQUISITES:\n"
                "- Loan must be in Sanctioned/Partially Disbursed status\n"
                "- All sanction pre-conditions met\n"
                "- NACH mandate registered\n"
                "- Insurance premium paid\n\n"
                "SUBMISSION:\n"
                "- Creates GL entries: Loan Account Dr, Disbursement Account Cr\n"
                "- Updates Loan status and disbursed amount\n"
                "- Triggers repayment schedule activation"
            ),
        },
        {
            "title": "How to record a Loan Repayment",
            "content": (
                "Recording a Loan Repayment (EMI payment):\n"
                "DocType: Loan Repayment\n"
                "Module: Loan Management\n\n"
                "REQUIRED FIELDS:\n"
                "- against_loan: Link to Loan\n"
                "- company: NBFC company name\n"
                "- posting_date: Payment date\n"
                "- amount_paid: Total EMI amount paid\n\n"
                "AUTO-CALCULATED:\n"
                "- principal_amount: Principal portion of EMI\n"
                "- interest_amount: Interest portion of EMI\n"
                "- penalty_amount: Late payment penalty (if any)\n"
                "- outstanding_amount: Remaining loan balance\n\n"
                "PAYMENT MODES:\n"
                "- NACH: Auto-debit (linked to Mandate)\n"
                "- Cheque: From PDC/SPDC collection\n"
                "- Cash: Via Receipt document\n"
                "- Bank Transfer: NEFT/RTGS/UPI\n\n"
                "SUBMISSION:\n"
                "- Creates GL entries: Bank Dr, Loan Account Cr (principal), Interest Income Cr\n"
                "- Updates repayment schedule (marks EMI as paid)\n"
                "- Updates loan outstanding balance"
            ),
        },
        {
            "title": "How to create a Receipt",
            "content": (
                "Creating a Receipt (Cash/Payment collection):\n"
                "DocType: Receipt\n"
                "Module: NBFC\n\n"
                "REQUIRED FIELDS:\n"
                "- loan: Link to Loan\n"
                "- receipt_head: Receipt type (EMI, Foreclosure, Charges, etc.)\n"
                "- amount: Payment amount\n"
                "- mode_of_payment: Cash/Cheque/NEFT/UPI\n"
                "- posting_date: Receipt date\n\n"
                "RECEIPT TYPES (Receipt Head):\n"
                "- EMI Receipt: Regular installment payment\n"
                "- Part Payment: Extra payment toward principal\n"
                "- Foreclosure: Full loan pre-payment\n"
                "- Charges: Processing fee, bounce charges, etc.\n"
                "- Insurance: Insurance premium collection\n\n"
                "SUBMISSION:\n"
                "- Creates Loan Repayment (if EMI type)\n"
                "- Updates loan outstanding\n"
                "- Generates receipt number for customer\n\n"
                "CANCELLATION:\n"
                "- Receipt Cancellation Request: To reverse a receipt\n"
                "- Requires approval before cancellation"
            ),
        },
        {
            "title": "Common NBFC Queries and How to Answer Them",
            "content": (
                "Common NBFC Queries — Tool Usage Guide:\n\n"
                "Q: How many loans are disbursed this month?\n"
                "A: list_documents(doctype='Loan Disbursement', filters={'posting_date':['between',['2026-02-01','2026-02-28']], 'docstatus':1})\n\n"
                "Q: What is total outstanding loan amount?\n"
                "A: run_database_query('SELECT SUM(total_payment - total_amount_paid) as outstanding FROM `tabLoan` WHERE docstatus=1 AND status NOT IN (\"Closed\",\"Written Off\")')\n\n"
                "Q: Show all NPA accounts / overdue loans:\n"
                "A: list_documents(doctype='Loan', filters={'status':'Loan Closure Requested'}) or check Bucket classification\n\n"
                "Q: NACH bounce report this month:\n"
                "A: list_documents(doctype='NACH Settlement', filters={'posting_date':['between',[start,end]], 'status':'Bounced'})\n\n"
                "Q: Loan application status:\n"
                "A: get_document(doctype='Loan Application', name='<app_id>') — shows full details\n\n"
                "Q: Collection summary:\n"
                "A: run_database_query('SELECT mode_of_payment, SUM(amount_paid) FROM `tabLoan Repayment` WHERE posting_date BETWEEN ... GROUP BY mode_of_payment')\n\n"
                "Q: Branch-wise disbursement:\n"
                "A: run_database_query('SELECT branch, COUNT(*), SUM(disbursed_amount) FROM `tabLoan Disbursement` WHERE docstatus=1 GROUP BY branch')\n\n"
                "Q: Customer loan details:\n"
                "A: list_documents(doctype='Loan', filters={'applicant':'<customer_name>'}, fields=['name','loan_amount','total_amount_paid','status'])"
            ),
        },
    ]

    texts = [k["content"] for k in guides]
    metadatas = [{"source": "nbfc_doctype_guide", "title": k["title"]} for k in guides]
    from .rag import add_documents
    count = add_documents(texts, metadatas)
    print(f"[NBFC RAG] DocType Guides: {count} chunks")
    return count


def index_nbfc_collection():
    """Index collection and recovery workflow knowledge."""
    from .rag import add_documents, delete_by_source

    delete_by_source("nbfc_collection")

    knowledge = [
        {
            "title": "Collection & Recovery Process",
            "content": (
                "Collection & Recovery Workflow:\n\n"
                "STAGE 1 — SOFT COLLECTION (1-30 DPD):\n"
                "- SMS/WhatsApp reminders\n"
                "- Calling by tele-calling team\n"
                "- Loan Reminder sent (DocType: Loan Reminder)\n"
                "- Offer to pay via alternate mode\n\n"
                "STAGE 2 — FIRM COLLECTION (31-60 DPD):\n"
                "- Field visit by collection agent\n"
                "- Recovery Agents assigned\n"
                "- Collection Request Against Statement\n"
                "- Repayment Mode Change Request if needed\n\n"
                "STAGE 3 — HARD COLLECTION (61-90 DPD):\n"
                "- Legal notice sent (DocType: Notice)\n"
                "- Daily follow-up\n"
                "- Restructure offer (Loan Restructure)\n"
                "- Settlement discussion\n\n"
                "STAGE 4 — LEGAL/NPA (90+ DPD):\n"
                "- Account classified as NPA\n"
                "- Court Case filed (DocType: Court Case)\n"
                "- Repossession initiated (for secured loans)\n"
                "- Litigation module activated\n\n"
                "COLLECTION TOOLS:\n"
                "- Daily Cash Collection: Field agent cash pickup\n"
                "- Agent Money Deposit: Agent deposits at branch\n"
                "- Wallet: Agent wallet balance management\n"
                "- Wallet Settlement Activity: Settlement of agent wallets"
            ),
        },
        {
            "title": "Litigation Process in NBFC",
            "content": (
                "Litigation Module — Legal Recovery:\n\n"
                "NOTICE:\n"
                "- DocType: Notice\n"
                "- Types: Legal notice, demand notice, SARFAESI notice\n"
                "- Sent before filing court case\n\n"
                "COURT CASE:\n"
                "- DocType: Court Case\n"
                "- Case Type: Recovery suit, arbitration, SARFAESI, DRT\n"
                "- Forum: District Court, High Court, NCLT, DRT\n"
                "- Status tracking: Filed → Hearing → Order → Execution\n"
                "- Task CT: Action items and next dates\n"
                "- Expense CT: Legal expenses tracking\n\n"
                "COMPLIANCE:\n"
                "- Compliance Name: Regulatory compliance items\n"
                "- Trademark Document: IP protection\n\n"
                "KEY LEGAL ACTIONS:\n"
                "1. Section 138 (Cheque Bounce): Criminal complaint for bounced cheques\n"
                "2. SARFAESI Act: For secured loans > ₹20 lakhs\n"
                "3. Arbitration: As per loan agreement clause\n"
                "4. Civil Suit: Recovery suit in civil court\n"
                "5. DRT (Debt Recovery Tribunal): For debts > ₹20 lakhs"
            ),
        },
    ]

    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": "nbfc_collection", "title": k["title"]} for k in knowledge]
    from .rag import add_documents
    count = add_documents(texts, metadatas)
    print(f"[NBFC RAG] Collection: {count} chunks")
    return count


def index_nbfc_colending():
    """Index co-lending and borrowing knowledge."""
    from .rag import add_documents, delete_by_source

    delete_by_source("nbfc_colending")

    knowledge = [
        {
            "title": "Co-Lending Model",
            "content": (
                "Co-Lending (Co-Origination) Model:\n\n"
                "CONCEPT:\n"
                "- Bank + NBFC jointly fund a loan\n"
                "- Typical split: Bank 80% + NBFC 20%\n"
                "- Lower cost of funds → better rates for borrower\n"
                "- NBFC handles origination, bank provides capital\n\n"
                "FLOW:\n"
                "1. NBFC originates and assesses the loan\n"
                "2. Co-Lending Agreement with partner bank\n"
                "3. Loan sanctioned jointly\n"
                "4. Co-Funded Loan created with split details\n"
                "5. Disbursement: Bank portion + NBFC portion\n"
                "6. EMI collected by NBFC, shared with bank per schedule\n"
                "7. Co-Lending Repayment Schedule: Split of EMI between parties\n\n"
                "DocTypes:\n"
                "- Lending Partner: Bank/institution details\n"
                "- Co-Lending Agreement: Terms of partnership\n"
                "- Co-Funded Loan: Individual loan split details\n"
                "- Co-Lending Repayment Schedule: EMI split per installment\n"
                "- Co-Funding RS (child table): Repayment schedule rows\n\n"
                "BORROWING (Liability side):\n"
                "- Borrowing Application: NBFC borrows from bank/institution\n"
                "- Borrowing Agreement: Terms of borrowing\n"
                "- Borrowing Disbursement: Funds received\n"
                "- Borrowing Repayment: Repayment to lender\n"
                "- Borrowing Repayment Schedule: Repayment plan"
            ),
        },
        {
            "title": "Business Correspondent (BC) Model",
            "content": (
                "Business Correspondent (BC) Model:\n\n"
                "CONCEPT:\n"
                "- BC acts as agent for NBFC in remote/rural areas\n"
                "- Handles lead generation, cash collection, customer service\n"
                "- Earns commission on business sourced\n\n"
                "DocTypes:\n"
                "- Business Correspondent: BC master record\n"
                "- BC Partner: Partner registration\n"
                "- BC Territory (child table): Areas assigned to BC\n"
                "- BC Service (child table): Services offered by BC\n"
                "- BC Loan Agreement: Loan originated through BC\n"
                "- BC Commission Entry: Commission calculation and payment\n\n"
                "BC FLOW:\n"
                "1. BC registers as Business Correspondent\n"
                "2. Territory and services assigned\n"
                "3. BC sources leads and applications\n"
                "4. NBFC processes and disburses\n"
                "5. BC collects EMIs (cash/cheque)\n"
                "6. Commission calculated and paid\n"
                "7. Agent Money Deposit for collected cash"
            ),
        },
    ]

    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": "nbfc_colending", "title": k["title"]} for k in knowledge]
    from .rag import add_documents
    count = add_documents(texts, metadatas)
    print(f"[NBFC RAG] Co-Lending & BC: {count} chunks")
    return count
