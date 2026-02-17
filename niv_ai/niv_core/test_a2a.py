
import frappe
from niv_ai.niv_core.a2a.runner import stream_a2a

def test():
    # Find a conversation
    conv = frappe.get_all("Niv Conversation", limit=1)
    if not conv:
        print("No conversation found")
        return
    
    conv_id = conv[0].name
    print(f"Testing A2A Stream for conversation: {conv_id}")
    
    for event in stream_a2a(
        message="Hello, who are you and what tools do you have?",
        conversation_id=conv_id
    ):
        etype = event.get('type')
        print(f"EVENT: {etype} | Content: {str(event.get('content', event.get('value', '')))[:200]}")
        if etype == 'tool_call':
            print(f"  TOOL: {event.get('tool')} ({event.get('arguments')})")
        elif etype == 'error':
            print(f"  ERROR: {event.get('content')}")

if __name__ == "__main__":
    test()
