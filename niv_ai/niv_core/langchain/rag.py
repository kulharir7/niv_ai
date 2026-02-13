"""
RAG (Retrieval-Augmented Generation) — FAISS vectorstore.
No raw SQL, no injection risk. Lazy-loaded.

Embeddings: Uses provider API (Mistral/OpenAI) — zero local install.
Fallback: Simple keyword matching if embeddings unavailable.
"""
import os
import json
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from typing import List, Dict, Optional

# Lazy singletons
_vectorstore = None
_embeddings = None


def _get_embeddings():
    """Get embeddings from configured AI provider (Mistral/OpenAI).
    
    Uses the same API key as chat — no extra config needed.
    Falls back to OpenAI-compatible endpoint.
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    settings = get_niv_settings()
    provider = None

    # For embeddings, prefer a provider that supports /v1/embeddings
    # Mistral has mistral-embed; Ollama Cloud does NOT support embeddings
    embedding_provider_name = getattr(settings, "embedding_provider", "") or ""
    if embedding_provider_name:
        try:
            provider = frappe.get_doc("Niv AI Provider", embedding_provider_name)
        except Exception:
            pass

    # Try providers with known embedding support (mistral first)
    if not provider:
        for pname in ["mistral"]:
            try:
                provider = frappe.get_doc("Niv AI Provider", pname)
                break
            except Exception:
                continue

    # Fallback to default provider
    if not provider and settings.default_provider:
        try:
            provider = frappe.get_doc("Niv AI Provider", settings.default_provider)
        except Exception:
            pass

    if not provider:
        frappe.throw("No AI provider configured for embeddings.")

    api_key = provider.get_password("api_key") if provider.api_key else ""
    base_url = (provider.base_url or "").rstrip("/")

    # Use OpenAIEmbeddings for all providers (OpenAI-compatible API)
    # Mistral, OpenAI, Groq — all support /v1/embeddings endpoint
    from langchain_openai import OpenAIEmbeddings

    provider_name_lower = (provider.provider_name or provider.name or "").lower()

    if "mistral" in provider_name_lower or "mistral" in base_url:
        # Mistral uses OpenAI-compatible API at api.mistral.ai/v1
        # check_embedding_ctx_length=False prevents tiktoken tokenization
        # (Mistral expects raw strings, not token IDs)
        _embeddings = OpenAIEmbeddings(
            model="mistral-embed",
            api_key=api_key,
            base_url="https://api.mistral.ai/v1",
            check_embedding_ctx_length=False,
        )
    else:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        _embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            **kwargs,
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


def add_documents(texts: List[str], metadatas: List[dict] = None, batch_size: int = 50) -> int:
    """Add documents to knowledge base in batches. Returns count added."""
    from langchain_core.documents import Document

    store = _get_vectorstore()
    total_added = 0

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        docs = []
        for j, text in enumerate(batch_texts):
            idx = i + j
            meta = metadatas[idx] if metadatas and idx < len(metadatas) else {}
            docs.append(Document(page_content=text, metadata=meta))

        store.add_documents(docs)
        total_added += len(docs)

    store.save_local(_get_store_path())
    return total_added


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
    settings = get_niv_settings()
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
        settings = get_niv_settings()
        if not settings.enable_knowledge_base:
            return ""

        results = search(query, k=k)
        if not results:
            return ""

        parts = ["Relevant context from knowledge base:"]
        for i, r in enumerate(results, 1):
            title = r["metadata"].get("title", "")
            source = r["metadata"].get("source", "")
            prefix = f"[{title}]" if title else f"[{source}]" if source else ""
            parts.append(f"{i}. {prefix} {r['content']}")
        return "\n".join(parts)
    except Exception as e:
        # RAG failure should never block chat
        print(f"[Niv AI RAG] Context retrieval failed: {e}")
        return ""
