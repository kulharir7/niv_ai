import frappe
import json
import time
import requests
from datetime import date, datetime

try:
    from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
    from niv_ai.niv_core.utils.validators import sanitize_message, validate_conversation_id, validate_model_name
    from niv_ai.niv_core.utils.error_handler import handle_stream_errors
    from niv_ai.niv_core.utils.logger import log_api_call
    from niv_ai.niv_core.utils.retry import get_timeout_settings
except ImportError:
    check_rate_limit = lambda *a, **kw: None
    sanitize_message = lambda t: t
    validate_conversation_id = lambda c: c
    validate_model_name = lambda m: m
    handle_stream_errors = lambda f: f
    log_api_call = lambda *a, **kw: None
    get_timeout_settings = lambda: {"api_timeout": 60, "max_retries": 3}


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


@frappe.whitelist(allow_guest=False)
def stream_message(conversation_id=None, message=None, model=None, context=None):
    """
    SSE streaming endpoint for chat.
    Returns Server-Sent Events for real-time streaming.

    Events:
    - data: {"type": "token", "content": "..."}
    - data: {"type": "tool_call", "tool": "...", "params": {...}}
    - data: {"type": "tool_result", "tool": "...", "result": {...}}
    - data: {"type": "done", "message_id": "...", "tokens": {...}}
    - data: {"type": "error", "message": "..."}
    """
    # Get params from query string if not passed (for EventSource GET requests)
    if not conversation_id:
        conversation_id = frappe.request.args.get("conversation_id")
    if not message:
        message = frappe.request.args.get("message")
    if not model:
        model = frappe.request.args.get("model")
    if not context:
        context = frappe.request.args.get("context")
    user = frappe.session.user
    log_api_call("stream_message", user, conversation_id=conversation_id)

    # Rate limiting
    check_rate_limit(user)

    # Input validation
    if message:
        message = sanitize_message(message)
    if conversation_id:
        conversation_id = validate_conversation_id(conversation_id)
    if model:
        model = validate_model_name(model)

    settings = frappe.get_single("Niv Settings")

    # Validate
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    # Check billing
    if settings.enable_billing:
        from niv_ai.niv_billing.api.billing import check_balance
        bal = check_balance(user)
        if bal.get("balance", 0) <= 0:
            pool_msg = "Company credit pool exhausted. Contact admin." if bal.get("mode") == "shared_pool" else "Insufficient credits. Please recharge."
            frappe.throw(pool_msg)
        # Check daily limit for shared pool
        if bal.get("mode") == "shared_pool" and bal.get("daily_limit") and bal.get("daily_used", 0) >= bal["daily_limit"]:
            frappe.throw(f"Daily limit reached ({bal['daily_used']}/{bal['daily_limit']} tokens). Try again tomorrow.")

    provider = _get_provider(conv.provider or settings.default_provider)
    active_model = model or conv.model or settings.default_model or provider.default_model

    # Save user message
    user_msg = frappe.get_doc({
        "doctype": "Niv Message",
        "conversation": conversation_id,
        "role": "user",
        "content": message,
    })
    user_msg.insert(ignore_permissions=True)
    frappe.db.commit()

    # Build messages
    from niv_ai.niv_core.api.chat import _build_messages
    messages = _build_messages(conv, settings, message, context=context)

    # Get tools
    tools_payload = None
    if settings.enable_tools:
        from niv_ai.niv_tools.api.tool_executor import get_available_tools, tools_to_openai_format
        available_tools = get_available_tools(user)
        if available_tools:
            tools_payload = tools_to_openai_format(available_tools)

    # Stream response
    def sse_event(data_dict, **kwargs):
        """Format and encode an SSE event as bytes."""
        return f"data: {json.dumps(data_dict, **kwargs)}\n\n".encode("utf-8")

    def generate():
        tool_calls_log = []
        tool_results_log = []
        full_content = ""
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        nonlocal messages

        max_iterations = 10
        for iteration in range(max_iterations):
            payload = {
                "model": active_model,
                "messages": messages,
                "max_tokens": settings.max_tokens_per_message or 4096,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tools_payload and iteration < max_iterations - 1:
                payload["tools"] = tools_payload

            headers = {
                "Authorization": f"Bearer {provider.get_password('api_key')}",
                "Content-Type": "application/json",
            }
            if provider.headers_json:
                try:
                    headers.update(json.loads(provider.headers_json))
                except json.JSONDecodeError:
                    pass

            try:
                timeout_config = get_timeout_settings()
                resp = requests.post(
                    f"{provider.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=timeout_config["api_timeout"],
                )
            except Exception as e:
                yield sse_event({'type': 'error', 'message': str(e)})
                return

            if resp.status_code != 200:
                if resp.status_code == 429:
                    retry_after = resp.headers.get('retry-after', '30')
                    yield sse_event({'type': 'error', 'message': f'⏳ AI service is busy. Please wait {retry_after} seconds and try again.'})
                elif resp.status_code == 401:
                    yield sse_event({'type': 'error', 'message': '🔑 API key is invalid or expired. Contact admin.'})
                elif resp.status_code == 503:
                    yield sse_event({'type': 'error', 'message': '🔧 AI service is temporarily unavailable. Try again shortly.'})
                else:
                    try:
                        err_body = resp.json()
                        err_msg = err_body.get('error', {}).get('message', resp.text[:200])
                    except Exception:
                        err_msg = resp.text[:200]
                    yield sse_event({'type': 'error', 'message': f'AI error ({resp.status_code}): {err_msg}'})
                return

            # Parse SSE stream
            collected_tool_calls = {}
            iteration_content = ""

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                delta = chunk.get("choices", [{}])[0].get("delta", {})

                # Content tokens
                if delta.get("content"):
                    token = delta["content"]
                    iteration_content += token
                    yield sse_event({'type': 'token', 'content': token})

                # Tool calls (streamed)
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": tc.get("id", ""),
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.get("id"):
                            collected_tool_calls[idx]["id"] = tc["id"]
                        func = tc.get("function", {})
                        if func.get("name"):
                            collected_tool_calls[idx]["function"]["name"] = func["name"]
                        if func.get("arguments"):
                            collected_tool_calls[idx]["function"]["arguments"] += func["arguments"]

                # Usage in final chunk
                if chunk.get("usage"):
                    u = chunk["usage"]
                    total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                    total_usage["completion_tokens"] += u.get("completion_tokens", 0)
                    total_usage["total_tokens"] += u.get("total_tokens", 0)

            full_content += iteration_content

            # If API didn't return usage, estimate with tiktoken
            if total_usage["total_tokens"] == 0 and full_content:
                try:
                    import tiktoken
                    enc = tiktoken.get_encoding("cl100k_base")
                    prompt_text = json.dumps(messages)
                    total_usage["prompt_tokens"] = len(enc.encode(prompt_text))
                    total_usage["completion_tokens"] = len(enc.encode(full_content))
                    total_usage["total_tokens"] = total_usage["prompt_tokens"] + total_usage["completion_tokens"]
                except Exception:
                    # Rough estimate: 1 token per 4 chars
                    total_usage["prompt_tokens"] = len(json.dumps(messages)) // 4
                    total_usage["completion_tokens"] = len(full_content) // 4
                    total_usage["total_tokens"] = total_usage["prompt_tokens"] + total_usage["completion_tokens"]

            # Handle tool calls
            if collected_tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": iteration_content or None,
                    "tool_calls": list(collected_tool_calls.values()),
                }
                messages.append(assistant_msg)

                from niv_ai.niv_tools.api.tool_executor import execute_tool
                for tc in collected_tool_calls.values():
                    func_name = tc["function"]["name"]
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        func_args = {}

                    yield sse_event({'type': 'tool_call', 'tool': func_name, 'params': func_args})

                    tool_calls_log.append({"id": tc["id"], "name": func_name, "arguments": func_args})

                    try:
                        result = execute_tool(func_name, func_args, user, conversation_id)
                    except Exception as e:
                        result = {"error": str(e)}

                    tool_results_log.append({"tool_call_id": tc["id"], "name": func_name, "result": result})
                    yield sse_event({'type': 'tool_result', 'tool': func_name, 'result': result}, default=str)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, default=str),
                    })

                continue  # Loop back for final response
            else:
                break  # No tool calls, done

        # Save assistant message
        assistant_doc = frappe.get_doc({
            "doctype": "Niv Message",
            "conversation": conversation_id,
            "role": "assistant",
            "content": full_content,
            "model": active_model,
            "input_tokens": total_usage["prompt_tokens"],
            "output_tokens": total_usage["completion_tokens"],
            "total_tokens": total_usage["total_tokens"],
            "tool_calls_json": json.dumps(tool_calls_log, cls=DateTimeEncoder) if tool_calls_log else None,
            "tool_results_json": json.dumps(tool_results_log, cls=DateTimeEncoder) if tool_results_log else None,
        })
        assistant_doc.insert(ignore_permissions=True)

        # Auto title
        if conv.message_count <= 1 and conv.title == "New Chat":
            title = message[:50].strip() + ("..." if len(message) > 50 else "")
            frappe.db.set_value("Niv Conversation", conversation_id, "title", title)

        # Billing
        remaining_balance = None
        if settings.enable_billing:
            from niv_ai.niv_billing.api.billing import deduct_tokens
            result = deduct_tokens(user, total_usage["prompt_tokens"], total_usage["completion_tokens"],
                         conversation_id, assistant_doc.name, active_model)
            remaining_balance = result.get("remaining_balance") if isinstance(result, dict) else None

        frappe.db.commit()

        done_data = {'type': 'done', 'message_id': assistant_doc.name, 'tokens': total_usage}
        if remaining_balance is not None:
            done_data['remaining_balance'] = remaining_balance
        yield sse_event(done_data)

        # Generate follow-up suggestions
        try:
            suggestion_payload = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": "Based on the assistant's last response, suggest exactly 3 short follow-up questions the user might ask. Return ONLY a JSON array of 3 strings, no other text."},
                    {"role": "user", "content": full_content[:1000]},
                ],
                "max_tokens": 200,
                "temperature": 0.7,
            }
            suggestion_resp = requests.post(
                f"{provider.base_url}/chat/completions",
                headers=headers,
                json=suggestion_payload,
                timeout=15,
            )
            if suggestion_resp.status_code == 200:
                sr = suggestion_resp.json()
                suggestion_text = sr.get("choices", [{}])[0].get("message", {}).get("content", "")
                # Extract JSON array from response
                import re
                match = re.search(r'\[.*\]', suggestion_text, re.DOTALL)
                if match:
                    suggestions = json.loads(match.group())
                    if isinstance(suggestions, list) and len(suggestions) > 0:
                        yield sse_event({'type': 'suggestions', 'items': suggestions[:3]})
        except Exception:
            pass  # Suggestions are optional, don't fail the stream

    # Return Werkzeug Response directly — Frappe handler.py checks isinstance(data, Response)
    from werkzeug.wrappers import Response
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
        direct_passthrough=True,
    )


def _get_provider(provider_name):
    if not provider_name:
        frappe.throw("No AI provider configured.")
    return frappe.get_doc("Niv AI Provider", provider_name)
