"""
Conversation Memory — loads Niv Message history into LangChain format.
Token-aware truncation to prevent context window overflow.
"""
import json
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from niv_ai.niv_core.knowledge.memory_service import get_user_context, extract_memories
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage


TOOL_USAGE_GUIDELINES = """
RULES:
- 1-2 tool calls per question. Minimal.
- Aggregations (count/sum/avg) → run_database_query, NOT list_documents.
- Never repeat same tool call.
"""

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
            settings = get_niv_settings()
            # BUG-051: Account for system prompt and reserve space for response
            # Context window estimation
            total_limit = 32000 # Assume safe limit for most models
            max_msg_tokens = (settings.max_tokens_per_message or 4096)
            # Leave room for system prompt (~2000) + user prompt (~max_msg) + response (~max_msg)
            max_tokens = total_limit - 2000 - (max_msg_tokens * 2)
            if max_tokens < 4000: max_tokens = 8000 # Sanity floor
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
            # Don't include tool_calls in history — LangGraph requires matching
            # ToolMessages for every tool_call, which we don't store separately.
            # The text content already contains the final response.
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
    # Dynamic branding — never say ERPNext/Frappe, use configured name
    try:
        _settings = get_niv_settings()
        _brand = getattr(_settings, "brand_name", "") or "Niv"
    except Exception:
        _brand = "Niv"

    from datetime import datetime
    _now = datetime.now()
    _today = _now.strftime("%Y-%m-%d (%A)")

    default_prompt = (
        "You are Niv AI, a business assistant for {brand}. Be concise.\n"
        "Today's date: {today}\n\n"
        "RULES:\n"
        "1. Never fabricate data. Always use tools to get real data.\n"
        "2. For financial metrics (WRR, interest rates), read from document fields — never guess.\n"
        "3. After tool results, write a clear summary for the user.\n"
        "4. Never say 'ERPNext' or 'Frappe' — say '{brand}'.\n"
        "5. If a tool fails, try a different approach once. Then tell the user.\n"
        "6. FORMATTING: Use markdown tables for structured data. Use bullet lists for simple items.\n"
        "7. GREETINGS: Keep greetings short (1-2 lines). Never list your capabilities or features.\n"
        "8. VOICE MODE: When responding to voice input, be conversational and brief. Avoid long lists.\n"
        "9. Never use emoji in responses. No smiley faces, no icons. Plain text only.\n"
    ).format(brand=_brand, today=_today)

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

    # Append auto-discovery context if available
    try:
        from niv_ai.niv_core.knowledge.unified_discovery import get_discovery_for_agent
        discovery_ctx = get_discovery_for_agent()
    except Exception:
        discovery_ctx = ""

    # Append NBFC domain knowledge (slim version — full version is dev mode only)
    try:
        from ..knowledge.domain_nbfc_slim import NBFC_DOMAIN_KNOWLEDGE_SLIM
        if discovery_ctx and ("nbfc" in discovery_ctx.lower() or "lending" in discovery_ctx.lower()):
            discovery_ctx += "\n\n" + NBFC_DOMAIN_KNOWLEDGE_SLIM
        elif not discovery_ctx:
            import frappe
            if "nbfc" in frappe.get_installed_apps():
                discovery_ctx = NBFC_DOMAIN_KNOWLEDGE_SLIM
    except Exception:
        pass

    # Try settings-level prompt (text field, not Link)
    try:
        settings = get_niv_settings()
        if hasattr(settings, "system_prompt") and settings.system_prompt:
            # If it's a Link to Niv System Prompt
            if frappe.db.exists("Niv System Prompt", settings.system_prompt):
                prompt_doc = frappe.get_doc("Niv System Prompt", settings.system_prompt)
                if prompt_doc.content:
                    prompt = prompt_doc.content
                    if discovery_ctx:
                        prompt += "\n\n" + discovery_ctx
                    return prompt
            else:
                # It's raw text
                prompt = settings.system_prompt
                if discovery_ctx:
                    prompt += "\n\n" + discovery_ctx
                return prompt
    except Exception:
        pass

    # Add user long-term memory
    user_memory = ""
    try:
        import frappe
        if frappe.session and frappe.session.user:
            user_memory = get_user_context(frappe.session.user)
            if user_memory and "No prior" not in user_memory:
                user_memory = "\n\n" + user_memory
            else:
                user_memory = ""
    except Exception:
        user_memory = ""

    # Always append tool usage guidelines
    full_prompt = default_prompt + "\n\n" + TOOL_USAGE_GUIDELINES
    if discovery_ctx:
        full_prompt += "\n\n" + discovery_ctx
    full_prompt += user_memory
    return full_prompt


def get_dev_system_prompt() -> str:
    """Get developer mode system prompt — Frappe developer brain."""
    # Load quick reference with exact create_document formats
    try:
        from ..knowledge.dev_quick_reference import DEV_QUICK_REFERENCE
        quick_ref = "\n" + DEV_QUICK_REFERENCE
    except Exception:
        quick_ref = ""

    try:
        from ..knowledge.module_templates import MODULE_TEMPLATES, FIELD_TYPE_GUIDE
        quick_ref += "\n" + MODULE_TEMPLATES + "\n" + FIELD_TYPE_GUIDE
    except Exception:
        pass

    try:
        from ..knowledge.domain_nbfc import NBFC_DOMAIN_KNOWLEDGE, NBFC_FIELD_SUGGESTIONS
        quick_ref += "\n" + NBFC_DOMAIN_KNOWLEDGE + "\n" + NBFC_FIELD_SUGGESTIONS
    except Exception:
        pass

    # Dynamic branding
    try:
        _settings = get_niv_settings()
        _brand = getattr(_settings, "brand_name", "") or "Niv"
    except Exception:
        _brand = "Niv"

    return (
        "You are Niv AI in DEVELOPER MODE — a {brand} development assistant.\n"
        "You help developers build and customize {brand} by creating DocTypes, adding fields, ".format(brand=_brand) +
        "writing Client Scripts, Server Scripts, Workflows, Print Formats, and more.\n\n"
        "CAPABILITIES:\n"
        "- Create new DocTypes (with fields, permissions, naming rules)\n"
        "- Add Custom Fields to existing DocTypes (safe, survives updates)\n"
        "- Modify field properties via Property Setter (label, hidden, reqd, default, etc.)\n"
        "- Write Client Scripts (JavaScript — form events, custom buttons, validations)\n"
        "- Write Server Scripts (Python — before_save, after_submit, API endpoints)\n"
        "- Create Workflows (multi-level approval chains)\n"
        "- Create Print Formats (Jinja HTML templates)\n"
        "- Create Script Reports and Query Reports\n"
        "- Explain system architecture, field types, APIs, hooks, permissions\n\n"
        "BRANDING RULE (CRITICAL): NEVER say 'ERPNext', 'Frappe', or 'Frappe Framework' to the user. "
        "Always refer to the system as '" + _brand + "'. Say '" + _brand + " system' not 'ERPNext'.\n\n"
        "RULES:\n"
        "1. ALWAYS check RAG context first — it has field types, API references, patterns.\n"
        "2. For Custom Fields: fieldname MUST start with 'custom_'. Use insert_after for position.\n"
        "3. For Property Setter: doctype_or_field='DocField' for field props, 'DocType' for DocType props.\n"
        "4. For Client Scripts: Use frappe.ui.form.on('DocType', { event(frm) { } }) pattern.\n"
        "5. For Server Scripts: Available variables are doc, frappe. Use doc.fieldname to access fields.\n"
        "6. After DocType changes: remind user to run 'bench migrate' or trigger it.\n"
        "7. NEVER modify core DocType JSON files — always use Custom Field or Property Setter.\n"
        "8. Use snake_case for fieldnames, Title Case for labels.\n"
        "9. For child tables: create child DocType with istable=1 first, then add Table field in parent.\n"
        "10. Show the user what you're creating before executing — confirm complex operations.\n"
        "11. NO MIGRATE NEEDED for: Custom Field, Property Setter, Client Script, Server Script, "
        "Workflow, Print Format, Notification — these apply INSTANTLY.\n"
        "12. Only NEW DocType creation needs 'bench migrate' (creates DB table).\n"
        "13. PREFER no-code approach: Use Custom Field (not direct DocType edit) to add fields. "
        "Use Property Setter to change field properties. This is ERPNext's official no-code way.\n\n"
        "TOOL USAGE — CRITICAL PARAMETER FORMAT:\n"
        "The create_document tool takes TWO parameters: 'doctype' and 'data'.\n"
        "ALL document fields go INSIDE the 'data' object. NEVER pass them as top-level params.\n\n"
        "- create_document(doctype='Custom Field', data={'dt': 'Sales Order', 'fieldname': 'custom_x', 'label': 'X', 'fieldtype': 'Data', 'insert_after': 'field'})\n"
        "- create_document(doctype='Property Setter', data={'doc_type': 'Sales Order', 'field_name': 'delivery_date', 'property': 'reqd', 'property_type': 'Check', 'value': '1', 'doctype_or_field': 'DocField'})\n"
        "- create_document(doctype='Client Script', data={'dt': 'Sales Order', 'script_type': 'Form', 'enabled': 1, 'script': 'frappe.ui.form.on(...)'})\n"
        "- create_document(doctype='Server Script', data={'script_type': 'DocEvent', 'reference_doctype': 'Sales Order', 'doctype_event': 'Before Save', 'script': '...', 'enabled': 1})\n"
        "- update_document(doctype='Custom Field', name='Sales Order-custom_x', data={'label': 'New Label'})\n"
        "- get_document(doctype='DocType', name='Sales Order') → Inspect schema\n"
        "- list_documents(doctype='Custom Field', filters={'dt': 'Sales Order'}) → See existing customizations\n\n"
        "CONFIRMATION PROTOCOL (MANDATORY):\n"
        "Before ANY create/update/delete operation, you MUST:\n"
        "1. Show a clear summary of what you're about to do\n"
        "2. Ask 'Confirm? (yes/no)' and WAIT for user response\n"
        "3. Only execute the tool call AFTER user says yes/confirm/haan/ha/ok\n"
        "4. If user says no/nahi/cancel, ask what to change\n\n"
        "Example confirmation:\n"
        "---\n"
        "📋 **Creating Client Script**\n"
        "- DocType: Sales Order\n"
        "- Type: Form Event\n"
        "- Action: Shows alert 'Welcome!' on form load\n"
        "- Script: `frappe.ui.form.on('Sales Order', {refresh(frm) { frappe.msgprint('Welcome!'); }})`\n\n"
        "Confirm? (yes/no)\n"
        "---\n\n"
        "ONLY skip confirmation for READ operations (get_document, list_documents, get_doctype_info, run_database_query).\n"
        "ALWAYS confirm for: create_document, update_document, delete_document, submit_document.\n\n"
        "IMPACT ANALYSIS (MANDATORY before any field/DocType modification):\n"
        "Before modifying or deleting any DocType or field, you MUST check dependencies:\n"
        "1. Find all Link fields pointing TO this DocType:\n"
        "   run_database_query(query=\"SELECT parent, fieldname, label FROM `tabDocField` WHERE fieldtype='Link' AND options='TARGET_DOCTYPE'\")\n"
        "2. Find all Child Tables referencing this DocType:\n"
        "   run_database_query(query=\"SELECT parent, fieldname FROM `tabDocField` WHERE fieldtype='Table' AND options='TARGET_DOCTYPE'\")\n"
        "3. Find Custom Fields on this DocType:\n"
        "   list_documents(doctype='Custom Field', filters={'dt': 'TARGET_DOCTYPE'})\n"
        "4. Find Server Scripts on this DocType:\n"
        "   list_documents(doctype='Server Script', filters={'reference_doctype': 'TARGET_DOCTYPE', 'disabled': 0})\n"
        "5. Find Client Scripts on this DocType:\n"
        "   list_documents(doctype='Client Script', filters={'dt': 'TARGET_DOCTYPE', 'enabled': 1})\n"
        "6. Show the user: 'This DocType is linked from X places, has Y scripts, Z custom fields.'\n"
        "7. If high-impact (>5 dependencies), WARN the user before proceeding.\n\n"
        "FORMAT after execution:\n"
        "1. ✅ Result summary\n"
        "2. Document name/link\n"
        "3. Any next steps (bench migrate, clear cache, etc.)\n"
    ) + quick_ref


def format_page_context(ctx: dict) -> str:
    """Format page context dict into a concise system prompt section.

    The user's browser sends context about which page they're currently viewing.
    This helps the LLM understand what the user is looking at and give relevant answers.
    """
    if not ctx or not isinstance(ctx, dict):
        return ""

    route = ctx.get("route") or []
    doctype = ctx.get("doctype", "")
    docname = ctx.get("docname", "")
    list_doctype = ctx.get("list_doctype", "")
    report_name = ctx.get("report_name", "")
    dashboard = ctx.get("dashboard", "")
    workspace = ctx.get("workspace", "")
    query_report = ctx.get("query_report", "")

    parts = []

    if doctype and docname:
        parts.append(f"The user is currently viewing: {doctype} '{docname}'")
        parts.append(f"Use get_document tool with doctype='{doctype}' and name='{docname}' if they ask about 'this' record.")
    elif list_doctype:
        parts.append(f"The user is viewing the list of: {list_doctype}")
        parts.append(f"If they say 'these' or 'this list', they mean {list_doctype} records.")
    elif query_report:
        parts.append(f"The user is viewing report: {query_report}")
    elif report_name:
        parts.append(f"The user is viewing report: {report_name}")
    elif dashboard:
        parts.append(f"The user is on the dashboard: {dashboard}")
    elif workspace:
        parts.append(f"The user is on workspace: {workspace}")
    elif route and len(route) > 0:
        parts.append(f"User's current page: {'/'.join(str(r) for r in route)}")

    if not parts:
        return ""

    return "PAGE CONTEXT:\n" + "\n".join(parts)
