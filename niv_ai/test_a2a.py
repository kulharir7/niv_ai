"""
Quick A2A Test Script
"""
import frappe
import json

def test_a2a_full():
    """Test A2A with actual query."""
    from niv_ai.niv_core.a2a.runner import stream_a2a, run_a2a_sync
    
    print("=" * 50)
    print("Testing A2A with: 'List all customers'")
    print("=" * 50)
    
    events = []
    for event in stream_a2a(
        message="List all customers",
        conversation_id="test_conv_001",
    ):
        events.append(event)
        event_type = event.get("type", "")
        
        if event_type == "token":
            print(f"TOKEN: {event.get('content', '')[:100]}")
        elif event_type == "tool_call":
            print(f"TOOL CALL: {event.get('tool')} with {event.get('arguments')}")
        elif event_type == "tool_result":
            print(f"TOOL RESULT: {event.get('tool')} -> {event.get('result', '')[:200]}")
        elif event_type == "agent_transfer":
            print(f"TRANSFER: {event.get('from')} -> {event.get('to')}")
        elif event_type == "thought":
            print(f"THOUGHT: {event.get('content')}")
        elif event_type == "error":
            print(f"ERROR: {event.get('content')}")
        elif event_type == "complete":
            print("COMPLETE")
    
    print("=" * 50)
    print(f"Total events: {len(events)}")
    
    # Count by type
    type_counts = {}
    for e in events:
        t = e.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"Event types: {json.dumps(type_counts)}")
    
    return {"success": True, "event_count": len(events), "types": type_counts}
