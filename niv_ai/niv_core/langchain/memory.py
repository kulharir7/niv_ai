"""
Conversation Memory — loads Niv Message history into LangChain format.
Token-aware truncation to prevent context window overflow.
"""
import json
import frappe
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage


# Rough token estimate: 1 token ≈ 4 chars (conservative)
_CHARS_PER_TOKEN = 4

# Default max context tokens (leave room for system prompt + new message + response)
_DEFAULT_MAX_CONTEXT_TOKENS = 12000


def _estimate_tokens(text: str) -> int:
    """Fast token estimate without tiktoken (avoids import overhead)."""
    return max(1, len(text or "") // _CHARS_PER_TOKEN)


def get_chat_history(conversation_id: str, limit: int = 50, max_tokens: int = None) -> list:
    """Load conversation history as LangChain message objects.

    Token-aware: truncates oldest messages if total exceeds max_tokens.
    Always keeps the most recent messages.
    """
    if max_tokens is None:
        try:
            settings = frappe.get_cached_doc("Niv Settings")
            max_tokens = (settings.max_tokens_per_message or 4096) * 3  # ~3x single message limit
        except Exception:
            max_tokens = _DEFAULT_MAX_CONTEXT_TOKENS

    messages = frappe.get_all(
        "Niv Message",
        filters={"conversation": conversation_id},
        fields=["role", "content", "tool_calls_json", "tool_results_json"],
        order_by="creation asc",
        limit_page_length=limit,
    )

    lc_messages = _convert_to_langchain(messages)

    # Token-aware truncation: keep newest, drop oldest
    if max_tokens > 0:
        lc_messages = _truncate_by_tokens(lc_messages, max_tokens)

    return lc_messages


def _convert_to_langchain(messages: list) -> list:
    """Convert Niv Message dicts → LangChain message objects."""
    lc_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            lc_messages.append(SystemMessage(content=content))

        elif role == "user":
            lc_messages.append(HumanMessage(content=content))

        elif role == "assistant":
            tool_calls_raw = msg.get("tool_calls_json")
            if tool_calls_raw:
                lc_tool_calls = _parse_tool_calls(tool_calls_raw)
                if lc_tool_calls:
                    lc_messages.append(AIMessage(content=content, tool_calls=lc_tool_calls))
                else:
                    lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(AIMessage(content=content))

        elif role == "tool":
            # Tool results stored inline — skip as separate messages
            # (tool_results_json is on assistant messages, not separate rows)
            pass

    return lc_messages


def _parse_tool_calls(raw) -> list:
    """Parse tool_calls JSON → LangChain format. Handles bad data gracefully."""
    try:
        tc_list = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(tc_list, list):
            return []

        result = []
        for tc in tc_list:
            func = tc.get("function", {})
            args = func.get("arguments", {})
            # Arguments might be a JSON string
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {"raw": args}

            result.append({
                "id": tc.get("id", f"call_{id(tc)}"),
                "name": func.get("name", tc.get("tool", tc.get("name", ""))),
                "args": args if isinstance(args, dict) else {"raw": str(args)},
            })
        return result
    except Exception:
        return []


def _truncate_by_tokens(messages: list, max_tokens: int) -> list:
    """Keep most recent messages within token budget."""
    if not messages:
        return messages

    # Calculate tokens per message (from newest)
    token_counts = []
    for msg in reversed(messages):
        content = msg.content if hasattr(msg, "content") else ""
        token_counts.append(_estimate_tokens(content))

    # Walk from newest, accumulate until budget exceeded
    total = 0
    keep_count = 0
    for count in token_counts:
        if total + count > max_tokens:
            break
        total += count
        keep_count += 1

    if keep_count == 0:
        keep_count = 1  # Always keep at least the latest message

    return messages[-keep_count:]


def get_system_prompt(conversation_id: str = None) -> str:
    """Get system prompt for conversation.

    Priority: conversation.system_prompt → settings.system_prompt (text field) → built-in default
    """
    default_prompt = (
        "You are Niv AI, an intelligent assistant embedded in ERPNext. "
        "You help users with their business tasks, answer questions about their data, "
        "and perform actions using available tools. Be concise, helpful, and professional. "
        "When using tools, explain what you are doing. Format data in tables when appropriate."
    )

    # Try conversation-level prompt
    if conversation_id:
        try:
            conv = frappe.get_doc("Niv Conversation", conversation_id)
            if hasattr(conv, "system_prompt") and conv.system_prompt:
                if frappe.db.exists("Niv System Prompt", conv.system_prompt):
                    prompt_doc = frappe.get_doc("Niv System Prompt", conv.system_prompt)
                    if prompt_doc.content:
                        return prompt_doc.content
        except Exception:
            pass

    # Try settings-level prompt (text field, not Link)
    try:
        settings = frappe.get_cached_doc("Niv Settings")
        if hasattr(settings, "system_prompt") and settings.system_prompt:
            # If it's a Link to Niv System Prompt
            if frappe.db.exists("Niv System Prompt", settings.system_prompt):
                prompt_doc = frappe.get_doc("Niv System Prompt", settings.system_prompt)
                if prompt_doc.content:
                    return prompt_doc.content
            else:
                # It's raw text
                return settings.system_prompt
    except Exception:
        pass

    return default_prompt
