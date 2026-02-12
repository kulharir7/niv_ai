import frappe
from niv_ai.niv_core.langchain.rag import add_documents, delete_by_source
import niv_ai.niv_core.langchain.dev_knowledge as dk

# Delete old DEF chunks first, then re-add with fixed recipes
# Use targeted delete + add to avoid full reindex token limit
original = dk._index_chunks

def _index_targeted(knowledge, source):
    """Delete specific source then add new chunks."""
    try:
        delete_by_source(source)
        print(f"[DEV RAG] Deleted old {source}")
    except Exception as e:
        print(f"[DEV RAG] Delete failed for {source}: {e}, adding anyway")
    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": source, "title": k["title"]} for k in knowledge]
    count = add_documents(texts, metadatas)
    print(f"[DEV RAG] {source}: {count} chunks re-indexed")
    return count

dk._index_chunks = _index_targeted
c1 = dk.index_phase_def_recipes()
c2 = dk.index_phase_ijkl_recipes()
dk._index_chunks = original
print(f"Total: {c1 + c2}")
