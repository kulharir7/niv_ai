"""
Niv AI Agent — LangGraph ReAct agent with MCP tools.
Main entry point for all LangChain-powered chat.
"""
import frappe
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .tools import get_langchain_tools
from .memory import get_chat_history, get_system_prompt
from .callbacks import NivStreamingCallback, NivBillingCallback, NivLoggingCallback


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
    # Generic — don't leak stack traces
    return "Something went wrong. Please try again or contact your administrator."


def create_niv_agent(
    provider_name: str = None,
    model: str = None,
    conversation_id: str = None,
    user: str = None,
    streaming: bool = True,
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

    # Tools
    tools = get_langchain_tools()

    # System prompt
    system_prompt = get_system_prompt(conversation_id)

    # Create agent with system prompt built-in
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=system_prompt) if system_prompt else None,
    )

    config = {
        "recursion_limit": 12,
        "callbacks": all_callbacks,
    }

    callbacks_dict = {
        "stream": stream_cb,
        "billing": billing_cb,
        "logging": logging_cb,
    }

    return agent, config, system_prompt, callbacks_dict


def run_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
) -> str:
    """Run agent synchronously — returns final response text."""
    agent, config, system_prompt, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=False,
    )

    messages = _build_messages(message, conversation_id, system_prompt)

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
        # Always finalize billing + logging
        cbs["billing"].finalize()
        cbs["logging"].finalize()


def stream_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
):
    """Stream agent — yields SSE event dicts.

    Handles LangGraph stream_mode="messages" output format.
    """
    agent, config, system_prompt, cbs = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=True,
    )

    messages = _build_messages(message, conversation_id, system_prompt)

    try:
        for event in agent.stream({"messages": messages}, config=config, stream_mode="messages"):
            # LangGraph yields (message, metadata) tuples
            if isinstance(event, tuple):
                msg, _meta = event
            else:
                msg = event

            if not hasattr(msg, "type"):
                continue

            # AI message chunks (streaming tokens)
            if msg.type == "ai":
                # Tool call chunks
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        yield {
                            "type": "tool_call",
                            "tool": tc.get("name", ""),
                            "arguments": tc.get("args", {}),
                        }
                # Text content
                elif msg.content:
                    yield {"type": "token", "content": msg.content}

            # Tool results
            elif msg.type == "tool":
                yield {
                    "type": "tool_result",
                    "tool": getattr(msg, "name", "unknown"),
                    "result": (msg.content or "")[:2000],
                }

    except Exception as e:
        frappe.log_error(f"Stream agent error: {e}", "Niv AI Agent")
        yield {"type": "error", "content": _sanitize_error(e)}

    finally:
        cbs["billing"].finalize()
        cbs["logging"].finalize()
