import frappe


def _as_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _ensure_access(doc):
    user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return
    if doc.owner_user and doc.owner_user != user:
        frappe.throw("Not allowed", frappe.PermissionError)


@frappe.whitelist(allow_guest=False)
def create_artifact(title, artifact_type="App", source_prompt=None, artifact_content=None, preview_html=None):
    """Create a new artifact and initial version snapshot."""
    if not title:
        frappe.throw("Title is required")

    user = frappe.session.user
    content = artifact_content or "{}"

    doc = frappe.get_doc({
        "doctype": "Niv Artifact",
        "artifact_title": title,
        "artifact_type": artifact_type or "App",
        "status": "Draft",
        "owner_user": user,
        "source_prompt": source_prompt or "",
        "artifact_content": content,
        "preview_html": preview_html or "",
        "version_count": 1,
        "last_generated_on": frappe.utils.now_datetime(),
    })
    doc.insert(ignore_permissions=True)

    _create_version_row(doc.name, 1, "Initial version", content, user)
    frappe.db.commit()

    return {
        "name": doc.name,
        "title": doc.artifact_title,
        "artifact_type": doc.artifact_type,
        "status": doc.status,
        "version_count": doc.version_count,
    }


@frappe.whitelist(allow_guest=False)
def list_artifacts(limit=20, offset=0, status=None):
    """List artifacts visible to current user."""
    user = frappe.session.user
    filters = {}
    if status:
        filters["status"] = status

    if user != "Administrator" and "System Manager" not in frappe.get_roles(user):
        filters["owner_user"] = user

    rows = frappe.get_all(
        "Niv Artifact",
        filters=filters,
        fields=[
            "name",
            "artifact_title",
            "artifact_type",
            "status",
            "owner_user",
            "version_count",
            "is_published",
            "modified",
            "last_generated_on",
        ],
        order_by="modified desc",
        limit_start=_as_int(offset, 0),
        limit_page_length=_as_int(limit, 20),
    )
    return rows


@frappe.whitelist(allow_guest=False)
def get_artifact(artifact_id, with_versions=1):
    """Get artifact details with optional version history."""
    doc = frappe.get_doc("Niv Artifact", artifact_id)
    _ensure_access(doc)

    out = {
        "name": doc.name,
        "artifact_title": doc.artifact_title,
        "artifact_type": doc.artifact_type,
        "status": doc.status,
        "owner_user": doc.owner_user,
        "source_prompt": doc.source_prompt,
        "artifact_content": doc.artifact_content,
        "preview_html": doc.preview_html,
        "version_count": doc.version_count,
        "is_published": doc.is_published,
        "last_generated_on": doc.last_generated_on,
        "modified": doc.modified,
    }

    if _as_int(with_versions, 1):
        out["versions"] = frappe.get_all(
            "Niv Artifact Version",
            filters={"artifact": doc.name},
            fields=["name", "version_no", "change_summary", "created_by_user", "creation"],
            order_by="version_no desc",
            limit_page_length=20,
        )

    return out


@frappe.whitelist(allow_guest=False)
def update_artifact_content(artifact_id, artifact_content=None, preview_html=None, change_summary=None):
    """Update artifact content and auto-create a new version row."""
    doc = frappe.get_doc("Niv Artifact", artifact_id)
    _ensure_access(doc)

    next_version = _as_int(doc.version_count, 1) + 1
    user = frappe.session.user

    content = artifact_content or doc.artifact_content or "{}"
    doc.artifact_content = content
    if preview_html is not None:
        doc.preview_html = preview_html
    doc.version_count = next_version
    doc.last_generated_on = frappe.utils.now_datetime()
    if doc.status == "Draft":
        doc.status = "Ready"
    doc.save(ignore_permissions=True)

    _create_version_row(
        doc.name,
        next_version,
        change_summary or "Updated artifact",
        doc.artifact_content,
        user,
    )
    frappe.db.commit()

    return {"status": "ok", "name": doc.name, "version_count": next_version}


@frappe.whitelist(allow_guest=False)
def set_artifact_publish_state(artifact_id, is_published=1):
    """Publish/unpublish artifact."""
    doc = frappe.get_doc("Niv Artifact", artifact_id)
    _ensure_access(doc)

    publish_val = 1 if _as_int(is_published, 0) else 0
    doc.is_published = publish_val
    if publish_val:
        doc.status = "Published"
    elif doc.status == "Published":
        doc.status = "Ready"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ok", "is_published": publish_val, "artifact_status": doc.status}


@frappe.whitelist(allow_guest=False)
def get_artifact_version(version_id):
    """Get full snapshot of one artifact version."""
    row = frappe.get_doc("Niv Artifact Version", version_id)
    parent = frappe.get_doc("Niv Artifact", row.artifact)
    _ensure_access(parent)

    return {
        "name": row.name,
        "artifact": row.artifact,
        "version_no": row.version_no,
        "change_summary": row.change_summary,
        "content_snapshot": row.content_snapshot,
        "created_by_user": row.created_by_user,
        "creation": row.creation,
    }


def _create_version_row(artifact, version_no, summary, content_snapshot, user):
    row = frappe.get_doc({
        "doctype": "Niv Artifact Version",
        "artifact": artifact,
        "version_no": _as_int(version_no, 1),
        "change_summary": summary or "",
        "content_snapshot": content_snapshot or "{}",
        "created_by_user": user,
    })
    row.insert(ignore_permissions=True)
    return row
