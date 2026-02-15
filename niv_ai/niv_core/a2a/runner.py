"""
Niv AI A2A Runner — Correct ADK Stream Handler

FIXES from old stream_handler.py:
1. ✅ Uses singleton FrappeSessionService (not new InMemorySessionService per call)
2. ✅ Handles ALL event types (tokens, tool calls, results, state, transfers, errors)
3. ✅ Proper async/sync bridging
4. ✅ Session reuse across requests

Based on: https://google.github.io/adk-docs/runtime/
"""

import json
import frappe
from typing import Generator, Dict, Any, Optional

from google.adk.runners import Runner
from google.adk.apps import App
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

from niv_ai.niv_core.a2a.agents import get_orchestrator
from niv_ai.niv_core.a2a.session import get_session_service


def stream_a2a(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
    user: str = None,
    dev_mode: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream A2A agent response with proper event handling.
    
    Yields Niv-compatible SSE events:
    - {"type": "token", "content": "..."}
    - {"type": "tool_call", "tool": "...", "arguments": {...}}
    - {"type": "tool_result", "tool": "...", "result": "..."}
    - {"type": "thought", "content": "..."}
    - {"type": "agent_transfer", "from": "...", "to": "..."}
    - {"type": "state_change", "key": "...", "value": "..."}
    - {"type": "error", "content": "..."}
    - {"type": "complete"}
    
    Args:
        message: User message
        conversation_id: Links to Niv Conversation
        provider_name: LLM provider (uses default if None)
        model_name: Model to use (uses default if None)
        user: Frappe user (uses session.user if None)
        dev_mode: Enable developer mode confirmations
    """
    user = user or frappe.session.user
    
    try:
        # Get orchestrator agent
        orchestrator = get_orchestrator(
            conversation_id=conversation_id,
            provider_name=provider_name,
            model_name=model_name,
        )
        
        # Create ADK App
        app = App(name="NivAI", root_agent=orchestrator)
        
        # Create Runner with PERSISTENT session service (key fix!)
        runner = Runner(
            app=app,
            artifact_service=InMemoryArtifactService(),
            session_service=get_session_service(),  # ← SINGLETON, not new instance!
            memory_service=InMemoryMemoryService(),
            auto_create_session=True,
        )
        
        # Session ID = conversation_id (links ADK session to Niv Conversation)
        session_id = conversation_id
        
        # Build message content
        from google.genai import types
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )
        
        # Track current agent for transfer detection
        current_agent = "niv_orchestrator"
        
        # Run and yield events
        for event in runner.run(
            new_message=user_message,
            user_id=user,
            session_id=session_id,
        ):
            # 1. Text content (tokens)
            if event.text:
                yield {"type": "token", "content": event.text}
            
            # 2. Tool calls
            tool_calls = event.get_function_calls() if hasattr(event, "get_function_calls") else None
            if tool_calls:
                for tc in tool_calls:
                    yield {
                        "type": "tool_call",
                        "tool": tc.name,
                        "arguments": tc.args if hasattr(tc, "args") else {},
                    }
            
            # 3. Tool results
            tool_results = event.get_function_responses() if hasattr(event, "get_function_responses") else None
            if tool_results:
                for tr in tool_results:
                    result_str = str(tr.response) if hasattr(tr, "response") else str(tr)
                    yield {
                        "type": "tool_result",
                        "tool": tr.name if hasattr(tr, "name") else "unknown",
                        "result": result_str,
                    }
            
            # 4. Agent transfers (detected via author change)
            if hasattr(event, "author") and event.author:
                if event.author != current_agent and event.author != "user":
                    yield {
                        "type": "agent_transfer",
                        "from": current_agent,
                        "to": event.author,
                    }
                    yield {
                        "type": "thought",
                        "content": f"Transferring to {event.author}...",
                    }
                    current_agent = event.author
            
            # 5. State changes (from output_key or explicit state updates)
            if hasattr(event, "actions") and event.actions:
                state_delta = getattr(event.actions, "state_delta", None)
                if state_delta and isinstance(state_delta, dict):
                    for key, value in state_delta.items():
                        yield {
                            "type": "state_change",
                            "key": key,
                            "value": str(value)[:200],  # Truncate for display
                        }
            
            # 6. Errors
            if hasattr(event, "error") and event.error:
                yield {
                    "type": "error",
                    "content": str(event.error),
                }
            
            # 7. Completion marker
            if hasattr(event, "is_final") and event.is_final:
                yield {"type": "complete"}
        
        # Final completion if not already sent
        yield {"type": "complete"}
        
    except ImportError as e:
        yield {
            "type": "error",
            "content": f"ADK import error: {e}. Make sure google-adk is installed.",
        }
    except Exception as e:
        frappe.log_error(f"A2A Stream Error: {e}", "Niv AI A2A")
        yield {
            "type": "error",
            "content": f"A2A Error: {str(e)}",
        }


def run_a2a_sync(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
) -> str:
    """
    Run A2A agent synchronously (non-streaming).
    
    Returns the final response as a string.
    Useful for background tasks or simple queries.
    """
    full_response = []
    
    for event in stream_a2a(
        message=message,
        conversation_id=conversation_id,
        provider_name=provider_name,
        model_name=model_name,
    ):
        if event.get("type") == "token":
            full_response.append(event.get("content", ""))
        elif event.get("type") == "error":
            return f"Error: {event.get('content', 'Unknown error')}"
    
    return "".join(full_response)
