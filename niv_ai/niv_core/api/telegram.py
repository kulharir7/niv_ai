"""
Niv AI — Telegram Bot Webhook (v5.0 — Live Streaming)
Live-edits message as AI generates response. Clean table output.
"""
import json
import time
import requests
import frappe
import re
from frappe import _
from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**kwargs):
    """Telegram webhook endpoint."""
    try:
        data = dict(frappe.form_dict)
        data.pop("cmd", None)

        if not data:
            return {"ok": True}

        # Security: validate secret token if configured
        settings = _get_settings()
        secret = getattr(settings, "telegram_secret_token", None)
        if secret:
            header_secret = frappe.request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header_secret != secret:
                frappe.log_error("Telegram webhook: invalid secret token", "Niv AI Telegram")
                return {"ok": True}

        message = data.get("message") or data.get("edited_message")
        if not message:
            return {"ok": True}

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        telegram_user_id = str(message["from"]["id"])
        
        if not text:
            return {"ok": True}

        # Commands
        if text == "/start":
            _send_telegram(chat_id, 
                "🤖 *Hello! I'm Niv AI*\n\n"
                "Ask me anything:\n"
                "• _Show top 5 loans_\n"
                "• _Create a new Customer_\n"
                "• _Give me the sales report_\n\n"
                "Let's get started! 🚀"
            )
            return {"ok": True}

        if text == "/help":
            _send_telegram(chat_id,
                "💬 *Just type anything!*\n\n"
                "*Examples:*\n"
                "• Show top 5 loans\n"
                "• How many overdue loans?\n"
                "• Details of Customer XYZ\n"
                "• NPA report"
            )
            return {"ok": True}

        # Map telegram user
        frappe_user = _get_frappe_user(telegram_user_id, chat_id)
        if not frappe_user:
            _send_telegram(chat_id, "❌ No linked account found. Please contact your admin.")
            return {"ok": True}

        # Get conversation
        conversation_id = _get_or_create_conversation(frappe_user, chat_id)
        frappe.set_user(frappe_user)

        # Check if live streaming is enabled
        live_stream = getattr(settings, "telegram_live_stream", 1)

        if live_stream:
            _handle_stream(chat_id, text, conversation_id, frappe_user)
        else:
            _handle_batch(chat_id, text, conversation_id, frappe_user)

        frappe.db.commit()
        return {"ok": True}

    except Exception as e:
        frappe.log_error("Niv Telegram Error", frappe.get_traceback())
        return {"ok": True}


def _handle_stream(chat_id, text, conversation_id, frappe_user):
    """Live streaming — edit message as tokens arrive."""
    # Send initial "thinking" message
    msg_id = _send_telegram(chat_id, "💭 _Thinking..._")
    
    agent_message = text
    full_response = ""
    tools_used = []
    last_edit_time = time.time()
    last_edit_text = ""
    token_data = {}

    try:
        from niv_ai.niv_core.langchain.agent import stream_agent
        
        for event in stream_agent(message=agent_message, conversation_id=conversation_id, user=frappe_user):
            event_type = event.get("type")
            
            if event_type == "tool_call":
                tool_name = event.get("tool", "")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)
                    # Show which tool is being used
                    tool_text = f"🔧 Using _{tool_name}_..."
                    if msg_id:
                        _edit_telegram(chat_id, msg_id, tool_text)
            
            elif event_type == "token":
                content = event.get("content", "")
                full_response += content
                
                # Edit message every 1.5 seconds (avoid Telegram rate limit)
                now = time.time()
                if now - last_edit_time >= 1.5 and full_response.strip():
                    display_text = _clean_response(full_response) + " ▌"
                    if display_text != last_edit_text and msg_id:
                        _edit_telegram(chat_id, msg_id, display_text)
                        last_edit_text = display_text
                        last_edit_time = now
            
            elif event_type == "_token_usage":
                token_data = {
                    "input_tokens": event.get("input_tokens", 0),
                    "output_tokens": event.get("output_tokens", 0),
                    "total_tokens": event.get("total_tokens", 0),
                }
            
            elif event_type == "error":
                full_response = "❌ Error: " + event.get("content", "Unknown")[:200]

    except Exception as e:
        frappe.log_error("Telegram Stream Error", frappe.get_traceback())
        full_response = full_response or ("❌ " + str(e)[:200])

    if not full_response.strip():
        full_response = "🤔 No response received."

    # Final edit with complete response (remove cursor)
    final_msg = _clean_response(full_response)
    
    if msg_id:
        # Check if message is too long for edit
        if len(final_msg) > 4000:
            _delete_telegram(chat_id, msg_id)
            _send_long_message(chat_id, final_msg)
        else:
            _edit_telegram(chat_id, msg_id, final_msg)
    else:
        _send_long_message(chat_id, final_msg)

    # Save messages
    save_user_message(conversation_id, text)
    save_assistant_message(
        conversation_id, full_response,
        input_tokens=token_data.get("input_tokens", 0),
        output_tokens=token_data.get("output_tokens", 0),
        total_tokens=token_data.get("total_tokens", 0),
    )


def _handle_batch(chat_id, text, conversation_id, frappe_user):
    """Batch mode — collect full response then send."""
    _send_chat_action(chat_id, "typing")
    status_msg_id = _send_telegram(chat_id, "⏳ _Processing..._")

    agent_message = text
    full_response = ""
    tools_used = []
    token_data = {}

    try:
        from niv_ai.niv_core.langchain.agent import stream_agent
        
        for event in stream_agent(message=agent_message, conversation_id=conversation_id, user=frappe_user):
            event_type = event.get("type")
            
            if event_type == "tool_call":
                tool_name = event.get("tool", "")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)
                    _send_chat_action(chat_id, "typing")
            
            elif event_type == "token":
                full_response += event.get("content", "")
            
            elif event_type == "_token_usage":
                token_data = {
                    "input_tokens": event.get("input_tokens", 0),
                    "output_tokens": event.get("output_tokens", 0),
                    "total_tokens": event.get("total_tokens", 0),
                }
            
            elif event_type == "error":
                full_response = "❌ Error: " + event.get("content", "Unknown")[:200]

    except Exception as e:
        frappe.log_error("Telegram Error", frappe.get_traceback())
        full_response = full_response or ("❌ " + str(e)[:200])

    if status_msg_id:
        _delete_telegram(chat_id, status_msg_id)

    if not full_response.strip():
        full_response = "🤔 No response received."

    final_msg = _clean_response(full_response)
    _send_long_message(chat_id, final_msg)

    save_user_message(conversation_id, text)
    save_assistant_message(
        conversation_id, full_response,
        input_tokens=token_data.get("input_tokens", 0),
        output_tokens=token_data.get("output_tokens", 0),
        total_tokens=token_data.get("total_tokens", 0),
    )


# ─── Response Cleaning ──────────────────────────────────────────────

def _clean_response(text):
    """Clean response for Telegram."""
    # Remove thought blocks
    text = re.sub(r'\[\[?THOUGHT\]?\].*?\[\[?/?THOUGHT\]?\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\[THOUGHT\].*?$', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove system hints
    text = re.sub(r'\[TELEGRAM:.*?\]', '', text, flags=re.IGNORECASE)
    
    # Headers → bold
    text = re.sub(r'^#{1,3}\s*(.+)$', r'*\1*', text, flags=re.MULTILINE)
    
    # Format tables
    text = _format_tables(text)
    
    # Clean whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _format_tables(text):
    """Convert markdown tables to clean Telegram bullet lists."""
    lines = text.split('\n')
    result = []
    table_rows = []
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith('|') and stripped.endswith('|'):
            if re.match(r'^[\|\s\-:]+$', stripped):
                continue
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if cells:
                table_rows.append(cells)
                in_table = True
        else:
            if in_table and table_rows:
                result.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            result.append(line)
    
    if table_rows:
        result.append(_render_table(table_rows))
    
    return '\n'.join(result)


def _render_table(rows):
    """Render table as mobile-friendly stacked cards for Telegram."""
    if not rows or len(rows) < 2:
        return ""
    
    headers = rows[0]
    data_rows = rows[1:]
    
    if not data_rows:
        return ""
    
    output = []
    
    for i, row in enumerate(data_rows):
        # Each row as a numbered card with fields on separate lines
        entry_lines = []
        for j, cell in enumerate(row):
            if j < len(headers) and cell.strip():
                header = headers[j].strip()
                value = cell.strip()
                if header and value and value != "-":
                    entry_lines.append(f"  {header}: *{value}*")
        
        if entry_lines:
            num = i + 1
            output.append(f"*{num}.*\n" + "\n".join(entry_lines))
    
    return '\n\n'.join(output)


# ─── User Mapping ───────────────────────────────────────────────────

def _get_frappe_user(telegram_user_id, chat_id):
    """Map Telegram user to Frappe user."""
    users = frappe.get_all(
        "Niv Telegram User", 
        filters={"telegram_user_id": telegram_user_id, "enabled": 1}, 
        fields=["frappe_user"]
    )
    if users:
        return users[0].frappe_user
    
    users = frappe.get_all(
        "Niv Telegram User", 
        filters={"telegram_chat_id": str(chat_id), "enabled": 1}, 
        fields=["frappe_user"]
    )
    if users:
        return users[0].frappe_user
    
    return None


def _get_or_create_conversation(user, chat_id):
    """Get or create Telegram conversation."""
    convs = frappe.get_all(
        "Niv Conversation", 
        filters={"owner": user, "channel": "telegram", "channel_id": str(chat_id)}, 
        fields=["name"], 
        order_by="modified desc", 
        limit=1
    )
    if convs:
        return convs[0].name
    
    conv = frappe.get_doc({
        "doctype": "Niv Conversation", 
        "user": user, 
        "title": "Telegram Chat", 
        "channel": "telegram", 
        "channel_id": str(chat_id)
    })
    conv.insert(ignore_permissions=True)
    frappe.db.commit()
    return conv.name


# ─── Telegram API ───────────────────────────────────────────────────

def _get_settings():
    """Get Niv Settings (cached)."""
    try:
        return frappe.get_doc("Niv Settings", "Niv Settings")
    except Exception:
        return frappe._dict()


def _get_bot_token():
    """Get bot token from settings."""
    try:
        settings = _get_settings()
        return settings.get_password("telegram_bot_token")
    except Exception:
        return None


def _send_telegram(chat_id, text, parse_mode="Markdown"):
    """Send message to Telegram. Returns message_id."""
    token = _get_bot_token()
    if not token:
        return None
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    
    try:
        r = requests.post(url, json=payload, timeout=15)
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            r = requests.post(url, json=payload, timeout=15)
        if r.ok:
            return r.json().get("result", {}).get("message_id")
        return None
    except Exception:
        return None


def _edit_telegram(chat_id, message_id, text, parse_mode="Markdown"):
    """Edit existing message (for live streaming)."""
    token = _get_bot_token()
    if not token or not message_id:
        return False
    
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            r = requests.post(url, json=payload, timeout=10)
        return r.ok
    except Exception:
        return False


def _delete_telegram(chat_id, message_id):
    """Delete a message."""
    token = _get_bot_token()
    if not token or not message_id:
        return
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=5)
    except Exception:
        pass


def _send_long_message(chat_id, text):
    """Send long message in chunks (max 4000 chars each)."""
    MAX_LEN = 4000
    
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
        time.sleep(0.3)


def _send_chat_action(chat_id, action="typing"):
    """Send typing indicator."""
    token = _get_bot_token()
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except Exception:
        pass


# ─── Webhook Setup ──────────────────────────────────────────────────

@frappe.whitelist(methods=["POST"])
def setup_webhook():
    """Setup Telegram webhook from settings."""
    frappe.only_for("System Manager")
    
    settings = _get_settings()
    token = settings.get_password("telegram_bot_token")
    webhook_url = getattr(settings, "telegram_webhook_url", None)
    secret = getattr(settings, "telegram_secret_token", None)
    
    if not token:
        frappe.throw(_("Telegram Bot Token not set"))
    if not webhook_url:
        frappe.throw(_("Webhook URL not set"))
    
    if not webhook_url.endswith("/api/method/niv_ai.niv_core.api.telegram.webhook"):
        webhook_url = webhook_url.rstrip("/") + "/api/method/niv_ai.niv_core.api.telegram.webhook"
    
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {"url": webhook_url}
    if secret:
        payload["secret_token"] = secret
    
    r = requests.post(url, json=payload, timeout=10)
    result = r.json()
    
    if result.get("ok"):
        frappe.msgprint(_("✅ Webhook set successfully!"))
    else:
        frappe.throw(_("❌ Failed: " + result.get("description", "Unknown")))
    
    return result
