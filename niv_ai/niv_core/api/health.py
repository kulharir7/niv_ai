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
        from niv_ai import __version__
        return __version__
    except ImportError:
        pass
    try:
        import niv_ai
        init_path = niv_ai.__file__.replace("__init__.pyc", "__init__.py")
        with open(init_path) as f:
            for line in f:
                if "__version__" in line:
                    return line.split("=")[1].strip().strip("'").strip('"')
    except Exception:
        pass
    try:
        return frappe.get_attr("niv_ai.hooks.app_version", "unknown")
    except Exception:
        return "unknown"


def _check_llm():
    try:
        settings = get_niv_settings()
        api_key = settings.get_password("api_key", raise_exception=False)
        model = getattr(settings, "default_model", "") or ""
        base_url = getattr(settings, "api_base_url", "") or ""
        provider_name = getattr(settings, "default_provider", "") or ""

        # Also check Provider doc for API key (common setup)
        if not api_key and provider_name:
            try:
                provider = frappe.get_doc("Niv AI Provider", provider_name)
                api_key = provider.get_password("api_key")
                if not base_url:
                    base_url = getattr(provider, "base_url", "") or ""
            except Exception:
                pass

        if not api_key:
            return {"status": "error", "message": "No API key configured"}

        return {
            "status": "ok",
            "model": model,
            "provider": provider_name or (base_url.split("/")[2] if base_url and "/" in base_url else "unknown"),
            "base_url": base_url,
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

# ═══════════════════════════════════════════════════════════════════
# Deep System Doctor — comprehensive diagnosis + auto-fix suggestions
# Added: 2026-02-21
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=False)
def deep_check():
    """Comprehensive system health check — the System Doctor.
    
    Goes beyond basic health.check() to diagnose real issues:
    - Error Log analysis (frequency, severity, patterns)
    - Scheduled Job health
    - Voice/TTS/STT availability
    - Disk/file storage usage
    - Recent performance metrics
    - Auto-fix suggestions with severity levels
    
    Endpoint: /api/method/niv_ai.niv_core.api.health.deep_check
    """
    if not frappe.has_permission("Niv Settings", "read"):
        frappe.throw(_("Insufficient permissions"), frappe.PermissionError)

    result = {
        "status": "ok",
        "version": _get_version(),
        "basic": {},
        "errors": _check_errors(),
        "jobs": _check_scheduled_jobs(),
        "voice": _check_voice(),
        "storage": _check_storage(),
        "performance": _check_performance(),
        "fixes": [],
    }

    # Run basic checks too
    result["basic"]["llm"] = _check_llm()
    result["basic"]["mcp"] = _check_mcp()
    result["basic"]["database"] = _check_database()

    # Generate fix suggestions based on all findings
    result["fixes"] = _suggest_fixes(result)

    # Overall status
    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    for fix in result["fixes"]:
        sev = fix.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    if severity_counts.get("critical", 0) > 0:
        result["status"] = "critical"
    elif severity_counts.get("warning", 0) > 0:
        result["status"] = "warning"
    else:
        result["status"] = "healthy"

    result["summary"] = {
        "total_issues": len(result["fixes"]),
        "critical": severity_counts.get("critical", 0),
        "warnings": severity_counts.get("warning", 0),
        "info": severity_counts.get("info", 0),
    }

    return result


def _check_errors():
    """Analyze Error Log — frequency, patterns, severity."""
    from datetime import datetime, timedelta
    now = datetime.now()
    result = {
        "last_1h": 0,
        "last_24h": 0,
        "last_7d": 0,
        "recent_errors": [],
        "top_methods": [],
        "niv_errors": [],
    }

    try:
        # Count by time window
        result["last_1h"] = frappe.db.count("Error Log", {
            "creation": [">", now - timedelta(hours=1)]
        })
        result["last_24h"] = frappe.db.count("Error Log", {
            "creation": [">", now - timedelta(hours=24)]
        })
        result["last_7d"] = frappe.db.count("Error Log", {
            "creation": [">", now - timedelta(days=7)]
        })

        # Recent errors (last 10)
        recent = frappe.get_all("Error Log",
            filters={"creation": [">", now - timedelta(hours=24)]},
            fields=["name", "method", "creation", "error"],
            order_by="creation desc",
            limit=10,
        )
        for e in recent:
            result["recent_errors"].append({
                "time": str(e.creation),
                "method": e.method or "",
                "preview": (e.error or "")[:200],
            })

        # Top error methods (grouping)
        top = frappe.db.sql("""
            SELECT method, COUNT(*) as cnt
            FROM `tabError Log`
            WHERE creation > %s
            GROUP BY method
            ORDER BY cnt DESC
            LIMIT 5
        """, [now - timedelta(hours=24)], as_dict=True)
        result["top_methods"] = [{"method": t.method or "unknown", "count": t.cnt} for t in top]

        # Niv AI specific errors
        niv_errs = frappe.get_all("Error Log",
            filters=[
                ["creation", ">", now - timedelta(days=7)],
                ["error", "like", "%niv%"],
            ],
            fields=["name", "method", "creation", "error"],
            order_by="creation desc",
            limit=5,
        )
        for e in niv_errs:
            result["niv_errors"].append({
                "time": str(e.creation),
                "method": e.method or "",
                "preview": (e.error or "")[:200],
            })

    except Exception as e:
        result["error"] = str(e)

    return result


def _check_scheduled_jobs():
    """Check Scheduled Job health — failures, stuck jobs."""
    result = {
        "total": 0,
        "failed": [],
        "status": "ok",
    }

    try:
        result["total"] = frappe.db.count("Scheduled Job Type")

        failed = frappe.get_all("Scheduled Job Type",
            filters={"status": ["in", ["Failed", "Error"]]},
            fields=["name", "method", "last_execution", "status"],
            limit=10,
        )
        for j in failed:
            result["failed"].append({
                "name": j.name,
                "method": j.method,
                "last_run": str(j.last_execution) if j.last_execution else "never",
                "status": j.status,
            })

        if len(failed) > 5:
            result["status"] = "critical"
        elif len(failed) > 0:
            result["status"] = "warning"

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"

    return result


def _check_voice():
    """Check TTS/STT engine availability."""
    result = {
        "tts_engines": {},
        "stt_engines": {},
        "config": {},
        "status": "ok",
    }

    try:
        settings = get_niv_settings()
        result["config"] = {
            "tts_engine": getattr(settings, "tts_engine", "") or "auto",
            "stt_engine": getattr(settings, "stt_engine", "") or "auto",
            "enable_voice": getattr(settings, "enable_voice", 1),
        }

        # Check TTS engines
        try:
            import piper
            result["tts_engines"]["piper"] = True
        except ImportError:
            result["tts_engines"]["piper"] = False

        try:
            import edge_tts
            result["tts_engines"]["edge_tts"] = True
        except ImportError:
            result["tts_engines"]["edge_tts"] = False

        elevenlabs_key = False
        try:
            elevenlabs_key = bool(settings.get_password("elevenlabs_api_key"))
        except Exception:
            pass
        result["tts_engines"]["elevenlabs"] = elevenlabs_key

        # Check STT engines
        try:
            from faster_whisper import WhisperModel
            result["stt_engines"]["faster_whisper"] = True
        except ImportError:
            result["stt_engines"]["faster_whisper"] = False

        # Voxtral (API-based STT)
        provider_name = getattr(settings, "default_provider", "")
        has_api_key = False
        if provider_name:
            try:
                provider = frappe.get_doc("Niv AI Provider", provider_name)
                has_api_key = bool(provider.get_password("api_key"))
            except Exception:
                pass
        result["stt_engines"]["voxtral_api"] = has_api_key

        # Status assessment
        any_tts = any(result["tts_engines"].values())
        any_stt = any(result["stt_engines"].values())
        if not any_tts and not any_stt:
            result["status"] = "error"
        elif not any_tts or not any_stt:
            result["status"] = "warning"

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"

    return result


def _check_storage():
    """Check file storage usage."""
    import os
    result = {
        "public_files": {"count": 0, "size_mb": 0},
        "private_files": {"count": 0, "size_mb": 0},
        "tts_temp_files": 0,
        "status": "ok",
    }

    try:
        # Public files
        public_dir = frappe.get_site_path("public", "files")
        if os.path.exists(public_dir):
            files = os.listdir(public_dir)
            result["public_files"]["count"] = len(files)
            total_size = sum(
                os.path.getsize(os.path.join(public_dir, f))
                for f in files
                if os.path.isfile(os.path.join(public_dir, f))
            )
            result["public_files"]["size_mb"] = round(total_size / (1024 * 1024), 2)

            # Count leftover TTS temp files
            tts_files = [f for f in files if f.startswith(("tts_", "niv_tts_"))]
            result["tts_temp_files"] = len(tts_files)

        # Private files
        private_dir = frappe.get_site_path("private", "files")
        if os.path.exists(private_dir):
            files = os.listdir(private_dir)
            result["private_files"]["count"] = len(files)
            total_size = sum(
                os.path.getsize(os.path.join(private_dir, f))
                for f in files
                if os.path.isfile(os.path.join(private_dir, f))
            )
            result["private_files"]["size_mb"] = round(total_size / (1024 * 1024), 2)

        # Warnings
        total_mb = result["public_files"]["size_mb"] + result["private_files"]["size_mb"]
        if total_mb > 5000:
            result["status"] = "critical"
        elif total_mb > 1000:
            result["status"] = "warning"

        if result["tts_temp_files"] > 100:
            result["status"] = "warning"

    except Exception as e:
        result["error"] = str(e)

    return result


def _check_performance():
    """Check recent Niv AI response performance."""
    from datetime import datetime, timedelta
    result = {
        "today_conversations": 0,
        "today_messages": 0,
        "total_conversations": 0,
        "avg_tokens_per_response": 0,
        "status": "ok",
    }

    try:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        result["today_conversations"] = frappe.db.count("Niv Conversation", {
            "creation": [">", today]
        })
        result["today_messages"] = frappe.db.count("Niv Message", {
            "creation": [">", today]
        })
        result["total_conversations"] = frappe.db.count("Niv Conversation")

        # Average tokens (if tracked)
        try:
            avg = frappe.db.sql("""
                SELECT AVG(total_tokens) as avg_tokens
                FROM `tabNiv Message`
                WHERE role='assistant' AND creation > %s AND total_tokens > 0
            """, [now - timedelta(hours=24)], as_dict=True)
            if avg and avg[0].avg_tokens:
                result["avg_tokens_per_response"] = round(float(avg[0].avg_tokens))
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


def _suggest_fixes(result):
    """Analyze all check results and suggest fixes with severity."""
    fixes = []

    # ─── LLM issues ───
    llm = result.get("basic", {}).get("llm", {})
    if llm.get("status") == "error":
        fixes.append({
            "severity": "critical",
            "area": "LLM",
            "issue": "No LLM API key configured",
            "fix": "Go to Niv Settings → Set API key, or configure a Niv AI Provider with API key",
            "auto_fixable": False,
        })

    # ─── MCP Tools ───
    mcp = result.get("basic", {}).get("mcp", {})
    if mcp.get("status") == "error":
        fixes.append({
            "severity": "critical",
            "area": "MCP Tools",
            "issue": "MCP tools not available: " + mcp.get("message", ""),
            "fix": "Check frappe_assistant_core installation and MCP server configuration",
            "auto_fixable": False,
        })
    elif mcp.get("tool_count", 0) == 0:
        fixes.append({
            "severity": "warning",
            "area": "MCP Tools",
            "issue": "No MCP tools found — AI has no tools to work with",
            "fix": "Ensure frappe_assistant_core has tools configured and enabled",
            "auto_fixable": False,
        })

    # ─── Error Log ───
    errors = result.get("errors", {})
    err_1h = errors.get("last_1h", 0)
    err_24h = errors.get("last_24h", 0)
    if err_1h > 50:
        fixes.append({
            "severity": "critical",
            "area": "Errors",
            "issue": "%d errors in last 1 hour — system under stress" % err_1h,
            "fix": "Check Error Log for repeating patterns. Top errors: %s" % str(
                [e["method"] for e in errors.get("top_methods", [])[:3]]
            ),
            "auto_fixable": False,
        })
    elif err_24h > 100:
        fixes.append({
            "severity": "warning",
            "area": "Errors",
            "issue": "%d errors in last 24 hours" % err_24h,
            "fix": "Review Error Log — may indicate a recurring issue",
            "auto_fixable": False,
        })

    # Niv-specific errors
    niv_errs = errors.get("niv_errors", [])
    if niv_errs:
        methods = set(e["method"] for e in niv_errs)
        for method in methods:
            if "Stream error" in method:
                fixes.append({
                    "severity": "warning",
                    "area": "Niv AI Stream",
                    "issue": "Stream errors found: " + method,
                    "fix": "Check if LLM responses contain unexpected formats (lists instead of strings)",
                    "auto_fixable": False,
                })
            elif "Two-model" in method:
                fixes.append({
                    "severity": "info",
                    "area": "Niv AI",
                    "issue": "Two-model fallbacks detected — fast model may not be configured",
                    "fix": "Set fast_model in Niv Settings or leave empty to use single model",
                    "auto_fixable": True,
                    "auto_fix_action": "clear_fast_model",
                })

    # ─── Scheduled Jobs ───
    jobs = result.get("jobs", {})
    if jobs.get("failed"):
        fixes.append({
            "severity": "warning",
            "area": "Scheduled Jobs",
            "issue": "%d failed scheduled jobs" % len(jobs["failed"]),
            "fix": "Review failed jobs: %s" % str([j["name"] for j in jobs["failed"][:3]]),
            "auto_fixable": False,
        })

    # ─── Voice ───
    voice = result.get("voice", {})
    voice_config = voice.get("config", {})
    tts_engines = voice.get("tts_engines", {})
    stt_engines = voice.get("stt_engines", {})

    if voice_config.get("tts_engine") == "piper" and not tts_engines.get("piper"):
        fixes.append({
            "severity": "warning",
            "area": "Voice",
            "issue": "TTS engine set to 'piper' but Piper is not installed",
            "fix": "Change tts_engine to 'auto' in Niv Settings (will use Edge TTS)",
            "auto_fixable": True,
            "auto_fix_action": "set_tts_auto",
        })

    if voice_config.get("tts_engine") == "piper":
        fixes.append({
            "severity": "info",
            "area": "Voice",
            "issue": "TTS engine is 'piper' — Hindi voice not available (Piper has no Hindi model)",
            "fix": "Change to 'auto' to enable Edge TTS Hindi (hi-IN-SwaraNeural)",
            "auto_fixable": True,
            "auto_fix_action": "set_tts_auto",
        })

    if not any(tts_engines.values()):
        fixes.append({
            "severity": "critical",
            "area": "Voice",
            "issue": "No TTS engine available — voice output disabled",
            "fix": "Install edge-tts (pip install edge-tts) or configure ElevenLabs API key",
            "auto_fixable": False,
        })

    if not any(stt_engines.values()):
        fixes.append({
            "severity": "warning",
            "area": "Voice",
            "issue": "No STT engine available — voice input relies on browser only",
            "fix": "Install faster-whisper or configure Voxtral API key",
            "auto_fixable": False,
        })

    # ─── Storage ───
    storage = result.get("storage", {})
    tts_temp = storage.get("tts_temp_files", 0)
    if tts_temp > 100:
        fixes.append({
            "severity": "warning",
            "area": "Storage",
            "issue": "%d leftover TTS temp files in public/files" % tts_temp,
            "fix": "Clean up TTS temp files to free disk space",
            "auto_fixable": True,
            "auto_fix_action": "cleanup_tts_files",
        })

    total_mb = storage.get("public_files", {}).get("size_mb", 0) + storage.get("private_files", {}).get("size_mb", 0)
    if total_mb > 5000:
        fixes.append({
            "severity": "critical",
            "area": "Storage",
            "issue": "File storage at %.1f GB — running out of space" % (total_mb / 1024),
            "fix": "Clean up old files, backup, and archive",
            "auto_fixable": False,
        })

    # ─── Database ───
    db = result.get("basic", {}).get("database", {})
    if db.get("status") == "error":
        fixes.append({
            "severity": "critical",
            "area": "Database",
            "issue": "Database connection error: " + db.get("message", ""),
            "fix": "Check MariaDB/MySQL service status",
            "auto_fixable": False,
        })

    return fixes


@frappe.whitelist(allow_guest=False)
def auto_fix(action):
    """Apply an auto-fix suggestion.
    
    Endpoint: /api/method/niv_ai.niv_core.api.health.auto_fix
    Args: action — the auto_fix_action from suggest_fixes
    """
    if not frappe.has_permission("Niv Settings", "write"):
        frappe.throw(_("Insufficient permissions"), frappe.PermissionError)

    results = []

    if action == "set_tts_auto":
        settings = get_niv_settings()
        old = getattr(settings, "tts_engine", "")
        settings.tts_engine = "auto"
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        results.append("TTS engine changed from '%s' to 'auto'" % old)

    elif action == "clear_fast_model":
        settings = get_niv_settings()
        old = getattr(settings, "fast_model", "")
        settings.fast_model = ""
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        results.append("fast_model cleared (was '%s'). Two-model optimization disabled." % old)

    elif action == "cleanup_tts_files":
        import os
        public_dir = frappe.get_site_path("public", "files")
        count = 0
        if os.path.exists(public_dir):
            for f in os.listdir(public_dir):
                if f.startswith(("tts_", "niv_tts_", "tts_s_", "tts_edge_", "tts_stream_", "tts_11labs_")):
                    try:
                        fpath = os.path.join(public_dir, f)
                        os.unlink(fpath)
                        count += 1
                    except Exception:
                        pass
        results.append("Cleaned up %d TTS temp files" % count)

    else:
        frappe.throw("Unknown auto-fix action: %s" % action)

    return {"applied": results}

