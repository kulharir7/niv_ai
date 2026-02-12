import frappe
import json
import re


@frappe.whitelist(allow_guest=False)
def search_knowledge(query, limit=5):
    """
    Simple keyword search across KB chunks using SQL LIKE with relevance scoring.
    Returns the most relevant chunks.
    """
    limit = int(limit)
    if not query or not query.strip():
        return []

    # Split query into keywords
    keywords = [k.strip().lower() for k in query.split() if len(k.strip()) >= 2]
    if not keywords:
        return []

    # Build LIKE conditions for each keyword
    conditions = []
    values = {}
    for i, kw in enumerate(keywords):
        conditions.append(f"c.content LIKE %(kw_{i})s")
        values[f"kw_{i}"] = f"%{kw}%"

    where_clause = " OR ".join(conditions)

    # Score = number of keywords matched
    score_parts = []
    for i in range(len(keywords)):
        score_parts.append(f"(CASE WHEN c.content LIKE %(kw_{i})s THEN 1 ELSE 0 END)")
    score_expr = " + ".join(score_parts) if score_parts else "0"

    sql = f"""
        SELECT
            c.name, c.knowledge_base, c.chunk_index, c.content, c.word_count,
            kb.title as kb_title, kb.category,
            ({score_expr}) as relevance_score
        FROM `tabNiv KB Chunk` c
        JOIN `tabNiv Knowledge Base` kb ON kb.name = c.knowledge_base
        WHERE kb.is_active = 1 AND ({where_clause})
        ORDER BY relevance_score DESC, c.chunk_index ASC
        LIMIT {limit}
    """

    results = frappe.db.sql(sql, values, as_dict=True)
    return results


def index_document(kb_name):
    """
    Split a Knowledge Base document into chunks and save as Niv KB Chunk records.
    Deletes existing chunks first (re-index).
    """
    kb = frappe.get_doc("Niv Knowledge Base", kb_name)
    content = kb.content or ""

    # If no content but has source_file, try to extract
    if not content.strip() and kb.source_file:
        content = _extract_file_content(kb.source_file)
        if content:
            frappe.db.set_value("Niv Knowledge Base", kb_name, "content", content)

    if not content.strip():
        return

    # Delete existing chunks
    frappe.db.delete("Niv KB Chunk", {"knowledge_base": kb_name})

    # Split into chunks by word count
    chunk_size = kb.chunk_size or 500
    words = content.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))

    # Save chunks
    for idx, chunk_text in enumerate(chunks):
        doc = frappe.get_doc({
            "doctype": "Niv KB Chunk",
            "knowledge_base": kb_name,
            "chunk_index": idx,
            "content": chunk_text,
            "word_count": len(chunk_text.split()),
        })
        doc.insert(ignore_permissions=True)

    frappe.db.commit()


@frappe.whitelist(allow_guest=False)
def add_document(title, content, category=None):
    """Create a Knowledge Base entry and auto-index it."""
    doc = frappe.get_doc({
        "doctype": "Niv Knowledge Base",
        "title": title,
        "content": content,
        "category": category or "",
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "message": f"Knowledge base '{title}' created and indexed."}


def get_kb_context(query, limit=5):
    """
    Get knowledge base context for the system prompt.
    Returns formatted string of relevant chunks.
    """
    results = search_knowledge(query, limit=limit)
    if not results:
        return ""

    context_parts = []
    for r in results:
        context_parts.append(
            f"[From: {r.get('kb_title', 'Unknown')}]\n{r.get('content', '')}"
        )

    return "\n\n---\n\n".join(context_parts)


def _extract_file_content(file_url):
    """Extract text content from an uploaded file."""
    try:
        file_path = frappe.get_site_path("public", file_url.lstrip("/"))
        ext = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""

        if ext in ("txt", "md", "py", "js", "json", "html", "css", "xml", "yaml", "yml"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:200000]

        elif ext == "pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    return "\n".join(page.extract_text() or "" for page in pdf.pages)
            except ImportError:
                return ""

        elif ext == "docx":
            try:
                from docx import Document
                doc = Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                return ""

        elif ext in ("csv",):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:200000]

    except Exception as e:
        frappe.log_error(f"KB file extraction error: {e}", "Niv Knowledge Base")

    return ""
