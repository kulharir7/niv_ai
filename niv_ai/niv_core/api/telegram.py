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
        
        from niv_ai.niv_core.langchain.agent import stream_agent
        from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message

        full_response = ""
        tool_calls_shown = set()
        last_status_update = time.time()

        try:
            for event in stream_agent(
                message=text,
                conversation_id=conversation_id,
                user=frappe_user,
            ):
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
                        else:
                            _send_telegram(chat_id, label)
                        # Keep typing indicator alive
                        _send_chat_action(chat_id, "typing")

                elif event_type == "tool_result":
                    # Tool finished — update status
                    _send_chat_action(chat_id, "typing")

                elif event_type == "token":
                    content = event.get("content", "")
                    full_response += content

                elif event_type == "error":
                    full_response = "⚠️ Error: {}".format(event.get("content", "Unknown error"))

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

        # Build final message with tool summary
        final_msg = full_response
        if tool_calls_shown:
            tools_summary = " | ".join(["🔧 {}".format(t) for t in tool_calls_shown])
            final_msg = "{}\n\n_Tools used: {}_".format(full_response, tools_summary)

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
