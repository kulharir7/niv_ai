"""
ADK Stream Handler — Bridges Google ADK to Niv AI SSE format.
Ensures no existing functionality breaks.
"""
import json
import frappe
from google.adk.runners import InMemoryRunner
from google.adk.apps import App
from niv_ai.niv_core.adk.agent_factory import get_orchestrator


def stream_agent_adk(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
    user: str = None,
    dev_mode: bool = False,
):
    """Synchronous generator yielding Niv-compatible SSE events using ADK."""
    user = user or frappe.session.user
    
    orchestrator = get_orchestrator(conversation_id, provider_name, model_name)
    app = App(name="NivAI", root_agent=orchestrator)
    runner = InMemoryRunner(app=app)
    
    # ADK sessions are separate from Niv Conversations but linked by ID
    session_id = conversation_id
    
    try:
        # Use runner.run() which is a synchronous generator
        for event in runner.run(
            new_message=message,
            user_id=user,
            session_id=session_id
        ):
            # 1. Handle Tokens (Text content)
            if event.text:
                yield {"type": "token", "content": event.text}
            
            # 2. Handle Tool Calls
            tool_calls = event.get_function_calls()
            if tool_calls:
                for tc in tool_calls:
                    yield {
                        "type": "tool_call", 
                        "tool": tc.name, 
                        "arguments": tc.args
                    }
            
            # 3. Handle Tool Results
            tool_results = event.get_function_responses()
            if tool_results:
                for tr in tool_results:
                    # Learning Logic
                    if "error" in str(tr.response).lower():
                        _log_learning_opportunity(tr.name, str(tr.response))

                    yield {
                        "type": "tool_result",
                        "tool": tr.name,
                        "result": str(tr.response)
                    }
            
            # 4. Handle "Thinking" (Author change or internal events)
            if event.author != "user" and not event.text and not tool_calls:
                # Potential "Thinking" block or agent transfer
                if event.author != "niv_orchestrator":
                    yield {"type": "thought", "content": f"Handed control to {event.author}..."}

    except Exception as e:
        frappe.log_error(f"ADK Stream Error: {e}", "Niv AI ADK")
        yield {"type": "error", "content": f"A2A Error: {str(e)}"}

def _log_learning_opportunity(tool_name: str, error_msg: str):
    """Record mistakes to improve the AI's future performance."""
    try:
        from niv_ai.niv_core.adk.discovery import DiscoveryEngine
        summary = f"FAIL: Tool '{tool_name}' failed with error: {error_msg}. Avoid this sequence in future."
        DiscoveryEngine()._log_to_brain({"custom_doctypes": [], "active_workflows": [], "nbfc_related": {}, "correction": summary})
    except Exception:
        pass
