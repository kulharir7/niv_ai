
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
        print(f"EVENT: {event.get('type')} | Content: {str(event.get('content', ''))[:100]}")
        if event.get('type') == 'tool_call':
            print(f"  TOOL: {event.get('tool')} ({event.get('arguments')})")

if __name__ == "__main__":
    test()
