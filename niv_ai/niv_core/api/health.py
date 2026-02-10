"""
Health check endpoint for monitoring.
"""
import frappe
import requests
import time


@frappe.whitelist(allow_guest=False)
def health_check():
    """
    Check system health: DB, Redis, AI provider, billing.
    Returns status for each component.
    """
    checks = {}

    # Database
    try:
        frappe.db.sql("SELECT 1")
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)[:100]}

    # Redis
    try:
        cache = frappe.cache()
        cache.set_value("niv_health_check", "ok")
        val = cache.get_value("niv_health_check")
        checks["redis"] = {"status": "ok" if val == "ok" else "degraded"}
    except Exception as e:
        checks["redis"] = {"status": "error", "message": str(e)[:100]}

    # AI Provider
    try:
        settings = frappe.get_single("Niv Settings")
        provider_name = settings.default_provider
        if provider_name:
            provider = frappe.get_doc("Niv AI Provider", provider_name)
            api_key = provider.get_password("api_key")
            if api_key:
                start = time.time()
                resp = requests.get(
                    f"{provider.base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10,
                )
                latency_ms = int((time.time() - start) * 1000)
                checks["ai_provider"] = {
                    "status": "ok" if resp.status_code == 200 else "degraded",
                    "provider": provider_name,
                    "latency_ms": latency_ms,
                    "http_status": resp.status_code,
                }
            else:
                checks["ai_provider"] = {"status": "error", "message": "No API key configured"}
        else:
            checks["ai_provider"] = {"status": "error", "message": "No provider configured"}
    except requests.exceptions.Timeout:
        checks["ai_provider"] = {"status": "degraded", "message": "Timeout"}
    except Exception as e:
        checks["ai_provider"] = {"status": "error", "message": str(e)[:100]}

    # Billing
    try:
        settings = frappe.get_single("Niv Settings")
        if settings.enable_billing:
            if settings.billing_mode == "Shared Pool":
                bal = settings.shared_pool_balance or 0
                checks["billing"] = {
                    "status": "ok" if bal > 0 else "warning",
                    "mode": "shared_pool",
                    "balance": bal,
                }
            else:
                checks["billing"] = {"status": "ok", "mode": "per_user"}
        else:
            checks["billing"] = {"status": "ok", "mode": "disabled"}
    except Exception as e:
        checks["billing"] = {"status": "error", "message": str(e)[:100]}

    # Overall status
    statuses = [c.get("status") for c in checks.values()]
    if "error" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses or "warning" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": frappe.utils.now(),
    }
