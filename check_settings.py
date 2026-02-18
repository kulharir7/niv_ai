import frappe, os
os.chdir("/home/gws/frappe-bench/sites")
frappe.init(site="erp024.growthsystem.in")
frappe.connect()
s = frappe.get_single("Niv Settings")
fields = ["default_provider","default_model","model_light","model_medium","model_heavy","max_tokens_per_message","enable_agent_routing","enable_a2a","enable_knowledge_base"]
for f in fields:
    print(f + ": " + str(getattr(s, f, "N/A")))

# Check system prompt size
from niv_ai.niv_core.langchain.memory import get_system_prompt
sp = get_system_prompt()
print("system_prompt_chars: " + str(len(sp)))

# Check tool count
from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached
tools = get_all_mcp_tools_cached()
print("mcp_tools_count: " + str(len(tools)))
for t in tools:
    print("  tool: " + t.get("function",{}).get("name","?"))

frappe.destroy()
