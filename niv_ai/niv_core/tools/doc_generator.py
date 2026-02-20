"""
Document Generator for Niv AI
Generates PDFs from templates: Loan Agreements, Receipts, Statements, Letters.
Usage: Import in run_python_code MCP tool.
"""
import frappe
from frappe.utils import nowdate, fmt_money, getdate, formatdate
import json


# ─── Templates ────────────────────────────────────────────────────

TEMPLATES = {
    "loan_agreement": """
<html><head><style>
body { font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; padding: 40px; color: #333; }
h1 { text-align: center; font-size: 20px; border-bottom: 2px solid #333; padding-bottom: 10px; }
h2 { font-size: 15px; margin-top: 20px; color: #555; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; }
td { padding: 6px 10px; border: 1px solid #ddd; }
td:first-child { font-weight: bold; width: 35%; background: #f8f8f8; }
.signature { margin-top: 60px; display: flex; justify-content: space-between; }
.sig-block { width: 40%; border-top: 1px solid #333; padding-top: 5px; text-align: center; }
.footer { margin-top: 40px; font-size: 11px; color: #888; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }
</style></head><body>
<h1>LOAN AGREEMENT</h1>
<p style="text-align:center">Date: {{ date }}</p>

<h2>Parties</h2>
<table>
<tr><td>Lender</td><td>{{ company or "_______________" }}</td></tr>
<tr><td>Borrower</td><td>{{ customer_name or "_______________" }}</td></tr>
{% if customer_id %}<tr><td>Customer ID</td><td>{{ customer_id }}</td></tr>{% endif %}
{% if address %}<tr><td>Address</td><td>{{ address }}</td></tr>{% endif %}
</table>

<h2>Loan Details</h2>
<table>
{% if loan_id %}<tr><td>Loan ID</td><td>{{ loan_id }}</td></tr>{% endif %}
<tr><td>Loan Amount</td><td>{{ loan_amount }}</td></tr>
<tr><td>Interest Rate</td><td>{{ interest_rate }}% per annum</td></tr>
<tr><td>Tenure</td><td>{{ tenure }} months</td></tr>
<tr><td>EMI Amount</td><td>{{ emi_amount or "As per schedule" }}</td></tr>
<tr><td>Disbursement Date</td><td>{{ disbursement_date or date }}</td></tr>
{% if security %}<tr><td>Security/Collateral</td><td>{{ security }}</td></tr>{% endif %}
</table>

<h2>Terms & Conditions</h2>
<ol>
<li>The Borrower agrees to repay the loan amount along with interest as per the agreed schedule.</li>
<li>EMI payments are due on the {{ emi_day or "5th" }} of each month.</li>
<li>Late payment will attract a penalty of {{ late_fee or "2%" }} per month on the overdue amount.</li>
<li>The Borrower may prepay the loan subject to foreclosure charges as applicable.</li>
<li>The Lender reserves the right to recall the loan in case of default exceeding {{ default_days or "90" }} days.</li>
{% if extra_terms %}{% for term in extra_terms %}<li>{{ term }}</li>{% endfor %}{% endif %}
</ol>

<div class="signature">
<div class="sig-block">Authorized Signatory<br>({{ company or "Lender" }})</div>
<div class="sig-block">Borrower<br>({{ customer_name or "Borrower" }})</div>
</div>
<div class="footer">This is a computer-generated document. Generated on {{ date }} by {{ company or "the Lender" }}.</div>
</body></html>
""",

    "payment_receipt": """
<html><head><style>
body { font-family: Arial, sans-serif; font-size: 13px; padding: 40px; color: #333; }
h1 { text-align: center; font-size: 20px; }
.company { text-align: center; font-size: 16px; font-weight: bold; margin-bottom: 5px; }
table { width: 100%; border-collapse: collapse; margin: 15px 0; }
td { padding: 8px 12px; border: 1px solid #ddd; }
td:first-child { font-weight: bold; width: 35%; background: #f8f8f8; }
.amount-box { text-align: center; font-size: 24px; font-weight: bold; color: #2e7d32; margin: 20px 0; padding: 15px; background: #e8f5e9; border-radius: 8px; }
.footer { margin-top: 30px; font-size: 11px; color: #888; text-align: center; }
</style></head><body>
{% if company %}<div class="company">{{ company }}</div>{% endif %}
<h1>PAYMENT RECEIPT</h1>
<p style="text-align:center">Receipt No: {{ receipt_no or "AUTO" }} | Date: {{ date }}</p>

<div class="amount-box">₹ {{ amount }}</div>

<table>
<tr><td>Received From</td><td>{{ customer_name or "_______________" }}</td></tr>
{% if customer_id %}<tr><td>Customer ID</td><td>{{ customer_id }}</td></tr>{% endif %}
{% if loan_id %}<tr><td>Against Loan</td><td>{{ loan_id }}</td></tr>{% endif %}
<tr><td>Amount</td><td>₹ {{ amount }}</td></tr>
{% if amount_words %}<tr><td>Amount in Words</td><td>{{ amount_words }}</td></tr>{% endif %}
<tr><td>Payment Mode</td><td>{{ payment_mode or "Cash" }}</td></tr>
{% if reference_no %}<tr><td>Reference No</td><td>{{ reference_no }}</td></tr>{% endif %}
{% if reference_date %}<tr><td>Reference Date</td><td>{{ reference_date }}</td></tr>{% endif %}
{% if remarks %}<tr><td>Remarks</td><td>{{ remarks }}</td></tr>{% endif %}
</table>

<div style="margin-top:50px; width:40%; border-top:1px solid #333; padding-top:5px; text-align:center;">
Authorized Signatory
</div>
<div class="footer">This is a computer-generated receipt. Generated on {{ date }}.</div>
</body></html>
""",

    "statement_of_account": """
<html><head><style>
body { font-family: Arial, sans-serif; font-size: 12px; padding: 30px; color: #333; }
h1 { text-align: center; font-size: 18px; }
.header-table { width: 100%; margin-bottom: 20px; }
.header-table td { border: none; padding: 4px 8px; }
table.ledger { width: 100%; border-collapse: collapse; margin: 10px 0; }
table.ledger th { background: #333; color: #fff; padding: 8px; text-align: left; font-size: 11px; }
table.ledger td { padding: 6px 8px; border-bottom: 1px solid #eee; font-size: 11px; }
table.ledger tr:nth-child(even) { background: #f9f9f9; }
.total-row td { font-weight: bold; border-top: 2px solid #333; background: #f0f0f0; }
.summary { margin-top: 15px; padding: 10px; background: #e3f2fd; border-radius: 6px; }
.footer { margin-top: 20px; font-size: 10px; color: #888; text-align: center; }
</style></head><body>
{% if company %}<p style="text-align:center;font-size:16px;font-weight:bold;">{{ company }}</p>{% endif %}
<h1>STATEMENT OF ACCOUNT</h1>

<table class="header-table">
<tr><td><b>Customer:</b> {{ customer_name }}</td><td><b>Period:</b> {{ from_date }} to {{ to_date }}</td></tr>
{% if customer_id %}<tr><td><b>Customer ID:</b> {{ customer_id }}</td><td><b>Generated:</b> {{ date }}</td></tr>{% endif %}
</table>

<table class="ledger">
<tr><th>#</th><th>Date</th><th>Description</th><th>Debit (₹)</th><th>Credit (₹)</th><th>Balance (₹)</th></tr>
{% if opening_balance %}<tr><td></td><td>{{ from_date }}</td><td>Opening Balance</td><td></td><td></td><td>{{ opening_balance }}</td></tr>{% endif %}
{% for entry in entries %}
<tr>
<td>{{ loop.index }}</td>
<td>{{ entry.date }}</td>
<td>{{ entry.description or entry.voucher or "" }}</td>
<td>{{ entry.debit or "" }}</td>
<td>{{ entry.credit or "" }}</td>
<td>{{ entry.balance or "" }}</td>
</tr>
{% endfor %}
<tr class="total-row">
<td colspan="3">Total / Closing Balance</td>
<td>{{ total_debit or "" }}</td>
<td>{{ total_credit or "" }}</td>
<td>{{ closing_balance or "" }}</td>
</tr>
</table>

{% if summary %}
<div class="summary">{{ summary }}</div>
{% endif %}
<div class="footer">This is a computer-generated statement. Generated on {{ date }}.</div>
</body></html>
""",

    "letter": """
<html><head><style>
body { font-family: Arial, sans-serif; font-size: 13px; line-height: 1.8; padding: 50px; color: #333; }
.letterhead { text-align: center; font-size: 18px; font-weight: bold; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }
.ref-line { font-size: 12px; color: #555; margin-bottom: 20px; }
.address { margin-bottom: 20px; }
.subject { font-weight: bold; text-decoration: underline; margin: 15px 0; }
.body-text { text-align: justify; }
.closing { margin-top: 40px; }
.sig-block { margin-top: 50px; }
.footer { margin-top: 40px; font-size: 10px; color: #888; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }
</style></head><body>

{% if company %}<div class="letterhead">{{ company }}</div>{% endif %}

<div class="ref-line">
Date: {{ date }}<br>
{% if ref_no %}Ref: {{ ref_no }}<br>{% endif %}
</div>

<div class="address">
To,<br>
<b>{{ recipient_name or "_______________" }}</b><br>
{% if recipient_address %}{{ recipient_address }}<br>{% endif %}
</div>

<div class="subject">Subject: {{ subject }}</div>

<div class="body-text">
{{ body }}
</div>

<div class="closing">
Yours faithfully,<br>
<b>{{ company or "_______________" }}</b>
</div>

<div class="sig-block">
___________________<br>
Authorized Signatory
</div>

<div class="footer">This is a computer-generated letter. Generated on {{ date }}.</div>
</body></html>
"""
}


# ─── Generator Functions ──────────────────────────────────────────

def generate_document(template_name: str, data: dict, filename: str = None) -> str:
    """Generate a PDF document from template.
    
    Args:
        template_name: One of 'loan_agreement', 'payment_receipt', 'statement_of_account', 'letter'
        data: Dict of template variables
        filename: Optional filename (auto-generated if not provided)
    
    Returns:
        file_url of generated PDF
    """
    from frappe.utils.pdf import get_pdf
    from jinja2 import Template
    
    if template_name not in TEMPLATES:
        return f"Unknown template: {template_name}. Available: {', '.join(TEMPLATES.keys())}"
    
    # Add defaults
    data.setdefault("date", formatdate(nowdate()))
    data.setdefault("company", frappe.db.get_default("company"))
    
    # Render HTML
    html = Template(TEMPLATES[template_name]).render(**data)
    
    # Generate PDF
    pdf_content = get_pdf(html, options={
        "page-size": "A4",
        "margin-top": "15mm",
        "margin-bottom": "15mm",
        "margin-left": "15mm",
        "margin-right": "15mm",
    })
    
    # Save as file
    if not filename:
        safe_name = (data.get("customer_name") or data.get("recipient_name") or "document").replace(" ", "_")
        filename = f"{template_name}_{safe_name}_{nowdate()}.pdf"
    
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename,
        "content": pdf_content,
        "is_private": 1,
        "folder": "Home/Niv AI",
    })
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    
    return file_doc.file_url


def generate_loan_agreement(customer_name: str, loan_amount: str, interest_rate: str, 
                            tenure: str, **kwargs) -> str:
    """Generate Loan Agreement PDF.
    
    Example: generate_loan_agreement("Rajesh Kumar", "5,00,000", "12", "24")
    """
    data = {
        "customer_name": customer_name,
        "loan_amount": loan_amount,
        "interest_rate": interest_rate,
        "tenure": tenure,
        **kwargs
    }
    return generate_document("loan_agreement", data)


def generate_receipt(customer_name: str, amount: str, **kwargs) -> str:
    """Generate Payment Receipt PDF.
    
    Example: generate_receipt("Rajesh Kumar", "25,000", payment_mode="UPI", loan_id="LN-001")
    """
    data = {"customer_name": customer_name, "amount": amount, **kwargs}
    return generate_document("payment_receipt", data)


def generate_statement(customer_name: str, from_date: str, to_date: str, 
                       entries: list, **kwargs) -> str:
    """Generate Statement of Account PDF.
    
    entries: list of dicts with keys: date, description, debit, credit, balance
    Example: generate_statement("Rajesh Kumar", "2026-01-01", "2026-02-20", 
                                [{"date": "2026-01-05", "description": "EMI", "credit": "25,000", "balance": "4,75,000"}])
    """
    data = {
        "customer_name": customer_name,
        "from_date": from_date,
        "to_date": to_date,
        "entries": entries,
        **kwargs
    }
    return generate_document("statement_of_account", data)


def generate_letter(recipient_name: str, subject: str, body: str, **kwargs) -> str:
    """Generate formal letter PDF.
    
    Example: generate_letter("Rajesh Kumar", "Recovery Notice", "This is to inform you...")
    """
    data = {"recipient_name": recipient_name, "subject": subject, "body": body, **kwargs}
    return generate_document("letter", data)
