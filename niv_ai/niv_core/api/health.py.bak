"""
Health Check API — Returns status of LLM, MCP, RAG, and billing systems.
Endpoint: /api/method/niv_ai.niv_core.api.health.check
"""
import frappe
from niv_ai.niv_core.utils import get_niv_settings
from frappe import _


@frappe.whitelist(allow_guest=False)
def check():
    """Health check endpoint. Returns status of all Niv AI subsystems."""
    if not frappe.has_permission("Niv Settings", "read"):
        frappe.throw(_("Insufficient permissions"), frappe.PermissionError)

    result = {
        "status": "ok",
        "subsystems": {},
        "version": _get_version(),
    }

    # 1. LLM Provider
    result["subsystems"]["llm"] = _check_llm()

    # 2. MCP Tools
    result["subsystems"]["mcp"] = _check_mcp()

    # 3. RAG Knowledge Base
    result["subsystems"]["rag"] = _check_rag()

    # 4. Billing
    result["subsystems"]["billing"] = _check_billing()

    # 5. Database
    result["subsystems"]["database"] = _check_database()

    # Overall status
    statuses = [s["status"] for s in result["subsystems"].values()]
    if "error" in statuses:
        result["status"] = "degraded"
    if all(s == "error" for s in statuses):
        result["status"] = "down"

    return result


def _get_version():
    try:
        return frappe.get_attr("niv_ai.__version__", None) or "0.4.0"
    except Exception:
        return "unknown"


def _check_llm():
    try:
        settings = get_niv_settings()
        api_key = settings.get_password("api_key", raise_exception=False)
        model = getattr(settings, "default_model", "") or ""
        base_url = getattr(settings, "api_base_url", "") or ""

        if not api_key:
            return {"status": "error", "message": "No API key configured"}

        return {
            "status": "ok",
            "model": model,
            "provider": base_url.split("/")[2] if base_url and "/" in base_url else "unknown",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_mcp():
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools
        tools = get_all_mcp_tools()
        return {
            "status": "ok",
            "tool_count": len(tools),
            "source": "same-server (FAC)",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_rag():
    try:
        settings = get_niv_settings()
        enabled = getattr(settings, "enable_knowledge_base", 0)
        if not enabled:
            return {"status": "disabled", "message": "Knowledge base disabled in settings"}

        from niv_ai.niv_core.langchain.rag import _get_vectorstore
        store = _get_vectorstore()
        if store is None:
            return {"status": "error", "message": "FAISS index not found"}

        count = store.index.ntotal if hasattr(store, "index") else 0
        return {
            "status": "ok",
            "chunks": count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_billing():
    try:
        settings = get_niv_settings()
        mode = getattr(settings, "billing_mode", "Shared Pool") or "Shared Pool"

        if mode == "Shared Pool":
            balance = frappe.db.get_value("Niv Settings", None, "shared_pool_balance") or 0
            return {
                "status": "ok" if float(balance) > 0 else "warning",
                "mode": mode,
                "balance": float(balance),
            }
        else:
            return {"status": "ok", "mode": mode}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_database():
    try:
        result = frappe.db.sql("SELECT 1")
        conv_count = frappe.db.count("Niv Conversation")
        msg_count = frappe.db.count("Niv Message")
        return {
            "status": "ok",
            "conversations": conv_count,
            "messages": msg_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
