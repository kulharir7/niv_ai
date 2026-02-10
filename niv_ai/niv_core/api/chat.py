import frappe
import json
import time
import requests
from datetime import date, datetime

try:
    from niv_ai.niv_core.utils.rate_limiter import check_rate_limit
    from niv_ai.niv_core.utils.validators import sanitize_message, validate_conversation_id, validate_model_name, validate_attachments
    from niv_ai.niv_core.utils.error_handler import handle_errors
    from niv_ai.niv_core.utils.logger import log_api_call, log_ai_request
    from niv_ai.niv_core.utils.retry import request_with_retry, get_timeout_settings
except ImportError:
    check_rate_limit = lambda *a, **kw: None
    sanitize_message = lambda t: t
    validate_conversation_id = lambda c: c
    validate_model_name = lambda m: m
    validate_attachments = lambda a: a
    handle_errors = lambda f: f
    log_api_call = lambda *a, **kw: None
    log_ai_request = lambda *a, **kw: None
    request_with_retry = None
    get_timeout_settings = lambda: {"api_timeout": 60, "max_retries": 3}


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


@frappe.whitelist(allow_guest=False)
def send_message(conversation_id, message, model=None, attachments=None, context=None):
    """
    Main chat endpoint.
    1. Validate user has balance (if billing enabled)
    2. Get conversation context
    3. Build messages array with system prompt
    4. Call AI provider API
    5. If tool calls -> execute tools -> send results back to AI (loop)
    6. Save user message + AI response
    7. Deduct tokens from wallet
    8. Return response
    """
    user = frappe.session.user
    log_api_call("send_message", user, conversation_id=conversation_id)

    # Rate limiting
    check_rate_limit(user)

    # Input validation
    message = sanitize_message(message)
    conversation_id = validate_conversation_id(conversation_id)
    model = validate_model_name(model)
    attachments = validate_attachments(attachments)

    settings = frappe.get_single("Niv Settings")

    # Validate conversation ownership
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
        if bal.get("mode") == "shared_pool" and bal.get("daily_limit") and bal.get("daily_used", 0) >= bal["daily_limit"]:
            frappe.throw(f"Daily limit reached ({bal['daily_used']}/{bal['daily_limit']} tokens). Try again tomorrow.")

    # Determine model
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

    # Handle file attachments
    file_context = ""
    if attachments:
        for att in attachments:
            file_context += _process_attachment(att, conversation_id, user_msg.name)

    # Build messages array
    messages = _build_messages(conv, settings, message, file_context, context=context)

    # Get available tools
    tools_payload = None
    if settings.enable_tools:
        from niv_ai.niv_tools.api.tool_executor import get_available_tools, tools_to_openai_format
        available_tools = get_available_tools(user)
        if available_tools:
            tools_payload = tools_to_openai_format(available_tools)

    # Call AI with tool loop
    start_time = time.time()
    try:
        response_content, tool_calls_log, tool_results_log, usage = _call_ai_with_tools(
            provider, active_model, messages, tools_payload, settings, user, conversation_id
        )
    except Exception as e:
        # Save error message
        error_msg = frappe.get_doc({
            "doctype": "Niv Message",
            "conversation": conversation_id,
            "role": "assistant",
            "content": f"Error: {str(e)}",
            "is_error": 1,
            "error_message": str(e),
        })
        error_msg.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(str(e))

    response_time = int((time.time() - start_time) * 1000)

    # Calculate tokens
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

    # Save assistant message
    assistant_msg = frappe.get_doc({
        "doctype": "Niv Message",
        "conversation": conversation_id,
        "role": "assistant",
        "content": response_content,
        "model": active_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "tool_calls_json": json.dumps(tool_calls_log, cls=DateTimeEncoder) if tool_calls_log else None,
        "tool_results_json": json.dumps(tool_results_log, cls=DateTimeEncoder) if tool_results_log else None,
        "response_time_ms": response_time,
    })
    assistant_msg.insert(ignore_permissions=True)

    # Auto-generate title from first message
    if conv.message_count <= 1 and conv.title == "New Chat":
        title = message[:50].strip()
        if len(message) > 50:
            title += "..."
        frappe.db.set_value("Niv Conversation", conversation_id, "title", title)

    # Deduct tokens if billing enabled
    if settings.enable_billing:
        from niv_ai.niv_billing.api.billing import deduct_tokens
        deduct_tokens(user, input_tokens, output_tokens, conversation_id, assistant_msg.name, active_model)

    frappe.db.commit()

    return {
        "message": response_content,
        "message_id": assistant_msg.name,
        "model": active_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "response_time_ms": response_time,
        "tool_calls": tool_calls_log,
        "tool_results": tool_results_log,
    }


def _get_provider(provider_name):
    """Get provider config"""
    if not provider_name:
        frappe.throw("No AI provider configured. Go to Niv Settings.")
    return frappe.get_doc("Niv AI Provider", provider_name)


def _build_messages(conv, settings, current_message, file_context="", context=None):
    """Build the messages array for AI API call"""
    messages = []

    # System prompt
    system_prompt = conv.system_prompt or settings.system_prompt or ""

    # Append custom instructions
    try:
        from niv_ai.niv_core.api.instructions import get_instructions_for_prompt
        custom_instructions = get_instructions_for_prompt(conv.user or frappe.session.user)
        if custom_instructions:
            system_prompt += custom_instructions
    except Exception:
        pass

    # Context awareness - what page/doc is the user viewing
    if context:
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except (json.JSONDecodeError, TypeError):
                context = None

    if context:
        ctx_doctype = context.get("doctype")
        ctx_docname = context.get("docname")
        ctx_route = context.get("route", [])

        if ctx_doctype and ctx_docname:
            context_str = f"\n\nUser is currently viewing {ctx_doctype} '{ctx_docname}'. They might ask questions about this document."
            try:
                doc = frappe.get_doc(ctx_doctype, ctx_docname)
                meta = frappe.get_meta(ctx_doctype)
                key_fields = {}
                for f in meta.fields:
                    if f.fieldtype in ("Data", "Link", "Select", "Currency", "Float", "Int", "Date", "Datetime") and not f.hidden:
                        val = doc.get(f.fieldname)
                        if val is not None and val != "" and val != 0:
                            key_fields[f.label or f.fieldname] = val
                            if len(key_fields) >= 15:
                                break
                if key_fields:
                    context_str += f"\n\nKey fields of {ctx_doctype} '{ctx_docname}':\n"
                    for k, v in key_fields.items():
                        context_str += f"- {k}: {v}\n"
            except Exception:
                pass
            system_prompt += context_str
        elif ctx_route:
            system_prompt += f"\n\nUser is currently on page: {'/'.join(str(r) for r in ctx_route)}"

    # Knowledge Base RAG: prepend relevant context to system prompt
    if getattr(settings, "enable_knowledge_base", False) and current_message:
        try:
            from niv_ai.niv_core.api.knowledge import get_kb_context
            kb_context = get_kb_context(current_message, limit=5)
            if kb_context:
                system_prompt = (
                    system_prompt
                    + "\n\n--- Knowledge Base Context ---\n"
                    + "Use the following reference information to help answer the user's question:\n\n"
                    + kb_context
                    + "\n--- End Knowledge Base Context ---"
                )
        except Exception:
            pass  # Don't fail chat if KB search fails

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Get conversation history
    max_messages = settings.max_messages_per_conversation or 50
    history = frappe.get_all(
        "Niv Message",
        filters={"conversation": conv.name},
        fields=["role", "content", "tool_calls_json", "tool_results_json"],
        order_by="creation ASC",
        limit_page_length=max_messages,
    )

    for msg in history:
        entry = {"role": msg.role, "content": msg.content or ""}
        messages.append(entry)

    # Current message with file context
    content = current_message
    if file_context:
        content = f"{current_message}\n\n[Attached file content]:\n{file_context}"

    # The current user message is already saved, so it will be in history
    # But we just inserted it, so it should be the last one
    # No need to append again if history already includes it

    return messages


def _call_ai_with_tools(provider, model, messages, tools, settings, user, conversation_id):
    """Call AI API with tool calling loop"""
    tool_calls_log = []
    tool_results_log = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    max_iterations = 10  # Prevent infinite tool loops

    for iteration in range(max_iterations):
        # Build request
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": settings.max_tokens_per_message or 4096,
        }
        if tools and iteration < max_iterations - 1:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {provider.get_password('api_key')}",
            "Content-Type": "application/json",
        }

        # Parse extra headers
        if provider.headers_json:
            try:
                extra = json.loads(provider.headers_json)
                headers.update(extra)
            except json.JSONDecodeError:
                pass

        # Make API call with retry
        timeout_config = get_timeout_settings()
        response = request_with_retry(
            "post",
            f"{provider.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_config["api_timeout"],
        )

        if response.status_code != 200:
            if response.status_code == 429:
                retry_after = response.headers.get('retry-after', '30')
                frappe.throw(f"⏳ AI service is busy. Please wait {retry_after} seconds and try again.")
            elif response.status_code == 401:
                frappe.throw("🔑 API key is invalid or expired. Contact admin.")
            elif response.status_code == 503:
                frappe.throw("🔧 AI service is temporarily unavailable. Try again shortly.")
            else:
                try:
                    err_body = response.json()
                    error_detail = err_body.get('error', {}).get('message', response.text[:300])
                except Exception:
                    error_detail = response.text[:300]
                frappe.throw(f"AI error ({response.status_code}): {error_detail}")

        result = response.json()

        # Accumulate usage
        usage = result.get("usage", {})
        total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += usage.get("total_tokens", 0)

        choice = result["choices"][0]
        assistant_message = choice["message"]

        # Check for tool calls
        if assistant_message.get("tool_calls"):
            # Add assistant message with tool calls to conversation
            messages.append(assistant_message)

            # Execute each tool call
            from niv_ai.niv_tools.api.tool_executor import execute_tool
            for tc in assistant_message["tool_calls"]:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}

                tool_calls_log.append({
                    "id": tc["id"],
                    "name": func_name,
                    "arguments": func_args,
                })

                # Execute tool
                try:
                    tool_result = execute_tool(func_name, func_args, user, conversation_id)
                    result_str = json.dumps(tool_result, default=str)
                except Exception as e:
                    tool_result = {"error": str(e)}
                    result_str = json.dumps(tool_result)

                tool_results_log.append({
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "result": tool_result,
                })

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })

            # Continue loop to get AI's final response
            continue

        # No tool calls — we have the final response
        log_ai_request(provider.name, model, tokens=total_usage.get("total_tokens"))
        return (
            assistant_message.get("content", ""),
            tool_calls_log if tool_calls_log else None,
            tool_results_log if tool_results_log else None,
            total_usage,
        )

    # If we exhausted iterations
    return (
        "I apologize, but I hit the maximum number of tool call iterations. Please try rephrasing your request.",
        tool_calls_log if tool_calls_log else None,
        tool_results_log if tool_results_log else None,
        total_usage,
    )


def _process_attachment(attachment, conversation_id, message_name):
    """Process a file attachment and extract text"""
    file_url = attachment.get("file_url", "")
    if not file_url:
        return ""

    try:
        file_path = frappe.get_site_path("public", file_url.lstrip("/"))
        ext = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""

        extracted = ""
        file_type = "other"

        if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
            file_type = "image"
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(file_path)
                extracted = pytesseract.image_to_string(img, lang="eng+hin")
            except ImportError:
                extracted = "[Image uploaded - OCR not available. Install pytesseract.]"

        elif ext == "pdf":
            file_type = "pdf"
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    extracted = "\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
                if not extracted.strip():
                    # Try OCR for scanned PDFs
                    try:
                        import pytesseract
                        from PIL import Image
                        import tempfile
                        # Would need pdf2image here for full OCR
                        extracted = "[Scanned PDF - text extraction failed]"
                    except ImportError:
                        extracted = "[Scanned PDF - OCR not available]"
            except ImportError:
                extracted = "[PDF uploaded - pdfplumber not available]"

        elif ext in ("xlsx", "xls", "csv"):
            file_type = "excel"
            try:
                import pandas as pd
                if ext == "csv":
                    df = pd.read_csv(file_path)
                else:
                    df = pd.read_excel(file_path)
                extracted = df.to_markdown(index=False)
            except ImportError:
                extracted = "[Spreadsheet uploaded - pandas not available]"

        elif ext in ("docx",):
            file_type = "word"
            try:
                from docx import Document
                doc = Document(file_path)
                extracted = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                extracted = "[Word doc uploaded - python-docx not available]"

        elif ext in ("txt", "md", "py", "js", "json", "html", "css", "xml", "yaml", "yml", "sh", "bat"):
            file_type = "text"
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                extracted = f.read()[:50000]  # Limit to 50K chars

        # Save Niv File record
        niv_file = frappe.get_doc({
            "doctype": "Niv File",
            "conversation": conversation_id,
            "message": message_name,
            "file": file_url,
            "file_type": file_type,
            "extracted_text": extracted[:65000] if extracted else "",
        })
        niv_file.insert(ignore_permissions=True)

        return extracted

    except Exception as e:
        frappe.log_error(f"File processing error: {str(e)}", "Niv AI File Processing")
        return f"[Error processing file: {str(e)}]"


@frappe.whitelist(allow_guest=False)
def stop_generation(conversation_id):
    """Cancel ongoing generation - placeholder for future streaming support"""
    # In SSE mode, the client simply closes the connection
    return {"status": "ok"}
