"""
Niv AI A2A Runner — COMPLETE ADK Stream Handler (v2)

REWRITTEN for reliability. Every event type properly handled.

KEY CHANGES from v1:
1. Check event.text + event.content + event.parts (all 3 ways ADK returns text)
2. Track which results already yielded (no duplicates)
3. Proper agent transfer detection
4. Timeout protection
5. Debug logging for troubleshooting
"""

import json
import time
import traceback
from typing import Generator, Dict, Any, Optional, List, Set

import frappe

# ADK v1.0.0 imports
from google.adk.runners import (
    Runner,
    InMemoryArtifactService,
    InMemoryMemoryService,
    InMemorySessionService,
)

from niv_ai.niv_core.a2a.agents import get_orchestrator
from niv_ai.niv_core.a2a.session import get_session_service


# ─────────────────────────────────────────────────────────────────
# EVENT TYPES (match niv_chat.js expectations)
# ─────────────────────────────────────────────────────────────────

EVENT_TOKEN = "token"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_THOUGHT = "thought"
EVENT_AGENT_TRANSFER = "agent_transfer"
EVENT_STATE_CHANGE = "state_change"
EVENT_ERROR = "error"
EVENT_COMPLETE = "complete"

# Agent display names
AGENT_NAMES = {
    "niv_orchestrator": "🎯 Orchestrator",
    "frappe_coder": "💻 Frappe Developer",
    "data_analyst": "📊 Data Analyst",
    "nbfc_specialist": "🏦 NBFC Specialist",
    "system_discovery": "🔍 System Discovery",
    "niv_critique": "✅ Quality Check",
    "niv_planner": "📋 Planner",
}


# ─────────────────────────────────────────────────────────────────
# HELPER: Extract text from ADK event (multiple ways)
# ─────────────────────────────────────────────────────────────────

def _extract_text(event) -> str:
    """
    ADK events can have text in multiple places:
    1. event.text (most common)
    2. event.content.parts[].text (Content object)
    3. event.parts[].text (Parts directly)
    
    Returns extracted text or empty string.
    """
    raw = ""
    
    # Method 1: Direct text attribute
    if hasattr(event, "text") and event.text:
        raw = str(event.text)
    
    # Method 2: Content object with parts
    elif hasattr(event, "content") and event.content:
        content = event.content
        if hasattr(content, "parts") and content.parts:
            texts = []
            for part in content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(str(part.text))
            if texts:
                raw = "\n".join(texts)
    
    # Method 3: Direct parts
    elif hasattr(event, "parts") and event.parts:
        texts = []
        for part in event.parts:
            if hasattr(part, "text") and part.text:
                texts.append(str(part.text))
        if texts:
            raw = "\n".join(texts)
    
    return raw


def _is_meaningful_text(text: str) -> bool:
    """Check if text is meaningful (not empty, not just JSON, not just whitespace, not internal agent signals)."""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) < 5:
        return False
    
    # Skip critique agent outputs (internal signals, not user-facing)
    _critique_signals = {"PASSED", "FAILED", "APPROVED", "REJECTED"}
    if stripped.upper() in _critique_signals:
        return False
    if stripped.upper().startswith("PASSED") and len(stripped) < 20:
        return False
    if stripped.upper().startswith("FAILED:") and len(stripped) < 100:
        return False
    
    # Skip pure JSON objects (tool results get stored in state too)
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            # If it's a tool result dict, skip it
            if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed or "content" in parsed):
                return False
        except (json.JSONDecodeError, ValueError):
            pass  # Not JSON, could be text starting with {
    return True


# ─────────────────────────────────────────────────────────────────
# MAIN STREAMING FUNCTION
# ─────────────────────────────────────────────────────────────────

def stream_a2a(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
    user: str = None,
    dev_mode: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream A2A agent response.
    
    Yields SSE-compatible events for niv_chat.js:
    - token: Text content chunks
    - tool_call: Tool being called
    - tool_result: Tool response
    - thought: Thinking/processing status
    - agent_transfer: Agent handoff with names
    - error: Error message
    - complete: Stream finished
    """
    user = user or frappe.session.user
    site = getattr(frappe.local, "site", None)
    
    # Tracking
    current_agent = "niv_orchestrator"
    seen_agents: List[str] = []
    yielded_results: Set[str] = set()  # Track which *_result keys we already sent
    yielded_content_hashes: Set[int] = set()  # Track content hashes to prevent duplicate text
    yielded_full_text = ""  # Track full text we've sent to detect streaming duplicates
    has_yielded_text = False
    start_time = time.time()
    
    _log(f"A2A START: user={user}, conv={conversation_id}, msg={message[:50]}...")
    
    try:
        # ─── 1. CREATE ORCHESTRATOR ───
        try:
            orchestrator = get_orchestrator(
                conversation_id=conversation_id,
                provider_name=provider_name,
                model_name=model_name,
            )
            _log(f"Orchestrator created with {len(orchestrator.sub_agents)} sub_agents")
        except Exception as e:
            _log(f"Orchestrator creation FAILED: {e}")
            yield {"type": EVENT_ERROR, "content": f"Failed to create orchestrator: {e}"}
            return
        
        # ─── 2. CREATE RUNNER ───
        try:
            session_service = get_session_service(site=site)
            runner = Runner(
                app_name="NivAI",
                agent=orchestrator,
                artifact_service=InMemoryArtifactService(),
                session_service=session_service,
                memory_service=InMemoryMemoryService(),
            )
        except Exception as e:
            _log(f"Runner creation FAILED: {e}")
            yield {"type": EVENT_ERROR, "content": f"Failed to create ADK runner: {e}"}
            return
        
        # ─── 3. SETUP SESSION ───
        session_id = conversation_id
        try:
            required_keys = {
                "coder_result": "", "analyst_result": "", "nbfc_result": "",
                "discovery_result": "", "critique_result": "", "planner_result": "",
                "orchestrator_result": "", "user_memory": "No prior memory.",
                "nbfc_context": {}
            }
            
            existing = session_service.get_session_sync(
                app_name="NivAI", user_id=user, session_id=session_id
            )
            
            if not existing:
                session_service.create_session_sync(
                    app_name="NivAI", user_id=user, session_id=session_id, state=required_keys
                )
            else:
                state = existing.state or {}
                updated = False
                for k, v in required_keys.items():
                    if k not in state:
                        state[k] = v
                        updated = True
                if updated:
                    session_service.update_session_sync(
                        app_name="NivAI", user_id=user, session_id=session_id, state=state
                    )
        except Exception as e:
            _log(f"Session setup FAILED: {e}")
            yield {"type": EVENT_ERROR, "content": f"Session setup failed: {e}"}
            return
        
        # ─── 4. BUILD MESSAGE ───
        from google.genai import types
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )
        
        # ─── 5. STREAM EVENTS ───
        yield {"type": EVENT_THOUGHT, "content": "Processing request..."}
        
        import re
        _thought_pattern = re.compile(r'\[\[THOUGHT\]\](.*?)\[\[/THOUGHT\]\]', re.DOTALL)
        _thought_tag_fragments = {'[[', ']]', '[[/', 'THOUGHT', '[[THOUGHT]]', '[[/THOUGHT]]',
                                   '[', ']', 'TH', 'O', 'UGHT', '/TH', '/'}
        thought_buffer = ""
        
        event_count = 0
        for event in runner.run(
            new_message=user_message,
            user_id=user,
            session_id=session_id,
        ):
            event_count += 1
            elapsed = time.time() - start_time
            
            # Safety timeout (3 minutes)
            if elapsed > 180:
                _log(f"TIMEOUT after {elapsed:.0f}s, {event_count} events")
                yield {"type": EVENT_ERROR, "content": "Request timed out (3 min limit)"}
                break
            
            # ─── TEXT (3 methods) ───
            text = _extract_text(event)
            if text and _is_meaningful_text(text):
                # Handle [[THOUGHT]] tags — convert to thought events, not visible text
                if '[[THOUGHT]]' in text and '[[/THOUGHT]]' in text:
                    thought_match = _thought_pattern.search(text)
                    if thought_match:
                        thought_text = thought_match.group(1).strip()
                        if thought_text:
                            yield {"type": EVENT_THOUGHT, "content": thought_text}
                            _log(f"EVENT #{event_count}: THOUGHT ({len(thought_text)} chars)")
                        clean_text = _thought_pattern.sub('', text).strip()
                        if clean_text and _is_meaningful_text(clean_text):
                            text = clean_text
                        else:
                            continue  # Only thought tags, skip
                
                # Skip streaming thought tag fragments (word-by-word: "[[", "TH", "OUGHT", "]]")
                stripped = text.strip()
                if stripped in _thought_tag_fragments:
                    thought_buffer += text
                    _log(f"EVENT #{event_count}: buffer thought fragment: {repr(stripped)}")
                    continue
                
                # If we were buffering thought fragments, check for completion
                if thought_buffer:
                    thought_buffer += text
                    if '[[/THOUGHT]]' in thought_buffer:
                        thought_match2 = _thought_pattern.search(thought_buffer)
                        if thought_match2:
                            yield {"type": EVENT_THOUGHT, "content": thought_match2.group(1).strip()}
                        clean = _thought_pattern.sub('', thought_buffer).strip()
                        thought_buffer = ""
                        if clean and _is_meaningful_text(clean):
                            text = clean
                        else:
                            continue
                    elif len(thought_buffer) > 500:
                        # Too long without closing tag, flush as text
                        text = thought_buffer
                        thought_buffer = ""
                    else:
                        continue  # Still accumulating
                
                # Deduplicate: don't yield same content twice
                content_hash = hash(text.strip()[:200])  # Hash first 200 chars
                
                # Also check if this streaming token is part of already-yielded full text
                is_streaming_duplicate = False
                if len(text) < 50 and yielded_full_text:
                    # Short token — check if it's part of a previously yielded full response
                    # This catches: full block yielded first → same text streamed word-by-word later
                    check_text = text.strip()
                    if check_text and check_text in yielded_full_text:
                        is_streaming_duplicate = True
                
                if content_hash not in yielded_content_hashes and not is_streaming_duplicate:
                    yielded_content_hashes.add(content_hash)
                    has_yielded_text = True
                    yield {"type": EVENT_TOKEN, "content": text}
                    yielded_full_text += text
                    _log(f"EVENT #{event_count}: TOKEN ({len(text)} chars) from {current_agent}")
                else:
                    _log(f"EVENT #{event_count}: SKIP duplicate token ({len(text)} chars)")
            
            # ─── TOOL CALLS ───
            if hasattr(event, "get_function_calls"):
                calls = event.get_function_calls()
                if calls:
                    for tc in calls:
                        name = getattr(tc, "name", "unknown")
                        args = getattr(tc, "args", {})
                        # Skip internal transfer_to_agent tool display
                        if name == "transfer_to_agent":
                            _log(f"EVENT #{event_count}: TRANSFER via tool → {args}")
                        else:
                            yield {
                                "type": EVENT_TOOL_CALL,
                                "tool": name,
                                "arguments": args,
                                "agent": current_agent,
                            }
                            _log(f"EVENT #{event_count}: TOOL_CALL {name}")
            
            # ─── TOOL RESULTS ───
            if hasattr(event, "get_function_responses"):
                responses = event.get_function_responses()
                if responses:
                    for tr in responses:
                        name = getattr(tr, "name", "unknown")
                        response = getattr(tr, "response", str(tr))
                        
                        if name == "transfer_to_agent":
                            continue  # Skip transfer results
                        
                        result_str = str(response)
                        if len(result_str) > 500:
                            result_str = result_str[:500] + "... (truncated)"
                        
                        yield {
                            "type": EVENT_TOOL_RESULT,
                            "tool": name,
                            "result": result_str,
                            "agent": current_agent,
                        }
                        _log(f"EVENT #{event_count}: TOOL_RESULT {name}")
            
            # ─── AGENT TRANSFERS ───
            author = getattr(event, "author", None)
            if author and author != current_agent and author != "user":
                display = AGENT_NAMES.get(author, author)
                
                yield {
                    "type": EVENT_AGENT_TRANSFER,
                    "from": current_agent,
                    "to": author,
                }
                yield {
                    "type": EVENT_THOUGHT,
                    "content": f"Delegating to {display}...",
                }
                
                if author not in seen_agents:
                    seen_agents.append(author)
                current_agent = author
                _log(f"EVENT #{event_count}: TRANSFER → {author}")
            
            # ─── STATE CHANGES (2-way communication) ───
            actions = getattr(event, "actions", None)
            if actions:
                delta = getattr(actions, "state_delta", None)
                if delta and isinstance(delta, dict):
                    for key, value in delta.items():
                        # Skip tool tracking keys
                        if key in ("last_tool_result", "last_tool_name") or key.startswith("tool_result_"):
                            continue
                        
                        # Agent result keys → yield as text if meaningful AND not duplicate
                        if key.endswith("_result") and value:
                            value_str = str(value).strip()
                            
                            # Only yield if:
                            # 1. Not already yielded this key
                            # 2. Meaningful text
                            # 3. Content not already sent via event.text
                            content_hash = hash(value_str[:200])
                            if (key not in yielded_results 
                                and _is_meaningful_text(value_str)
                                and content_hash not in yielded_content_hashes):
                                yielded_results.add(key)
                                yielded_content_hashes.add(content_hash)
                                has_yielded_text = True
                                yield {"type": EVENT_TOKEN, "content": value_str}
                                _log(f"EVENT #{event_count}: STATE→TOKEN {key} ({len(value_str)} chars)")
                            else:
                                yielded_results.add(key)
                                _log(f"EVENT #{event_count}: SKIP duplicate state {key}")
                            
                            # Always send state change event for tracking
                            yield {
                                "type": EVENT_STATE_CHANGE,
                                "key": key,
                                "value": value_str[:500],
                            }
            
            # ─── ERRORS ───
            if hasattr(event, "error") and event.error:
                yield {"type": EVENT_ERROR, "content": str(event.error)}
                _log(f"EVENT #{event_count}: ERROR {event.error}")
            
            # ─── COMPLETION ───
            if hasattr(event, "is_final") and event.is_final:
                _log(f"EVENT #{event_count}: FINAL")
                break
        
        # ─── POST-LOOP: Check if we got any text ───
        if not has_yielded_text:
            _log("WARNING: No text yielded! Checking session state for results...")
            # Last resort: read final state from session
            try:
                final_session = session_service.get_session_sync(
                    app_name="NivAI", user_id=user, session_id=session_id
                )
                if final_session and final_session.state:
                    # Try orchestrator_result first, then any specialist result
                    for key in ["orchestrator_result", "analyst_result", "coder_result", 
                                "discovery_result", "nbfc_result", "planner_result"]:
                        val = final_session.state.get(key, "")
                        if val and _is_meaningful_text(str(val)):
                            yield {"type": EVENT_TOKEN, "content": str(val)}
                            _log(f"FALLBACK: Found text in state[{key}]")
                            has_yielded_text = True
                            break
            except Exception as e:
                _log(f"FALLBACK state read failed: {e}")
            
            if not has_yielded_text:
                yield {
                    "type": EVENT_TOKEN,
                    "content": "I processed your request but couldn't generate a response. Please try again."
                }
        
        elapsed = time.time() - start_time
        _log(f"A2A COMPLETE: {event_count} events, {elapsed:.1f}s, agents={seen_agents}")
        yield {"type": EVENT_COMPLETE}
        
    except ImportError as e:
        yield {"type": EVENT_ERROR, "content": f"ADK not installed: {e}. Run: pip install google-adk"}
    except Exception as e:
        frappe.log_error(f"A2A Stream Error:\n{traceback.format_exc()}", "Niv AI A2A")
        yield {"type": EVENT_ERROR, "content": f"A2A Error: {str(e)}"}
        yield {"type": EVENT_COMPLETE}


# ─────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────

def _log(msg: str):
    """Debug log for A2A events."""
    try:
        frappe.logger("niv_a2a").info(msg)
    except Exception:
        pass  # Don't fail on logging


# ─────────────────────────────────────────────────────────────────
# SYNC WRAPPER
# ─────────────────────────────────────────────────────────────────

def run_a2a_sync(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
) -> Dict[str, Any]:
    """Run A2A synchronously (non-streaming). For background tasks."""
    response_parts = []
    tools_used = []
    agents_involved = ["niv_orchestrator"]
    error = None
    
    for event in stream_a2a(
        message=message,
        conversation_id=conversation_id,
        provider_name=provider_name,
        model_name=model_name,
    ):
        t = event.get("type")
        if t == EVENT_TOKEN:
            response_parts.append(event.get("content", ""))
        elif t == EVENT_TOOL_CALL:
            tool = event.get("tool")
            if tool and tool not in tools_used:
                tools_used.append(tool)
        elif t == EVENT_AGENT_TRANSFER:
            to = event.get("to")
            if to and to not in agents_involved:
                agents_involved.append(to)
        elif t == EVENT_ERROR:
            error = event.get("content")
    
    return {
        "response": "".join(response_parts),
        "tools_used": tools_used,
        "agents_involved": agents_involved,
        "error": error,
    }


# ─────────────────────────────────────────────────────────────────
# TEST UTILITY
# ─────────────────────────────────────────────────────────────────

def test_a2a_setup() -> Dict[str, Any]:
    """Test A2A setup without running a query."""
    status = {
        "adk_installed": False,
        "session_service": False,
        "orchestrator": False,
        "mcp_tools": 0,
        "errors": [],
    }
    
    try:
        import google.adk
        status["adk_installed"] = True
    except ImportError as e:
        status["errors"].append(f"ADK not installed: {e}")
        return status
    
    try:
        svc = get_session_service()
        status["session_service"] = svc is not None
    except Exception as e:
        status["errors"].append(f"Session service error: {e}")
    
    try:
        orc = get_orchestrator(conversation_id="test")
        status["orchestrator"] = orc is not None
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached
        tools = get_all_mcp_tools_cached()
        status["mcp_tools"] = len(tools)
    except Exception as e:
        status["errors"].append(f"Orchestrator error: {e}")
    
    return status
