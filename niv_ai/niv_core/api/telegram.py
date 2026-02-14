"""
Niv AI — Telegram Bot Webhook (v3 — Progressive Updates)
Streams agent output with real-time tool call updates and progressive text.
"""
import json
import time
import requests
import frappe
from frappe import _


# Tool name → friendly emoji/label mapping
TOOL_LABELS = {
    "run_database_query": "📊 Database query chala raha hoon...",
    "list_documents": "📋 Documents search kar raha hoon...",
    "get_document": "📄 Document fetch kar raha hoon...",
    "create_document": "✏️ Document bana raha hoon...",
    "update_document": "📝 Document update kar raha hoon...",
    "delete_document": "🗑️ Document delete kar raha hoon...",
    "submit_document": "✅ Document submit kar raha hoon...",
    "search_documents": "🔍 Documents search kar raha hoon...",
    "search_doctype": "🔍 DocType search kar raha hoon...",
    "search_link": "🔗 Link search kar raha hoon...",
    "search": "🔍 Search kar raha hoon...",
    "fetch": "📥 Data fetch kar raha hoon...",
    "get_doctype_info": "ℹ️ DocType info le raha hoon...",
    "generate_report": "📊 Report generate kar raha hoon...",
    "run_python_code": "🐍 Code execute kar raha hoon...",
    "analyze_business_data": "📈 Business data analyze kar raha hoon...",
    "universal_search": "🔍 Universal search kar raha hoon...",
    "explore_fields": "🧩 Fields explore kar raha hoon...",
    "introspect_system": "🔬 System introspect kar raha hoon...",
    "run_workflow": "⚙️ Workflow run kar raha hoon...",
    "create_dashboard": "📊 Dashboard bana raha hoon...",
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
        first_name = message["from"].get("first_name", "")

        if not text:
            return {"ok": True}

        if text == "/start":
            _send_telegram(chat_id, "🤖 *Namaste! Main Niv AI hoon* — aapka ERPNext AI assistant.\n\nMujhse kuch bhi pucho:\n• \"Aaj ki sales kitni?\"\n• \"Naya Customer banao\"\n• \"Pending invoices dikhao\"\n\nShuru karte hain! 🚀")
            return {"ok": True}

        if text == "/help":
            _send_telegram(chat_id, "🔧 *Commands:*\n/start — Welcome message\n/help — Ye message\n\n💬 Kuch bhi type karo — main ERPNext se answer dunga!\n\n*Examples:*\n• Aaj ke Sales Orders dikhao\n• Naya Customer banao naam XYZ\n• Total revenue kitna hai?")
            return {"ok": True}

        # Map telegram user
        frappe_user = _get_frappe_user(telegram_user_id, chat_id)
        if not frappe_user:
            _send_telegram(chat_id, "❌ Aapka account link nahi hai.\n\nAdmin se Niv Telegram User mein apna Telegram ID map karwao.")
            return {"ok": True}

        # Send processing indicator
        status_msg_id = _send_telegram_get_id(chat_id, "⏳ Processing...")

        # Get or create conversation
        conversation_id = _get_or_create_conversation(frappe_user, chat_id)

        # Run agent with streaming for progressive updates
        frappe.set_user(frappe_user)
        
        from niv_ai.niv_core.utils import get_niv_settings
        settings = get_niv_settings()
        use_a2a = getattr(settings, "enable_a2a", 0)

        # Prepend Telegram formatting hint to user message
        telegram_hint = "[TELEGRAM BOT — Format rules: Use markdown tables with | pipes. Use bullet lists instead of wide tables. Keep responses concise. Use bold (*text*) for emphasis. Hindi/Hinglish reply preferred.]\n\n"
        agent_message = telegram_hint + text

        full_response = ""
        tool_calls_shown = set()
        last_status_update = time.time()

        def _handle_event(event):
            nonlocal full_response, status_msg_id
            event_type = event.get("type")

            if event_type == "tool_call":
                tool_name = event.get("tool", "unknown")
                if tool_name not in tool_calls_shown:
                    tool_calls_shown.add(tool_name)
                    label = TOOL_LABELS.get(tool_name, "🔧 {} chala raha hoon...".format(tool_name))
                    # Update status message
                    if status_msg_id:
                        tools_text = "\n".join([
                            TOOL_LABELS.get(t, "🔧 {}".format(t)) 
                            for t in tool_calls_shown
                        ])
                        _edit_telegram(chat_id, status_msg_id, "⏳ Working...\n\n{}".format(tools_text))
                    # Keep typing indicator alive
                    _send_chat_action(chat_id, "typing")

            elif event_type == "token":
                content = event.get("content", "")
                full_response += content

            elif event_type == "error":
                full_response = "⚠️ Error: {}".format(event.get("content", "Unknown error"))

        try:
            if use_a2a:
                from niv_ai.niv_core.adk.stream_handler import stream_agent_adk
                for event in stream_agent_adk(
                    message=agent_message,
                    conversation_id=conversation_id,
                    user=frappe_user,
                ):
                    _handle_event(event)
            else:
                from niv_ai.niv_core.langchain.agent import stream_agent
                for event in stream_agent(
                    message=agent_message,
                    conversation_id=conversation_id,
                    user=frappe_user,
                ):
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

        # Format response for Telegram
        final_msg = _format_for_telegram(full_response)
        
        # Add tool calls header if tools were used
        if tool_calls_shown:
            tools_header = "🔧 *Tools used:*\n"
            for t in tool_calls_shown:
                label = TOOL_LABELS.get(t, t)
                # Remove "kar raha hoon..." suffix for summary
                short = label.split("...")[0].strip() if "..." in label else label
                tools_header += "  • {}\n".format(short)
            tools_header += "\n"
            final_msg = tools_header + final_msg

        # Send final response
        _send_long_message(chat_id, final_msg)
        frappe.db.commit()

        return {"ok": True}

    except Exception as e:
        frappe.log_error("Niv Telegram Bot Error", frappe.get_traceback())
        try:
            if 'chat_id' in locals():
                _send_telegram(chat_id, "⚠️ Error: {}".format(str(e)[:200]))
        except Exception:
            pass
        return {"ok": True}


def _get_frappe_user(telegram_user_id, chat_id):
    """Map Telegram user ID to Frappe user."""
    users = frappe.get_all(
        "Niv Telegram User",
        filters={"telegram_user_id": telegram_user_id, "enabled": 1},
        fields=["frappe_user"],
        limit=1,
    )
    if users:
        return users[0].frappe_user

    users = frappe.get_all(
        "Niv Telegram User",
        filters={"telegram_chat_id": str(chat_id), "enabled": 1},
        fields=["frappe_user"],
        limit=1,
    )
    if users:
        return users[0].frappe_user

    return None


def _get_or_create_conversation(user, chat_id):
    """Get existing Telegram conversation or create new one."""
    convs = frappe.get_all(
        "Niv Conversation",
        filters={"owner": user, "channel": "telegram", "channel_id": str(chat_id)},
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )
    if convs:
        return convs[0].name

    conv = frappe.get_doc({
        "doctype": "Niv Conversation",
        "user": user,
        "title": "Telegram Chat",
        "channel": "telegram",
        "channel_id": str(chat_id),
    })
    conv.insert(ignore_permissions=True)
    frappe.db.commit()
    return conv.name


def _get_bot_token():
    """Get Telegram bot token from Niv Settings."""
    try:
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        try:
            settings = frappe.get_doc("Niv Settings")
            token = getattr(settings, "telegram_bot_token", None)
            if token:
                return settings.get_password("telegram_bot_token")
            return None
        finally:
            frappe.set_user(current_user)
    except Exception as e:
        frappe.logger("telegram").error("Token error: {}".format(str(e)))
        return None


def _format_for_telegram(text):
    """Convert markdown to Telegram-friendly format.
    - Markdown tables (|...|) → monospace pre blocks
    - Space-aligned tables (--- lines) → monospace pre blocks
    - Headers → bold
    - Escape Telegram markdown special chars in regular text
    """
    import re
    
    lines = text.split("\n")
    result = []
    table_block = []
    in_pipe_table = False
    in_space_table = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # === Pipe table detection (|col1|col2|) ===
        if stripped.startswith("|") and stripped.endswith("|"):
            # Separator row — skip
            if re.match(r'^[\|\s\-:]+$', stripped):
                i += 1
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if cells:
                table_block.append(cells)
                in_pipe_table = True
            i += 1
            continue
        
        # Flush pipe table
        if in_pipe_table and table_block:
            result.append(_render_table_cells(table_block))
            table_block = []
            in_pipe_table = False
        
        # === Space-aligned table detection (line of dashes like --------) ===
        if re.match(r'^[\-\s]{10,}$', stripped) and not in_space_table:
            # Look back — previous line is likely header
            # Look forward — next lines are data rows
            in_space_table = True
            # Previous line was header — wrap it
            header = result.pop() if result else ""
            table_block = [header]
            i += 1
            continue
        
        if in_space_table:
            if stripped and not re.match(r'^[\-\s]{10,}$', stripped):
                table_block.append(line)
                i += 1
                continue
            else:
                # End of space table — flush
                if table_block:
                    result.append("```\n{}\n```".format("\n".join(table_block)))
                    table_block = []
                in_space_table = False
                if re.match(r'^[\-\s]{10,}$', stripped):
                    i += 1
                    continue
        
        # === Headers → bold ===
        if stripped.startswith("#"):
            clean = stripped.lstrip("#").strip()
            # Escape any * in header text
            result.append("*{}*".format(clean.replace("*", "")))
        else:
            result.append(line)
        
        i += 1
    
    # Flush remaining tables
    if in_pipe_table and table_block:
        result.append(_render_table_cells(table_block))
    if in_space_table and table_block:
        result.append("```\n{}\n```".format("\n".join(table_block)))
    
    return "\n".join(result)


def _render_table_cells(rows):
    """Render parsed table cells as monospace pre block."""
    if not rows:
        return ""
    
    num_cols = max(len(r) for r in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], len(cell))
    
    formatted = []
    for idx, row in enumerate(rows):
        parts = []
        for i in range(num_cols):
            cell = row[i] if i < len(row) else ""
            parts.append(cell.ljust(col_widths[i]))
        formatted.append(" | ".join(parts))
        if idx == 0:
            formatted.append(" | ".join(["-" * w for w in col_widths]))
    
    return "```\n{}\n```".format("\n".join(formatted))


def _send_telegram(chat_id, text, parse_mode="Markdown"):
    """Send message to Telegram chat."""
    token = _get_bot_token()
    if not token:
        return None

    url = "https://api.telegram.org/bot{}/sendMessage".format(token)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok and parse_mode:
            # Markdown failed — retry plain
            payload.pop("parse_mode")
            r = requests.post(url, json=payload, timeout=10)
        return r.json().get("result", {}).get("message_id") if r.ok else None
    except Exception:
        return None


def _send_telegram_get_id(chat_id, text):
    """Send message and return message_id for later editing/deletion."""
    return _send_telegram(chat_id, text)


def _edit_telegram(chat_id, message_id, text, parse_mode="Markdown"):
    """Edit an existing Telegram message."""
    token = _get_bot_token()
    if not token or not message_id:
        return

    url = "https://api.telegram.org/bot{}/editMessageText".format(token)
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def _delete_telegram(chat_id, message_id):
    """Delete a Telegram message."""
    token = _get_bot_token()
    if not token or not message_id:
        return

    url = "https://api.telegram.org/bot{}/deleteMessage".format(token)
    try:
        requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=5)
    except Exception:
        pass


def _send_long_message(chat_id, text):
    """Split and send messages longer than 4096 chars."""
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        _send_telegram(chat_id, text)
        return

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        _send_telegram(chat_id, chunk)


def _send_chat_action(chat_id, action="typing"):
    """Send typing indicator."""
    token = _get_bot_token()
    if not token:
        return
    url = "https://api.telegram.org/bot{}/sendChatAction".format(token)
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except Exception:
        pass


@frappe.whitelist(methods=["POST"])
def setup_webhook():
    """Setup Telegram webhook URL."""
    frappe.only_for("System Manager")
    
    settings = frappe.get_doc("Niv Settings")
    token = settings.get_password("telegram_bot_token") if getattr(settings, "telegram_bot_token", None) else None
    webhook_url = getattr(settings, "telegram_webhook_url", None)
    
    if not token:
        frappe.throw(_("Telegram Bot Token not set"))
    if not webhook_url:
        frappe.throw(_("Webhook URL not set"))

    if not webhook_url.endswith("/api/method/niv_ai.niv_core.api.telegram.webhook"):
        webhook_url = webhook_url.rstrip("/") + "/api/method/niv_ai.niv_core.api.telegram.webhook"

    url = "https://api.telegram.org/bot{}/setWebhook".format(token)
    r = requests.post(url, json={"url": webhook_url}, timeout=10)
    result = r.json()

    if result.get("ok"):
        frappe.msgprint(_("✅ Telegram webhook set!"))
    else:
        frappe.throw(_("❌ Failed: {}".format(result.get("description", "Unknown"))))
    return result


@frappe.whitelist(methods=["POST"])
def link_user(telegram_user_id, frappe_user_email):
    """Link Telegram user to Frappe user."""
    frappe.only_for("System Manager")
    
    if not frappe.db.exists("User", frappe_user_email):
        frappe.throw(_("User {} not found").format(frappe_user_email))

    existing = frappe.get_all("Niv Telegram User", filters={"telegram_user_id": str(telegram_user_id)}, limit=1)
    if existing:
        doc = frappe.get_doc("Niv Telegram User", existing[0].name)
        doc.frappe_user = frappe_user_email
        doc.enabled = 1
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Niv Telegram User",
            "telegram_user_id": str(telegram_user_id),
            "frappe_user": frappe_user_email,
            "enabled": 1,
        }).insert(ignore_permissions=True)
    
    frappe.db.commit()
    return {"ok": True}
