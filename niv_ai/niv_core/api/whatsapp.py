"""
Niv AI — WhatsApp Bot Webhook (Meta Cloud API)
Receives messages from WhatsApp, runs through Niv AI agent, sends response back.

Setup:
1. Create Meta Business App at https://developers.facebook.com
2. Add WhatsApp product
3. Get Phone Number ID, Access Token, Verify Token
4. Set in Niv Settings > WhatsApp section
5. Register webhook URL: https://yourdomain.com/api/method/niv_ai.niv_core.api.whatsapp.webhook
"""
import json
import requests
import frappe
from frappe import _


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def webhook(**kwargs):
    """WhatsApp webhook endpoint. Handles verification and messages."""
    try:
        # GET = Webhook verification (Meta sends challenge)
        if hasattr(frappe, 'request') and frappe.request and frappe.request.method == "GET":
            return _verify_webhook()

        # POST = Incoming message
        data = dict(frappe.form_dict)
        data.pop("cmd", None)

        if not data:
            return {"ok": True}

        # WhatsApp sends nested structure
        entry = data.get("entry", [])
        if not entry:
            return {"ok": True}

        for entry_item in entry:
            changes = entry_item.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                for msg in messages:
                    _process_whatsapp_message(msg, value)

        return {"ok": True}

    except Exception as e:
        frappe.log_error("Niv WhatsApp Bot Error", frappe.get_traceback())
        return {"ok": True}


def _verify_webhook():
    """Handle Meta webhook verification challenge."""
    mode = frappe.form_dict.get("hub.mode")
    token = frappe.form_dict.get("hub.verify_token")
    challenge = frappe.form_dict.get("hub.challenge")

    verify_token = _get_setting("whatsapp_verify_token")

    if mode == "subscribe" and token == verify_token:
        frappe.logger("whatsapp").info("Webhook verified!")
        frappe.response["type"] = "text"
        frappe.response["message"] = challenge
        return int(challenge)
    else:
        frappe.throw(_("Verification failed"), frappe.AuthenticationError)


def _process_whatsapp_message(msg, value):
    """Process a single WhatsApp message."""
    msg_type = msg.get("type")
    wa_id = msg.get("from")  # WhatsApp phone number
    
    # Only handle text messages for now
    if msg_type != "text":
        _send_whatsapp(wa_id, "🤖 Abhi sirf text messages support hain. Text mein likho!")
        return

    text = msg.get("text", {}).get("body", "").strip()
    if not text:
        return

    frappe.logger("whatsapp").info("Message from {}: {}".format(wa_id, text))

    # Map WhatsApp number to Frappe user
    frappe_user = _get_frappe_user(wa_id)
    if not frappe_user:
        _send_whatsapp(wa_id, "❌ Aapka number link nahi hai. Admin se setup karwao.\n\nAdmin: Niv WhatsApp User mein phone number aur Frappe user map karo.")
        return

    # Mark as read
    _mark_as_read(msg.get("id"))

    # Get or create conversation
    conversation_id = _get_or_create_conversation(frappe_user, wa_id)

    # Run Niv AI agent
    frappe.set_user(frappe_user)
    
    from niv_ai.niv_core.langchain.agent import run_agent
    from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message

    response = run_agent(
        message=text,
        conversation_id=conversation_id,
        user=frappe_user,
    )

    if not response:
        response = "🤔 Koi response nahi mila. Dobara try karo."

    # Save messages
    save_user_message(conversation_id, text)
    save_assistant_message(conversation_id, response)

    # Send response (WhatsApp limit is 4096 chars per message)
    _send_long_message(wa_id, response)
    frappe.db.commit()


def _get_frappe_user(wa_id):
    """Map WhatsApp number to Frappe user."""
    # Normalize: remove leading +, spaces
    wa_id_clean = wa_id.replace("+", "").replace(" ", "").strip()
    
    users = frappe.get_all(
        "Niv WhatsApp User",
        filters={"whatsapp_number": ["like", "%{}".format(wa_id_clean[-10:])], "enabled": 1},
        fields=["frappe_user"],
        limit=1,
    )
    if users:
        return users[0].frappe_user
    return None


def _get_or_create_conversation(user, wa_id):
    """Get existing WhatsApp conversation or create new one."""
    convs = frappe.get_all(
        "Niv Conversation",
        filters={"owner": user, "channel": "whatsapp", "channel_id": wa_id},
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )
    if convs:
        return convs[0].name

    conv = frappe.get_doc({
        "doctype": "Niv Conversation",
        "user": user,
        "title": "WhatsApp Chat",
        "channel": "whatsapp",
        "channel_id": wa_id,
    })
    conv.insert(ignore_permissions=True)
    frappe.db.commit()
    return conv.name


def _send_whatsapp(to, text):
    """Send text message via WhatsApp Cloud API."""
    token = _get_setting_password("whatsapp_access_token")
    phone_id = _get_setting("whatsapp_phone_number_id")
    
    if not token or not phone_id:
        frappe.logger("whatsapp").error("WhatsApp credentials not configured")
        return

    url = "https://graph.facebook.com/v21.0/{}/messages".format(phone_id)
    headers = {
        "Authorization": "Bearer {}".format(token),
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        frappe.logger("whatsapp").info("Send result: {} {}".format(r.status_code, r.text[:200]))
    except Exception as e:
        frappe.logger("whatsapp").error("Send error: {}".format(str(e)))


def _send_long_message(to, text):
    """Split and send messages longer than 4096 chars."""
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        _send_whatsapp(to, text)
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
        _send_whatsapp(to, chunk)


def _mark_as_read(message_id):
    """Mark WhatsApp message as read."""
    if not message_id:
        return
    token = _get_setting_password("whatsapp_access_token")
    phone_id = _get_setting("whatsapp_phone_number_id")
    if not token or not phone_id:
        return

    url = "https://graph.facebook.com/v21.0/{}/messages".format(phone_id)
    headers = {"Authorization": "Bearer {}".format(token), "Content-Type": "application/json"}
    try:
        requests.post(url, json={
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }, headers=headers, timeout=5)
    except Exception:
        pass


def _get_setting(field):
    """Get a Niv Settings field value."""
    try:
        settings = frappe.get_cached_doc("Niv Settings")
        return getattr(settings, field, None)
    except Exception:
        return None


def _get_setting_password(field):
    """Get a password field from Niv Settings."""
    try:
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        try:
            settings = frappe.get_doc("Niv Settings")
            val = getattr(settings, field, None)
            if val:
                return settings.get_password(field)
            return None
        finally:
            frappe.set_user(current_user)
    except Exception:
        return None
