"""
Stream API — SSE endpoint powered by LangChain agent.
Primary chat endpoint (frontend uses EventSource).
"""
import json
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from frappe import _
from niv_ai.niv_core.api._helpers import validate_conversation, save_user_message, save_assistant_message, auto_title


def _smart_route_model(message, default_model, dev_mode, settings):
    """Route to optimal model based on message complexity. Zero API call — keyword based."""
    import re

    # Read routing config from settings (custom fields)
    model_light = getattr(settings, "model_light", "") or ""
    model_medium = getattr(settings, "model_medium", "") or ""
    model_heavy = getattr(settings, "model_heavy", "") or ""

    # If no routing models configured, use default
    if not (model_light or model_medium or model_heavy):
        return default_model

    msg = message.strip().lower()
    msg_len = len(message.strip())

    # LIGHT — casual greetings, short responses (< 20 chars, no question)
    _casual = {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye",
               "good morning", "good evening", "good night", "haan", "ha", "nahi",
               "theek hai", "shukriya", "dhanyavaad", "namaste", "kya haal"}
    if msg in _casual or (msg_len < 15 and "?" not in msg and not dev_mode):
        return model_light or default_model

    # HEAVY — dev mode, coding, creation, complex analysis
    _heavy_patterns = [
        r"(create|banao|bana do|build|design|write|likh)",
        r"(doctype|custom field|script|workflow|print format|report)",
        r"(code|function|api|endpoint|hook|migration)",
        r"(analyze|analysis|trend|pattern|compare|optimize)",
        r"(blueprint|module|system|architecture|schema)",
        r"(explain|samjhao|detail|in depth|step by step)",
    ]
    if dev_mode or any(re.search(p, msg) for p in _heavy_patterns) or msg_len > 200:
        return model_heavy or default_model

    # MEDIUM — queries, reports, data questions (default)
    return model_medium or default_model


def _check_rate_limit(user):
    """Check rate limits from Niv Settings. Throws if exceeded."""
    settings = get_niv_settings()
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


@frappe.whitelist(methods=["GET", "POST"])
def stream_chat(**kwargs):
    """Stream chat via LangChain agent (SSE)."""
    # Support both GET (legacy EventSource) and POST (new fetch)
    if frappe.request.method == "POST":
        try:
            data = frappe.request.get_json(silent=True) or {}
        except Exception:
            data = {}
        conversation_id = data.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = data.get("message") or frappe.form_dict.get("message")
        model = data.get("model") or frappe.form_dict.get("model")
        provider = data.get("provider") or frappe.form_dict.get("provider")
        dev_mode = data.get("dev_mode") or frappe.form_dict.get("dev_mode")
    else:
        conversation_id = kwargs.get("conversation_id") or frappe.form_dict.get("conversation_id")
        message = kwargs.get("message") or frappe.form_dict.get("message")
        model = kwargs.get("model") or frappe.form_dict.get("model")
        provider = kwargs.get("provider") or frappe.form_dict.get("provider")
        dev_mode = kwargs.get("dev_mode") or frappe.form_dict.get("dev_mode")

    user = frappe.session.user
    message = (message or "").strip()

    if not message:
        frappe.throw(_("Message cannot be empty"))

    # Developer mode — only for System Manager
    dev_mode = bool(int(dev_mode or 0))
    if dev_mode and "System Manager" not in frappe.get_roles(user):
        dev_mode = False

    # Auto-create conversation if not provided (mobile app support)
    if not conversation_id:
        conv = frappe.get_doc({
            "doctype": "Niv Conversation",
            "user": user,
            "title": message[:50],
            "channel": "mobile",
        })
        conv.insert(ignore_permissions=True)
        frappe.db.commit()
        conversation_id = conv.name

    validate_conversation(conversation_id, user)

    # Rate limiting
    _check_rate_limit(user)

    save_user_message(conversation_id, message, dedup=True)

    settings = get_niv_settings()
    provider = provider or settings.default_provider
    model = model or settings.default_model

    # Capture site for re-init inside generator (Frappe may destroy() before generator finishes)
    _site_name = frappe.local.site

    # Smart Model Routing — auto-select model based on message complexity
    if not (kwargs.get("model") or (frappe.request.method == "POST" and (frappe.request.get_json(silent=True) or {}).get("model"))):
        model = _smart_route_model(message, model, dev_mode, settings)

    # Dev Mode: check if user is confirming a pending action
    if dev_mode:
        _confirm_words = {"yes", "y", "ha", "haan", "ok", "confirm", "proceed", "kar do", "kardo"}
        _cancel_words = {"no", "n", "nahi", "nhi", "cancel", "mat karo", "ruk"}
        msg_lower = message.strip().lower()

        from niv_ai.niv_core.langchain.tools import (
            get_pending_dev_action, execute_pending_dev_action,
            clear_pending_dev_action, set_dev_mode as _set_dev_mode,
            get_undo_stack, execute_undo
        )

        _undo_words = {"undo", "rollback", "revert", "wapas", "vapas", "hatao", "delete last"}

        # Handle undo
        if msg_lower in _undo_words:
            undo_stack = get_undo_stack(conversation_id)
            if undo_stack:
                def generate_undo():
                    try:
                        result = execute_undo(conversation_id)
                        if result:
                            yield _sse({"type": "token", "content": f"↩️ **Undo Complete:**\n\n{result}"})
                            try:
                                frappe.db.sql("SELECT 1")
                            except Exception:
                                frappe.db.connect()
                            save_assistant_message(conversation_id, f"↩️ Undo Complete:\n\n{result}", [])
                        else:
                            msg = "Nothing to undo."
                            yield _sse({"type": "token", "content": msg})
                            save_assistant_message(conversation_id, msg, [])
                    except Exception as e:
                        err = f"Undo failed: {str(e)}"
                        yield _sse({"type": "error", "content": err})
                    yield _sse({"type": "done", "content": ""})
                from werkzeug.wrappers import Response
                return Response(generate_undo(), content_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
            else:
                def generate_no_undo():
                    msg = "❌ Nothing to undo. No recent dev actions found."
                    yield _sse({"type": "token", "content": msg})
                    save_assistant_message(conversation_id, msg, [])
                    yield _sse({"type": "done", "content": msg})
                from werkzeug.wrappers import Response
                return Response(generate_no_undo(), content_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

        pending = get_pending_dev_action(conversation_id)
        if pending and msg_lower in _confirm_words:
            # Execute all pending actions directly
            def generate_confirm():
                _set_dev_mode(False)  # Don't intercept during execution
                try:
                    # Show tool calls being executed
                    for action in pending:
                        yield _sse({"type": "tool_call", "tool": action.get("tool_name", ""), "arguments": action.get("arguments", {})})

                    result = execute_pending_dev_action(conversation_id)
                    if result:
                        yield _sse({"type": "tool_result", "tool": "dev_actions", "result": (result or "")[:2000]})
                        # Let AI summarize
                        from niv_ai.niv_core.langchain.agent import stream_agent as _sa
                        summary_msg = f"Developer actions executed successfully. Results:\n{result}\n\nSummarize what was done for the user. Be concise."
                        full_resp = ""
                        for evt in _sa(message=summary_msg, conversation_id=conversation_id, provider_name=provider, model=model, user=user, dev_mode=False):
                            if evt.get("type") == "token":
                                full_resp += evt.get("content", "")
                                yield _sse(evt)
                        try:
                            frappe.db.sql("SELECT 1")
                        except Exception:
                            frappe.db.connect()
                        tc_data = [{"tool": a.get("tool_name", ""), "arguments": a.get("arguments", {})} for a in pending]
                        save_assistant_message(conversation_id, full_resp, tc_data)
                    else:
                        msg = "No pending action found to execute."
                        yield _sse({"type": "token", "content": msg})
                        save_assistant_message(conversation_id, msg, [])
                except Exception as e:
                    err_msg = f"Error executing actions: {str(e)}"
                    yield _sse({"type": "error", "content": err_msg})
                finally:
                    _set_dev_mode(False)
                yield _sse({"type": "done", "content": ""})

            from werkzeug.wrappers import Response
            return Response(generate_confirm(), content_type="text/event-stream",
                          headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

        elif pending and msg_lower in _cancel_words:
            clear_pending_dev_action(conversation_id)
            def generate_cancel():
                msg = "❌ Action cancelled. What would you like to do instead?"
                yield _sse({"type": "token", "content": msg})
                save_assistant_message(conversation_id, msg, [])
                yield _sse({"type": "done", "content": msg})
            from werkzeug.wrappers import Response
            return Response(generate_cancel(), content_type="text/event-stream",
                          headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

    def generate():
        full_response = ""
        tool_calls_data = []
        tool_results_data = []
        saw_token = False
        saw_tool_activity = False
        saw_error = False

        try:
            # Always re-init frappe context inside generator
            # (Frappe's app.py calls destroy() after returning the Response,
            #  but the generator hasn't finished yielding yet)
            frappe.init(site=_site_name)
            frappe.connect()

            from niv_ai.niv_core.langchain.agent import stream_agent
            from niv_ai.niv_core.langchain.tools import set_dev_mode as _set_dev_mode, set_active_dev_conversation

            # ─── A2A (google-adk) Branch ───
            use_a2a = getattr(settings, "enable_a2a", 0)
            adk_failed = False
            if use_a2a:
                try:
                    from niv_ai.niv_core.a2a.runner import stream_a2a
                    for event in stream_a2a(
                        message=message,
                        conversation_id=conversation_id,
                        provider_name=provider,
                        model_name=model,
                        user=user,
                        dev_mode=dev_mode
                    ):
                        event_type = event.get("type", "")
                        if event_type == "token":
                            content = event.get("content", "")
                            if content:
                                saw_token = True
                                full_response += content
                            yield _sse(event)
                        elif event_type == "complete":
                            # A2A finished - save message and send done
                            pass  # Will be handled after loop
                        elif event_type in ("tool_call", "tool_result", "thought", "error", "agent_transfer", "state_change"):
                            if event_type == "tool_call":
                                saw_tool_activity = True
                                tool_calls_data.append({"tool": event.get("tool", ""), "arguments": event.get("arguments", {})})
                            elif event_type == "tool_result":
                                tool_results_data.append({"tool": event.get("tool", ""), "result": str(event.get("result", ""))[:500]})
                            yield _sse(event)
                    
                    # ─── A2A COMPLETION ───
                    # Clean up full_response — remove critique signals + thought tags
                    import re as _re
                    _critique_words = {"PASSED", "FAILED", "APPROVED", "REJECTED"}
                    clean_parts = []
                    for part in full_response.split("\n"):
                        if part.strip().upper() not in _critique_words:
                            clean_parts.append(part)
                    full_response = "\n".join(clean_parts).strip()
                    # Strip [[THOUGHT]]...[[/THOUGHT]] blocks
                    full_response = _re.sub(r'\[\[THOUGHT\]\].*?\[\[/THOUGHT\]\]', '', full_response, flags=_re.DOTALL).strip()
                    # Remove fallback message if real content follows
                    _fallback = "I processed your request but couldn't generate a response. Please try again."
                    if _fallback in full_response and len(full_response) > len(_fallback) + 20:
                        full_response = full_response.replace(_fallback, "").strip()
                    
                    # Save assistant message if we got a response
                    if full_response.strip():
                        try:
                            # Ensure DB connection is alive
                            frappe.db.sql("SELECT 1")
                        except Exception:
                            frappe.init(site=_site_name)
                            frappe.connect()
                        save_assistant_message(conversation_id, full_response, tool_calls_data)
                        auto_title(conversation_id)
                    
                    # Send done event
                    yield _sse({"type": "done", "content": ""})
                    return
                except Exception as adk_err:
                    frappe.log_error(f"Niv AI: ADK failed, falling back to LangGraph: {adk_err}", "Niv AI Stream")
                    adk_failed = True

            # ─── Legacy LangGraph Branch (or Fallback) ───
            # Set dev mode on tools layer (Redis flag + global conv_id for cross-thread)
            if dev_mode:
                _set_dev_mode(True, conversation_id)
                set_active_dev_conversation(conversation_id)

            for event in stream_agent(
                message=message,
                conversation_id=conversation_id,
                provider_name=provider,
                model=model,
                user=user,
                dev_mode=dev_mode,
            ):
                event_type = event.get("type", "")

                if event_type == "token":
                    content = event.get("content", "")
                    if content:
                        saw_token = True
                        full_response += content
                    yield _sse({"type": "token", "content": content})

                elif event_type == "tool_call":
                    saw_tool_activity = True
                    tc = {"tool": event.get("tool", ""), "arguments": event.get("arguments", {})}
                    tool_calls_data.append(tc)
                    yield _sse({"type": "tool_call", **tc})

                elif event_type == "tool_result":
                    saw_tool_activity = True
                    result_text = event.get("result", "")
                    tool_results_data.append({"tool": event.get("tool", ""), "result": result_text[:2000]})
                    yield _sse({"type": "tool_result", "tool": event.get("tool", ""), "result": result_text})

                elif event_type == "error":
                    saw_error = True
                    full_response = event.get("content", "An error occurred.")
                    yield _sse(event)

        except Exception as e:
            full_response = "Something went wrong. Please try again."
            try:
                frappe.log_error(f"Stream error: {e}", "Niv AI Stream")
            except Exception:
                print(f"[Niv AI Stream] Error: {e}")
            yield _sse({"type": "error", "content": full_response})
        finally:
            # Clear dev mode flag
            if dev_mode:
                _set_dev_mode(False, conversation_id)
                set_active_dev_conversation("")

        # Ensure final text exists when tools ran but model text was empty or garbage
        # Force a summary LLM call (no tools) so user always gets a text answer
        # Also fires after timeout/limit errors — user still deserves a summary of what was found
        # "Garbage" = raw JSON, tool call plans, or very short text
        _text_is_useful = saw_token and len(full_response.strip()) > 100 and not full_response.strip().startswith('{')
        if saw_tool_activity and not _text_is_useful:
            try:
                # Build a summary of tool results for the LLM
                tool_summary_parts = []
                for i, tc in enumerate(tool_calls_data):
                    result_str = ""
                    if i < len(tool_results_data):
                        result_str = f"\n  Result: {tool_results_data[i].get('result', '')[:2000]}"
                    tool_summary_parts.append(f"- `{tc.get('tool', 'unknown')}`: args={json.dumps(tc.get('arguments', {}), default=str)[:150]}{result_str}")
                tool_list_text = "\n".join(tool_summary_parts[:8]) if tool_summary_parts else "Multiple tools were called."

                summary_prompt = (
                    f"The user asked: \"{message}\"\n\n"
                    f"Tool results:\n{tool_list_text}\n\n"
                    "Summarize the findings for the user. Be concise, use tables/lists for data. "
                    "If tools returned errors, explain what info you couldn't get."
                )

                from niv_ai.niv_core.langchain.llm import get_llm
                summary_llm = get_llm(provider, model, streaming=False, callbacks=[])
                from langchain_core.messages import HumanMessage as _HM
                summary_result = summary_llm.invoke([_HM(content=summary_prompt)])
                full_response = summary_result.content if hasattr(summary_result, 'content') else str(summary_result)
                yield _sse({"type": "token", "content": full_response})
            except Exception as e:
                full_response = (
                    "I gathered data using multiple tools but couldn't generate a summary. "
                    "Please ask me to 'summarize' or rephrase your question."
                )
                yield _sse({"type": "token", "content": full_response})

        # Reconnect DB if stale before saving (gthread workers lose connections during streaming)
        try:
            frappe.db.sql("SELECT 1")
        except Exception:
            try:
                frappe.db.connect()
            except Exception:
                print("[Niv AI Stream] DB reconnect failed, skipping save")
                yield _sse({"type": "done", "content": full_response})
                return

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
