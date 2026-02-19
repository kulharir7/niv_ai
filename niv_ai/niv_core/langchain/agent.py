"""
Niv AI Agent — LangGraph ReAct agent with MCP tools.
Simple flow: User → LLM (thinks) → MCP Tools (data) → LLM (summarize) → Response
"""
import json
import re
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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


def _has_incomplete_tag(text):
    """Check if text has an incomplete thinking tag that might close later.
    Returns True if we should hold the buffer (don't yield yet).
    Safety: never hold more than 2000 chars — force flush to avoid lost output."""
    if not text:
        return False
    # Safety cap: if buffer is huge, the close tag isn't coming — force flush
    if len(text) > 2000:
        return False
    # Check for complete opener without closer (buffering until close tag arrives)
    _TAG_PAIRS = [
        ('<think>', '</think>'),
        ('<reasoning>', '</reasoning>'),
        ('[[THOUGHT]]', '[[/THOUGHT]]'),
        ('[[THINKING]]', '[[/THINKING]]'),
    ]
    for opener, closer in _TAG_PAIRS:
        if opener in text and closer not in text:
            return True
    # Check for partial opener at END of text only (min 3 chars to avoid false positives)
    tail = text[-15:]
    _PARTIAL_OPENERS = ['<think>', '<reasoning>', '[[THOUGHT]]', '[[THINKING]]']
    for opener in _PARTIAL_OPENERS:
        for i in range(3, len(opener)):
            partial = opener[:i]
            if tail.endswith(partial):
                return True
    return False


def _is_tool_call_text(text):
    """Detect if text is a raw tool call that the LLM output as plain text
    instead of using the function calling API. Returns True if it looks like
    a tool call, not a real response."""
    if not text or len(text) > 500:
        return False  # Real responses are usually longer
    stripped = text.strip()
    # Pattern: starts with a function-like name and has JSON args
    import re
    if re.match(r'^[a-z_]+\s*[\w\W]*\{.*\}\s*$', stripped, re.DOTALL):
        # Looks like: "list_documents {\"doctype\": ...}" or "get_report {...}"
        return True
    return False


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

    # Resolve actual model name for billing
    settings = get_niv_settings()
    resolved_model = model or settings.default_model or "unknown"

    # Callbacks
    stream_cb = NivStreamingCallback(conversation_id or "")
    billing_cb = NivBillingCallback(user, conversation_id or "", prompt_text=prompt_text, model=resolved_model)
    logging_cb = NivLoggingCallback(user, conversation_id or "")
    all_callbacks = [stream_cb, billing_cb, logging_cb]

    # LLM
    llm = get_llm(provider_name, model, streaming=streaming, callbacks=all_callbacks)

    # ALL tools — LLM decides which to use
    tools = get_langchain_tools()

    # Create agent (system prompt is built separately by caller)
    agent = create_react_agent(model=llm, tools=tools)

    config = {
        "recursion_limit": 25,
        "callbacks": all_callbacks,
    }

    return agent, config, {
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

    agent, config, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=False,
        prompt_text=message,
    )

    if not system_prompt:
        system_prompt = _build_system_prompt(conversation_id)
    messages = _build_messages(message, conversation_id, system_prompt)

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

def _get_fast_model():
    """Get fast model name from settings, or None if not configured."""
    try:
        settings = get_niv_settings()
        return getattr(settings, "fast_model", None) or None
    except Exception:
        return None


def _build_system_prompt(conversation_id, dev_mode=False, page_context=None):
    """Build complete system prompt with context."""
    if dev_mode:
        from .memory import get_dev_system_prompt
        return get_dev_system_prompt()

    system_prompt = get_system_prompt(conversation_id)
    prompt_suffix = get_agent_prompt_suffix("general")
    if prompt_suffix:
        system_prompt = f"{system_prompt}\n\n{prompt_suffix}"

    if page_context:
        from .memory import format_page_context
        ctx_text = format_page_context(page_context)
        if ctx_text:
            system_prompt += "\n\n" + ctx_text

    return system_prompt


def _stream_single_model(agent, messages, config, cbs, dev_mode=False, max_tool_calls=12):
    """Original single-model streaming via LangGraph ReAct agent."""
    pending_tool_calls = {}
    tool_call_count = 0
    start_ts = frappe.utils.now_datetime()
    buffer = ""

    for event in agent.stream({"messages": messages}, config=config, stream_mode="messages"):
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

            if msg.content:
                buffer += msg.content
                # Hold buffer if it might contain an incomplete thinking tag
                if not _has_incomplete_tag(buffer):
                    clean = _strip_thinking(buffer)
                    if clean:
                        yield {"type": "token", "content": clean}
                        buffer = ""

            if tool_calls or tool_call_chunks:
                if buffer:
                    clean = _strip_thinking(buffer, final=True)
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
            if tool_call_count >= max_tool_calls:
                yield {"type": "error", "content": "Tool call limit reached."}
                break

    # Flush remaining buffer after stream ends
    if buffer:
        clean = _strip_thinking(buffer, final=True)
        if clean:
            yield {"type": "token", "content": clean}


def _stream_two_model(
    message, messages, system_prompt, conversation_id, user,
    provider_name, model, cbs, dev_mode=False, max_tool_calls=12,
):
    """Two-model optimization: fast model for tool selection, big model for final answer.
    
    Flow:
    1. Fast LLM (non-streaming) with tools → decides tool call or direct answer
    2. If tool call → execute tool → get result
    3. Big LLM (streaming) with original question + tool result → stream final answer
    
    Falls back to single-model if fast model fails or isn't configured.
    
    Yields a special {"type": "_fallback"} event if fast model fails,
    signaling the caller to use single-model instead.
    """
    from .tools import get_langchain_tools

    fast_model_name = _get_fast_model()
    tools = get_langchain_tools()

    # ── Step 1: Fast model decides tool call (non-streaming, ~1-2s) ──
    # Pass billing callback so fast model tokens are tracked too
    fast_callbacks = [cbs["billing"]] if "billing" in cbs else []
    fast_llm = get_llm(provider_name, fast_model_name, streaming=False, callbacks=fast_callbacks)
    fast_llm_with_tools = fast_llm.bind_tools(tools)

    try:
        fast_response = fast_llm_with_tools.invoke(messages)
    except Exception as e:
        frappe.logger().warning(f"Niv AI: Fast model failed, falling back to single-model: {e}")
        yield {"type": "_fallback"}
        return

    fast_tool_calls = getattr(fast_response, "tool_calls", None) or []

    # Detect fast model outputting tool calls as plain text (broken function calling)
    fast_content = getattr(fast_response, "content", "") or ""
    if not fast_tool_calls and _is_tool_call_text(fast_content):
        frappe.logger().warning(f"Niv AI: Fast model output tool call as text, falling back: {fast_content[:100]}")
        yield {"type": "_fallback"}
        return

    # ── No tool call needed → stream answer with big model directly ──
    if not fast_tool_calls:
        # Fast model answered directly — but we want the big model's quality
        # Stream with big model (no tools needed, pure text generation)
        big_llm = get_llm(provider_name, model, streaming=True, callbacks=list(cbs.values()))
        buffer = ""
        for chunk in big_llm.stream(messages):
            if chunk.content:
                buffer += chunk.content
                if not _has_incomplete_tag(buffer):
                    clean = _strip_thinking(buffer)
                    if clean:
                        yield {"type": "token", "content": clean}
                        buffer = ""
        # Flush remaining buffer
        if buffer:
            clean = _strip_thinking(buffer, final=True)
            if clean:
                yield {"type": "token", "content": clean}
        return

    # ── Step 2: Execute tool calls (~0.5-1s) ──
    tool_map = {t.name: t for t in tools}
    tool_results = []

    for tc in fast_tool_calls[:max_tool_calls]:
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})
        tool_call_id = tc.get("id", f"call_{tool_name}")

        yield {"type": "tool_call", "tool": tool_name, "arguments": tool_args}

        if tool_name in tool_map:
            try:
                result = tool_map[tool_name].invoke(tool_args)
                result_str = str(result) if not isinstance(result, str) else result
            except Exception as e:
                result_str = f"Error: {e}"
        else:
            result_str = f"Tool '{tool_name}' not found."

        yield {
            "type": "tool_result",
            "tool": tool_name,
            "result": result_str[:2000],
        }
        tool_results.append({
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "result": result_str,
        })

    # ── Check if all tools failed — fall back to single-model for retry capability ──
    all_failed = all("error" in (tr["result"] or "").lower() for tr in tool_results)
    if all_failed:
        # Tool errors → big model will try to call tools again but we don't give it tools
        # Fall back to single-model ReAct agent which can retry with corrected args
        yield {"type": "_fallback"}
        return

    # ── Step 3: Big model streams final answer with tool results (~5-8s) ──
    # Build messages with tool results appended
    answer_messages = list(messages)  # Copy original messages

    # Add the fast model's AI message with tool calls
    answer_messages.append(fast_response)

    # Add tool results as ToolMessages
    for tr in tool_results:
        answer_messages.append(ToolMessage(
            content=tr["result"],
            tool_call_id=tr["tool_call_id"],
            name=tr["tool_name"],
        ))

    big_llm = get_llm(provider_name, model, streaming=True, callbacks=list(cbs.values()))
    buffer = ""
    for chunk in big_llm.stream(answer_messages):
        if chunk.content:
            buffer += chunk.content
            if not _has_incomplete_tag(buffer):
                clean = _strip_thinking(buffer)
                if clean:
                    yield {"type": "token", "content": clean}
                    buffer = ""
    # Flush remaining buffer
    if buffer:
        clean = _strip_thinking(buffer, final=True)
        if clean:
            yield {"type": "token", "content": clean}


def stream_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
    dev_mode: bool = False,
    page_context: dict = None,
):
    """Stream agent — yields SSE event dicts.
    
    Uses two-model optimization when fast_model is configured:
      - Fast model (small) for tool selection (~1-2s)
      - Big model for final answer streaming (~5-8s)
      - Total: ~7-10s vs ~15-20s with single model
    
    Falls back to single-model LangGraph ReAct agent if:
      - fast_model not configured
      - fast model call fails
      - dev_mode enabled (needs full agent loop)
    """
    user = user or frappe.session.user

    agent, config, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=True,
        prompt_text=message,
    )

    system_prompt = _build_system_prompt(conversation_id, dev_mode, page_context)
    messages = _build_messages(message, conversation_id, system_prompt)

    _setup_user_api_key(user)
    MAX_TOOL_CALLS = 40 if dev_mode else 12
    fast_model_name = _get_fast_model()
    # Skip two-model if already routed to fast model (simple queries) — avoids calling fast model twice
    use_two_model = not dev_mode and fast_model_name and model != fast_model_name

    try:
        if use_two_model:
            # Try two-model optimization
            fell_back = False
            for event in _stream_two_model(
                message=message,
                messages=messages,
                system_prompt=system_prompt,
                conversation_id=conversation_id,
                user=user,
                provider_name=provider_name,
                model=model,
                cbs={"stream": cbs["stream"], "billing": cbs["billing"], "logging": cbs["logging"]},
                dev_mode=dev_mode,
                max_tool_calls=MAX_TOOL_CALLS,
            ):
                if event.get("type") == "_fallback":
                    fell_back = True
                    break
                yield event
            if fell_back:
                yield from _stream_single_model(agent, messages, config, cbs, dev_mode, MAX_TOOL_CALLS)
        else:
            yield from _stream_single_model(agent, messages, config, cbs, dev_mode, MAX_TOOL_CALLS)

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
        # Build full prompt text for accurate token estimation
        full_prompt = "\n".join(
            getattr(m, "content", str(m)) for m in messages if hasattr(m, "content")
        )
        cbs["billing"].finalize(stream_cb=cbs["stream"], full_prompt_text=full_prompt)
        cbs["logging"].finalize()
        
        # Yield token usage for stream.py to save with the message
        yield {
            "type": "_token_usage",
            "input_tokens": cbs["billing"].total_prompt_tokens,
            "output_tokens": cbs["billing"].total_completion_tokens,
            "total_tokens": cbs["billing"].total_tokens,
        }
