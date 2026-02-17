import frappe
import json

def check_data():
    frappe.connect()
    # Check schema
    meta = frappe.get_meta("Repayment Schedule")
    print(f"DocType: {meta.name}")
    print("Fields in Repayment Schedule:")
    for f in meta.fields:
        if f.fieldtype in ('Currency', 'Float', 'Date', 'Select'):
            print(f"- {f.fieldname} ({f.fieldtype})")

    # Check some data
    res = frappe.db.sql("""
        SELECT parent, payment_date, principal_amount, interest_amount, total_payment 
        FROM `tabRepayment Schedule` 
        WHERE total_payment > 0 
        LIMIT 5
    """, as_dict=1)
    
    print("\nReal Data Samples:")
    print(json.dumps(res, indent=2, default=str))

if __name__ == "__main__":
    check_data()
