"""
Niv AI Form Guide — AI-Powered Message Parser

Takes any error/validation message + current form fields,
asks the AI to understand what happened and which field(s) need attention.

Uses fast model for speed + low cost.
"""
import json
import frappe
from frappe import _


@frappe.whitelist()
def parse_message(message, doctype=None, fields_json=None):
    """
    AI parses an error message and returns which field(s) need attention.

    Args:
        message: The error/validation message text (can contain HTML)
        doctype: Current form's DocType (e.g., "Sales Invoice")
        fields_json: JSON string of form fields [{fieldname, label, fieldtype, reqd}, ...]

    Returns:
        {
            "fields": [
                {"fieldname": "customer", "label": "Customer", "row": null, "table": null, "reason": "Customer is required"},
                {"fieldname": "delivery_date", "label": "Delivery Date", "row": 1, "table": "items", "reason": "Delivery Date missing in Row 1"}
            ],
            "type": "mandatory|validation|permission|link_error|general",
            "user_message": "Customer aur Row 1 mein Delivery Date fill karo",
            "ai_powered": true
        }
    """
    if not message:
        return {"fields": [], "type": "unknown", "user_message": "", "ai_powered": False}

    # Strip HTML for cleaner AI input
    import re
    clean_msg = re.sub(r'<[^>]*>', ' ', message).strip()
    clean_msg = re.sub(r'\s+', ' ', clean_msg)

    # Parse form fields
    form_fields = []
    if fields_json:
        try:
            if isinstance(fields_json, str):
                form_fields = json.loads(fields_json)
            elif isinstance(fields_json, list):
                form_fields = fields_json
        except (json.JSONDecodeError, ValueError):
            pass

    # Build field list for AI context
    field_list = ""
    if form_fields:
        lines = []
        for f in form_fields:
            fname = f.get("fieldname", "")
            flabel = f.get("label", "")
            ftype = f.get("fieldtype", "")
            reqd = f.get("reqd", 0)
            table_name = f.get("parent_table", "")
            if fname and flabel:
                line = f"- {flabel} (fieldname: {fname}, type: {ftype}"
                if reqd:
                    line += ", mandatory"
                if table_name:
                    line += f", in table: {table_name}"
                line += ")"
                lines.append(line)
        field_list = "\n".join(lines)

    # Build AI prompt
    prompt = f"""You are a form error analyzer. Read the error message and identify which form field(s) need attention.

ERROR MESSAGE:
"{clean_msg}"

DOCTYPE: {doctype or "Unknown"}

FORM FIELDS:
{field_list if field_list else "No field list provided"}

RESPOND IN THIS EXACT JSON FORMAT (no markdown, no explanation, just JSON):
{{
    "fields": [
        {{
            "fieldname": "exact_fieldname_from_list",
            "label": "Field Label",
            "row": null,
            "table": null,
            "reason": "Short reason why this field needs attention"
        }}
    ],
    "type": "mandatory",
    "user_message": "Short helpful message for the user in simple language"
}}

RULES:
1. "type" must be one of: mandatory, validation, permission, link_error, general
2. "row" should be a number if the error mentions a specific row (e.g., Row 1, Row #3), otherwise null
3. "table" should be the table fieldname if the error is about a child table field, otherwise null
4. "fieldname" MUST match exactly from the FORM FIELDS list above
5. "user_message" should be helpful and concise — tell user what to do
6. If the message is about permission, return empty fields array with type "permission"
7. Return ONLY valid JSON, nothing else"""

    try:
        # Use fast model for speed + low cost
        from niv_ai.niv_core.utils import get_niv_settings
        settings = get_niv_settings()
        
        provider_name = settings.default_provider
        # Prefer fast model, fallback to default
        model = getattr(settings, "fast_model", None) or settings.default_model

        if not provider_name or not model:
            return _fallback_parse(clean_msg)

        provider = frappe.get_doc("Niv AI Provider", provider_name)
        api_key = provider.get_password("api_key")
        base_url = provider.base_url

        if not api_key:
            return _fallback_parse(clean_msg)

        # Direct API call (no LangChain overhead — fast)
        import requests
        
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 500,
                "temperature": 0.1,  # Low temp = precise
            },
            timeout=30,  # 30 sec — ollama cloud can be slow
        )

        if resp.status_code != 200:
            frappe.log_error(f"Form Guide AI error: {resp.status_code} {resp.text[:200]}", "Niv Form Guide")
            return _fallback_parse(clean_msg)

        result = resp.json()
        ai_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse AI response (handle markdown code blocks)
        ai_text = ai_text.strip()
        if ai_text.startswith("```"):
            # Remove markdown code block
            ai_text = re.sub(r'^```(?:json)?\s*', '', ai_text)
            ai_text = re.sub(r'\s*```\s*$', '', ai_text)

        parsed = json.loads(ai_text)
        parsed["ai_powered"] = True

        # Validate response structure
        if "fields" not in parsed:
            parsed["fields"] = []
        if "type" not in parsed:
            parsed["type"] = "general"
        if "user_message" not in parsed:
            parsed["user_message"] = ""

        return parsed

    except json.JSONDecodeError as e:
        frappe.log_error(f"Form Guide AI JSON parse error: {e}\nAI output: {ai_text[:500]}", "Niv Form Guide")
        return _fallback_parse(clean_msg)
    except requests.exceptions.Timeout:
        # AI took too long — use fallback
        return _fallback_parse(clean_msg)
    except Exception as e:
        frappe.log_error(f"Form Guide AI error: {e}", "Niv Form Guide")
        return _fallback_parse(clean_msg)


def _fallback_parse(message):
    """Simple regex fallback when AI is unavailable."""
    import re
    
    fields = []
    msg_type = "general"
    user_msg = message

    # Try to extract from <li> tags
    li_items = re.findall(r'<li[^>]*>(.*?)</li>', message, re.IGNORECASE)
    if li_items:
        for item in li_items:
            clean = re.sub(r'<[^>]*>', '', item).strip()
            if clean:
                fields.append({
                    "fieldname": clean.lower().replace(" ", "_"),
                    "label": clean,
                    "row": None,
                    "table": None,
                    "reason": f"{clean} is required"
                })
        msg_type = "mandatory"
        user_msg = "Please fill the required fields"

    # Check for mandatory keyword
    if not fields:
        m = re.search(r'(?:mandatory|required)[\s:]+(.+)', message, re.IGNORECASE)
        if m:
            for part in m.group(1).split(","):
                part = re.sub(r'<[^>]*>', '', part).strip()
                if part:
                    fields.append({
                        "fieldname": part.lower().replace(" ", "_"),
                        "label": part,
                        "row": None,
                        "table": None,
                        "reason": f"{part} is required"
                    })
            msg_type = "mandatory"

    # Check for permission
    if re.search(r'not\s+permitted|permission\s+denied|no\s+permission', message, re.IGNORECASE):
        msg_type = "permission"
        user_msg = "You don't have permission for this action"

    return {
        "fields": fields,
        "type": msg_type,
        "user_message": user_msg,
        "ai_powered": False
    }
