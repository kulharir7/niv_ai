"""
Niv AI — WhatsApp Bot Webhook (Meta Cloud API)
Progressive updates, tool call display, formatted responses.

Setup:
1. Create Meta Business App at https://developers.facebook.com
2. Add WhatsApp product → get Phone Number ID + Access Token
3. Set Verify Token (any secret string)
4. Configure in Niv Settings > WhatsApp section
5. Register webhook: https://yourdomain.com/api/method/niv_ai.niv_core.api.whatsapp.webhook
6. Subscribe to 'messages' webhook field
"""
import json
import re
import time
import requests
import frappe
from frappe import _


# Tool name → friendly emoji/label
TOOL_LABELS = {
    "run_database_query": "📊 Database query",
    "list_documents": "📋 Documents search",
    "get_document": "📄 Document fetch",
    "create_document": "✏️ Document create",
    "update_document": "📝 Document update",
    "delete_document": "🗑️ Document delete",
    "submit_document": "✅ Document submit",
    "search_documents": "🔍 Documents search",
    "search_doctype": "🔍 DocType search",
    "search_link": "🔗 Link search",
    "search": "🔍 Search",
    "fetch": "📥 Data fetch",
    "get_doctype_info": "ℹ️ DocType info",
    "generate_report": "📊 Report generate",
    "run_python_code": "🐍 Code execute",
    "analyze_business_data": "📈 Business data analyze",
    "universal_search": "🔍 Universal search",
    "explore_fields": "🧩 Fields explore",
    "introspect_system": "🔬 System introspect",
    "run_workflow": "⚙️ Workflow run",
    "create_dashboard": "📊 Dashboard create",
}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def webhook(**kwargs):
    """WhatsApp webhook — handles verification (GET) and messages (POST)."""
    try:
        # GET = Meta webhook verification
        if hasattr(frappe, 'request') and frappe.request and frappe.request.method == "GET":
            return _verify_webhook()

        # POST = Incoming message
        data = dict(frappe.form_dict)
        data.pop("cmd", None)

        if not data:
            return {"ok": True}

        entry = data.get("entry", [])
        if not entry:
            return {"ok": True}

        for entry_item in entry:
            changes = entry_item.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    _process_message(msg, value)

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
        # Must return challenge as plain text
        frappe.response["type"] = "page"
        frappe.response["page_content"] = str(challenge)
        return
    else:
        frappe.throw(_("Verification failed"), frappe.AuthenticationError)


def _process_message(msg, value):
    """Process a single WhatsApp message with progressive updates."""
    msg_type = msg.get("type")
    wa_id = msg.get("from")  # WhatsApp phone number

    # Only handle text for now
    if msg_type != "text":
        _send_whatsapp(wa_id, "🤖 Abhi sirf text messages support hain. Text mein likho!")
        return

    text = msg.get("text", {}).get("body", "").strip()
    if not text:
        return

    # Mark as read immediately
    _mark_as_read(msg.get("id"))

    # Map WhatsApp number to Frappe user
    frappe_user = _get_frappe_user(wa_id)
    if not frappe_user:
        _send_whatsapp(wa_id, (
            "❌ Aapka number link nahi hai.\n\n"
            "Admin se Niv WhatsApp User mein apna number map karwao.\n"
            "Number: {}".format(wa_id)
        ))
        return

    # Send processing indicator
    _send_whatsapp(wa_id, "⏳ Processing...")

    # Get or create conversation
    conversation_id = _get_or_create_conversation(frappe_user, wa_id)

    # Run agent with streaming
    frappe.set_user(frappe_user)

    from niv_ai.niv_core.langchain.agent import stream_agent
    from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message

    # WhatsApp formatting hint
    wa_hint = (
        "[WHATSAPP BOT — Format rules: NO markdown tables (WhatsApp doesn't support them). "
        "Use bullet lists (• item) for structured data. Use *bold* for emphasis. "
        "Keep responses concise. Hindi/Hinglish reply preferred. "
        "For tabular data use numbered lists with key: value format.]\n\n"
    )
    agent_message = wa_hint + text

    full_response = ""
    tool_calls_shown = []
    tool_update_sent = False

    try:
        for event in stream_agent(
            message=agent_message,
            conversation_id=conversation_id,
            user=frappe_user,
        ):
            event_type = event.get("type")

            if event_type == "tool_call":
                tool_name = event.get("tool", "unknown")
                if tool_name not in tool_calls_shown:
                    tool_calls_shown.append(tool_name)
                    # Send tool update (max 1 to avoid spam)
                    if not tool_update_sent:
                        label = TOOL_LABELS.get(tool_name, "🔧 {}".format(tool_name))
                        _send_whatsapp(wa_id, "🔧 {} kar raha hoon...".format(label))
                        tool_update_sent = True

            elif event_type == "token":
                full_response += event.get("content", "")

            elif event_type == "error":
                full_response = "⚠️ Error: {}".format(event.get("content", "Unknown"))

    except Exception as e:
        frappe.log_error("WhatsApp Stream Error", frappe.get_traceback())
        full_response = "⚠️ Agent error: {}".format(str(e)[:200])

    if not full_response:
        full_response = "🤔 Koi response nahi mila. Dobara try karo."

    # Save messages (original text without hint)
    save_user_message(conversation_id, text)
    save_assistant_message(conversation_id, full_response)

    # Format for WhatsApp
    final_msg = _format_for_whatsapp(full_response)

    # Add tool calls header
    if tool_calls_shown:
        tools_header = "🔧 *Tools used:*\n"
        for t in tool_calls_shown:
            label = TOOL_LABELS.get(t, t)
            tools_header += "  • {}\n".format(label)
        tools_header += "\n"
        final_msg = tools_header + final_msg

    # Send final response
    _send_long_message(wa_id, final_msg)
    frappe.db.commit()


# ── Formatting ──────────────────────────────────────────────

def _format_for_whatsapp(text):
    """Convert markdown to WhatsApp-friendly format.
    WhatsApp supports: *bold*, _italic_, ~strikethrough~, ```monospace```
    NO tables, NO headers, NO links with []() syntax.
    """
    lines = text.split("\n")
    result = []
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()

        # Convert markdown tables to bullet lists
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r'^[\|\s\-:]+$', stripped):
                continue  # Skip separator
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if cells:
                table_rows.append(cells)
                in_table = True
            continue

        # Flush table as bullet list
        if in_table and table_rows:
            result.append(_table_to_bullets(table_rows))
            table_rows = []
            in_table = False

        # Detect space-aligned tables (--- lines)
        if re.match(r'^[\-\s]{10,}$', stripped):
            continue  # Skip separator lines

        # Headers → bold
        if stripped.startswith("#"):
            clean = stripped.lstrip("#").strip()
            result.append("*{}*".format(clean))
        # Convert [text](url) links
        elif re.search(r'\[([^\]]+)\]\(([^)]+)\)', stripped):
            cleaned = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1: \2', stripped)
            result.append(cleaned)
        else:
            result.append(line)

    if table_rows:
        result.append(_table_to_bullets(table_rows))

    return "\n".join(result)


def _table_to_bullets(rows):
    """Convert table rows to WhatsApp bullet list format."""
    if not rows:
        return ""

    # First row is header
    headers = rows[0] if rows else []
    result_lines = []

    for row in rows[1:]:
        parts = []
        for i, cell in enumerate(row):
            if cell and cell != "-":
                header = headers[i] if i < len(headers) else ""
                if header:
                    parts.append("*{}*: {}".format(header, cell))
                else:
                    parts.append(cell)
        if parts:
            result_lines.append("• " + " | ".join(parts))

    # If only header row (no data rows), show headers as single entry
    if not result_lines and headers:
        result_lines.append("• " + " | ".join(headers))

    return "\n".join(result_lines)


# ── WhatsApp API ────────────────────────────────────────────

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
        if not r.ok:
            frappe.logger("whatsapp").error("Send failed: {} {}".format(r.status_code, r.text[:300]))
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
    """Mark WhatsApp message as read (blue ticks)."""
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


# ── User Mapping ────────────────────────────────────────────

def _get_frappe_user(wa_id):
    """Map WhatsApp number to Frappe user."""
    wa_clean = wa_id.replace("+", "").replace(" ", "").strip()

    # Try exact match first
    users = frappe.get_all(
        "Niv WhatsApp User",
        filters={"whatsapp_number": wa_clean, "enabled": 1},
        fields=["frappe_user"],
        limit=1,
    )
    if users:
        return users[0].frappe_user

    # Try last 10 digits match
    if len(wa_clean) >= 10:
        users = frappe.get_all(
            "Niv WhatsApp User",
            filters={"whatsapp_number": ["like", "%{}".format(wa_clean[-10:])], "enabled": 1},
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


# ── Settings Helpers ────────────────────────────────────────

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


# ── Admin APIs ──────────────────────────────────────────────

@frappe.whitelist(methods=["POST"])
def setup_webhook():
    """Register webhook with Meta. Admin only."""
    frappe.only_for("System Manager")

    verify_token = _get_setting("whatsapp_verify_token")
    webhook_url = _get_setting("whatsapp_webhook_url") or _get_setting("telegram_webhook_url")

    if not verify_token:
        frappe.throw(_("WhatsApp Verify Token not set in Niv Settings"))

    frappe.msgprint(_(
        "✅ Webhook URL ready!\n\n"
        "Go to Meta Business Dashboard → WhatsApp → Configuration → Webhook:\n"
        "1. Callback URL: {}/api/method/niv_ai.niv_core.api.whatsapp.webhook\n"
        "2. Verify Token: {}\n"
        "3. Subscribe to: messages".format(
            webhook_url or "https://yourdomain.com",
            verify_token
        )
    ))


@frappe.whitelist(methods=["POST"])
def link_user(whatsapp_number, frappe_user_email):
    """Link WhatsApp number to Frappe user. Admin only."""
    frappe.only_for("System Manager")

    if not frappe.db.exists("User", frappe_user_email):
        frappe.throw(_("User {} not found").format(frappe_user_email))

    wa_clean = whatsapp_number.replace("+", "").replace(" ", "").strip()

    existing = frappe.get_all("Niv WhatsApp User", filters={"whatsapp_number": wa_clean}, limit=1)
    if existing:
        doc = frappe.get_doc("Niv WhatsApp User", existing[0].name)
        doc.frappe_user = frappe_user_email
        doc.enabled = 1
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Niv WhatsApp User",
            "whatsapp_number": wa_clean,
            "frappe_user": frappe_user_email,
            "enabled": 1,
        }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def generate_qr(phone_number=None, prefill_text="Hi"):
    """Generate QR code URL for WhatsApp chat link. Returns wa.me link."""
    frappe.only_for("System Manager")

    phone = phone_number or _get_setting("whatsapp_phone_number_id")
    if not phone:
        frappe.throw(_("Phone number not configured"))

    # wa.me link — users scan QR to open chat
    import urllib.parse
    wa_link = "https://wa.me/{}?text={}".format(phone, urllib.parse.quote(prefill_text))

    # QR code via Google Charts API (free, no deps)
    qr_url = "https://chart.googleapis.com/chart?cht=qr&chs=300x300&chl={}".format(
        urllib.parse.quote(wa_link)
    )

    return {
        "wa_link": wa_link,
        "qr_url": qr_url,
        "instructions": "Print this QR or share the link. Users scan → WhatsApp opens → they type → Niv AI replies!"
    }
