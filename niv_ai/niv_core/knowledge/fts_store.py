"""
SQLite FTS5 Knowledge Store — Fast, local, zero API dependency.

Replaces FAISS embedding approach for dev knowledge retrieval.
No external API calls, no timeouts, instant indexing.

Inspired by HUF's SQLite FTS approach.

Usage:
    # Index all dev knowledge
    bench --site frontend execute niv_ai.niv_core.knowledge.fts_store.index_all

    # Search
    bench --site frontend execute niv_ai.niv_core.knowledge.fts_store.search --kwargs "{'query': 'Custom Field'}"

    # Get RAG context for agent
    from niv_ai.niv_core.knowledge.fts_store import get_fts_context
    context = get_fts_context("how to create Custom Field")
"""
from __future__ import unicode_literals
import os
import re
import sqlite3
import frappe
from typing import List, Dict, Optional


def _get_db_path():
    """SQLite FTS database path under site private files."""
    db_dir = os.path.join(frappe.get_site_path(), "private", "niv_ai")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "knowledge.db")


def _get_conn():
    """Get SQLite connection with FTS5 table ready."""
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
            title,
            content,
            source,
            tokenize='porter unicode61'
        )
    """)
    # Metadata table for tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_meta (
            source TEXT PRIMARY KEY,
            chunk_count INTEGER,
            indexed_at TEXT
        )
    """)
    conn.commit()
    return conn


def clear_source(source):
    """Delete all chunks from a source."""
    conn = _get_conn()
    conn.execute("DELETE FROM knowledge_fts WHERE source = ?", (source,))
    conn.execute("DELETE FROM knowledge_meta WHERE source = ?", (source,))
    conn.commit()
    conn.close()


def add_chunks(chunks, source):
    """Add knowledge chunks to FTS index.

    Args:
        chunks: list of dicts with 'title' and 'content' keys
        source: source identifier string
    Returns:
        count of chunks added
    """
    conn = _get_conn()

    # Clear existing chunks for this source
    conn.execute("DELETE FROM knowledge_fts WHERE source = ?", (source,))

    for chunk in chunks:
        conn.execute(
            "INSERT INTO knowledge_fts (title, content, source) VALUES (?, ?, ?)",
            (chunk.get("title", ""), chunk["content"], source)
        )

    conn.execute(
        "INSERT OR REPLACE INTO knowledge_meta (source, chunk_count, indexed_at) VALUES (?, ?, datetime('now'))",
        (source, len(chunks))
    )
    conn.commit()
    conn.close()
    return len(chunks)


def search(query, limit=5):
    """FTS5 search with BM25 ranking.

    Args:
        query: search query string
        limit: max results (default 5)
    Returns:
        list of dicts with title, content, source, rank
    """
    conn = _get_conn()

    # Sanitize query for FTS5 — remove special chars, keep words
    words = re.findall(r'\w+', query)
    if not words:
        conn.close()
        return []

    # Use OR matching for broader results, FTS5 handles ranking via BM25
    fts_query = " OR ".join(words)

    try:
        rows = conn.execute("""
            SELECT title, content, source, rank
            FROM knowledge_fts
            WHERE knowledge_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit)).fetchall()
    except sqlite3.OperationalError:
        # Fallback: try simpler query
        fts_query = " ".join(words)
        try:
            rows = conn.execute("""
                SELECT title, content, source, rank
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit)).fetchall()
        except sqlite3.OperationalError:
            conn.close()
            return []

    conn.close()

    results = []
    for title, content, source, rank in rows:
        results.append({
            "title": title,
            "content": content,
            "source": source,
            "rank": round(float(rank), 4)
        })
    return results


def get_fts_context(query, k=3):
    """Get RAG context from FTS for agent prompt injection.

    Returns formatted string or empty string if nothing found.
    """
    try:
        results = search(query, limit=k)
        if not results:
            return ""

        parts = ["Relevant developer knowledge:"]
        for i, r in enumerate(results, 1):
            title = r["title"]
            # Truncate long content to ~800 chars for prompt efficiency
            content = r["content"]
            if len(content) > 800:
                content = content[:800] + "..."
            prefix = "[{}]".format(title) if title else ""
            parts.append("{}. {} {}".format(i, prefix, content))
        return "\n".join(parts)
    except Exception as e:
        print("[Niv FTS] Context retrieval failed: {}".format(e))
        return ""


def get_stats():
    """Get indexing statistics."""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0]
    sources = conn.execute(
        "SELECT source, chunk_count, indexed_at FROM knowledge_meta ORDER BY indexed_at DESC"
    ).fetchall()
    conn.close()
    return {
        "total_chunks": total,
        "sources": [
            {"source": s[0], "chunks": s[1], "indexed_at": s[2]}
            for s in sources
        ]
    }


# ─── Indexing Functions ─────────────────────────────────────────────

def _chunk_text(text, chunk_size=1500, overlap=200):
    """Split text into overlapping chunks at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            for sep in [". ", ".\n", "\n\n", "\n", " "]:
                last_sep = text[start:end].rfind(sep)
                if last_sep > chunk_size // 2:
                    end = start + last_sep + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break
    return chunks


def index_markdown_guide():
    """Index the comprehensive Frappe developer guide markdown."""
    guide_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "frappe_developer_guide.md"
    )
    if not os.path.exists(guide_path):
        print("[Niv FTS] frappe_developer_guide.md not found at {}".format(guide_path))
        return 0

    with open(guide_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by ## headings
    sections = re.split(r'\n(?=## )', content)

    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 50:
            continue
        first_line = section.split('\n', 1)[0].strip('#').strip()
        text_chunks = _chunk_text(section)
        for chunk in text_chunks:
            chunks.append({"title": first_line, "content": chunk})

    count = add_chunks(chunks, "dev_markdown_guide")
    print("[Niv FTS] dev_markdown_guide: {} chunks".format(count))
    return count


def index_quick_reference():
    """Index the dev quick reference (condensed create_document formats)."""
    try:
        from niv_ai.niv_core.knowledge.dev_quick_reference import DEV_QUICK_REFERENCE
    except ImportError:
        print("[Niv FTS] dev_quick_reference.py not found, skipping")
        return 0

    # Split by sections (--- or ### headings)
    sections = re.split(r'\n(?=### |---)', DEV_QUICK_REFERENCE)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 30:
            continue
        first_line = section.split('\n', 1)[0].strip('#').strip('-').strip()
        chunks.append({"title": first_line or "Quick Reference", "content": section})

    count = add_chunks(chunks, "dev_quick_reference")
    print("[Niv FTS] dev_quick_reference: {} chunks".format(count))
    return count


def index_dev_knowledge():
    """Index dev knowledge from dev_knowledge.py by intercepting _index_chunks.

    Uses import-time monkey-patch to capture knowledge without triggering FAISS.
    """
    import importlib
    import niv_ai.niv_core.langchain.dev_knowledge as dk_module

    # Monkey-patch _index_chunks to capture instead of indexing to FAISS
    all_captured = {}

    original_index = dk_module._index_chunks

    def capture_index(knowledge, source):
        all_captured[source] = [{"title": k["title"], "content": k["content"]} for k in knowledge]
        return len(knowledge)

    dk_module._index_chunks = capture_index

    # List of functions to call (skip index_markdown_guide — we do that separately)
    func_names = [
        "index_field_types", "index_doctype_creation", "index_client_script",
        "index_server_script", "index_custom_field", "index_property_setter",
        "index_workflow", "index_print_format", "index_permissions",
        "index_api_patterns", "index_naming", "index_child_table",
        "index_report", "index_hooks", "index_jinja", "index_best_practices",
        "index_fac_tool_formats", "index_dev_dashboard",
        "index_phase_a_recipes", "index_phase_b_recipes",
        "index_phase_c_recipes", "index_phase_def_recipes",
        "index_phase_ijkl_recipes",
    ]

    for func_name in func_names:
        func = getattr(dk_module, func_name, None)
        if not func:
            continue
        try:
            func()
        except Exception as e:
            print("[Niv FTS] Error in {}: {}".format(func_name, e))

    # Restore original
    dk_module._index_chunks = original_index

    # Now index all captured chunks into SQLite FTS
    total = 0
    for source, chunks in all_captured.items():
        count = add_chunks(chunks, source)
        total += count
        print("[Niv FTS] {}: {} chunks".format(source, count))

    return total


def index_all(force=False):
    """Index ALL developer knowledge into SQLite FTS.

    This replaces the FAISS indexing which times out on Mistral API.
    """
    if force:
        # Clear everything
        conn = _get_conn()
        conn.execute("DELETE FROM knowledge_fts")
        conn.execute("DELETE FROM knowledge_meta")
        conn.commit()
        conn.close()
        print("[Niv FTS] Cleared all existing knowledge")

    stats = {}

    # 1. Index dev knowledge (from existing dev_knowledge.py functions)
    stats["dev_knowledge"] = index_dev_knowledge()

    # 2. Index markdown guide
    stats["markdown_guide"] = index_markdown_guide()

    # 3. Index quick reference
    stats["quick_reference"] = index_quick_reference()

    total = sum(stats.values())
    print("\n[Niv FTS] === COMPLETE === Total: {} chunks indexed".format(total))
    for key, count in stats.items():
        print("  {}: {}".format(key, count))

    return stats


# ─── Frappe API ─────────────────────────────────────────────────────

@frappe.whitelist()
def search_fts(query, k=5):
    """Search FTS knowledge base (whitelisted API)."""
    return {"results": search(query, limit=min(int(k), 20))}


@frappe.whitelist()
def fts_stats():
    """Get FTS index statistics (whitelisted API)."""
    return get_stats()
