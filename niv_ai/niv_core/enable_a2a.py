
import frappe
def enable():
    frappe.db.set_single_value('Niv Settings', 'enable_a2a', 1)
    frappe.db.commit()
    print("A2A Enabled in Settings")
if __name__ == "__main__":
    enable()
