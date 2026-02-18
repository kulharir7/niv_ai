import frappe, os
os.chdir("/home/gws/frappe-bench/sites")
frappe.init(site="erp024.growthsystem.in")
frappe.connect()
from niv_ai.niv_core.langchain.memory import get_system_prompt
sp = get_system_prompt()
with open("/tmp/system_prompt_dump.txt", "w") as f:
    f.write(sp)
print("TOTAL_CHARS: " + str(len(sp)))

# Also check what discovery adds
try:
    from niv_ai.niv_core.knowledge.unified_discovery import get_discovery_for_agent
    dc = get_discovery_for_agent()
    print("DISCOVERY_CHARS: " + str(len(dc or "")))
except Exception as e:
    print("DISCOVERY_ERROR: " + str(e))

frappe.destroy()
