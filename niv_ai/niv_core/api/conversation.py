import frappe
import json

try:
    from niv_ai.niv_core.utils.validators import validate_model_name, validate_title
    from niv_ai.niv_core.utils.error_handler import handle_errors
except ImportError:
    validate_model_name = lambda m: m
    validate_title = lambda t: t
    handle_errors = lambda f: f


@frappe.whitelist(allow_guest=False)
def create_conversation(title=None, system_prompt=None, model=None, provider=None):
    """Create a new chat session"""
    user = frappe.session.user
    settings = frappe.get_single("Niv Settings")

    title = validate_title(title)
    model = validate_model_name(model)

    doc = frappe.get_doc({
        "doctype": "Niv Conversation",
        "user": user,
        "title": title,
        "provider": provider or settings.default_provider,
        "model": model or settings.default_model,
        "system_prompt": system_prompt or settings.system_prompt,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "name": doc.name,
        "title": doc.title,
        "model": doc.model,
        "provider": doc.provider,
    }


@frappe.whitelist(allow_guest=False)
def get_conversations(limit=20, offset=0, archived=False):
    """List user's conversations"""
    user = frappe.session.user
    filters = {"user": user, "is_archived": 1 if archived else 0, "title": ["!=", ""]}

    conversations = frappe.get_all(
        "Niv Conversation",
        filters=filters,
        fields=["name", "title", "model", "message_count", "total_tokens_used",
                "last_message_at", "is_archived", "creation", "modified"],
        order_by="last_message_at DESC, creation DESC",
        limit_start=int(offset),
        limit_page_length=int(limit),
    )

    return conversations


@frappe.whitelist(allow_guest=False)
def get_messages(conversation_id, limit=50, offset=0):
    """Get messages for a conversation"""
    user = frappe.session.user

    # Verify ownership
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    messages = frappe.get_all(
        "Niv Message",
        filters={"conversation": conversation_id},
        fields=["name", "role", "content", "model", "input_tokens", "output_tokens",
                "total_tokens", "tool_calls_json", "tool_results_json",
                "response_time_ms", "is_error", "error_message", "reactions_json", "creation"],
        order_by="creation ASC",
        limit_start=int(offset),
        limit_page_length=int(limit),
    )

    # Parse JSON fields
    for msg in messages:
        if msg.tool_calls_json:
            try:
                msg["tool_calls"] = json.loads(msg.tool_calls_json)
            except json.JSONDecodeError:
                msg["tool_calls"] = None
        else:
            msg["tool_calls"] = None

        if msg.tool_results_json:
            try:
                msg["tool_results"] = json.loads(msg.tool_results_json)
            except json.JSONDecodeError:
                msg["tool_results"] = None
        else:
            msg["tool_results"] = None

    return messages


@frappe.whitelist(allow_guest=False)
def delete_conversation(conversation_id):
    """Delete a conversation and all its messages"""
    user = frappe.session.user
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    # Delete messages
    frappe.db.delete("Niv Message", {"conversation": conversation_id})
    frappe.db.delete("Niv File", {"conversation": conversation_id})
    frappe.db.delete("Niv Tool Log", {"conversation": conversation_id})
    frappe.db.delete("Niv Usage Log", {"conversation": conversation_id})
    frappe.db.delete("Niv Run Log", {"conversation": conversation_id})

    # Delete conversation
    frappe.delete_doc("Niv Conversation", conversation_id, ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok"}


@frappe.whitelist(allow_guest=False)
def rename_conversation(conversation_id, title):
    """Rename a conversation"""
    user = frappe.session.user
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    frappe.db.set_value("Niv Conversation", conversation_id, "title", title)
    frappe.db.commit()
    return {"status": "ok", "title": title}


@frappe.whitelist(allow_guest=False)
def archive_conversation(conversation_id):
    """Archive/unarchive a conversation"""
    user = frappe.session.user
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    new_val = 0 if conv.is_archived else 1
    frappe.db.set_value("Niv Conversation", conversation_id, "is_archived", new_val)
    frappe.db.commit()
    return {"status": "ok", "is_archived": new_val}


@frappe.whitelist(allow_guest=False)
def get_models():
    """Get available AI models from all active providers"""
    providers = frappe.get_all(
        "Niv AI Provider",
        filters={"is_active": 1},
        fields=["name", "provider_name", "models", "default_model"],
    )

    result = []
    for p in providers:
        models = [m.strip() for m in (p.models or "").split(",") if m.strip()]
        for m in models:
            result.append({
                "model": m,
                "provider": p.name,
                "provider_name": p.provider_name,
                "is_default": m == p.default_model,
            })

    return result


@frappe.whitelist(allow_guest=False)
def list_conversations(limit=50, archived=False):
    """Alias for get_conversations (used by chat UI)"""
    return get_conversations(limit=limit, archived=archived)


@frappe.whitelist(allow_guest=False)
def get_widget_config():
    """Get widget configuration for the floating chat button"""
    try:
        settings = frappe.get_single("Niv Settings")
    except Exception:
        return {"enabled": False}

    if not settings.enable_widget:
        return {"enabled": False}

    # Check if current user's role is allowed
    if settings.allowed_roles:
        user_roles = set(frappe.get_roles())
        allowed = set(r.role for r in settings.allowed_roles)
        if not user_roles.intersection(allowed):
            return {"enabled": False}

    return {
        "enabled": True,
        "title": settings.widget_title or "Niv AI",
        "color": settings.widget_color or "#5e64ff",
        "position": settings.widget_position or "bottom-right",
    }


@frappe.whitelist(allow_guest=False)
def toggle_reaction(message_id, emoji):
    """Toggle a reaction emoji on a message. Returns updated reactions dict."""
    user = frappe.session.user
    msg = frappe.get_doc("Niv Message", message_id)

    # Verify ownership of conversation
    conv = frappe.get_doc("Niv Conversation", msg.conversation)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    reactions = {}
    if msg.reactions_json:
        try:
            reactions = json.loads(msg.reactions_json)
        except json.JSONDecodeError:
            reactions = {}

    # reactions format: { "👍": ["user1@x.com", "user2@x.com"], "❤️": ["user1@x.com"] }
    if emoji not in reactions:
        reactions[emoji] = []

    if user in reactions[emoji]:
        reactions[emoji].remove(user)
        if not reactions[emoji]:
            del reactions[emoji]
    else:
        reactions[emoji].append(user)

    frappe.db.set_value("Niv Message", message_id, "reactions_json", json.dumps(reactions))
    frappe.db.commit()

    return {"reactions": reactions}


@frappe.whitelist(allow_guest=False)
def toggle_pin(message_id):
    """Toggle pin status on a message"""
    user = frappe.session.user
    msg = frappe.get_doc("Niv Message", message_id)
    conv = frappe.get_doc("Niv Conversation", msg.conversation)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    new_val = 0 if msg.is_pinned else 1
    frappe.db.set_value("Niv Message", message_id, "is_pinned", new_val)
    frappe.db.commit()
    return {"status": "ok", "is_pinned": new_val}


@frappe.whitelist(allow_guest=False)
def share_conversation(conversation_id):
    """Create a shareable link for a conversation"""
    import hashlib, time as _time
    user = frappe.session.user
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    # Check if already shared
    existing = frappe.db.get_value("Niv Shared Chat",
        {"conversation": conversation_id, "shared_by": user, "is_active": 1},
        ["name", "share_hash"], as_dict=True)
    if existing:
        return {"share_hash": existing.share_hash, "url": f"/app/niv-chat-shared/{existing.share_hash}"}

    share_hash = hashlib.sha256(f"{conversation_id}-{user}-{_time.time()}".encode()).hexdigest()[:16]
    doc = frappe.get_doc({
        "doctype": "Niv Shared Chat",
        "conversation": conversation_id,
        "share_hash": share_hash,
        "shared_by": user,
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"share_hash": share_hash, "url": f"/app/niv-chat-shared/{share_hash}"}


@frappe.whitelist(allow_guest=True)
def get_shared_messages(share_hash):
    """Get messages for a shared chat (no login required)"""
    shared = frappe.db.get_value("Niv Shared Chat",
        {"share_hash": share_hash, "is_active": 1},
        ["conversation", "expires_at"], as_dict=True)
    if not shared:
        frappe.throw("Shared chat not found or expired", frappe.DoesNotExistError)

    if shared.expires_at and frappe.utils.now_datetime() > frappe.utils.get_datetime(shared.expires_at):
        frappe.throw("This shared chat has expired", frappe.ValidationError)

    conv = frappe.get_doc("Niv Conversation", shared.conversation)
    messages = frappe.get_all(
        "Niv Message",
        filters={"conversation": shared.conversation},
        fields=["name", "role", "content", "creation"],
        order_by="creation ASC",
    )
    return {"title": conv.title, "messages": messages}


@frappe.whitelist(allow_guest=False)
def get_pinned_messages(conversation_id):
    """Get pinned messages for a conversation"""
    user = frappe.session.user
    conv = frappe.get_doc("Niv Conversation", conversation_id)
    if conv.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Not your conversation", frappe.PermissionError)

    messages = frappe.get_all(
        "Niv Message",
        filters={"conversation": conversation_id, "is_pinned": 1},
        fields=["name", "role", "content", "creation"],
        order_by="creation ASC",
    )
    return messages


@frappe.whitelist(allow_guest=False)
def get_system_prompts():
    """Get available system prompts for the user"""
    prompts = frappe.get_all(
        "Niv System Prompt",
        fields=["name", "prompt_name", "prompt", "description", "category", "is_default"],
        order_by="is_default DESC, prompt_name ASC",
    )
    return prompts


@frappe.whitelist(allow_guest=False)
def search_conversations(query, limit=20):
    """Full-text search across conversation messages.
    Returns conversations with matching messages."""
    if not query or len(query.strip()) < 2:
        return []

    user = frappe.session.user
    q = f"%{query.strip()}%"

    results = frappe.db.sql("""
        SELECT DISTINCT c.name, c.title, c.modified,
               SUBSTRING(m.content, 1, 200) as snippet
        FROM `tabNiv Conversation` c
        JOIN `tabNiv Message` m ON m.conversation = c.name
        WHERE c.user = %(user)s
          AND m.content LIKE %(query)s
        ORDER BY c.modified DESC
        LIMIT %(limit)s
    """, {"user": user, "query": q, "limit": int(limit)}, as_dict=True)

    return results
