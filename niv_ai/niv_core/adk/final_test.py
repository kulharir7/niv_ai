"""
Final Server-Side real data test.
"""
import frappe
import json
from niv_ai.niv_core.adk.stream_handler import stream_agent_adk

def run_test():
    frappe.connect()
    # Find Administrator conversation
    conv = frappe.get_all("Niv Conversation", filters={"user": "Administrator"}, limit=1)
    if not conv:
        # Fallback to any
        conv = frappe.get_all("Niv Conversation", limit=1)
    
    conv_id = conv[0].name
    print(f"Testing on server with conv: {conv_id}")
    
    gen = stream_agent_adk(
        message="System mein last 3 Loan Applications ke real amounts batao.",
        conversation_id=conv_id,
        user="Administrator"
    )
    
    for evt in gen:
        if evt.get("type") == "token":
            print(evt.get("content"), end="", flush=True)
        elif evt.get("type") == "tool_call":
            print(f"\n[TOOL CALL: {evt.get('tool')}]")
        elif evt.get("type") == "tool_result":
            print(f"\n[TOOL RESULT: {evt.get('tool')}]")

if __name__ == "__main__":
    run_test()
