"""
Stream API — SSE endpoint for Niv AI chat.
Handles request parsing, message saving, and SSE response streaming.
The agent (agent.py) handles all LLM/tool logic.
"""
import json
import frappe
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


# ─── Simple Query Detection ────────────────────────────────────────

_SIMPLE_PATTERNS = frozenset({
    "hi", "hello", "hey", "hii", "hiii", "namaste", "namaskar",
    "thanks", "thank you", "thankyou", "dhanyavaad", "shukriya",
    "ok", "okay", "k", "done", "yes", "no", "haan", "nahi", "na",
    "good", "great", "nice", "awesome", "cool", "fine", "accha",
    "bye", "goodbye", "good night", "good morning", "good evening",
    "gm", "gn", "morning", "evening",
    "hmm", "hm", "oh", "ah", "wow",
})

_QUESTION_WORDS = frozenset({
    "what", "how", "why", "when", "where", "which", "who",
    "kya", "kaise", "kab", "kahan", "kaun", "kitna", "kitne",
    "show", "list", "get", "find", "create", "make", "delete",
    "calculate", "report", "export", "analyze",
})


def _check_rate_limit(user=None):
    """Rate limit check - uses settings if configured."""
    try:
        from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
        check_rate_limit(user)
    except ImportError:
        pass


def _is_simple_query(message: str) -> bool:
    """Detect simple queries that don't need a powerful model."""
    msg = (message or "").strip().lower()
    word_count = len(msg.split())
    if word_count > 3:
        return False
    # Check exact match against simple patterns (strip trailing punctuation)
    if msg.rstrip("!.?") in _SIMPLE_PATTERNS:
        return True
    # 1-2 word messages without question/action words
    if word_count <= 2 and not any(w in msg for w in _QUESTION_WORDS):
        return True
    return False


# ─── DB Connection Helpers ──────────────────────────────────────────

def _ensure_db(site_name=None):
    """Ensure DB connection is alive, reconnect if dead."""
    try:
        if not frappe.db or getattr(frappe.db, '_conn', None) is None:
            raise Exception("No DB connection")
        frappe.db.sql("SELECT 1")
    except Exception:
        try:
            if site_name:
                frappe.init(site=site_name)
            frappe.connect()
        except Exception:
            # Last resort — full reinit
            try:
                frappe.init(site=site_name or getattr(frappe.local, 'site', None))
                frappe.connect()
            except Exception:
                pass


# ─── SSE Formatting ────────────────────────────────────────────────

def _sse(data):
    """Format SSE event."""
    return f"data: {json.dumps(data)}\n\n"


# ─── Main Endpoint ─────────────────────────────────────────────────

@frappe.whitelist(methods=["GET", "POST"])
def stream_chat(**kwargs):
    """Stream chat via Niv AI Agent (SSE)."""
    
    # ── Parse request ──
    if frappe.request.method == "POST":
        try:
            data = frappe.request.get_json(silent=True) or {}
        except Exception:
            data = {}
        conversation_id = data.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = data.get("message") or frappe.form_dict.get("message")
        page_context = data.get("context") or frappe.form_dict.get("context")
        model = data.get("model") or frappe.form_dict.get("model")
    else:
        conversation_id = kwargs.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = kwargs.get("message") or frappe.form_dict.get("message")
        page_context = kwargs.get("context") or frappe.form_dict.get("context")
        model = kwargs.get("model") or frappe.form_dict.get("model")

    # Parse page context JSON
    if page_context and isinstance(page_context, str):
        try:
            page_context = json.loads(page_context)
        except (json.JSONDecodeError, ValueError):
            page_context = None

    # Parse attachments
    if frappe.request.method == "POST":
        attachments_raw = data.get("attachments") or frappe.form_dict.get("attachments")
    else:
        attachments_raw = kwargs.get("attachments") or frappe.form_dict.get("attachments")
    
    attachments = []
    if attachments_raw:
        if isinstance(attachments_raw, str):
            try:
                attachments = json.loads(attachments_raw)
            except (json.JSONDecodeError, ValueError):
                attachments = []
        elif isinstance(attachments_raw, list):
            attachments = attachments_raw
    

    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    # ── Auto-route simple queries to fast model ──
    if not model:
        try:
            from niv_ai.niv_core.utils import get_niv_settings
            _settings = get_niv_settings()
            fast_model = getattr(_settings, "fast_model", None)
            if fast_model and _is_simple_query(message):
                model = fast_model
        except Exception:
            pass

    # ── Auto-create conversation if needed ──
    if not conversation_id:
        conv = frappe.get_doc({
            "doctype": "Niv Conversation",
            "user": user,
            "title": message[:50],
            "channel": "web",
        })
        conv.insert(ignore_permissions=True)
        frappe.db.commit()
        conversation_id = conv.name

    validate_conversation(conversation_id, user)
    save_user_message(conversation_id, message, dedup=True)

    # -- Check token balance BEFORE running agent --
    _insufficient_balance = False
    _balance_msg = ""
    try:
        from niv_ai.niv_core.utils import get_niv_settings
        _billing_settings = get_niv_settings()
        if getattr(_billing_settings, 'enable_billing', False):
            from niv_ai.niv_billing.api.billing import check_balance
            _bal = check_balance(user)
            _user_balance = _bal.get('balance', 0)
            _msg_tokens = max(1, len(message) // 4)
            _estimated_min = 3000 + _msg_tokens + 500  # system prompt ~2500 + history ~500 + response ~500
            if _user_balance < _estimated_min:
                _insufficient_balance = True
                _balance_msg = (
                    f'Your token balance ({_user_balance:,} tokens) is not enough to process this query. '
                    f'Estimated minimum required: ~{_estimated_min:,} tokens. '
                    f'Please recharge your tokens to continue using the AI assistant.'
                )
    except Exception as _bex:
        import traceback
        frappe.log_error(f"Balance pre-check FAILED: {_bex}\n{traceback.format_exc()}", "Niv Balance PreCheck")

    # Track balance for mid-stream check
    _user_token_balance = 0
    try:
        if not _insufficient_balance:
            from niv_ai.niv_core.utils import get_niv_settings
            _bs = get_niv_settings()
            if getattr(_bs, 'enable_billing', False):
                from niv_ai.niv_billing.api.billing import check_balance as _cb
                _user_token_balance = _cb(user).get('balance', 0)
    except Exception:
        _user_token_balance = 999999  # if check fails, don't block

    _site_name = frappe.local.site

    def generate():
        import time as _time
        
        full_response = ""
        tool_calls_data = []
        _balance_exhausted = False
        _next_balance_check = 2000  # check every 2000 chars

        # If balance is insufficient, send message and stop immediately
        if _insufficient_balance:
            yield _sse({"type": "token", "content": _balance_msg})
            full_response = _balance_msg
            _ensure_db(_site_name)
            save_assistant_message(conversation_id, _balance_msg, [])
            yield _sse({"type": "done", "content": "", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
            return
        token_data = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        _last_db_check = _time.time()

        def _heartbeat_db():
            """Keep DB alive during long streams."""
            nonlocal _last_db_check
            now = _time.time()
            if now - _last_db_check > 5:
                _ensure_db(_site_name)
                _last_db_check = now

        try:
            frappe.init(site=_site_name)
            frappe.connect()

            from niv_ai.niv_core.langchain.agent import stream_agent

            for event in stream_agent(
                message=message,
                conversation_id=conversation_id,
                user=user,
                model=model or None,
                page_context=page_context,
                attachments=attachments,
            ):
                _heartbeat_db()
                event_type = event.get("type", "")

                if event_type == "token":
                    content = event.get("content", "")
                    if content:
                        full_response += content
                        yield _sse(event)
                        
                        # Mid-stream balance check (every ~2000 chars)
                        if len(full_response) > _next_balance_check:
                            frappe.log_error(f"Mid-stream check: balance={_user_token_balance}, response_len={len(full_response)}, estimate={3000 + max(1, len(full_response) // 4)}", "Niv Balance Debug")
                        if _user_token_balance > 0 and len(full_response) > _next_balance_check:
                            _next_balance_check += 2000
                            _consumed_estimate = 3000 + max(1, len(full_response) // 4)
                            if _consumed_estimate >= _user_token_balance:
                                _cutoff_msg = "\n\n---\n⚠️ Your token balance has been exhausted. Please recharge to continue."
                                full_response += _cutoff_msg
                                yield _sse({"type": "token", "content": _cutoff_msg})
                                _balance_exhausted = True
                                break

                elif event_type == "tool_call":
                    _ensure_db(_site_name)  # DB must be alive before tool execution
                    tool_calls_data.append({
                        "tool": event.get("tool", ""),
                        "arguments": event.get("arguments", {})
                    })
                    yield _sse(event)

                elif event_type == "tool_result":
                    _ensure_db(_site_name)
                    yield _sse(event)

                elif event_type == "thought":
                    yield _sse(event)

                elif event_type == "_token_usage":
                    # Internal — capture for saving, don't send to client
                    token_data = {
                        "input_tokens": event.get("input_tokens", 0),
                        "output_tokens": event.get("output_tokens", 0),
                        "total_tokens": event.get("total_tokens", 0),
                    }

                elif event_type == "error":
                    yield _sse(event)
                    if not full_response.strip():
                        full_response = event.get("content", "Error occurred")

                else:
                    yield _sse(event)

        except Exception as e:
            error_str = str(e).lower()
            # Check if this is a billing/token error
            if any(kw in error_str for kw in ['insufficient', 'credit', 'balance', 'daily limit', 'exhausted', 'recharge']):
                billing_msg = f"Your token balance is not enough to process this query. Please recharge your tokens to continue using the AI assistant."
                if not full_response.strip():
                    full_response = billing_msg
                yield _sse({"type": "token", "content": billing_msg})
            else:
                error_msg = f"Error: {str(e)}"
                if not full_response.strip():
                    full_response = error_msg
                frappe.log_error(f"Stream error: {e}", "Niv AI Stream")
                yield _sse({"type": "error", "content": error_msg})

        finally:
            # ── Fallback: if tools ran but no text response, tell the user ──
            if not full_response.strip() and tool_calls_data:
                full_response = "I found some data but couldn't generate a response. Please try rephrasing your question."
                yield _sse({"type": "token", "content": full_response})
            
            # ── Fallback: completely empty response ──
            if not full_response.strip():
                full_response = "I couldn't generate a response. Please try again."
                yield _sse({"type": "token", "content": full_response})

            # ── Save assistant message to DB ──
            _ensure_db(_site_name)
            _model_used = model
            if not _model_used:
                try:
                    from niv_ai.niv_core.utils import get_niv_settings
                    _s = get_niv_settings()
                    _model_used = _s.default_model
                except Exception:
                    pass
            
            try:
                save_assistant_message(
                    conversation_id, full_response, tool_calls_data,
                    input_tokens=token_data.get("input_tokens", 0),
                    output_tokens=token_data.get("output_tokens", 0),
                    total_tokens=token_data.get("total_tokens", 0),
                    model=_model_used,
                )
                auto_title(conversation_id, message)
            except Exception as e:
                frappe.log_error(f"Save message error: {e}", "Niv AI Stream")

            # ── Send done event ──
            yield _sse({
                "type": "done", "content": "",
                "input_tokens": token_data.get("input_tokens", 0),
                "output_tokens": token_data.get("output_tokens", 0),
                "total_tokens": token_data.get("total_tokens", 0),
            })

    from werkzeug.wrappers import Response
    return Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
