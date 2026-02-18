"""
Niv AI — Telegram Bot (v6.0 — Full Featured)

Features:
- Live streaming responses with message editing
- Conversation memory (full chat history)
- Voice message support (STT → AI → TTS reply)
- Inline quick-action buttons & callback handling
- File/document sending (PDF, Excel, images)
- Group chat support (@mention detection)
- Rich commands: /start, /help, /loans, /npa, /report, /link, /unlink, /export, /voice, /status
- Scheduled report delivery
- Mobile-friendly table formatting (stacked cards)
- Auto typing indicator during processing
- Long message splitting (4000 char Telegram limit)
- Error recovery and graceful fallbacks
"""
import json
import time
import re
import os
import tempfile
import uuid
import requests
import frappe
from frappe import _
from niv_ai.niv_core.api._helpers import save_user_message, save_assistant_message


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: MAIN WEBHOOK — Routes all incoming updates
# ═══════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook(**kwargs):
    """Main Telegram webhook endpoint. Routes messages, callbacks, voice."""
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

        # Route: Callback query (inline button press)
        callback_query = data.get("callback_query")
        if callback_query:
            _handle_callback_query(callback_query)
            return {"ok": True}

        # Route: Message (text, voice, photo, document)
        message = data.get("message") or data.get("edited_message")
        if not message:
            return {"ok": True}

        chat_id = message["chat"]["id"]
        chat_type = message["chat"].get("type", "private")  # private, group, supergroup
        telegram_user_id = str(message["from"]["id"])
        first_name = message["from"].get("first_name", "")

        # Group chat: only respond if mentioned or replied to
        if chat_type in ("group", "supergroup"):
            if not _is_bot_mentioned(message, settings):
                return {"ok": True}

        # Voice message
        voice = message.get("voice") or message.get("audio")
        if voice:
            frappe_user = _get_frappe_user(telegram_user_id, chat_id)
            if not frappe_user:
                _send_telegram(chat_id, "❌ No linked account. Please ask your admin to link your Telegram ID.")
                return {"ok": True}
            conversation_id = _get_or_create_conversation(frappe_user, chat_id)
            frappe.set_user(frappe_user)
            _handle_voice_message(chat_id, voice, conversation_id, frappe_user, message)
            frappe.db.commit()
            return {"ok": True}

        # Photo with caption
        if message.get("photo") and message.get("caption"):
            text = message["caption"].strip()
        else:
            text = message.get("text", "").strip()

        if not text:
            return {"ok": True}

        # Strip bot mention from group messages
        if chat_type in ("group", "supergroup"):
            text = _strip_bot_mention(text, settings)

        # Commands
        command = _parse_command(text)
        if command:
            _handle_command(command, chat_id, telegram_user_id, first_name, message, settings)
            return {"ok": True}

        # Regular message — authenticate and process
        frappe_user = _get_frappe_user(telegram_user_id, chat_id)
        if not frappe_user:
            _send_telegram(chat_id, "❌ No linked account. Use /link your@email.com to connect.")
            return {"ok": True}

        conversation_id = _get_or_create_conversation(frappe_user, chat_id)
        frappe.set_user(frappe_user)

        # Check streaming preference
        live_stream = getattr(settings, "telegram_live_stream", 1)
        if live_stream:
            _handle_stream(chat_id, text, conversation_id, frappe_user)
        else:
            _handle_batch(chat_id, text, conversation_id, frappe_user)

        frappe.db.commit()
        return {"ok": True}

    except Exception:
        frappe.log_error("Niv Telegram Error", frappe.get_traceback())
        return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════

def _parse_command(text):
    """Extract command from message text. Returns (command, args) or None."""
    if not text.startswith("/"):
        return None
    parts = text.split(None, 1)
    cmd = parts[0].lower().split("@")[0]  # Remove @botname suffix
    args = parts[1] if len(parts) > 1 else ""
    return (cmd, args)


def _handle_command(command, chat_id, telegram_user_id, first_name, message, settings):
    """Route and handle bot commands."""
    cmd, args = command

    handlers = {
        "/start": lambda: _cmd_start(chat_id, first_name),
        "/help": lambda: _cmd_help(chat_id),
        "/loans": lambda: _cmd_quick_query(chat_id, telegram_user_id, "Show me the top 10 active loans with amounts and status"),
        "/npa": lambda: _cmd_quick_query(chat_id, telegram_user_id, "Show me all NPA (Non-Performing Asset) loans with details"),
        "/report": lambda: _cmd_report(chat_id, telegram_user_id, args),
        "/export": lambda: _cmd_export(chat_id, telegram_user_id, args),
        "/link": lambda: _cmd_link(chat_id, telegram_user_id, args, message),
        "/unlink": lambda: _cmd_unlink(chat_id, telegram_user_id),
        "/voice": lambda: _cmd_voice(chat_id),
        "/status": lambda: _cmd_status(chat_id, telegram_user_id),
    }

    handler = handlers.get(cmd)
    if handler:
        handler()
    else:
        _send_telegram(chat_id, f"Unknown command: {cmd}\nType /help to see available commands.")


def _cmd_start(chat_id, first_name):
    """Welcome message with quick action buttons."""
    greeting = f"Hello{(' ' + first_name) if first_name else ''}! I'm *Niv AI* 🤖"
    text = (
        f"{greeting}\n\n"
        "I can help you with your ERPNext data:\n"
        "• Query loans, customers, reports\n"
        "• Create and update records\n"
        "• Generate exports (Excel, PDF)\n"
        "• Answer questions about your data\n\n"
        "Just type your question or use the buttons below!"
    )
    buttons = [
        [
            {"text": "📊 Show Loans", "callback_data": "quick:show top 10 loans"},
            {"text": "📋 NPA Report", "callback_data": "quick:show NPA report"},
        ],
        [
            {"text": "👥 Customers", "callback_data": "quick:list all customers"},
            {"text": "💰 Collections", "callback_data": "quick:show collection summary"},
        ],
        [
            {"text": "❓ Help", "callback_data": "cmd:help"},
        ],
    ]
    _send_telegram_with_buttons(chat_id, text, buttons)


def _cmd_help(chat_id):
    """Show all available commands."""
    text = (
        "*Niv AI — Commands*\n\n"
        "*Queries:*\n"
        "/loans — Top active loans\n"
        "/npa — NPA report\n"
        "/report [type] — Generate report (sales, collection, overdue)\n\n"
        "*Tools:*\n"
        "/export [format] — Export last data (excel, pdf, csv)\n"
        "/voice — Voice message info\n"
        "/status — Your account status\n\n"
        "*Account:*\n"
        "/link email — Link your Telegram to ERPNext\n"
        "/unlink — Unlink your account\n\n"
        "*Tips:*\n"
        "• Just type any question naturally\n"
        "• Send a voice message and I'll process it\n"
        "• I remember our conversation history"
    )
    _send_telegram(chat_id, text)


def _cmd_quick_query(chat_id, telegram_user_id, query):
    """Execute a pre-built query via the AI agent."""
    frappe_user = _get_frappe_user(telegram_user_id, chat_id)
    if not frappe_user:
        _send_telegram(chat_id, "❌ No linked account. Use /link your@email.com first.")
        return

    conversation_id = _get_or_create_conversation(frappe_user, chat_id)
    frappe.set_user(frappe_user)
    _handle_stream(chat_id, query, conversation_id, frappe_user)
    frappe.db.commit()


def _cmd_report(chat_id, telegram_user_id, args):
    """Generate a specific report."""
    report_types = {
        "sales": "Show me the sales summary report for this month",
        "collection": "Show me the collection efficiency report",
        "overdue": "Show me all overdue loans with days overdue and amounts",
        "npa": "Show me the complete NPA report with classification",
        "disbursement": "Show me loan disbursement summary for this month",
    }

    if not args.strip():
        text = (
            "*Available Reports:*\n\n"
            "• /report sales — Sales summary\n"
            "• /report collection — Collection efficiency\n"
            "• /report overdue — Overdue loans\n"
            "• /report npa — NPA classification\n"
            "• /report disbursement — Disbursement summary\n\n"
            "Or just type what report you need!"
        )
        buttons = [
            [
                {"text": "📊 Sales", "callback_data": "report:sales"},
                {"text": "💰 Collection", "callback_data": "report:collection"},
            ],
            [
                {"text": "⚠️ Overdue", "callback_data": "report:overdue"},
                {"text": "🔴 NPA", "callback_data": "report:npa"},
            ],
        ]
        _send_telegram_with_buttons(chat_id, text, buttons)
        return

    report_key = args.strip().lower()
    query = report_types.get(report_key, f"Generate a {args.strip()} report")
    _cmd_quick_query(chat_id, telegram_user_id, query)


def _cmd_export(chat_id, telegram_user_id, args):
    """Export last conversation data as file."""
    frappe_user = _get_frappe_user(telegram_user_id, chat_id)
    if not frappe_user:
        _send_telegram(chat_id, "❌ No linked account.")
        return

    fmt = args.strip().lower() or "excel"
    if fmt not in ("excel", "pdf", "csv"):
        _send_telegram(chat_id, "Supported formats: excel, pdf, csv\nExample: /export excel")
        return

    # Get last assistant message with data
    conversation_id = _get_or_create_conversation(frappe_user, chat_id)
    last_msg = _get_last_assistant_message(conversation_id)

    if not last_msg:
        _send_telegram(chat_id, "No data to export. Ask me something first, then use /export.")
        return

    # Try to export
    try:
        from niv_ai.niv_core.api.export import export_data, _parse_markdown_table
        headers, rows = _parse_markdown_table(last_msg)

        if not headers or not rows:
            _send_telegram(chat_id, "Last response doesn't contain tabular data to export.")
            return

        result = export_data(
            data=json.dumps({"headers": headers, "rows": rows}),
            format=fmt,
            filename=f"niv_export_{int(time.time())}"
        )

        if result and result.get("file_url"):
            file_url = result["file_url"]
            site_url = frappe.utils.get_url()
            full_url = f"{site_url}{file_url}"

            # Download and send as document
            file_path = frappe.get_site_path(
                "private" if "/private/" in file_url else "public",
                "files",
                os.path.basename(file_url)
            )

            if os.path.exists(file_path):
                _send_document(chat_id, file_path, f"niv_export.{fmt if fmt != 'excel' else 'xlsx'}")
            else:
                _send_telegram(chat_id, f"📥 Download your export:\n{full_url}")
        else:
            _send_telegram(chat_id, "Export failed. Please try again.")

    except Exception as e:
        frappe.log_error("Telegram Export Error", frappe.get_traceback())
        _send_telegram(chat_id, f"Export error: {str(e)[:200]}")


def _cmd_link(chat_id, telegram_user_id, args, message):
    """Link Telegram user to Frappe account."""
    email = args.strip()

    if not email or "@" not in email:
        _send_telegram(chat_id, "Usage: /link your@email.com\n\nThis links your Telegram to your ERPNext account.")
        return

    # Check if Frappe user exists
    if not frappe.db.exists("User", email):
        _send_telegram(chat_id, f"❌ No ERPNext account found for: {email}\nPlease check the email address.")
        return

    # Check if already linked
    existing = frappe.get_all(
        "Niv Telegram User",
        filters={"telegram_user_id": telegram_user_id},
        fields=["name", "frappe_user"]
    )

    if existing:
        if existing[0].frappe_user == email:
            _send_telegram(chat_id, f"✅ Already linked to {email}")
        else:
            # Update existing link
            frappe.db.set_value("Niv Telegram User", existing[0].name, {
                "frappe_user": email,
                "telegram_chat_id": str(chat_id),
                "enabled": 1,
            })
            frappe.db.commit()
            _send_telegram(chat_id, f"✅ Updated! Now linked to {email}")
        return

    # Create new mapping
    try:
        tg_name = message["from"].get("first_name", "")
        tg_username = message["from"].get("username", "")

        doc = frappe.get_doc({
            "doctype": "Niv Telegram User",
            "telegram_user_id": telegram_user_id,
            "telegram_chat_id": str(chat_id),
            "telegram_name": tg_name,
            "telegram_username": tg_username,
            "frappe_user": email,
            "enabled": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        _send_telegram(chat_id, f"✅ Account linked successfully!\n\nTelegram: {tg_name or telegram_user_id}\nERPNext: {email}\n\nYou can now ask me anything!")

    except Exception as e:
        frappe.log_error("Telegram Link Error", frappe.get_traceback())
        _send_telegram(chat_id, f"❌ Failed to link: {str(e)[:200]}")


def _cmd_unlink(chat_id, telegram_user_id):
    """Unlink Telegram account."""
    users = frappe.get_all(
        "Niv Telegram User",
        filters={"telegram_user_id": telegram_user_id},
        fields=["name"]
    )

    if not users:
        _send_telegram(chat_id, "No linked account found.")
        return

    for u in users:
        frappe.db.set_value("Niv Telegram User", u.name, "enabled", 0)

    frappe.db.commit()
    _send_telegram(chat_id, "✅ Account unlinked. Use /link to reconnect.")


def _cmd_voice(chat_id):
    """Voice message instructions."""
    _send_telegram(
        chat_id,
        "*Voice Messages* 🎙️\n\n"
        "Just send me a voice message!\n\n"
        "*How it works:*\n"
        "1. Hold the mic button and speak\n"
        "2. I'll transcribe your message\n"
        "3. Process it and reply\n"
        "4. Optionally send a voice reply\n\n"
        "*Supported languages:*\n"
        "• English\n"
        "• Hindi\n"
        "• Mixed (Hinglish)"
    )


def _cmd_status(chat_id, telegram_user_id):
    """Show user account status."""
    frappe_user = _get_frappe_user(telegram_user_id, chat_id)
    if not frappe_user:
        _send_telegram(chat_id, "No linked account. Use /link your@email.com")
        return

    # Get conversation stats
    conv_count = frappe.db.count("Niv Conversation", {"owner": frappe_user, "channel": "telegram"})
    msg_count = 0
    convs = frappe.get_all(
        "Niv Conversation",
        filters={"owner": frappe_user, "channel": "telegram"},
        fields=["name"]
    )
    for c in convs:
        msg_count += frappe.db.count("Niv Message", {"parent": c.name})

    settings = _get_settings()
    model = getattr(settings, "default_model", "unknown")

    _send_telegram(
        chat_id,
        f"*Account Status*\n\n"
        f"👤 User: {frappe_user}\n"
        f"💬 Conversations: {conv_count}\n"
        f"📝 Messages: {msg_count}\n"
        f"🤖 Model: {model}\n"
        f"✅ Status: Active"
    )


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: STREAMING RESPONSE HANDLER
# ═══════════════════════════════════════════════════════════════════════

def _handle_stream(chat_id, text, conversation_id, frappe_user):
    """Live streaming — edit message as tokens arrive."""
    msg_id = _send_telegram(chat_id, "💭 _Thinking..._")

    full_response = ""
    tools_used = []
    last_edit_time = time.time()
    last_edit_text = ""
    token_data = {}

    try:
        from niv_ai.niv_core.langchain.agent import stream_agent

        # Keep typing indicator alive
        _send_chat_action(chat_id, "typing")

        for event in stream_agent(message=text, conversation_id=conversation_id, user=frappe_user):
            event_type = event.get("type")

            if event_type == "tool_call":
                tool_name = event.get("tool", "")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)
                    tool_text = f"🔧 Using _{tool_name}_..."
                    if msg_id:
                        _edit_telegram(chat_id, msg_id, tool_text)
                    _send_chat_action(chat_id, "typing")

            elif event_type == "token":
                content = event.get("content", "")
                full_response += content

                # Edit message every 1.5 seconds (Telegram rate limit)
                now = time.time()
                if now - last_edit_time >= 1.5 and full_response.strip():
                    display_text = _clean_response(full_response) + " ▌"
                    if display_text != last_edit_text and msg_id:
                        success = _edit_telegram(chat_id, msg_id, display_text)
                        if success:
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

    # Final edit — remove cursor
    final_msg = _clean_response(full_response)

    if msg_id:
        if len(final_msg) > 4000:
            _delete_telegram(chat_id, msg_id)
            _send_long_message(chat_id, final_msg)
        else:
            _edit_telegram(chat_id, msg_id, final_msg)
    else:
        _send_long_message(chat_id, final_msg)

    # Send follow-up buttons based on response content
    _send_context_buttons(chat_id, full_response, text)

    # Save messages
    save_user_message(conversation_id, text)
    save_assistant_message(
        conversation_id, full_response,
        input_tokens=token_data.get("input_tokens", 0),
        output_tokens=token_data.get("output_tokens", 0),
        total_tokens=token_data.get("total_tokens", 0),
    )


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: BATCH RESPONSE HANDLER
# ═══════════════════════════════════════════════════════════════════════

def _handle_batch(chat_id, text, conversation_id, frappe_user):
    """Batch mode — collect full response then send."""
    _send_chat_action(chat_id, "typing")
    status_msg_id = _send_telegram(chat_id, "⏳ _Processing..._")

    full_response = ""
    tools_used = []
    token_data = {}

    try:
        from niv_ai.niv_core.langchain.agent import stream_agent

        for event in stream_agent(message=text, conversation_id=conversation_id, user=frappe_user):
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

    # Follow-up buttons
    _send_context_buttons(chat_id, full_response, text)

    save_user_message(conversation_id, text)
    save_assistant_message(
        conversation_id, full_response,
        input_tokens=token_data.get("input_tokens", 0),
        output_tokens=token_data.get("output_tokens", 0),
        total_tokens=token_data.get("total_tokens", 0),
    )


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: VOICE MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════════

def _handle_voice_message(chat_id, voice, conversation_id, frappe_user, message):
    """Process voice message: Download → STT → AI → Reply (+ optional TTS)."""
    msg_id = _send_telegram(chat_id, "🎙️ _Transcribing your voice..._")
    _send_chat_action(chat_id, "typing")

    file_id = voice.get("file_id")
    if not file_id:
        _edit_telegram(chat_id, msg_id, "❌ Could not read voice message.")
        return

    try:
        # Download voice file from Telegram
        audio_path = _download_telegram_file(file_id)
        if not audio_path:
            _edit_telegram(chat_id, msg_id, "❌ Failed to download voice file.")
            return

        # Transcribe using STT
        transcript = _transcribe_audio(audio_path)

        # Clean up temp file
        try:
            os.unlink(audio_path)
        except Exception:
            pass

        if not transcript:
            _edit_telegram(chat_id, msg_id, "❌ Couldn't understand the audio. Please try again or type your message.")
            return

        # Show transcription
        _edit_telegram(chat_id, msg_id, f"🎙️ _\"{transcript}\"_\n\n💭 _Thinking..._")

        # Process through AI agent
        full_response = ""
        tools_used = []
        token_data = {}

        from niv_ai.niv_core.langchain.agent import stream_agent

        for event in stream_agent(message=transcript, conversation_id=conversation_id, user=frappe_user):
            event_type = event.get("type")

            if event_type == "tool_call":
                tool_name = event.get("tool", "")
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)

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

        if not full_response.strip():
            full_response = "🤔 No response received."

        # Send text response
        final_msg = _clean_response(full_response)
        if len(final_msg) > 4000:
            _delete_telegram(chat_id, msg_id)
            _send_long_message(chat_id, final_msg)
        else:
            _edit_telegram(chat_id, msg_id, final_msg)

        # Send voice reply if response is short enough
        if len(full_response) < 1000:
            _send_voice_reply(chat_id, full_response)

        # Save messages
        save_user_message(conversation_id, f"[Voice] {transcript}")
        save_assistant_message(
            conversation_id, full_response,
            input_tokens=token_data.get("input_tokens", 0),
            output_tokens=token_data.get("output_tokens", 0),
            total_tokens=token_data.get("total_tokens", 0),
        )

    except Exception as e:
        frappe.log_error("Telegram Voice Error", frappe.get_traceback())
        if msg_id:
            _edit_telegram(chat_id, msg_id, f"❌ Voice processing failed: {str(e)[:200]}")


def _download_telegram_file(file_id):
    """Download a file from Telegram servers. Returns local temp path."""
    token = _get_bot_token()
    if not token:
        return None

    try:
        # Get file path
        url = f"https://api.telegram.org/bot{token}/getFile"
        r = requests.post(url, json={"file_id": file_id}, timeout=10)
        if not r.ok:
            return None

        file_path = r.json().get("result", {}).get("file_path", "")
        if not file_path:
            return None

        # Download file
        download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        r = requests.get(download_url, timeout=30)
        if not r.ok:
            return None

        # Save to temp file
        ext = os.path.splitext(file_path)[1] or ".ogg"
        tmp_path = os.path.join(tempfile.gettempdir(), f"tg_voice_{uuid.uuid4().hex[:8]}{ext}")
        with open(tmp_path, "wb") as f:
            f.write(r.content)

        return tmp_path

    except Exception as e:
        frappe.logger().warning(f"Telegram file download failed: {e}")
        return None


def _transcribe_audio(audio_path):
    """Transcribe audio file using available STT engine."""
    try:
        # Try Voxtral/API STT first
        from niv_ai.niv_core.api.voice import _get_voice_config

        config = _get_voice_config()
        if config.get("api_key"):
            provider_type = config.get("provider_type", "openai")
            stt_model = "voxtral-mini-latest" if provider_type == "mistral" else "whisper-1"

            try:
                with open(audio_path, "rb") as f:
                    resp = requests.post(
                        f"{config['base_url']}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {config['api_key']}"},
                        files={"file": (os.path.basename(audio_path), f, "audio/ogg")},
                        data={"model": stt_model},
                        timeout=30,
                    )

                if resp.status_code == 200:
                    text = resp.json().get("text", "").strip()
                    if text:
                        return text
            except Exception as e:
                frappe.logger().warning(f"Voxtral STT failed for Telegram voice: {e}")

        # Fallback: local Whisper
        from niv_ai.niv_core.api.voice import _stt_whisper
        result = _stt_whisper(audio_path)
        if result and result.get("text"):
            return result["text"]

    except Exception as e:
        frappe.logger().warning(f"Telegram STT failed: {e}")

    return None


def _send_voice_reply(chat_id, text):
    """Generate TTS and send as voice message."""
    try:
        from niv_ai.niv_core.api.voice import clean_text_for_tts, _tts_edge, _detect_language, _get_voice_config, _tts_elevenlabs

        clean_text = clean_text_for_tts(text)
        if not clean_text or len(clean_text) < 5:
            return

        config = _get_voice_config()

        # Try ElevenLabs first
        audio_result = None
        if config.get("elevenlabs_api_key"):
            audio_result = _tts_elevenlabs(clean_text, config=config)

        # Fallback to Edge TTS
        if not audio_result:
            lang = _detect_language(clean_text)
            voice = "hi-IN-SwaraNeural" if lang == "hi" else "en-IN-NeerjaExpressiveNeural"
            audio_result = _tts_edge(clean_text, voice)

        if audio_result and audio_result.get("audio_url"):
            audio_url = audio_result["audio_url"]
            # Resolve to file path
            if audio_url.startswith("/files/"):
                file_path = frappe.get_site_path("public", "files", os.path.basename(audio_url))
            elif audio_url.startswith("/private/"):
                file_path = frappe.get_site_path("private", "files", os.path.basename(audio_url))
            else:
                return

            if os.path.exists(file_path):
                _send_voice_file(chat_id, file_path)

                # Clean up TTS file
                try:
                    os.unlink(file_path)
                except Exception:
                    pass

    except Exception as e:
        frappe.logger().warning(f"Telegram voice reply failed: {e}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: INLINE BUTTONS & CALLBACK QUERIES
# ═══════════════════════════════════════════════════════════════════════

def _handle_callback_query(callback_query):
    """Handle inline button presses."""
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    telegram_user_id = str(callback_query.get("from", {}).get("id", ""))

    if not chat_id or not data:
        _answer_callback(callback_id, "Invalid request")
        return

    # Parse callback data
    if ":" in data:
        action, payload = data.split(":", 1)
    else:
        action, payload = data, ""

    if action == "quick":
        # Quick query — run through AI
        _answer_callback(callback_id, "Processing...")
        _cmd_quick_query(chat_id, telegram_user_id, payload)

    elif action == "report":
        # Report shortcut
        _answer_callback(callback_id, f"Generating {payload} report...")
        report_queries = {
            "sales": "Show me the sales summary report for this month",
            "collection": "Show me the collection efficiency report",
            "overdue": "Show me all overdue loans with days overdue",
            "npa": "Show me the complete NPA report",
        }
        query = report_queries.get(payload, f"Generate {payload} report")
        _cmd_quick_query(chat_id, telegram_user_id, query)

    elif action == "export":
        # Export in specified format
        _answer_callback(callback_id, f"Exporting as {payload}...")
        _cmd_export(chat_id, telegram_user_id, payload)

    elif action == "cmd":
        # Command shortcut
        _answer_callback(callback_id)
        if payload == "help":
            _cmd_help(chat_id)

    elif action == "more":
        # Follow-up query
        _answer_callback(callback_id, "Processing...")
        _cmd_quick_query(chat_id, telegram_user_id, payload)

    else:
        _answer_callback(callback_id, "Unknown action")


def _send_context_buttons(chat_id, response, original_query):
    """Send relevant follow-up buttons based on response content."""
    buttons = []
    response_lower = response.lower()

    # If response has tabular data, offer export
    if "|" in response and response.count("|") > 4:
        buttons.append([
            {"text": "📥 Excel", "callback_data": "export:excel"},
            {"text": "📄 PDF", "callback_data": "export:pdf"},
            {"text": "📋 CSV", "callback_data": "export:csv"},
        ])

    # Context-aware follow-ups
    if any(w in response_lower for w in ["loan", "disbursement", "emi", "repayment"]):
        buttons.append([
            {"text": "⚠️ Overdue Loans", "callback_data": "more:Show overdue loans"},
            {"text": "📊 NPA Report", "callback_data": "more:Show NPA summary"},
        ])
    elif any(w in response_lower for w in ["customer", "borrower", "client"]):
        buttons.append([
            {"text": "💰 Their Loans", "callback_data": "more:Show loans for this customer"},
            {"text": "📋 All Customers", "callback_data": "more:List all active customers"},
        ])
    elif any(w in response_lower for w in ["collection", "payment", "receipt"]):
        buttons.append([
            {"text": "📊 Efficiency", "callback_data": "more:Show collection efficiency"},
            {"text": "⏰ Pending", "callback_data": "more:Show pending collections"},
        ])

    if buttons:
        _send_telegram_with_buttons(chat_id, "↓ _Quick actions_", buttons)


def _answer_callback(callback_id, text=None):
    """Answer a callback query (removes loading indicator)."""
    token = _get_bot_token()
    if not token:
        return

    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: GROUP CHAT SUPPORT
# ═══════════════════════════════════════════════════════════════════════

def _is_bot_mentioned(message, settings):
    """Check if bot is mentioned or message is a reply to the bot."""
    text = message.get("text", "")

    # Reply to bot's message
    reply = message.get("reply_to_message")
    if reply and reply.get("from", {}).get("is_bot"):
        return True

    # @mention
    bot_username = getattr(settings, "telegram_bot_username", "") or ""
    if bot_username:
        if f"@{bot_username}" in text or f"@{bot_username.lower()}" in text.lower():
            return True

    # Check entities for bot mention
    entities = message.get("entities", [])
    for entity in entities:
        if entity.get("type") == "mention":
            mention_text = text[entity["offset"]:entity["offset"] + entity["length"]]
            if bot_username and mention_text.lower() == f"@{bot_username.lower()}":
                return True

    return False


def _strip_bot_mention(text, settings):
    """Remove @bot_mention from the message text."""
    bot_username = getattr(settings, "telegram_bot_username", "") or ""
    if bot_username:
        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE).strip()
    return text


# ═══════════════════════════════════════════════════════════════════════
# SECTION 8: RESPONSE CLEANING & TABLE FORMATTING
# ═══════════════════════════════════════════════════════════════════════

def _clean_response(text):
    """Clean LLM response for Telegram display."""
    # Remove thought blocks
    text = re.sub(r'\[\[?THOUGHT\]?\].*?\[\[?/?THOUGHT\]?\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\[THOUGHT\].*?$', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove system hints
    text = re.sub(r'\[TELEGRAM:.*?\]', '', text, flags=re.IGNORECASE)

    # Headers → bold
    text = re.sub(r'^#{1,3}\s*(.+)$', r'*\1*', text, flags=re.MULTILINE)

    # Bold/italic markdown → Telegram format
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'*_\1_*', text)  # bold italic
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)  # bold

    # Format tables
    text = _format_tables(text)

    # Clean code blocks for Telegram
    text = re.sub(r'```(\w*)\n', '```\n', text)  # Remove language hint

    # Remove empty lines excess
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _format_tables(text):
    """Convert markdown tables to mobile-friendly Telegram format."""
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


# ═══════════════════════════════════════════════════════════════════════
# SECTION 9: CONVERSATION MEMORY & DATA
# ═══════════════════════════════════════════════════════════════════════

def _get_last_assistant_message(conversation_id):
    """Get the last assistant message content from a conversation."""
    try:
        messages = frappe.get_all(
            "Niv Message",
            filters={"parent": conversation_id, "role": "assistant"},
            fields=["content"],
            order_by="creation desc",
            limit=1,
        )
        if messages:
            return messages[0].content
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════
# SECTION 10: USER MAPPING
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
# SECTION 11: TELEGRAM API HELPERS
# ═══════════════════════════════════════════════════════════════════════

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
    """Send message. Returns message_id."""
    token = _get_bot_token()
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

    try:
        r = requests.post(url, json=payload, timeout=15)
        if not r.ok and parse_mode:
            # Retry without parse mode if markdown is invalid
            payload.pop("parse_mode")
            r = requests.post(url, json=payload, timeout=15)
        if r.ok:
            return r.json().get("result", {}).get("message_id")
        return None
    except Exception:
        return None


def _send_telegram_with_buttons(chat_id, text, buttons, parse_mode="Markdown"):
    """Send message with inline keyboard buttons."""
    token = _get_bot_token()
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    keyboard = {"inline_keyboard": buttons}
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": json.dumps(keyboard),
    }

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
    """Edit existing message."""
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
    """Send message split into 4000-char chunks."""
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
    """Send typing/uploading indicator."""
    token = _get_bot_token()
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except Exception:
        pass


def _send_document(chat_id, file_path, filename=None):
    """Send a file/document to Telegram chat."""
    token = _get_bot_token()
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    _send_chat_action(chat_id, "upload_document")

    try:
        with open(file_path, "rb") as f:
            files = {"document": (filename or os.path.basename(file_path), f)}
            payload = {"chat_id": chat_id}
            r = requests.post(url, data=payload, files=files, timeout=30)
            if r.ok:
                return r.json().get("result", {}).get("message_id")
    except Exception as e:
        frappe.logger().warning(f"Telegram send document failed: {e}")

    return None


def _send_photo(chat_id, file_path_or_url, caption=None):
    """Send a photo to Telegram chat."""
    token = _get_bot_token()
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    _send_chat_action(chat_id, "upload_photo")

    try:
        payload = {"chat_id": chat_id}
        if caption:
            payload["caption"] = caption[:1024]  # Telegram caption limit
            payload["parse_mode"] = "Markdown"

        if file_path_or_url.startswith("http"):
            payload["photo"] = file_path_or_url
            r = requests.post(url, json=payload, timeout=15)
        else:
            with open(file_path_or_url, "rb") as f:
                files = {"photo": f}
                r = requests.post(url, data=payload, files=files, timeout=30)

        if r.ok:
            return r.json().get("result", {}).get("message_id")
    except Exception as e:
        frappe.logger().warning(f"Telegram send photo failed: {e}")

    return None


def _send_voice_file(chat_id, file_path):
    """Send a voice message to Telegram chat."""
    token = _get_bot_token()
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/sendVoice"

    try:
        with open(file_path, "rb") as f:
            files = {"voice": (os.path.basename(file_path), f)}
            payload = {"chat_id": chat_id}
            r = requests.post(url, data=payload, files=files, timeout=30)
            if r.ok:
                return r.json().get("result", {}).get("message_id")
    except Exception as e:
        frappe.logger().warning(f"Telegram send voice failed: {e}")

    return None


# ═══════════════════════════════════════════════════════════════════════
# SECTION 12: SCHEDULED REPORTS
# ═══════════════════════════════════════════════════════════════════════

def send_scheduled_reports():
    """Called by Frappe scheduler — sends configured reports to users.
    
    Add to hooks.py:
        scheduler_events = {
            "cron": {
                "0 9 * * 1-5": ["niv_ai.niv_core.api.telegram.send_scheduled_reports"]
            }
        }
    
    Reads schedule config from Niv Settings.
    """
    try:
        settings = _get_settings()
        schedules_json = getattr(settings, "telegram_report_schedules", None)
        if not schedules_json:
            return

        schedules = json.loads(schedules_json)
        if not isinstance(schedules, list):
            return

        for schedule in schedules:
            chat_id = schedule.get("chat_id")
            query = schedule.get("query")
            user = schedule.get("user")

            if not all([chat_id, query, user]):
                continue

            try:
                frappe.set_user(user)
                conversation_id = _get_or_create_conversation(user, chat_id)

                _send_telegram(chat_id, f"📊 *Scheduled Report*\n_{query}_")
                _handle_stream(chat_id, query, conversation_id, user)
                frappe.db.commit()

            except Exception:
                frappe.log_error(f"Scheduled report failed for {chat_id}", frappe.get_traceback())

    except Exception:
        frappe.log_error("Scheduled reports error", frappe.get_traceback())


def send_notification(chat_id, message, parse_mode="Markdown"):
    """Public API to send notifications to a Telegram chat.
    
    Can be called from other parts of Niv AI:
        from niv_ai.niv_core.api.telegram import send_notification
        send_notification(chat_id, "⚠️ Overdue alert: Loan #1234")
    """
    return _send_telegram(chat_id, message, parse_mode)


def send_alert_to_user(frappe_user, message):
    """Send alert to a user's Telegram (looks up their chat_id)."""
    users = frappe.get_all(
        "Niv Telegram User",
        filters={"frappe_user": frappe_user, "enabled": 1},
        fields=["telegram_chat_id"]
    )
    
    results = []
    for u in users:
        chat_id = u.telegram_chat_id
        if chat_id:
            result = _send_telegram(int(chat_id), message)
            results.append(result)
    
    return results


# ═══════════════════════════════════════════════════════════════════════
# SECTION 13: WEBHOOK SETUP & MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

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

    # Set allowed updates to include callback_query
    payload["allowed_updates"] = json.dumps(["message", "edited_message", "callback_query"])

    r = requests.post(url, json=payload, timeout=10)
    result = r.json()

    if result.get("ok"):
        frappe.msgprint(_("✅ Webhook set successfully!"))
    else:
        frappe.throw(_("❌ Failed: " + result.get("description", "Unknown")))

    return result


@frappe.whitelist(methods=["POST"])
def remove_webhook():
    """Remove Telegram webhook."""
    frappe.only_for("System Manager")

    token = _get_bot_token()
    if not token:
        frappe.throw(_("No bot token configured"))

    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    r = requests.post(url, timeout=10)
    result = r.json()

    if result.get("ok"):
        frappe.msgprint(_("✅ Webhook removed."))
    else:
        frappe.throw(_("❌ Failed: " + result.get("description", "Unknown")))

    return result


@frappe.whitelist(methods=["GET"])
def webhook_info():
    """Get current webhook info."""
    frappe.only_for("System Manager")

    token = _get_bot_token()
    if not token:
        return {"error": "No bot token configured"}

    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    r = requests.get(url, timeout=10)
    return r.json().get("result", {})


@frappe.whitelist(methods=["GET"])
def bot_info():
    """Get bot information (username, name, etc.)."""
    frappe.only_for("System Manager")

    token = _get_bot_token()
    if not token:
        return {"error": "No bot token configured"}

    url = f"https://api.telegram.org/bot{token}/getMe"
    r = requests.get(url, timeout=10)
    return r.json().get("result", {})


@frappe.whitelist(methods=["POST"])
def set_bot_commands():
    """Register bot commands with Telegram (shows in command menu)."""
    frappe.only_for("System Manager")

    token = _get_bot_token()
    if not token:
        frappe.throw(_("No bot token configured"))

    commands = [
        {"command": "start", "description": "Start the bot"},
        {"command": "help", "description": "Show available commands"},
        {"command": "loans", "description": "View top loans"},
        {"command": "npa", "description": "NPA report"},
        {"command": "report", "description": "Generate a report"},
        {"command": "export", "description": "Export data (excel/pdf/csv)"},
        {"command": "voice", "description": "Voice message info"},
        {"command": "status", "description": "Account status"},
        {"command": "link", "description": "Link your account"},
        {"command": "unlink", "description": "Unlink your account"},
    ]

    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    r = requests.post(url, json={"commands": commands}, timeout=10)
    result = r.json()

    if result.get("ok"):
        frappe.msgprint(_("✅ Bot commands registered!"))
    else:
        frappe.throw(_("❌ Failed: " + result.get("description", "Unknown")))

    return result
