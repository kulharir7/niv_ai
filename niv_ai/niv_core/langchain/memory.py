"""
Conversation Memory — loads Niv Message history into LangChain format.
"""
import frappe
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage


def get_chat_history(conversation_id: str, limit: int = 50) -> list:
    """Load conversation history as LangChain message objects.
    
    Reads from Niv Message DocType — no changes to storage.
    """
    messages = frappe.get_all(
        "Niv Message",
        filters={"conversation": conversation_id},
        fields=["role", "content", "tool_calls", "tool_call_id", "name as msg_name"],
        order_by="creation asc",
        limit_page_length=limit,
    )
    
    lc_messages = []
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        
        elif role == "assistant":
            # Check for tool calls
            tool_calls_raw = msg.get("tool_calls")
            if tool_calls_raw:
                try:
                    import json
                    tc_list = json.loads(tool_calls_raw) if isinstance(tool_calls_raw, str) else tool_calls_raw
                    # LangChain AIMessage with tool_calls
                    lc_tool_calls = []
                    for tc in tc_list:
                        lc_tool_calls.append({
                            "id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "args": tc.get("function", {}).get("arguments", {}),
                        })
                    lc_messages.append(AIMessage(content=content, tool_calls=lc_tool_calls))
                except Exception:
                    lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(AIMessage(content=content))
        
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            lc_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id))
    
    return lc_messages


def get_system_prompt(conversation_id: str = None) -> str:
    """Get system prompt for conversation.
    
    Priority: conversation.system_prompt → Niv Settings default → built-in
    """
    default_prompt = (
        "You are Niv AI, an intelligent assistant embedded in ERPNext. "
        "You help users with their business tasks, answer questions about their data, "
        "and perform actions using available tools. Be concise, helpful, and professional."
    )
    
    if conversation_id:
        try:
            conv = frappe.get_doc("Niv Conversation", conversation_id)
            if conv.system_prompt:
                prompt_doc = frappe.get_doc("Niv System Prompt", conv.system_prompt)
                if prompt_doc.content:
                    return prompt_doc.content
        except Exception:
            pass
    
    # Check Niv Settings for default prompt
    try:
        settings = frappe.get_cached_doc("Niv Settings")
        if settings.default_system_prompt:
            prompt_doc = frappe.get_doc("Niv System Prompt", settings.default_system_prompt)
            if prompt_doc.content:
                return prompt_doc.content
    except Exception:
        pass
    
    return default_prompt
