"""
Stream API ??? SSE endpoint using LangChain Agent
Uses existing battle-tested LangChain agent (sync, no async issues)
"""
import json
import frappe
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


def _check_rate_limit(user=None):
    """Rate limit check - uses settings if configured"""
    try:
        from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
        check_rate_limit(user)
    except ImportError:
        pass  # Rate limiter not available, skip


def _sse(data):
    """Format SSE event"""
    return f"data: {json.dumps(data)}\n\n"


def _is_simple_query(message: str) -> bool:
    """Detect simple queries that don't need a powerful model.
    Greetings, thanks, yes/no, short confirmations, etc."""
    msg = (message or "").strip().lower()
    # Very short messages (1-3 words) are usually simple
    word_count = len(msg.split())
    if word_count <= 3:
        # Check if it's a greeting/thanks/confirmation
        simple_patterns = {
            "hi", "hello", "hey", "hii", "hiii", "namaste", "namaskar",
            "thanks", "thank you", "thankyou", "dhanyavaad", "shukriya",
            "ok", "okay", "k", "done", "yes", "no", "haan", "nahi", "na",
            "good", "great", "nice", "awesome", "cool", "fine", "accha",
            "bye", "goodbye", "good night", "good morning", "good evening",
            "gm", "gn", "morning", "evening",
            "hmm", "hm", "oh", "ah", "wow",
        }
        if msg.rstrip("!.?") in simple_patterns:
            return True
        # Very short messages without question words
        question_words = {"what", "how", "why", "when", "where", "which", "who",
                         "kya", "kaise", "kab", "kahan", "kaun", "kitna", "kitne",
                         "show", "list", "get", "find", "create", "make", "delete",
                         "calculate", "report", "export", "analyze"}
        if word_count <= 2 and not any(w in msg for w in question_words):
            return True
    return False


def _ensure_db(site_name=None):
    """Ensure DB connection is alive, reconnect if dead.
    Fixes pymysql.err.InterfaceError: (0, '') from stale connections."""
    try:
        frappe.db.sql("SELECT 1")
    except Exception:
        try:
            if site_name:
                frappe.init(site=site_name)
            frappe.connect()
        except Exception:
            pass


@frappe.whitelist(methods=["GET", "POST"])
def stream_chat(**kwargs):
    """Stream chat via LangChain Agent (SSE)"""
    # Parse request
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

    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    # Auto-route to fast model for simple queries (when user hasn't explicitly picked a model)
    if not model:
        try:
            from niv_ai.niv_core.utils import get_niv_settings
            _settings = get_niv_settings()
            fast_model = getattr(_settings, "fast_model", None)
            if fast_model and _is_simple_query(message):
                model = fast_model
        except Exception:
            pass

    # Auto-create conversation if not provided
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

    _site_name = frappe.local.site

    def generate():
        full_response = ""
        tool_calls_data = []
        token_data = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        
        try:
            frappe.init(site=_site_name)
            frappe.connect()

            # Use existing LangChain agent - it handles everything!
            from niv_ai.niv_core.langchain.agent import stream_agent
            
            for event in stream_agent(
                message=message,
                conversation_id=conversation_id,
                user=user,
                model=model or None,
                page_context=page_context,
            ):
                event_type = event.get("type", "")
                
                if event_type == "token":
                    content = event.get("content", "")
                    full_response += content
                    yield _sse(event)
                
                elif event_type == "tool_call":
                    tool_calls_data.append({
                        "tool": event.get("tool", ""),
                        "arguments": event.get("arguments", {})
                    })
                    yield _sse(event)
                
                elif event_type == "tool_result":
                    yield _sse(event)
                
                elif event_type == "thought":
                    # Pass through thought events for UI
                    yield _sse(event)
                
                elif event_type == "_token_usage":
                    # Internal event from agent — capture but don't send to client
                    token_data = {
                        "input_tokens": event.get("input_tokens", 0),
                        "output_tokens": event.get("output_tokens", 0),
                        "total_tokens": event.get("total_tokens", 0),
                    }
                
                elif event_type == "error":
                    yield _sse(event)
                    full_response = event.get("content", "Error occurred")
                
                else:
                    # Pass through any other events
                    yield _sse(event)

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            full_response = error_msg
            frappe.log_error(f"Stream error: {e}", "Niv AI Stream")
            yield _sse({"type": "error", "content": error_msg})

        finally:
            # Save response - ensure DB connection is alive
            if full_response.strip():
                _ensure_db(_site_name)
                # Resolve actual model name for DB
                _model_used = model
                if not _model_used:
                    try:
                        from niv_ai.niv_core.utils import get_niv_settings
                        _s = get_niv_settings()
                        _model_used = _s.default_model
                    except Exception:
                        pass
                save_assistant_message(
                    conversation_id, full_response, tool_calls_data,
                    input_tokens=token_data.get("input_tokens", 0),
                    output_tokens=token_data.get("output_tokens", 0),
                    total_tokens=token_data.get("total_tokens", 0),
                    model=_model_used,
                )
                auto_title(conversation_id, message)

            yield _sse({
                "type": "done", "content": "",
                "input_tokens": token_data.get("input_tokens", 0),
                "output_tokens": token_data.get("output_tokens", 0),
                "total_tokens": token_data.get("total_tokens", 0),
            })

            # Don't call frappe.destroy() here — it kills the DB connection
            # for subsequent requests. Let Frappe's request lifecycle handle cleanup.

    from werkzeug.wrappers import Response
    return Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
