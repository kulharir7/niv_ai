"""
Niv AI — Telegram Bot Webhook (v4.0 — Clean Output)
Clean, readable output without noise.
"""
import json
import time
import requests
import frappe
import re
from frappe import _
from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message


# Tool name → friendly emoji
TOOL_LABELS = {
    "list_documents": "📋",
    "get_document": "📄",
    "create_document": "✏️",
    "update_document": "📝",
    "delete_document": "🗑️",
    "run_database_query": "📊",
    "search_documents": "🔍",
    "generate_report": "📊",
    "run_python_code": "🐍",
}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**kwargs):
    """Telegram webhook endpoint."""
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

        # Commands
        if text == "/start":
            _send_telegram(chat_id, 
                "🤖 *Namaste! Main Niv AI hoon*\n\n"
                "Mujhse kuch bhi pucho:\n"
                "• _Top 5 loans dikhao_\n"
                "• _Naya Customer banao_\n"
                "• _Sales report do_\n\n"
                "Shuru karte hain! 🚀"
            )
            return {"ok": True}

        if text == "/help":
            _send_telegram(chat_id,
                "💬 *Kuch bhi type karo!*\n\n"
                "*Examples:*\n"
                "• Top 5 loans dikhao\n"
                "• Overdue loans kitne hain?\n"
                "• Customer XYZ ki details\n"
                "• NPA report do"
            )
            return {"ok": True}

        # Map telegram user
        frappe_user = _get_frappe_user(telegram_user_id, chat_id)
        if not frappe_user:
            _send_telegram(chat_id, "❌ Account link nahi hai. Admin se contact karo.")
            return {"ok": True}

        # Send typing indicator
        _send_chat_action(chat_id, "typing")
        status_msg_id = _send_telegram(chat_id, "⏳ _Processing..._")

        # Get conversation
        conversation_id = _get_or_create_conversation(frappe_user, chat_id)

        # Run agent
        frappe.set_user(frappe_user)
        
        # Simple hint for agent
        agent_message = "[TELEGRAM: Reply concise, use tables for data, Hindi/English match user]\n\n" + text

        full_response = ""
        tools_used = []

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
                
                elif event_type == "error":
                    full_response = "❌ Error: " + event.get("content", "Unknown")[:200]

        except Exception as e:
            frappe.log_error("Telegram Error", frappe.get_traceback())
            full_response = "❌ " + str(e)[:200]

        # Delete status
        if status_msg_id:
            _delete_telegram(chat_id, status_msg_id)

        if not full_response.strip():
            full_response = "🤔 Koi response nahi mila."

        # Save messages
        save_user_message(conversation_id, text)
        save_assistant_message(conversation_id, full_response)

        # Clean and format
        final_msg = _clean_response(full_response)
        
        # Send response
        _send_long_message(chat_id, final_msg)
        frappe.db.commit()

        return {"ok": True}

    except Exception as e:
        frappe.log_error("Niv Telegram Error", frappe.get_traceback())
        return {"ok": True}


def _clean_response(text):
    """Clean response for Telegram - remove noise, format nicely."""
    
    # 1. Remove ALL thought blocks completely
    text = re.sub(r'\[\[?THOUGHT\]?\].*?\[\[?/?THOUGHT\]?\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\[THOUGHT\].*?$', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Remove system hints
    text = re.sub(r'\[TELEGRAM:.*?\]', '', text, flags=re.IGNORECASE)
    
    # 3. Clean markdown headers → bold
    text = re.sub(r'^#{1,3}\s*(.+)$', r'*\1*', text, flags=re.MULTILINE)
    
    # 4. Format tables nicely
    text = _format_tables(text)
    
    # 5. Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    # 6. Escape special chars for Telegram markdown
    # Only escape if not already in formatting
    
    return text


def _format_tables(text):
    """Convert markdown tables to clean Telegram format."""
    lines = text.split('\n')
    result = []
    table_rows = []
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check if it's a table row (starts and ends with |)
        if stripped.startswith('|') and stripped.endswith('|'):
            # Skip separator rows (|---|---|)
            if re.match(r'^[\|\s\-:]+$', stripped):
                continue
            
            # Extract cells
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if cells:
                table_rows.append(cells)
                in_table = True
        else:
            # End of table
            if in_table and table_rows:
                result.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            
            result.append(line)
    
    # Handle table at end of text
    if table_rows:
        result.append(_render_table(table_rows))
    
    return '\n'.join(result)


def _render_table(rows):
    """Render table as clean text list."""
    if not rows:
        return ""
    
    # If only 1-2 columns, use simple format
    if len(rows[0]) <= 2:
        output = []
        header = rows[0] if rows else []
        for row in rows[1:]:
            if len(row) >= 2:
                output.append(f"• *{row[0]}*: {row[1]}")
            elif len(row) == 1:
                output.append(f"• {row[0]}")
        return '\n'.join(output) if output else ''
    
    # For wider tables, use monospace
    output = ["```"]
    
    # Calculate column widths
    col_widths = []
    for i in range(len(rows[0])):
        max_width = 0
        for row in rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))
        col_widths.append(min(max_width, 15))  # Max 15 chars per column
    
    for idx, row in enumerate(rows):
        cells = []
        for i, cell in enumerate(row):
            width = col_widths[i] if i < len(col_widths) else 10
            cell_str = str(cell)[:width].ljust(width)
            cells.append(cell_str)
        output.append(' | '.join(cells))
        
        # Add separator after header
        if idx == 0:
            output.append('-' * (sum(col_widths) + 3 * (len(col_widths) - 1)))
    
    output.append("```")
    return '\n'.join(output)


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


def _get_bot_token():
    """Get bot token from settings."""
    try:
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        settings = frappe.get_doc("Niv Settings")
        return settings.get_password("telegram_bot_token")
    except Exception:
        return None
    finally:
        frappe.set_user(current_user)


def _send_telegram(chat_id, text, parse_mode="Markdown"):
    """Send message to Telegram."""
    token = _get_bot_token()
    if not token:
        return None
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": parse_mode
    }
    
    try:
        r = requests.post(url, json=payload, timeout=15)
        
        # Retry without parse_mode if failed
        if not r.ok and parse_mode:
            payload.pop("parse_mode")
            r = requests.post(url, json=payload, timeout=15)
        
        if r.ok:
            return r.json().get("result", {}).get("message_id")
        return None
    except Exception:
        return None


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
    """Send long message in chunks."""
    MAX_LEN = 4000  # Leave some room
    
    if len(text) <= MAX_LEN:
        _send_telegram(chat_id, text)
        return
    
    # Split by paragraphs first
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
        time.sleep(0.3)  # Small delay between chunks


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


@frappe.whitelist(methods=["POST"])
def setup_webhook():
    """Setup Telegram webhook from settings."""
    frappe.only_for("System Manager")
    
    settings = frappe.get_doc("Niv Settings")
    token = settings.get_password("telegram_bot_token")
    webhook_url = getattr(settings, "telegram_webhook_url", None)
    
    if not token:
        frappe.throw(_("Telegram Bot Token not set"))
    if not webhook_url:
        frappe.throw(_("Webhook URL not set"))
    
    if not webhook_url.endswith("/api/method/niv_ai.niv_core.api.telegram.webhook"):
        webhook_url = webhook_url.rstrip("/") + "/api/method/niv_ai.niv_core.api.telegram.webhook"
    
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    r = requests.post(url, json={"url": webhook_url}, timeout=10)
    result = r.json()
    
    if result.get("ok"):
        frappe.msgprint(_("✅ Webhook set successfully!"))
    else:
        frappe.throw(_("❌ Failed: " + result.get("description", "Unknown")))
    
    return result
