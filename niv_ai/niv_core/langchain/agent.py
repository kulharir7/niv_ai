"""
Niv AI Agent — LangGraph ReAct agent with MCP tools.
Simple flow: User → LLM (thinks) → MCP Tools (data) → LLM (summarize) → Response
"""
import json
import re
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .tools import get_langchain_tools
from .memory import get_chat_history, get_system_prompt
from .agent_router import get_agent_prompt_suffix
from .callbacks import NivStreamingCallback, NivBillingCallback, NivLoggingCallback


# ─── Helpers ────────────────────────────────────────────────────────

def _parse_tc_args(args_str):
    """Parse tool_call_chunks args string into dict."""
    if isinstance(args_str, dict):
        return args_str
    if not args_str:
        return {}
    try:
        return json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def _build_messages(message: str, conversation_id: str = None, system_prompt: str = ""):
    """Build message list: system + history + user message."""
    messages = []

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

    if conversation_id:
        history = get_chat_history(conversation_id)
        messages.extend(history)

    messages.append(HumanMessage(content=message))
    return messages


def _sanitize_error(error: Exception) -> str:
    """User-friendly error message."""
    err_str = str(error).lower()
    if "api key" in err_str or "auth" in err_str:
        return "AI provider authentication failed. Please check your API key."
    if "rate limit" in err_str or "429" in err_str:
        return "Rate limit reached. Please try again in a moment."
    if "timeout" in err_str:
        return "Request timed out. Please try again."
    if "connection" in err_str:
        return "Could not connect to AI provider."
    if "recursion" in err_str or "iteration" in err_str:
        return "Too many steps. Please try a simpler query."
    if "insufficient" in err_str or "balance" in err_str or "credit" in err_str:
        return "Insufficient credits. Please recharge."
    return "Something went wrong. Please try again."


_THINKING_PATTERNS = [
    (r'<think>[\s\S]*?</think>', ''),
    (r'<reasoning>[\s\S]*?</reasoning>', ''),
    (r'\[\[THOUGHT\]\][\s\S]*?\[\[/THOUGHT\]\]', ''),
    (r'\[\[THINKING\]\][\s\S]*?\[\[/THINKING\]\]', ''),
    (r'(?m)^Thought:.*$', ''),
    (r'(?m)^Action:.*$', ''),
    (r'(?m)^Action Input:.*$', ''),
    (r'(?m)^Observation:.*$', ''),
]

def _strip_thinking(text, final=False):
    """Remove thinking/reasoning tags from response.
    
    Args:
        text: Text to clean
        final: If True, also strip leading/trailing whitespace (for saved responses).
               If False (streaming), preserve spaces so token concatenation works.
    """
    if not text:
        return text
    for pattern, repl in _THINKING_PATTERNS:
        text = re.sub(pattern, repl, text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() if final else text


# ─── API Key Isolation ──────────────────────────────────────────────

def _setup_user_api_key(user: str):
    """Set per-user API key for MCP tool permission isolation."""
    try:
        settings = get_niv_settings()
        if not getattr(settings, "per_user_tool_permissions", 0):
            return
        from niv_ai.niv_core.api._helpers import get_user_api_key
        from .tools import set_current_user_api_key
        api_key = get_user_api_key(user)
        if api_key:
            set_current_user_api_key(api_key)
    except Exception:
        pass


def _cleanup_user_api_key():
    """Clear per-user API key after request."""
    try:
        from .tools import set_current_user_api_key
        set_current_user_api_key(None)
    except Exception:
        pass


# ─── Agent Creation ─────────────────────────────────────────────────

def create_niv_agent(
    provider_name: str = None,
    model: str = None,
    conversation_id: str = None,
    user: str = None,
    streaming: bool = True,
    prompt_text: str = None,
):
    """Create a LangGraph ReAct agent with MCP tools."""
    from langgraph.prebuilt import create_react_agent

    user = user or frappe.session.user

    # Callbacks
    stream_cb = NivStreamingCallback(conversation_id or "")
    billing_cb = NivBillingCallback(user, conversation_id or "", prompt_text=prompt_text)
    logging_cb = NivLoggingCallback(user, conversation_id or "")
    all_callbacks = [stream_cb, billing_cb, logging_cb]

    # LLM
    llm = get_llm(provider_name, model, streaming=streaming, callbacks=all_callbacks)

    # ALL tools — LLM decides which to use
    tools = get_langchain_tools()

    # System prompt + few-shot examples
    system_prompt = get_system_prompt(conversation_id)
    prompt_suffix = get_agent_prompt_suffix("general")
    if prompt_suffix:
        system_prompt = f"{system_prompt}\n\n{prompt_suffix}"

    # Create agent
    agent = create_react_agent(model=llm, tools=tools)

    config = {
        "recursion_limit": 25,
        "callbacks": all_callbacks,
    }

    return agent, config, system_prompt, {
        "stream": stream_cb,
        "billing": billing_cb,
        "logging": logging_cb,
    }


# ─── Run (non-streaming) ───────────────────────────────────────────

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

    agent, config, default_prompt, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=False,
        prompt_text=message,
    )

    messages = _build_messages(message, conversation_id, system_prompt or default_prompt)

    _setup_user_api_key(user)
    try:
        result = agent.invoke({"messages": messages}, config=config)

        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                return _strip_thinking(msg.content, final=True)

        return _strip_thinking(cbs["stream"].get_full_response() or "I could not generate a response.", final=True)

    except Exception as e:
        frappe.log_error(f"Agent error: {e}", "Niv AI Agent")
        return _sanitize_error(e)

    finally:
        _cleanup_user_api_key()
        cbs["billing"].finalize(stream_cb=cbs["stream"])
        cbs["logging"].finalize()


# ─── Stream ─────────────────────────────────────────────────────────

def stream_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
    dev_mode: bool = False,
    page_context: dict = None,
):
    """Stream agent — yields SSE event dicts."""
    user = user or frappe.session.user

    agent, config, system_prompt, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=True,
        prompt_text=message,
    )

    # Developer mode: use dev system prompt
    if dev_mode:
        from .memory import get_dev_system_prompt
        system_prompt = get_dev_system_prompt()

    # Inject page context into system prompt
    if page_context:
        from .memory import format_page_context
        ctx_text = format_page_context(page_context)
        if ctx_text:
            system_prompt += "\n\n" + ctx_text

    messages = _build_messages(message, conversation_id, system_prompt)

    _setup_user_api_key(user)
    pending_tool_calls = {}
    tool_call_count = 0
    MAX_TOOL_CALLS = 40 if dev_mode else 12
    start_ts = frappe.utils.now_datetime()
    
    # Thought tag stripping state
    buffer = ""

    try:
        for event in agent.stream({"messages": messages}, config=config, stream_mode="messages"):
            # Timeout guard
            elapsed = (frappe.utils.now_datetime() - start_ts).total_seconds()
            if elapsed > (180 if dev_mode else 120):
                yield {"type": "error", "content": "Request took too long."}
                break

            msg = event[0] if isinstance(event, tuple) else event
            if not hasattr(msg, "type"):
                continue

            if msg.type == "ai" or msg.type == "AIMessageChunk":
                tool_calls = getattr(msg, "tool_calls", None) or []
                tool_call_chunks = getattr(msg, "tool_call_chunks", None) or []
                
                # Stream text content (strip thinking tags inline)
                if msg.content:
                    buffer += msg.content
                    # Check for thinking tags
                    clean = _strip_thinking(buffer)
                    if clean:
                        yield {"type": "token", "content": clean}
                        buffer = ""
                
                # Tool calls
                if tool_calls or tool_call_chunks:
                    if buffer:
                        clean = _strip_thinking(buffer)
                        if clean:
                            yield {"type": "token", "content": clean}
                        buffer = ""
                        
                    if tool_calls:
                        for tc in tool_calls:
                            yield {"type": "tool_call", "tool": tc.get("name", ""), "arguments": tc.get("args", {})}
                    else:
                        for tc in tool_call_chunks:
                            idx = tc.get("index", 0)
                            if idx not in pending_tool_calls:
                                pending_tool_calls[idx] = {"name": "", "args": ""}
                            if tc.get("name"):
                                pending_tool_calls[idx]["name"] = tc["name"]
                            if tc.get("args"):
                                pending_tool_calls[idx]["args"] += tc["args"]

            elif msg.type == "tool":
                tool_call_count += 1
                # Flush pending tool call chunks
                for idx in list(pending_tool_calls.keys()):
                    tc_data = pending_tool_calls[idx]
                    if tc_data["name"]:
                        yield {"type": "tool_call", "tool": tc_data["name"], "arguments": _parse_tc_args(tc_data["args"])}
                pending_tool_calls.clear()
                
                yield {
                    "type": "tool_result",
                    "tool": getattr(msg, "name", "unknown"),
                    "result": (str(msg.content) or "")[:2000],
                }
                if tool_call_count >= MAX_TOOL_CALLS:
                    yield {"type": "error", "content": "Tool call limit reached."}
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
        
        # Yield token usage for stream.py to save with the message
        yield {
            "type": "_token_usage",
            "input_tokens": cbs["billing"].total_prompt_tokens,
            "output_tokens": cbs["billing"].total_completion_tokens,
            "total_tokens": cbs["billing"].total_tokens,
        }
