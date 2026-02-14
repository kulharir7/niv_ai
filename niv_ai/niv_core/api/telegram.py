"""
Niv AI — Telegram Bot Webhook (v3.1 — Progressive Updates & Thought Filtering)
Streams agent output with real-time tool call updates and progressive text.
Filters [THOUGHT] blocks to separate reasoning from the final answer.
"""
import json
import time
import requests
import frappe
import re
from frappe import _
from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message


# Tool name → friendly emoji/label mapping
TOOL_LABELS = {
    "run_database_query": "📊 Checking database...",
    "list_documents": "📋 Searching documents...",
    "get_document": "📄 Fetching details...",
    "create_document": "✏️ Creating document...",
    "update_document": "📝 Updating document...",
    "delete_document": "🗑️ Deleting document...",
    "submit_document": "✅ Submitting...",
    "search_documents": "🔍 Searching...",
    "search_doctype": "🔍 Finding DocType...",
    "search_link": "🔗 Finding link...",
    "search": "🔍 Searching...",
    "fetch": "📥 Fetching data...",
    "get_doctype_info": "ℹ️ Getting info...",
    "generate_report": "📊 Generating report...",
    "run_python_code": "🐍 Executing logic...",
    "analyze_business_data": "📈 Analyzing data...",
    "universal_search": "🔍 Universal search...",
    "explore_fields": "🧩 Exploring fields...",
    "introspect_system": "🔬 Introspecting system...",
    "run_workflow": "⚙️ Running workflow...",
    "create_dashboard": "📊 Creating dashboard...",
}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**kwargs):
    """Telegram webhook endpoint with progressive updates."""
    try:
        data = dict(frappe.form_dict)
        data.pop("cmd", None)

        if not data:
            return {"ok": True}

        message = data.get("message") or data.get("edited_message")
        if not message:
            return {"ok": True}

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        telegram_user_id = str(message["from"]["id"])
        
        if not text:
            return {"ok": True}

        if text == "/start":
            _send_telegram(chat_id, "🤖 *Namaste! Main Niv AI hoon* — aapka ERPNext assistant.\n\nMujhse kuch bhi pucho:\n• \"Aaj ki sales kitni?\"\n• \"Naya Customer banao\"\n• \"Pending invoices dikhao\"\n\nShuru karte hain! 🚀")
            return {"ok": True}

        if text == "/help":
            _send_telegram(chat_id, "🔧 *Commands:*\n/start — Welcome message\n/help — Help guide\n\n💬 Kuch bhi type karo — main ERPNext se answer dunga!\n\n*Examples:*\n• Aaj ke Sales Orders dikhao\n• Naya Customer banao naam XYZ\n• Total revenue kitna hai?")
            return {"ok": True}

        # Map telegram user
        frappe_user = _get_frappe_user(telegram_user_id, chat_id)
        if not frappe_user:
            _send_telegram(chat_id, "❌ Aapka account link nahi hai.\n\nAdmin se Niv Telegram User mein apna Telegram ID map karwao.")
            return {"ok": True}

        # Send processing indicator
        status_msg_id = _send_telegram_get_id(chat_id, "⏳ Thinking...")

        # Get or create conversation
        conversation_id = _get_or_create_conversation(frappe_user, chat_id)

        # Run agent with streaming for progressive updates
        frappe.set_user(frappe_user)
        
        from niv_ai.niv_core.utils import get_niv_settings
        settings = get_niv_settings()
        use_a2a = getattr(settings, "enable_a2a", 0)

        # Prepend Telegram formatting hint
        telegram_hint = (
            "[TELEGRAM BOT MODE]\n"
            "- CRITICAL: DO NOT include [THOUGHT] blocks in your final output tokens.\n"
            "- LANGUAGE: Reply in the SAME language as the user (Hindi -> Hindi, English -> English, Hinglish -> Hinglish).\n"
            "- Format: Use markdown tables with | pipes. Use bullet lists for long data.\n"
            "- Bold (*text*) for emphasis.\n\n"
        )
        agent_message = telegram_hint + text

        full_response = ""
        tool_calls_shown = set()

        def _handle_event(event):
            nonlocal full_response, status_msg_id
            event_type = event.get("type")

            if event_type == "tool_call":
                tool_name = event.get("tool", "unknown")
                if tool_name not in tool_calls_shown:
                    tool_calls_shown.add(tool_name)
                    if status_msg_id:
                        tools_text = "\n".join([
                            TOOL_LABELS.get(t, "🔧 {}".format(t)) 
                            for t in tool_calls_shown
                        ])
                        _edit_telegram(chat_id, status_msg_id, "⏳ Working...\n\n{}".format(tools_text))
                    _send_chat_action(chat_id, "typing")

            elif event_type == "thought":
                # Show thoughts in status message instead of main response
                thought_content = event.get("content", "")
                if status_msg_id and thought_content:
                    _edit_telegram(chat_id, status_msg_id, "🤔 *Thinking...*\n\n_{}_".format(thought_content[:200]))

            elif event_type == "token":
                full_response += event.get("content", "")

            elif event_type == "error":
                full_response = "⚠️ Error: {}".format(event.get("content", "Unknown error"))

        try:
            if use_a2a:
                from niv_ai.niv_core.adk.stream_handler import stream_agent_adk
                for event in stream_agent_adk(message=agent_message, conversation_id=conversation_id, user=frappe_user):
                    _handle_event(event)
            else:
                from niv_ai.niv_core.langchain.agent import stream_agent
                for event in stream_agent(message=agent_message, conversation_id=conversation_id, user=frappe_user):
                    _handle_event(event)

        except Exception as e:
            frappe.log_error("Telegram Stream Error", frappe.get_traceback())
            full_response = "⚠️ Agent error: {}".format(str(e)[:200])

        if not full_response:
            full_response = "🤔 Koi response nahi mila. Dobara try karo."

        # Delete status message
        if status_msg_id:
            _delete_telegram(chat_id, status_msg_id)

        # Save messages
        save_user_message(conversation_id, text)
        save_assistant_message(conversation_id, full_response)

        # Format and Filter Response
        final_msg = _format_for_telegram(full_response)
        
        # Add tool summary if tools were used
        if tool_calls_shown:
            tools_header = "🔧 *Tools used:*\n"
            for t in tool_calls_shown:
                label = TOOL_LABELS.get(t, t)
                short = label.split("...")[0].strip() if "..." in label else label
                tools_header += "  • {}\n".format(short)
            final_msg = tools_header + "\n" + final_msg

        # Send final response
        _send_long_message(chat_id, final_msg)
        frappe.db.commit()

        return {"ok": True}

    except Exception as e:
        frappe.log_error("Niv Telegram Bot Error", frappe.get_traceback())
        return {"ok": True}


def _get_frappe_user(telegram_user_id, chat_id):
    """Map Telegram user ID to Frappe user."""
    users = frappe.get_all("Niv Telegram User", filters={"telegram_user_id": telegram_user_id, "enabled": 1}, fields=["frappe_user"])
    if users: return users[0].frappe_user
    users = frappe.get_all("Niv Telegram User", filters={"telegram_chat_id": str(chat_id), "enabled": 1}, fields=["frappe_user"])
    if users: return users[0].frappe_user
    return None


def _get_or_create_conversation(user, chat_id):
    """Get existing Telegram conversation or create new one."""
    convs = frappe.get_all("Niv Conversation", filters={"owner": user, "channel": "telegram", "channel_id": str(chat_id)}, fields=["name"], order_by="modified desc", limit=1)
    if convs: return convs[0].name
    conv = frappe.get_doc({"doctype": "Niv Conversation", "user": user, "title": "Telegram Chat", "channel": "telegram", "channel_id": str(chat_id)})
    conv.insert(ignore_permissions=True)
    frappe.db.commit()
    return conv.name


def _get_bot_token():
    """Get Telegram bot token from Niv Settings."""
    try:
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        settings = frappe.get_doc("Niv Settings")
        return settings.get_password("telegram_bot_token")
    except Exception:
        return None
    finally:
        frappe.set_user(current_user)


def _format_for_telegram(text):
    """Clean reasoning [THOUGHT] blocks and format markdown for Telegram."""
    
    # 1. Extract and separate [THOUGHT] blocks
    # Logic: If [THOUGHT] exists, move it to a header or hide it.
    thought_match = re.search(r'\[THOUGHT\](.*?)(\[THOUGHT\]|Namaste|hy|hello|Namaste|$)', text, re.DOTALL | re.IGNORECASE)
    if thought_match:
        thought_content = thought_match.group(1).strip()
        # Remove thought from main text
        text = text.replace("[THOUGHT]{}[THOUGHT]".format(thought_content), "").replace("[THOUGHT]{}".format(thought_content), "").strip()
        # If text starts with something like "Thinking complete...", clean that too
        text = re.sub(r'^(Thinking complete|Thought process finished).*?\n', '', text, flags=re.IGNORECASE)
        # Prefix the main text with a clean thought indicator
        if thought_content:
            text = "🧠 _Thinking:_ {}\n\n---\n\n{}".format(thought_content[:300] + "..." if len(thought_content) > 300 else thought_content, text)

    lines = text.split("\n")
    result = []
    table_block = []
    in_pipe_table = False
    in_space_table = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Pipe table detection
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r'^[\|\s\-:]+$', stripped):
                i += 1; continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if cells:
                table_block.append(cells)
                in_pipe_table = True
            i += 1; continue
        
        if in_pipe_table and table_block:
            result.append(_render_table_cells(table_block))
            table_block = []; in_pipe_table = False
        
        # Space table detection
        if re.match(r'^[\-\s]{10,}$', stripped) and not in_space_table:
            in_space_table = True
            header = result.pop() if result else ""
            table_block = [header]
            i += 1; continue
        
        if in_space_table:
            if stripped and not re.match(r'^[\-\s]{10,}$', stripped):
                table_block.append(line)
                i += 1; continue
            else:
                if table_block:
                    result.append("```\n{}\n```".format("\n".join(table_block)))
                    table_block = []
                in_space_table = False
                if re.match(r'^[\-\s]{10,}$', stripped): i += 1; continue
        
        # Headers -> bold
        if stripped.startswith("#"):
            result.append("*{}*".format(stripped.lstrip("#").strip().replace("*", "")))
        else:
            result.append(line)
        i += 1
    
    if in_pipe_table and table_block: result.append(_render_table_cells(table_block))
    if in_space_table and table_block: result.append("```\n{}\n```".format("\n".join(table_block)))
    
    return "\n".join(result)


def _render_table_cells(rows):
    if not rows: return ""
    num_cols = max(len(r) for r in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols: col_widths[i] = max(col_widths[i], len(cell))
    formatted = []
    for idx, row in enumerate(rows):
        parts = []
        for i in range(num_cols):
            cell = row[i] if i < len(row) else ""
            parts.append(cell.ljust(col_widths[i]))
        formatted.append(" | ".join(parts))
        if idx == 0: formatted.append(" | ".join(["-" * w for w in col_widths]))
    return "```\n{}\n```".format("\n".join(formatted))


def _send_telegram(chat_id, text, parse_mode="Markdown"):
    token = _get_bot_token()
    if not token: return None
    url = "https://api.telegram.org/bot{}/sendMessage".format(token)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            r = requests.post(url, json=payload, timeout=15)
        return r.json().get("result", {}).get("message_id") if r.ok else None
    except Exception: return None


def _send_telegram_get_id(chat_id, text):
    return _send_telegram(chat_id, text)


def _edit_telegram(chat_id, message_id, text, parse_mode="Markdown"):
    token = _get_bot_token()
    if not token or not message_id: return
    url = "https://api.telegram.org/bot{}/editMessageText".format(token)
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            requests.post(url, json=payload, timeout=10)
    except Exception: pass


def _delete_telegram(chat_id, message_id):
    token = _get_bot_token()
    if not token or not message_id: return
    url = "https://api.telegram.org/bot{}/deleteMessage".format(token)
    try: requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=5)
    except Exception: pass


def _send_long_message(chat_id, text):
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        _send_telegram(chat_id, text)
        return
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN:
            if current: chunks.append(current)
            current = line
        else: current = current + "\n" + line if current else line
    if current: chunks.append(current)
    for chunk in chunks: _send_telegram(chat_id, chunk)


def _send_chat_action(chat_id, action="typing"):
    token = _get_bot_token()
    if not token: return
    url = "https://api.telegram.org/bot{}/sendChatAction".format(token)
    try: requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except Exception: pass


@frappe.whitelist(methods=["POST"])
def setup_webhook():
    frappe.only_for("System Manager")
    settings = frappe.get_doc("Niv Settings")
    token = settings.get_password("telegram_bot_token")
    webhook_url = getattr(settings, "telegram_webhook_url", None)
    if not token: frappe.throw(_("Telegram Bot Token not set"))
    if not webhook_url: frappe.throw(_("Webhook URL not set"))
    if not webhook_url.endswith("/api/method/niv_ai.niv_core.api.telegram.webhook"):
        webhook_url = webhook_url.rstrip("/") + "/api/method/niv_ai.niv_core.api.telegram.webhook"
    url = "https://api.telegram.org/bot{}/setWebhook".format(token)
    r = requests.post(url, json={"url": webhook_url}, timeout=10)
    result = r.json()
    if result.get("ok"): frappe.msgprint(_("✅ Telegram webhook set!"))
    else: frappe.throw(_("❌ Failed: {}".format(result.get("description", "Unknown"))))
    return result
