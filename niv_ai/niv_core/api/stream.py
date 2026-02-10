"""
Stream API — SSE endpoint powered by LangChain agent.
Primary chat endpoint (frontend uses EventSource).
"""
import json
import frappe
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


def _check_rate_limit(user):
    """Check rate limits from Niv Settings. Throws if exceeded."""
    settings = frappe.get_cached_doc("Niv Settings")
    limit_hour = getattr(settings, "rate_limit_per_hour", 60) or 0
    limit_day = getattr(settings, "rate_limit_per_day", 500) or 0
    custom_msg = getattr(settings, "rate_limit_message", "") or "Rate limit exceeded. Please try again later."

    if limit_hour > 0:
        from datetime import datetime, timedelta
        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        count = frappe.db.count("Niv Message", {"role": "user", "owner": user, "creation": [">", one_hour_ago]})
        if count >= limit_hour:
            frappe.throw(_(custom_msg))

    if limit_day > 0:
        from datetime import datetime, timedelta
        today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        count = frappe.db.count("Niv Message", {"role": "user", "owner": user, "creation": [">", today_start]})
        if count >= limit_day:
            frappe.throw(_(custom_msg))


@frappe.whitelist()
def stream_chat(conversation_id, message, model=None, provider=None):
    """Stream chat via LangChain agent (SSE)."""
    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    validate_conversation(conversation_id, user)

    # Rate limiting
    _check_rate_limit(user)

    save_user_message(conversation_id, message, dedup=True)

    settings = frappe.get_cached_doc("Niv Settings")
    provider = provider or settings.default_provider
    model = model or settings.default_model

    def generate():
        full_response = ""
        tool_calls_data = []

        try:
            from niv_ai.niv_core.langchain.agent import stream_agent

            for event in stream_agent(
                message=message,
                conversation_id=conversation_id,
                provider_name=provider,
                model=model,
                user=user,
            ):
                event_type = event.get("type", "")

                if event_type == "token":
                    content = event.get("content", "")
                    full_response += content
                    yield _sse({"type": "token", "content": content})

                elif event_type == "tool_call":
                    tc = {"tool": event.get("tool", ""), "arguments": event.get("arguments", {})}
                    tool_calls_data.append(tc)
                    yield _sse({"type": "tool_call", **tc})

                elif event_type == "tool_result":
                    yield _sse({"type": "tool_result", "tool": event.get("tool", ""), "result": event.get("result", "")})

                elif event_type == "error":
                    full_response = event.get("content", "An error occurred.")
                    yield _sse(event)

        except Exception as e:
            full_response = "Something went wrong. Please try again."
            frappe.log_error(f"Stream error: {e}", "Niv AI Stream")
            yield _sse({"type": "error", "content": full_response})

        # Save response
        save_assistant_message(conversation_id, full_response, tool_calls_data)
        auto_title(conversation_id, message)

        yield _sse({"type": "done", "content": full_response})

    # Return Werkzeug Response directly — Frappe handler.py checks isinstance(data, Response)
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


def _sse(data: dict) -> bytes:
    """Format SSE event line."""
    return f"data: {json.dumps(data, default=str)}\n\n".encode("utf-8")
