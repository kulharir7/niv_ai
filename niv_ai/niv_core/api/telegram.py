"""
Niv AI — Telegram Bot Webhook
Receives messages from Telegram, runs through Niv AI agent, sends response back.
"""
import json
import requests
import frappe
from frappe import _


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**kwargs):
    """Telegram webhook endpoint. Called by Telegram servers on every message."""
    try:
        # Frappe parses JSON body into kwargs and form_dict
        data = dict(frappe.form_dict)
        # Remove 'cmd' key added by Frappe
        data.pop("cmd", None)

        frappe.logger("telegram").info("Webhook received: {}".format(json.dumps(data or {})[:500]))

        if not data:
            return {"ok": True}

        # Handle message
        message = data.get("message") or data.get("edited_message")
        if not message:
            # Maybe nested under frappe's wrapper
            if "message" in str(data):
                frappe.logger("telegram").info("Data keys: {}".format(list(data.keys()) if isinstance(data, dict) else type(data)))
            return {"ok": True}

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        telegram_user_id = str(message["from"]["id"])
        first_name = message["from"].get("first_name", "")

        frappe.logger("telegram").info("Message from {} ({}): {}".format(first_name, telegram_user_id, text))

        # Ignore empty messages
        if not text:
            return {"ok": True}

        if text == "/start":
            _send_telegram(chat_id, "🤖 Namaste! Main Niv AI hoon — aapka ERPNext AI assistant.\n\nMujhse kuch bhi pucho:\n• \"Aaj ki sales kitni?\"\n• \"Naya Customer banao\"\n• \"Pending invoices dikhao\"\n\nShuru karte hain! 🚀")
            return {"ok": True}

        # Map telegram user to Frappe user
        frappe_user = _get_frappe_user(telegram_user_id, chat_id)
        if not frappe_user:
            _send_telegram(chat_id, "❌ Aapka account link nahi hai. Admin se setup karwao.\n\nAdmin: Niv Telegram User mein Telegram ID aur Frappe user map karo.")
            return {"ok": True}

        # Send "typing" indicator
        _send_chat_action(chat_id, "typing")

        # Get or create conversation for this chat
        conversation_id = _get_or_create_conversation(frappe_user, chat_id)

        # Run Niv AI agent
        frappe.set_user(frappe_user)
        
        from niv_ai.niv_core.langchain.agent import run_agent
        from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message
        
        frappe.logger("telegram").info("Running agent for user {} conv {}".format(frappe_user, conversation_id))
        
        response = run_agent(
            message=text,
            conversation_id=conversation_id,
            user=frappe_user,
        )

        if not response:
            response = "🤔 Koi response nahi mila. Dobara try karo."

        frappe.logger("telegram").info("Agent response: {}".format(response[:200]))

        # Save messages
        save_user_message(conversation_id, text)
        save_assistant_message(conversation_id, response)

        # Send response (split if >4096 chars — Telegram limit)
        _send_long_message(chat_id, response)
        frappe.db.commit()

        return {"ok": True}

    except Exception as e:
        frappe.log_error("Niv Telegram Bot Error", frappe.get_traceback())
        frappe.logger("telegram").error("Webhook error: {}".format(str(e)))
        # Try to send error message to user
        try:
            if 'chat_id' in dir():
                _send_telegram(chat_id, "⚠️ Error: {}".format(str(e)[:200]))
        except Exception:
            pass
        return {"ok": True}


def _get_frappe_user(telegram_user_id, chat_id):
    """Map Telegram user ID to Frappe user. Returns email or None."""
    users = frappe.get_all(
        "Niv Telegram User",
        filters={"telegram_user_id": telegram_user_id, "enabled": 1},
        fields=["frappe_user"],
        limit=1,
    )
    if users:
        return users[0].frappe_user

    # Check chat_id mapping
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


def _send_telegram(chat_id, text, parse_mode="Markdown"):
    """Send message to Telegram chat."""
    token = _get_bot_token()
    if not token:
        frappe.logger("telegram").error("Bot token not configured")
        return

    url = "https://api.telegram.org/bot{}/sendMessage".format(token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        frappe.logger("telegram").info("Send result: {} {}".format(r.status_code, r.text[:200]))
        # If Markdown fails, retry without parse_mode
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            r2 = requests.post(url, json=payload, timeout=10)
            frappe.logger("telegram").info("Retry result: {} {}".format(r2.status_code, r2.text[:200]))
    except Exception as e:
        frappe.logger("telegram").error("Send error: {}".format(str(e)))


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


def _get_bot_token():
    """Get Telegram bot token from Niv Settings."""
    try:
        # Must read as Administrator to access Password fields
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


@frappe.whitelist(methods=["POST"])
def setup_webhook():
    """Setup Telegram webhook URL. Call from admin panel."""
    frappe.only_for("System Manager")
    
    settings = frappe.get_cached_doc("Niv Settings")
    token = settings.get_password("telegram_bot_token") if getattr(settings, "telegram_bot_token", None) else None
    webhook_url = getattr(settings, "telegram_webhook_url", None)
    
    if not token:
        frappe.throw(_("Telegram Bot Token not set in Niv Settings"))
    if not webhook_url:
        frappe.throw(_("Telegram Webhook URL not set in Niv Settings"))

    if not webhook_url.endswith("/api/method/niv_ai.niv_core.api.telegram.webhook"):
        webhook_url = webhook_url.rstrip("/") + "/api/method/niv_ai.niv_core.api.telegram.webhook"

    url = "https://api.telegram.org/bot{}/setWebhook".format(token)
    r = requests.post(url, json={"url": webhook_url}, timeout=10)
    result = r.json()

    if result.get("ok"):
        frappe.msgprint(_("✅ Telegram webhook set successfully!"))
    else:
        frappe.throw(_("❌ Failed: {}".format(result.get("description", "Unknown error"))))

    return result


@frappe.whitelist(methods=["POST"])
def link_user(telegram_user_id, frappe_user_email):
    """Link a Telegram user to a Frappe user. Admin only."""
    frappe.only_for("System Manager")
    
    if not frappe.db.exists("User", frappe_user_email):
        frappe.throw(_("User {} does not exist").format(frappe_user_email))

    existing = frappe.get_all(
        "Niv Telegram User",
        filters={"telegram_user_id": str(telegram_user_id)},
        limit=1,
    )
    if existing:
        doc = frappe.get_doc("Niv Telegram User", existing[0].name)
        doc.frappe_user = frappe_user_email
        doc.enabled = 1
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "Niv Telegram User",
            "telegram_user_id": str(telegram_user_id),
            "frappe_user": frappe_user_email,
            "enabled": 1,
        })
        doc.insert(ignore_permissions=True)
    
    frappe.db.commit()
    return {"ok": True, "message": "User linked successfully"}
