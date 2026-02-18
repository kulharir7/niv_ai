import frappe, os, json
os.chdir("/home/gws/frappe-bench/sites")
frappe.init(site="erp024.growthsystem.in")
frappe.connect()

for dt in ["Loan", "Loan Application", "Loan Repayment", "Customer"]:
    try:
        meta = frappe.get_meta(dt)
        fields = [{"name": f.fieldname, "type": f.fieldtype, "label": f.label} 
                  for f in meta.fields if f.fieldtype not in ("Section Break", "Column Break", "Tab Break")]
        print(f"\n=== {dt} ({len(fields)} fields) ===")
        # Show first 20 most important
        for f in fields[:25]:
            print(f"  {f['name']} ({f['type']}): {f['label']}")
        if len(fields) > 25:
            print(f"  ... and {len(fields)-25} more")
    except Exception as e:
        print(f"=== {dt}: ERROR {e} ===")

# Also check what status values exist
print("\n=== Loan Status Values ===")
try:
    statuses = frappe.db.sql("SELECT DISTINCT status FROM `tabLoan` LIMIT 20", as_dict=True)
    print([s.status for s in statuses])
except Exception as e:
    print(f"ERROR: {e}")

print("\n=== Loan Application Status Values ===")
try:
    statuses = frappe.db.sql("SELECT DISTINCT status FROM `tabLoan Application` LIMIT 20", as_dict=True)
    print([s.status for s in statuses])
except Exception as e:
    print(f"ERROR: {e}")

frappe.destroy()
