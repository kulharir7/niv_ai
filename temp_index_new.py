import frappe
from niv_ai.niv_core.langchain.rag import add_documents
import niv_ai.niv_core.langchain.dev_knowledge as dk

original = dk._index_chunks

def _index_no_delete(knowledge, source):
    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": source, "title": k["title"]} for k in knowledge]
    count = add_documents(texts, metadatas)
    print(f"[DEV RAG] {source}: {count} chunks")
    return count

dk._index_chunks = _index_no_delete
c1 = dk.index_phase_def_recipes()
c2 = dk.index_phase_ijkl_recipes()
dk._index_chunks = original
print(f"Total: {c1 + c2}")
