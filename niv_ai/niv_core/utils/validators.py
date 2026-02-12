"""
Input validation and sanitization for Niv AI.
"""
import frappe
import re
import json

# Max message length (characters)
MAX_MESSAGE_LENGTH = 10000
MAX_TITLE_LENGTH = 200
MAX_ATTACHMENT_SIZE_MB = 25
ALLOWED_ATTACHMENT_TYPES = {
    "image": {"jpg", "jpeg", "png", "gif", "webp", "bmp"},
    "document": {"pdf", "docx", "doc", "txt", "md", "csv", "xlsx", "xls"},
    "code": {"py", "js", "json", "html", "css", "xml", "yaml", "yml", "sh", "bat"},
}
ALL_ALLOWED_EXTENSIONS = set()
for exts in ALLOWED_ATTACHMENT_TYPES.values():
    ALL_ALLOWED_EXTENSIONS.update(exts)

# Patterns to strip from messages (potential injection attempts)
DANGEROUS_PATTERNS = [
    re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # onclick=, onerror=, etc.
]


def sanitize_message(text):
    """
    Sanitize user message text.
    - Enforce max length
    - Strip dangerous HTML/JS patterns
    - Normalize whitespace
    Returns sanitized text or raises on invalid input.
    """
    if not text or not isinstance(text, str):
        frappe.throw("Message cannot be empty", frappe.ValidationError)

    text = text.strip()
    if not text:
        frappe.throw("Message cannot be empty", frappe.ValidationError)

    if len(text) > MAX_MESSAGE_LENGTH:
        frappe.throw(
            f"Message too long ({len(text)} chars). Maximum is {MAX_MESSAGE_LENGTH} characters.",
            frappe.ValidationError,
        )

    # Strip dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        text = pattern.sub("", text)

    return text


def validate_conversation_id(conv_id):
    """Validate conversation ID format and existence."""
    if not conv_id or not isinstance(conv_id, str):
        frappe.throw("Invalid conversation ID", frappe.ValidationError)

    conv_id = conv_id.strip()

    # Frappe naming: should be alphanumeric with hyphens
    if not re.match(r'^[a-zA-Z0-9\-]+$', conv_id):
        frappe.throw("Invalid conversation ID format", frappe.ValidationError)

    if not frappe.db.exists("Niv Conversation", conv_id):
        frappe.throw("Conversation not found", frappe.DoesNotExistError)

    return conv_id


def validate_model_name(model):
    """Validate model name against allowed models from active providers."""
    if not model:
        return None  # Will use default

    model = str(model).strip()

    # Get all allowed models from active providers
    providers = frappe.get_all(
        "Niv AI Provider",
        filters={"is_active": 1},
        fields=["models"],
    )
    allowed_models = set()
    for p in providers:
        if p.models:
            for m in p.models.split(","):
                m = m.strip()
                if m:
                    allowed_models.add(m)

    if allowed_models and model not in allowed_models:
        frappe.throw(
            f"Model '{model}' is not available. Choose from: {', '.join(sorted(allowed_models))}",
            frappe.ValidationError,
        )

    return model


def validate_attachments(attachments):
    """
    Validate attachment list.
    - Check file extensions
    - Check file size limits
    Returns parsed attachment list.
    """
    if not attachments:
        return []

    if isinstance(attachments, str):
        try:
            attachments = json.loads(attachments)
        except (json.JSONDecodeError, TypeError):
            frappe.throw("Invalid attachments format", frappe.ValidationError)

    if not isinstance(attachments, list):
        frappe.throw("Attachments must be a list", frappe.ValidationError)

    if len(attachments) > 10:
        frappe.throw("Maximum 10 attachments allowed", frappe.ValidationError)

    validated = []
    for att in attachments:
        if not isinstance(att, dict):
            continue

        file_url = att.get("file_url", "")
        if not file_url:
            continue

        # Check extension
        ext = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""
        if ext and ext not in ALL_ALLOWED_EXTENSIONS:
            frappe.throw(
                f"File type '.{ext}' is not allowed. Allowed: {', '.join(sorted(ALL_ALLOWED_EXTENSIONS))}",
                frappe.ValidationError,
            )

        validated.append(att)

    return validated


def validate_title(title):
    """Validate conversation title."""
    if not title:
        return "New Chat"

    title = str(title).strip()
    if len(title) > MAX_TITLE_LENGTH:
        title = title[:MAX_TITLE_LENGTH]

    # Strip HTML
    title = re.sub(r'<[^>]+>', '', title)
    return title


def validate_pagination(limit, offset, max_limit=100):
    """Validate and sanitize pagination parameters."""
    try:
        limit = int(limit or 20)
    except (ValueError, TypeError):
        limit = 20
    try:
        offset = int(offset or 0)
    except (ValueError, TypeError):
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset
