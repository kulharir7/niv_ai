"""
Niv AI Agent — LangGraph ReAct agent with MCP tools.
Main entry point for all LangChain-powered chat.
"""
import json
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .tools import get_langchain_tools
from .memory import get_chat_history, get_system_prompt
from .agent_router import classify_query, get_agent_tools, get_agent_prompt_suffix
from .callbacks import NivStreamingCallback, NivBillingCallback, NivLoggingCallback


def _parse_tc_args(args_str):
    """BUG-004: Parse accumulated tool_call_chunks args string into dict."""
    if isinstance(args_str, dict):
        return args_str
    if not args_str:
        return {}
    try:
        return json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def _build_messages(message: str, conversation_id: str = None, system_prompt: str = ""):
    """Build the full message list: system + RAG + history + user message."""
    messages = []

    # System prompt
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    # RAG context (only if knowledge base enabled)
    try:
        from .rag import get_rag_context
        rag_ctx = get_rag_context(message)
        if rag_ctx:
            messages.append(SystemMessage(content=rag_ctx))
    except Exception:
        pass

    # Conversation history
    if conversation_id:
        history = get_chat_history(conversation_id)
        messages.extend(history)

    # New user message
    messages.append(HumanMessage(content=message))

    return messages


def _sanitize_error(error: Exception) -> str:
    """Return user-friendly error message — never expose raw internals."""
    err_str = str(error).lower()
    if "api key" in err_str or "auth" in err_str:
        return "AI provider authentication failed. Please check your API key configuration."
    if "rate limit" in err_str or "429" in err_str:
        return "AI provider rate limit reached. Please try again in a moment."
    if "timeout" in err_str:
        return "Request timed out. Please try again."
    if "connection" in err_str:
        return "Could not connect to AI provider. Please check your network."
    if "model" in err_str and "not found" in err_str:
        return "The configured AI model was not found. Please check Niv Settings."
    if "recursion" in err_str or "iteration" in err_str:
        return "The request required too many steps. Please try a simpler query."
    if "insufficient" in err_str or "balance" in err_str or "credit" in err_str:
        return "Insufficient credits. Please recharge to continue using Niv AI."
    # Generic — don't leak stack traces
    return "I wasn't able to complete that request. Please try rephrasing your question or try again."


def create_niv_agent(
    provider_name: str = None,
    model: str = None,
    conversation_id: str = None,
    user: str = None,
    streaming: bool = True,
    agent_id: str = "general",
):
    """Create a LangGraph ReAct agent with MCP tools.

    Returns (agent, config, system_prompt, callbacks_dict)
    """
    from langgraph.prebuilt import create_react_agent

    user = user or frappe.session.user

    # Callbacks
    stream_cb = NivStreamingCallback(conversation_id or "")
    billing_cb = NivBillingCallback(user, conversation_id or "")
    logging_cb = NivLoggingCallback(user, conversation_id or "")
    all_callbacks = [stream_cb, billing_cb, logging_cb]

    # LLM (callbacks attached for streaming token capture)
    llm = get_llm(provider_name, model, streaming=streaming, callbacks=all_callbacks)

    # Tools (agent-aware filtering)
    all_tools = get_langchain_tools()
    tools = get_agent_tools(agent_id, all_tools)

    # System prompt (agent-aware specialization)
    system_prompt = get_system_prompt(conversation_id)
    prompt_suffix = get_agent_prompt_suffix(agent_id)
    if prompt_suffix:
        system_prompt = f"{system_prompt}\n\n{prompt_suffix}"

    # Create agent
    agent = create_react_agent(
        model=llm,
        tools=tools,
    )

    config = {
        "recursion_limit": 25,  # Each tool call = 2 steps (call + result) + 1 for final response
        "callbacks": all_callbacks,
    }

    callbacks_dict = {
        "stream": stream_cb,
        "billing": billing_cb,
        "logging": logging_cb,
    }

    return agent, config, system_prompt, callbacks_dict


def _setup_user_api_key(user: str):
    """Set per-user API key for MCP tool permission isolation."""
    try:
        from niv_ai.niv_core.api._helpers import get_user_api_key
        from .tools import set_current_user_api_key
        
        # Check if per-user tool permissions is enabled
        settings = get_niv_settings()
        if not getattr(settings, "per_user_tool_permissions", 0):
            return  # Feature disabled — use admin key (default behavior)
        
        api_key = get_user_api_key(user)
        if api_key:
            set_current_user_api_key(api_key)
    except Exception as e:
        # Non-fatal — falls back to admin key
        frappe.logger().warning(f"Niv AI: Per-user key setup failed for {user}: {e}")


def _cleanup_user_api_key():
    """Clear per-user API key after request."""
    try:
        from .tools import set_current_user_api_key
        set_current_user_api_key(None)
    except Exception:
        pass


def run_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
    system_prompt: str = None,
) -> str:
    """Run agent synchronously — returns final response text."""
    user = user or frappe.session.user

    # Agent routing (feature-flagged)
    agent_id = "general"
    try:
        settings = get_niv_settings()
        if getattr(settings, "enable_agent_routing", 0):
            agent_id, _meta = classify_query(message)
    except Exception:
        pass

    agent, config, default_system_prompt, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=False,
        agent_id=agent_id,
    )
    # Use custom system_prompt if provided, else default
    final_system_prompt = system_prompt or default_system_prompt

    messages = _build_messages(message, conversation_id, final_system_prompt)

    _setup_user_api_key(user)
    try:
        result = agent.invoke({"messages": messages}, config=config)

        # Extract final AI response
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                return msg.content

        return cbs["stream"].get_full_response() or "I could not generate a response."

    except Exception as e:
        frappe.log_error(f"Agent error: {e}", "Niv AI Agent")
        return _sanitize_error(e)

    finally:
        _cleanup_user_api_key()
        cbs["billing"].finalize(stream_cb=cbs["stream"])
        cbs["logging"].finalize()


def stream_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
    dev_mode: bool = False,
):
    """Stream agent — yields SSE event dicts.

    Handles LangGraph stream_mode="messages" output format.
    """
    user = user or frappe.session.user

    # Agent routing (feature-flagged, dev mode aware)
    agent_id = "developer" if dev_mode else "general"
    route_meta = {"method": "default", "confidence": 1.0}
    try:
        settings = get_niv_settings()
        if dev_mode:
            agent_id = "developer"
            route_meta = {"method": "dev_mode", "confidence": 1.0}
        elif getattr(settings, "enable_agent_routing", 0):
            agent_id, route_meta = classify_query(message)
    except Exception:
        pass

    agent, config, system_prompt, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=True,
        agent_id=agent_id,
    )

    # Developer mode: use dev system prompt
    if dev_mode:
        from .memory import get_dev_system_prompt
        system_prompt = get_dev_system_prompt()

    messages = _build_messages(message, conversation_id, system_prompt)

    _setup_user_api_key(user)
    pending_tool_calls = {}
    tool_call_count = 0
    # Dev mode supports complex multi-step builds; normal mode remains controlled.
    MAX_TOOL_CALLS = 40 if dev_mode else 12
    start_ts = frappe.utils.now_datetime()
    
    # State for ReAct thought extraction
    current_thought = ""
    in_thought = False
    message_buffer = ""
    active_end_tag = ""
    
    def process_buffer(buffer, is_flushing=False):
        nonlocal in_thought, current_thought, active_end_tag
        remaining = buffer
        
        while remaining:
            upper = remaining.upper()
            if not in_thought:
                # Find any starting tag
                idx1 = upper.find("[[THOUGHT]]")
                idx2 = upper.find("<THOUGHT>")
                
                # Pick the earliest tag
                tag = None
                idx = -1
                if idx1 != -1 and (idx2 == -1 or idx1 < idx2):
                    tag, idx = "[[THOUGHT]]", idx1
                elif idx2 != -1:
                    tag, idx = "<THOUGHT>", idx2
                
                if idx != -1:
                    # Yield text before tag
                    if idx > 0:
                        yield {"type": "token", "content": remaining[:idx]}
                    
                    # Enter thought state
                    in_thought = True
                    active_end_tag = "[[/THOUGHT]]" if tag == "[[THOUGHT]]" else "</THOUGHT>"
                    remaining = remaining[idx + len(tag):]
                    continue
                
                # Check for partial start tag at end of buffer
                if not is_flushing:
                    last_lt = max(remaining.rfind("["), remaining.rfind("<"))
                    if last_lt != -1:
                        tail = remaining[last_lt:].upper()
                        if "[[THOUGHT]]".startswith(tail) or "<THOUGHT>".startswith(tail):
                            if last_lt > 0:
                                yield {"type": "token", "content": remaining[:last_lt]}
                            return remaining[last_lt:]
                
                # No tags, yield all
                yield {"type": "token", "content": remaining}
                return ""
            else:
                # In thought, look for matching end tag
                idx = upper.find(active_end_tag)
                if idx != -1:
                    # Append and yield full thought
                    current_thought += remaining[:idx]
                    yield {"type": "thought", "content": current_thought}
                    current_thought = ""
                    in_thought = False
                    remaining = remaining[idx + len(active_end_tag):]
                    continue
                
                # Check for partial end tag at end of buffer
                if not is_flushing:
                    last_lt = max(remaining.rfind("["), remaining.rfind("<"))
                    if last_lt != -1:
                        tail = remaining[last_lt:].upper()
                        if active_end_tag.startswith(tail):
                            if last_lt > 0:
                                current_thought += remaining[:last_lt]
                                yield {"type": "thought", "content": remaining[:last_lt]}
                            return remaining[last_lt:]
                
                # Still in thought, yield as thought
                current_thought += remaining
                yield {"type": "thought", "content": remaining}
                return ""
        return ""

    try:
        for event in agent.stream({"messages": messages}, config=config, stream_mode="messages"):
            # Runtime guard
            elapsed = (frappe.utils.now_datetime() - start_ts).total_seconds()
            if elapsed > (180 if dev_mode else 90):
                yield {"type": "error", "content": "Request took too long. I stopped safely."}
                break

            if isinstance(event, tuple):
                msg, _meta = event
            else:
                msg = event

            if not hasattr(msg, "type"):
                continue

            if msg.type == "ai" or msg.type == "AIMessageChunk":
                tool_calls = getattr(msg, "tool_calls", None) or []
                tool_call_chunks = getattr(msg, "tool_call_chunks", None) or []
                
                if msg.content:
                    message_buffer += msg.content
                    for chunk in process_buffer(message_buffer):
                        if isinstance(chunk, str):
                            message_buffer = chunk
                        else:
                            yield chunk
                
                if tool_calls or tool_call_chunks:
                    # Flush buffer before tools
                    if message_buffer:
                        for chunk in process_buffer(message_buffer, is_flushing=True):
                            yield chunk
                        message_buffer = ""
                        
                    if tool_calls:
                        for tc in tool_calls:
                            yield {"type": "tool_call", "tool": tc.get("name", ""), "arguments": tc.get("args", {})}
                    else:
                        for tc in tool_call_chunks:
                            idx = tc.get("index", 0)
                            if idx not in pending_tool_calls: pending_tool_calls[idx] = {"name": "", "args": ""}
                            if tc.get("name"): pending_tool_calls[idx]["name"] = tc["name"]
                            if tc.get("args"): pending_tool_calls[idx]["args"] += tc["args"]

            elif msg.type == "tool":
                tool_call_count += 1
                for idx in list(pending_tool_calls.keys()):
                    tc_data = pending_tool_calls[idx]
                    if tc_data["name"]:
                        yield {"type": "tool_call", "tool": tc_data["name"], "arguments": _parse_tc_args(tc_data["args"])}
                pending_tool_calls.clear()
                yield {
                    "type": "tool_result",
                    "tool": getattr(msg, "name", "unknown"),
                    "result": (str(msg.content) or "")[:1000],
                }
                if tool_call_count >= MAX_TOOL_CALLS:
                    yield {"type": "error", "content": "I reached the tool-call safety limit."}
                    break

    except Exception as e:
        frappe.log_error(f"Stream agent error: {e}", "Niv AI Agent")
        yield {"type": "error", "content": _sanitize_error(e)}

    finally:
        _cleanup_user_api_key()
        try:
            frappe.db.sql("SELECT 1")
        except Exception:
            try:
                frappe.db.connect()
            except Exception:
                pass
        cbs["billing"].finalize(stream_cb=cbs["stream"])
        cbs["logging"].finalize()
