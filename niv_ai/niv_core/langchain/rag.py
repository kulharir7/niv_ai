"""
RAG (Retrieval-Augmented Generation) — FAISS vectorstore.
No raw SQL, no injection risk. Lazy-loaded.
"""
import os
import json
import frappe
from typing import List, Dict, Optional

# Lazy singletons
_vectorstore = None
_embeddings = None


def _get_embeddings():
    """HuggingFace embeddings — free, local, ~90MB model."""
    global _embeddings
    if _embeddings is None:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


def _get_store_path() -> str:
    """FAISS index path under site private files."""
    store_dir = os.path.join(frappe.get_site_path(), "private", "niv_ai", "faiss_index")
    os.makedirs(store_dir, exist_ok=True)
    return store_dir


def _get_vectorstore():
    """Load or create FAISS vectorstore."""
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    store_path = _get_store_path()
    index_file = os.path.join(store_path, "index.faiss")
    embeddings = _get_embeddings()

    if os.path.exists(index_file):
        _vectorstore = FAISS.load_local(store_path, embeddings, allow_dangerous_deserialization=True)
    else:
        _vectorstore = FAISS.from_documents(
            [Document(page_content="Niv AI knowledge base initialized.", metadata={"source": "init"})],
            embeddings,
        )
        _vectorstore.save_local(store_path)

    return _vectorstore


def _reset_vectorstore():
    """Force reload on next access (after add/delete)."""
    global _vectorstore
    _vectorstore = None


def add_documents(texts: List[str], metadatas: List[dict] = None) -> int:
    """Add documents to knowledge base. Returns count added."""
    from langchain_core.documents import Document

    store = _get_vectorstore()
    docs = []
    for i, text in enumerate(texts):
        meta = metadatas[i] if metadatas and i < len(metadatas) else {}
        docs.append(Document(page_content=text, metadata=meta))

    store.add_documents(docs)
    store.save_local(_get_store_path())
    return len(docs)


def search(query: str, k: int = 5) -> List[Dict]:
    """Similarity search — returns relevant docs with scores."""
    store = _get_vectorstore()
    results = store.similarity_search_with_score(query, k=k)

    docs = []
    for doc, score in results:
        # Skip init placeholder
        if doc.metadata.get("source") == "init":
            continue
        docs.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": round(float(score), 4),
        })
    return docs


def delete_by_source(source: str) -> int:
    """Delete all documents from a source by rebuilding the index."""
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    store = _get_vectorstore()
    all_docs = store.docstore._dict

    # Filter out matching source
    keep_docs = []
    deleted = 0
    for _doc_id, doc in all_docs.items():
        if doc.metadata.get("source") == source:
            deleted += 1
        else:
            keep_docs.append(doc)

    if deleted == 0:
        return 0

    # Rebuild index without deleted docs
    if not keep_docs:
        keep_docs = [Document(page_content="Niv AI knowledge base initialized.", metadata={"source": "init"})]

    embeddings = _get_embeddings()
    new_store = FAISS.from_documents(keep_docs, embeddings)
    new_store.save_local(_get_store_path())
    _reset_vectorstore()

    return deleted


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks. Tries to break at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try to break at sentence boundary
        if end < len(text):
            for sep in [". ", ".\n", "\n\n", "\n", " "]:
                last_sep = text[start:end].rfind(sep)
                if last_sep > chunk_size // 2:
                    end = start + last_sep + len(sep)
                    break

        chunks.append(text[start:end].strip())
        start = end - overlap
        if start >= len(text):
            break

    return [c for c in chunks if c]


# ─── API Endpoints ─────────────────────────────────────────────────

@frappe.whitelist()
def search_knowledge(query, k=5):
    """Search knowledge base."""
    settings = frappe.get_cached_doc("Niv Settings")
    if not settings.enable_knowledge_base:
        return {"results": [], "message": "Knowledge base is disabled"}
    return {"results": search(query, k=min(int(k), 20))}


@frappe.whitelist()
def add_to_knowledge(content, source="manual", title=""):
    """Add content to knowledge base (admin only)."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Manager can add to knowledge base")

    meta = {"source": source, "title": title, "user": frappe.session.user}
    chunks = _chunk_text(content)
    count = add_documents(chunks, [meta] * len(chunks))
    return {"added": count, "chunks": len(chunks)}


@frappe.whitelist()
def delete_from_knowledge(source):
    """Delete all docs from a source (admin only)."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only System Manager can delete from knowledge base")
    deleted = delete_by_source(source)
    return {"deleted": deleted}


def get_rag_context(query: str, k: int = 3) -> str:
    """Get RAG context to inject into agent prompt. Returns empty string if disabled."""
    try:
        settings = frappe.get_cached_doc("Niv Settings")
        if not settings.enable_knowledge_base:
            return ""

        results = search(query, k=k)
        if not results:
            return ""

        parts = ["Relevant knowledge base information:"]
        for i, r in enumerate(results, 1):
            title = r["metadata"].get("title", "")
            prefix = f"[{title}] " if title else ""
            parts.append(f"{i}. {prefix}{r['content']}")
        return "\n".join(parts)
    except Exception:
        return ""
