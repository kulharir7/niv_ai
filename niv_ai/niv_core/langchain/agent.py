"""
Niv AI Agent — LangGraph ReAct agent with MCP tools.
Main entry point for LangChain-powered chat.
"""
import frappe
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .tools import get_langchain_tools
from .memory import get_chat_history, get_system_prompt
from .callbacks import NivStreamingCallback, NivBillingCallback, NivLoggingCallback


def create_niv_agent(
    provider_name: str = None,
    model: str = None,
    conversation_id: str = None,
    user: str = None,
    streaming: bool = True,
):
    """Create a LangGraph ReAct agent with MCP tools.
    
    Returns (agent, config) tuple ready for .invoke() or .stream()
    """
    from langgraph.prebuilt import create_react_agent
    
    user = user or frappe.session.user
    
    # Callbacks
    callbacks = []
    stream_cb = NivStreamingCallback(conversation_id or "")
    billing_cb = NivBillingCallback(user, conversation_id or "")
    logging_cb = NivLoggingCallback(user, conversation_id or "")
    callbacks = [stream_cb, billing_cb, logging_cb]
    
    # LLM
    llm = get_llm(provider_name, model, streaming=streaming, callbacks=callbacks)
    
    # Tools
    tools = get_langchain_tools()
    
    # System prompt
    system_prompt = get_system_prompt(conversation_id)
    
    # Create agent
    agent = create_react_agent(
        model=llm,
        tools=tools,
    )
    
    # Config with recursion limit (prevents infinite tool loops)
    config = {
        "recursion_limit": 12,  # ~5 tool calls max (each tool = 2 steps + final)
        "callbacks": callbacks,
    }
    
    return agent, config, system_prompt, stream_cb


def run_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
):
    """Run agent synchronously — returns final response text.
    
    Use for non-streaming chat (chat_v2.py).
    """
    agent, config, system_prompt, stream_cb = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=False,
    )
    
    # Build messages
    messages = []
    messages.append(SystemMessage(content=system_prompt))
    
    # RAG context
    from .rag import get_rag_context
    rag_ctx = get_rag_context(message)
    if rag_ctx:
        messages.append(SystemMessage(content=rag_ctx))
    
    # Load history
    if conversation_id:
        history = get_chat_history(conversation_id)
        messages.extend(history)
    
    # Add new user message
    messages.append(HumanMessage(content=message))
    
    # Run
    result = agent.invoke({"messages": messages}, config=config)
    
    # Extract final AI message
    ai_messages = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai" and m.content]
    if ai_messages:
        return ai_messages[-1].content
    
    return stream_cb.get_full_response() or "I could not generate a response."


def stream_agent(
    message: str,
    conversation_id: str = None,
    provider_name: str = None,
    model: str = None,
    user: str = None,
):
    """Stream agent — yields SSE events.
    
    Use for streaming chat (stream_v2.py).
    """
    agent, config, system_prompt, stream_cb = create_niv_agent(
        provider_name=provider_name,
        model=model,
        conversation_id=conversation_id,
        user=user,
        streaming=True,
    )
    
    # Build messages
    messages = []
    messages.append(SystemMessage(content=system_prompt))
    
    # RAG context
    from .rag import get_rag_context
    rag_ctx = get_rag_context(message)
    if rag_ctx:
        messages.append(SystemMessage(content=rag_ctx))
    
    if conversation_id:
        history = get_chat_history(conversation_id)
        messages.extend(history)
    
    messages.append(HumanMessage(content=message))
    
    # Stream with LangGraph
    for event in agent.stream({"messages": messages}, config=config, stream_mode="messages"):
        # event is (message, metadata) tuple
        if isinstance(event, tuple):
            msg, meta = event
        else:
            msg = event
        
        # Yield based on message type
        if hasattr(msg, "type"):
            if msg.type == "AIMessageChunk" or (hasattr(msg, "content") and msg.content):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        yield {
                            "type": "tool_call",
                            "tool": tc.get("name", ""),
                            "arguments": tc.get("args", {}),
                        }
                elif msg.content:
                    yield {
                        "type": "token",
                        "content": msg.content,
                    }
            
            elif msg.type == "tool":
                yield {
                    "type": "tool_result",
                    "tool": getattr(msg, "name", "unknown"),
                    "result": msg.content[:2000] if msg.content else "",
                }
