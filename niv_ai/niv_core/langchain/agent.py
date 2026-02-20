"""
Niv AI Agent — LangGraph ReAct agent with MCP tools.
Simple flow: User → LLM (thinks) → MCP Tools (data) → LLM (summarize) → Response

Two-model optimization:
  1. Fast model (non-streaming) decides: needs tools? which ones?
  2a. If tools needed → execute tools → big model streams answer with tool results
  2b. If no tools → big model streams answer directly
  Fallback: single-model LangGraph ReAct agent (handles retries, multi-step)
"""
import json
import re
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .llm import get_llm
from .tools import get_langchain_tools
from .memory import get_chat_history, get_chat_history_with_summary, get_system_prompt
from .agent_router import get_agent_prompt_suffix
from .callbacks import NivStreamingCallback, NivBillingCallback, NivLoggingCallback


# ─── Thinking Tag Patterns ──────────────────────────────────────────
# Models wrap internal reasoning in these tags. Must be stripped before user sees output.

_THINKING_PATTERNS = [
    (re.compile(r'<think>[\s\S]*?</think>'), ''),
    (re.compile(r'<reasoning>[\s\S]*?</reasoning>'), ''),
    (re.compile(r'\[\[THOUGHT\]\][\s\S]*?\[\[/THOUGHT\]\]'), ''),
    (re.compile(r'\[\[THINKING\]\][\s\S]*?\[\[/THINKING\]\]'), ''),
    (re.compile(r'(?m)^Thought:.*$'), ''),
    (re.compile(r'(?m)^Action:.*$'), ''),
    (re.compile(r'(?m)^Action Input:.*$'), ''),
    (re.compile(r'(?m)^Observation:.*$'), ''),
]

# Opening tags that may appear in streaming chunks
_TAG_OPENERS = [
    ('<think>', '</think>'),
    ('<reasoning>', '</reasoning>'),
    ('[[THOUGHT]]', '[[/THOUGHT]]'),
    ('[[THINKING]]', '[[/THINKING]]'),
]


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


def _strip_thinking(text, final=False):
    """Remove thinking/reasoning tags from response.
    
    Args:
        text: Text to clean
        final: If True, strip whitespace (for saved responses).
               If False (streaming), preserve trailing spaces for token concatenation.
    """
    if not text:
        return text
    for pattern, repl in _THINKING_PATTERNS:
        text = pattern.sub(repl, text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() if final else text


def _has_incomplete_thinking_tag(text):
    """Check if text has an unclosed thinking tag — we should hold the buffer.
    
    Safety limits:
    - Never hold more than 1500 chars (thinking blocks shouldn't be that long in streaming)
    - Only check for tag openers, not partial chars (too many false positives)
    """
    if not text or len(text) > 1500:
        return False
    for opener, closer in _TAG_OPENERS:
        if opener in text and closer not in text:
            return True
    return False


def _is_garbled_tool_text(text):
    """Detect if text is a raw tool call the LLM wrote as plain text.
    
    Some models (especially smaller Mistral variants) output tool calls
    as text content instead of using the function_call API:
      "list_documents {\"doctype\": \"Sales Order\", ...}"
      "list_documents Räikk{\"doctype\": ...}"  (garbled variant)
    
    This must be detected and suppressed — it's not a real response.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    # Must be relatively short (real responses are longer)
    if len(stripped) > 600:
        return False
    # Pattern: function_name + optional garbage + JSON object
    # Real responses don't start with a snake_case word followed by {
    if re.match(r'^[a-z][a-z0-9_]+\s*\S*\s*\{', stripped):
        # Verify there's a JSON-like structure
        brace_start = stripped.find('{')
        if brace_start >= 0:
            json_part = stripped[brace_start:]
            # Count braces — should roughly balance
            opens = json_part.count('{')
            closes = json_part.count('}')
            if opens > 0 and abs(opens - closes) <= 1:
                return True
    return False


def _build_messages(message: str, conversation_id: str = None, system_prompt: str = "", attachments: list = None):
    """Build message list: system + history + user message (with optional file attachments)."""
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
        history = get_chat_history_with_summary(conversation_id)
        messages.extend(history)

    # Build user message — multimodal if attachments present
    if attachments:
        try:
            from niv_ai.niv_core.tools.file_processor import process_attachments
            processed = process_attachments(attachments)
            
            # If images found, build multimodal message
            if processed.get("images"):
                content_parts = []
                # Add text context from non-image files
                if processed.get("text_context"):
                    message = message + "\n\n" + processed["text_context"]
                content_parts.append({"type": "text", "text": message})
                # Add images for vision
                for img_data in processed["images"]:
                    content_parts.append({"type": "image_url", "image_url": {"url": img_data}})
                messages.append(HumanMessage(content=content_parts))
            else:
                # Text-only attachments (PDF, Excel, Word)
                if processed.get("text_context"):
                    message = message + "\n\n" + processed["text_context"]
                messages.append(HumanMessage(content=message))
        except Exception as e:
            frappe.log_error(f"Niv AI: Attachment processing failed: {e}", "Niv Attachments")
            messages.append(HumanMessage(content=message))
    else:
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


# ─── Buffer Streaming ──────────────────────────────────────────────
# All streaming paths use this helper to avoid code duplication.

def _flush_buffer(buffer, final=False):
    """Process buffer → return (text_to_yield, remaining_buffer).
    
    If final=True, force flush everything (strip thinking, return result).
    If final=False, hold buffer if there's an incomplete thinking tag.
    """
    if not buffer:
        return "", ""
    
    if not final and _has_incomplete_thinking_tag(buffer):
        return "", buffer  # Hold it
    
    clean = _strip_thinking(buffer, final=final)
    if clean:
        return clean, ""
    elif final:
        return "", ""  # Thinking-only content → nothing to yield
    else:
        return "", buffer  # Still accumulating


def _stream_llm_tokens(llm_stream):
    """Yield cleaned token events from an LLM stream.
    
    Handles:
    - Thinking tag buffering and stripping
    - Garbled tool-call text detection
    - Buffer flushing at stream end
    
    Yields: {"type": "token", "content": str}
    """
    buffer = ""
    
    for chunk in llm_stream:
        content = getattr(chunk, "content", None)
        if not content:
            continue
        
        buffer += content
        text, buffer = _flush_buffer(buffer, final=False)
        if text:
            yield {"type": "token", "content": text}
    
    # Final flush
    if buffer:
        text, _ = _flush_buffer(buffer, final=True)
        if text:
            # Check if the entire output is garbled tool text
            if _is_garbled_tool_text(text):
                # Don't yield — this was a tool call masquerading as text
                pass
            else:
                yield {"type": "token", "content": text}


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
    messages = _build_messages(message, conversation_id, system_prompt, attachments=attachments)

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


# ─── Stream Helpers ─────────────────────────────────────────────────

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


# ─── Single-Model Streaming (LangGraph ReAct Agent) ────────────────

def _stream_single_model(agent, messages, config, cbs, dev_mode=False, max_tool_calls=12):
    """Stream via LangGraph ReAct agent.
    
    This is the reliable path — the agent handles tool selection, execution,
    retries with corrected args, and multi-step reasoning automatically.
    """
    pending_tool_calls = {}
    tool_call_count = 0
    start_ts = frappe.utils.now_datetime()
    buffer = ""
    yielded_any_text = False

    for event in agent.stream({"messages": messages}, config=config, stream_mode="messages"):
        # Timeout guard
        elapsed = (frappe.utils.now_datetime() - start_ts).total_seconds()
        if elapsed > (180 if dev_mode else 120):
            yield {"type": "error", "content": "Request took too long."}
            break

        msg = event[0] if isinstance(event, tuple) else event
        if not hasattr(msg, "type"):
            continue

        # ── AI message chunks (text + tool calls) ──
        if msg.type == "ai" or msg.type == "AIMessageChunk":
            tool_calls = getattr(msg, "tool_calls", None) or []
            tool_call_chunks = getattr(msg, "tool_call_chunks", None) or []

            # Text content
            if msg.content:
                buffer += msg.content
                text, buffer = _flush_buffer(buffer, final=False)
                if text:
                    yielded_any_text = True
                    yield {"type": "token", "content": text}

            # Tool calls — flush text buffer first
            if tool_calls or tool_call_chunks:
                if buffer:
                    text, buffer = _flush_buffer(buffer, final=True)
                    if text and not _is_garbled_tool_text(text):
                        yielded_any_text = True
                        yield {"type": "token", "content": text}
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

        # ── Tool result messages ──
        elif msg.type == "tool":
            tool_call_count += 1

            # Emit any pending tool call chunks
            for idx in sorted(pending_tool_calls.keys()):
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

    # ── Final buffer flush ──
    if buffer:
        text, _ = _flush_buffer(buffer, final=True)
        if text and not _is_garbled_tool_text(text):
            yielded_any_text = True
            yield {"type": "token", "content": text}


# ─── Two-Model Streaming ───────────────────────────────────────────

def _stream_two_model(
    message, messages, system_prompt, conversation_id, user,
    provider_name, model, cbs, dev_mode=False, max_tool_calls=12,
):
    """Two-model optimization: fast model selects tools, big model answers.
    
    Flow:
      1. Fast LLM (non-streaming, with tools) → decides which tools to call
      2. If tools needed → execute → big model streams answer with results
      3. If no tools → big model streams answer directly
    
    Yields {"type": "_fallback"} to signal caller to use single-model instead.
    This happens when:
      - Fast model fails (API error, timeout)
      - Fast model outputs garbled tool text instead of proper function calls
      - All tool calls fail (single-model can retry with corrected args)
    """
    from .tools import get_langchain_tools

    fast_model_name = _get_fast_model()
    tools = get_langchain_tools()

    # ── Step 1: Fast model decides tool call (non-streaming) ──
    fast_callbacks = [cbs["billing"]] if "billing" in cbs else []
    fast_llm = get_llm(provider_name, fast_model_name, streaming=False, callbacks=fast_callbacks)
    fast_llm_with_tools = fast_llm.bind_tools(tools)

    try:
        fast_response = fast_llm_with_tools.invoke(messages)
    except Exception as e:
        frappe.logger().warning(f"Niv AI: Fast model failed: {e}")
        yield {"type": "_fallback"}
        return

    fast_tool_calls = getattr(fast_response, "tool_calls", None) or []
    fast_content = getattr(fast_response, "content", "") or ""

    # ── Guard: fast model wrote tool call as text (broken function calling) ──
    if not fast_tool_calls and _is_garbled_tool_text(fast_content):
        frappe.logger().warning(f"Niv AI: Fast model output tool text, falling back: {fast_content[:100]}")
        yield {"type": "_fallback"}
        return

    # ── No tools needed → stream answer with big model ──
    if not fast_tool_calls:
        big_llm = get_llm(provider_name, model, streaming=True, callbacks=list(cbs.values()))
        yield from _stream_llm_tokens(big_llm.stream(messages))
        return

    # ── Step 2: Execute tool calls (parallel if 2+) ──
    tool_map = {t.name: t for t in tools}
    calls = fast_tool_calls[:max_tool_calls]

    # Emit all tool_call events first
    for tc in calls:
        yield {"type": "tool_call", "tool": tc.get("name", ""), "arguments": tc.get("args", {})}

    def _exec_one(tc):
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})
        tool_call_id = tc.get("id", f"call_{tool_name}")
        if tool_name in tool_map:
            try:
                result = tool_map[tool_name].invoke(tool_args)
                result_str = str(result) if not isinstance(result, str) else result
            except Exception as e:
                result_str = f"Error: {e}"
        else:
            result_str = f"Tool '{tool_name}' not found."
        return {"tool_call_id": tool_call_id, "tool_name": tool_name, "result": result_str}

    if len(calls) >= 2:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(calls), 4)) as pool:
            tool_results = list(pool.map(_exec_one, calls))
    else:
        tool_results = [_exec_one(tc) for tc in calls]

    for tr in tool_results:
        yield {
            "type": "tool_result",
            "tool": tr["tool_name"],
            "result": tr["result"][:2000],
        }

    # ── Step 3: Big model answers with tool results + sequential chaining ──
    # Big model gets tool results. If it needs more tools (sequential chain),
    # it can call them — up to 2 extra rounds. This enables patterns like:
    # "Show overdue loans and email them to manager" (tool 2 depends on tool 1)
    answer_messages = list(messages)
    answer_messages.append(fast_response)  # AI message with tool_calls
    for tr in tool_results:
        answer_messages.append(ToolMessage(
            content=tr["result"],
            tool_call_id=tr["tool_call_id"],
            name=tr["tool_name"],
        ))

    big_llm = get_llm(provider_name, model, streaming=True, callbacks=list(cbs.values()))
    big_llm_with_tools = big_llm.bind_tools(tools)

    # Chain loop: big model can call more tools if needed (max 2 extra rounds)
    max_chain_rounds = 2
    for chain_round in range(max_chain_rounds + 1):
        collected_text = ""
        buffer = ""
        chain_tool_calls = []
    
        # On last round, stream without tools (force final answer)
        llm_to_use = big_llm_with_tools if chain_round < max_chain_rounds else big_llm

        for chunk in llm_to_use.stream(answer_messages):
            # Collect tool calls from big model
            chunk_tool_calls = getattr(chunk, "tool_call_chunks", None) or []
            if chunk_tool_calls:
                for tc_chunk in chunk_tool_calls:
                    idx = tc_chunk.get("index", len(chain_tool_calls))
                    while len(chain_tool_calls) <= idx:
                        chain_tool_calls.append({"name": "", "args": "", "id": ""})
                    if tc_chunk.get("name"):
                        chain_tool_calls[idx]["name"] = tc_chunk["name"]
                    if tc_chunk.get("args"):
                        chain_tool_calls[idx]["args"] += tc_chunk["args"]
                    if tc_chunk.get("id"):
                        chain_tool_calls[idx]["id"] = tc_chunk["id"]
                continue

            # Also check complete tool_calls
            full_tc = getattr(chunk, "tool_calls", None) or []
            if full_tc:
                chain_tool_calls = [
                    {"name": tc.get("name", ""), "args": tc.get("args", {}), "id": tc.get("id", "")}
                    for tc in full_tc
                ]
                continue

            # Stream text tokens to user
            text_content = getattr(chunk, "content", None)
            if text_content:
                buffer += text_content
                text, buffer = _flush_buffer(buffer, final=False)
                if text:
                    collected_text += text
                    yield {"type": "token", "content": text}

        # Final flush of buffer
        if buffer:
            text, buffer = _flush_buffer(buffer, final=True)
            if text and not _is_garbled_tool_text(text):
                collected_text += text
                yield {"type": "token", "content": text}


        # If no tool calls from big model, we're done
        if not chain_tool_calls or not any(tc["name"] for tc in chain_tool_calls):
            break

        # Execute chained tool calls
        chain_tool_calls = [tc for tc in chain_tool_calls if tc["name"]]
        for tc in chain_tool_calls:
            if isinstance(tc["args"], str):
                tc["args"] = _parse_tc_args(tc["args"])
            yield {"type": "tool_call", "tool": tc["name"], "arguments": tc["args"]}

        # Build AI message for the chain
        from langchain_core.messages import AIMessage as _AIMsg
        chain_ai_msg = _AIMsg(
            content=collected_text,
            tool_calls=[{"name": tc["name"], "args": tc["args"], "id": tc.get("id", f"call_{tc['name']}")} for tc in chain_tool_calls],
        )
        answer_messages.append(chain_ai_msg)

        # Execute tools
        for tc in chain_tool_calls:
            tc_result = _exec_one({"name": tc["name"], "args": tc["args"], "id": tc.get("id", f"call_{tc['name']}")})
            yield {"type": "tool_result", "tool": tc_result["tool_name"], "result": tc_result["result"][:2000]}
            answer_messages.append(ToolMessage(
                content=tc_result["result"],
                tool_call_id=tc_result["tool_call_id"],
                name=tc_result["tool_name"],
            ))

        frappe.logger().info(f"Niv AI: Chain round {chain_round + 1}, {len(chain_tool_calls)} extra tool(s)")


# ─── Main Entry Point ──────────────────────────────────────────────

def stream_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
    dev_mode: bool = False,
    page_context: dict = None,
    attachments: list = None,
):
    """Stream agent — yields SSE event dicts.
    
    Two-model optimization when fast_model is configured, with automatic
    fallback to single-model LangGraph ReAct agent on any failure.
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
    # Skip two-model if: no fast model, dev mode, or already routed to fast model (simple queries)
    use_two_model = not dev_mode and fast_model_name and model != fast_model_name

    yielded_any_token = False

    try:
        if use_two_model:
            fell_back = False
            two_model_events = []  # Buffer events in case we need to fall back
            
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
                
                # Track if we yielded any real text tokens
                if event.get("type") == "token":
                    yielded_any_token = True
                
                yield event
            
            if fell_back or not yielded_any_token:
                # Single-model gets fresh start — it will re-discover and call tools itself
                # Also falls back when two-model produced tools but no text (garbled output)
                if not fell_back:
                    frappe.log_error("Two-model produced no text tokens, falling back to single-model", "Niv AI Fallback")
                for event in _stream_single_model(agent, messages, config, cbs, dev_mode, MAX_TOOL_CALLS):
                    if event.get("type") == "token":
                        yielded_any_token = True
                    yield event
        else:
            for event in _stream_single_model(agent, messages, config, cbs, dev_mode, MAX_TOOL_CALLS):
                if event.get("type") == "token":
                    yielded_any_token = True
                yield event

    except Exception as e:
        frappe.log_error(f"Stream agent error: {e}", "Niv AI Agent")
        yield {"type": "error", "content": _sanitize_error(e)}

    finally:
        _cleanup_user_api_key()
        
        # Ensure DB is alive for billing
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
        
        # Yield token usage for stream.py to capture
        yield {
            "type": "_token_usage",
            "input_tokens": cbs["billing"].total_prompt_tokens,
            "output_tokens": cbs["billing"].total_completion_tokens,
            "total_tokens": cbs["billing"].total_tokens,
        }
