"""
Niv AI Health System — Self-Healing + Auto-Setup + Feature Isolation

Design:
  - Every check returns {"status": "ok"|"warning"|"error"|"fixed", "message": str}
  - Every check has a paired auto-fix that runs when status is "error"
  - Features are isolated: Chat, RAG, Voice, MCP, Billing, Telegram, WhatsApp
  - No feature depends on another — graceful degradation everywhere

CLI commands are in commands.py (bench niv-setup, bench niv-health, bench niv-doctor)
API endpoint: /api/method/niv_ai.niv_health.api_health_check
"""
import frappe
import click
import os
import sys


# ─── Colors & Output ─────────────────────────────────────────────────────

def _ok(msg):
    click.echo(click.style(f"  ✅ {msg}", fg="green"))

def _warn(msg):
    click.echo(click.style(f"  ⚠️  {msg}", fg="yellow"))

def _err(msg):
    click.echo(click.style(f"  ❌ {msg}", fg="red"))

def _info(msg):
    click.echo(click.style(f"  ℹ️  {msg}", fg="cyan"))

def _fix(msg):
    click.echo(click.style(f"  🔧 {msg}", fg="blue"))

def _header(msg):
    click.echo()
    click.echo(click.style(f"{'─'*60}", fg="white"))
    click.echo(click.style(f"  {msg}", fg="white", bold=True))
    click.echo(click.style(f"{'─'*60}", fg="white"))


# ─── Health Check Registry ────────────────────────────────────────────────

CHECKS = []

def register_check(name, category="core"):
    """Decorator to register a health check function."""
    def decorator(fn):
        CHECKS.append({"name": name, "category": category, "fn": fn})
        return fn
    return decorator


# ─── Individual Health Checks ─────────────────────────────────────────────

@register_check("Niv Settings", "core")
def check_settings(auto_fix=True):
    """Verify Niv Settings singleton exists with required fields."""
    try:
        if not frappe.db.exists("Niv Settings", "Niv Settings"):
            if auto_fix:
                _create_default_settings()
                return {"status": "fixed", "message": "Created Niv Settings with defaults"}
            return {"status": "error", "message": "Niv Settings not found"}

        settings = frappe.get_doc("Niv Settings")
        issues = []
        if not getattr(settings, "default_model", ""):
            issues.append("default_model is empty")
        if not getattr(settings, "system_prompt", ""):
            issues.append("system_prompt is empty")

        if issues and auto_fix:
            if not settings.default_model:
                settings.default_model = "mistral-small-latest"
            if not settings.system_prompt:
                from niv_ai.install import DEFAULT_SYSTEM_PROMPT
                settings.system_prompt = DEFAULT_SYSTEM_PROMPT
            settings.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "fixed", "message": "Fixed: " + ", ".join(issues)}

        if issues:
            return {"status": "warning", "message": ", ".join(issues)}

        return {"status": "ok", "message": f"Model: {settings.default_model}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@register_check("LLM Provider", "core")
def check_llm_provider(auto_fix=True):
    """Verify at least one LLM provider is configured."""
    try:
        # Check if Niv AI Provider DocType exists
        if not frappe.db.exists("DocType", "Niv AI Provider"):
            # Fall back to legacy single-provider config
            settings = frappe.get_doc("Niv Settings")
            api_key = settings.get_password("api_key", raise_exception=False)
            base_url = getattr(settings, "api_base_url", "") or ""
            default_model = getattr(settings, "default_model", "") or ""

            if api_key:
                return {"status": "ok", "message": f"Legacy config: {default_model or 'no model'} @ {base_url or 'default'}"}
            return {"status": "error", "message": "No LLM provider configured. Set API key in Niv Settings."}

        # Check providers in child table
        try:
            providers = frappe.get_all("Niv AI Provider", fields=["name", "provider_name", "base_url"])
        except Exception as e:
            # Handle missing columns (older schema)
            if "Unknown column" in str(e):
                providers = frappe.get_all("Niv AI Provider", fields=["name"])
            else:
                raise

        if not providers:
            # Check legacy config
            settings = frappe.get_doc("Niv Settings")
            api_key = settings.get_password("api_key", raise_exception=False)
            if api_key:
                return {"status": "ok", "message": "Using legacy single-provider config"}
            return {"status": "error", "message": "No LLM provider configured. Add one in Niv Settings."}

        # Try to check is_default (may not exist in older schema)
        try:
            default = frappe.db.get_value("Niv AI Provider", {"is_default": 1}, "provider_name")
            if default:
                return {"status": "ok", "message": f"{len(providers)} provider(s), default: {default}"}
            # Set first as default
            if auto_fix and providers:
                first = providers[0]["name"]
                frappe.db.set_value("Niv AI Provider", first, "is_default", 1)
                frappe.db.commit()
                return {"status": "fixed", "message": f"Set first provider as default"}
        except Exception:
            pass  # is_default column doesn't exist

        return {"status": "ok", "message": f"{len(providers)} provider(s) configured"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@register_check("LLM Connectivity", "core")
def check_llm_connectivity(auto_fix=True):
    """Test actual LLM API connectivity with a minimal request."""
    try:
        from niv_ai.niv_core.langchain.llm import get_llm
        llm = get_llm()
        if llm is None:
            return {"status": "error", "message": "Could not initialize LLM model"}

        try:
            response = llm.invoke("Say 'ok'")
            content = getattr(response, "content", str(response))
            if content:
                return {"status": "ok", "message": f"LLM responds ({len(content)} chars)"}
            return {"status": "warning", "message": "LLM returned empty response"}
        except Exception as e:
            err = str(e)
            if "401" in err or "403" in err or "Unauthorized" in err:
                return {"status": "error", "message": "API key invalid or expired"}
            if "404" in err:
                return {"status": "error", "message": "Model not found — check model name"}
            if "timeout" in err.lower() or "connect" in err.lower():
                return {"status": "error", "message": f"Cannot reach LLM API: {err[:100]}"}
            return {"status": "error", "message": f"LLM error: {err[:150]}"}
    except ImportError as e:
        return {"status": "error", "message": f"Missing dependency: {e}"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


@register_check("MCP Tools", "tools")
def check_mcp_tools(auto_fix=True):
    """Check MCP tool discovery and availability."""
    try:
        from niv_ai.niv_core.mcp_client import get_all_mcp_tools
        tools = get_all_mcp_tools()

        if not tools:
            installed_apps = frappe.get_installed_apps()
            if "frappe_assistant_core" not in installed_apps:
                return {"status": "warning", "message": "No MCP tools. Install frappe_assistant_core for 23 built-in tools."}
            return {"status": "error", "message": "FAC installed but no tools discovered — check MCP server config"}

        # Check tool structure — tools are in OpenAI format: {"type":"function","function":{"name":...}}
        valid_tools = []
        for t in tools:
            if isinstance(t, dict):
                # OpenAI format: name is inside function dict
                func = t.get("function", {})
                name = func.get("name") if isinstance(func, dict) else None
                # Also handle flat format: {"name": ...}
                if not name:
                    name = t.get("name")
            else:
                name = getattr(t, "name", None)
            if name:
                valid_tools.append(name)

        broken_count = len(tools) - len(valid_tools)
        if broken_count > 0:
            return {"status": "warning", "message": f"{len(valid_tools)} valid tools, {broken_count} malformed"}

        return {"status": "ok", "message": f"{len(tools)} tools available"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


@register_check("MCP Circuit Breaker", "tools")
def check_circuit_breaker(auto_fix=True):
    """Check and reset tripped circuit breakers."""
    try:
        tripped = []
        try:
            keys = frappe.cache().get_keys("niv_mcp_cb_*") or []
            for key in keys:
                val = frappe.cache().get_value(key)
                if val and isinstance(val, dict) and val.get("state") == "open":
                    tripped.append(key)
        except Exception:
            pass

        if tripped:
            if auto_fix:
                for key in tripped:
                    frappe.cache().delete_value(key)
                return {"status": "fixed", "message": f"Reset {len(tripped)} tripped circuit breaker(s)"}
            return {"status": "warning", "message": f"{len(tripped)} circuit breaker(s) tripped"}

        return {"status": "ok", "message": "No tripped circuit breakers"}
    except Exception:
        return {"status": "ok", "message": "Circuit breaker check skipped (non-critical)"}


@register_check("RAG Knowledge Base", "rag")
def check_rag(auto_fix=True):
    """Verify RAG knowledge base: chunks exist, FAISS index valid."""
    try:
        settings = frappe.get_doc("Niv Settings")
        enabled = getattr(settings, "enable_knowledge_base", 0)

        if not enabled:
            return {"status": "ok", "message": "RAG disabled (optional feature)"}

        chunk_count = frappe.db.count("Niv KB Chunk")
        kb_count = frappe.db.count("Niv Knowledge Base")

        faiss_ok = False
        faiss_vectors = 0
        try:
            site_path = frappe.get_site_path("private", "niv_ai", "faiss_index")
            index_file = os.path.join(site_path, "index.faiss")
            if os.path.exists(index_file):
                faiss_ok = True
                try:
                    from niv_ai.niv_core.langchain.rag import _get_vectorstore
                    store = _get_vectorstore()
                    if store and hasattr(store, "index"):
                        faiss_vectors = store.index.ntotal
                except Exception:
                    pass
        except Exception:
            pass

        if chunk_count == 0 and kb_count == 0:
            return {"status": "warning", "message": "RAG enabled but no knowledge docs. Add via Niv Knowledge Base DocType."}

        if not faiss_ok and chunk_count > 0:
            if auto_fix:
                try:
                    from niv_ai.niv_core.langchain.rag_indexer import rebuild_index
                    rebuild_index()
                    return {"status": "fixed", "message": f"Re-indexed {chunk_count} chunks into FAISS"}
                except Exception as e:
                    return {"status": "warning", "message": f"{kb_count} docs, {chunk_count} chunks, FAISS missing (re-index failed: {str(e)[:80]})"}

        parts = [f"{kb_count} docs", f"{chunk_count} chunks"]
        if faiss_ok:
            parts.append(f"FAISS: {faiss_vectors} vectors")
        return {"status": "ok", "message": ", ".join(parts)}
    except Exception as e:
        return {"status": "ok", "message": f"RAG check skipped: {str(e)[:80]}"}


@register_check("Database Tables", "core")
def check_database(auto_fix=True):
    """Verify all Niv AI DocType tables exist."""
    # Single DocTypes don't have regular tables, skip them
    single_doctypes = {"Niv Settings"}
    required_doctypes = [
        "Niv Conversation", "Niv Message",
        "Niv AI Provider", "Niv System Prompt", "Niv Credit Plan",
        "Niv KB Chunk", "Niv Knowledge Base", "Niv Trigger",
    ]
    missing = []
    for dt in required_doctypes:
        try:
            frappe.db.sql(f"SELECT COUNT(*) FROM `tab{dt}` LIMIT 1")
        except Exception:
            missing.append(dt)

    if missing:
        return {"status": "error" if len(missing) > 3 else "warning",
                "message": f"Missing tables: {', '.join(missing)}. Run 'bench migrate'."}

    try:
        convs = frappe.db.count("Niv Conversation")
        msgs = frappe.db.count("Niv Message")
        return {"status": "ok", "message": f"{convs} conversations, {msgs} messages"}
    except Exception:
        return {"status": "ok", "message": "All tables exist"}


@register_check("Python Dependencies", "core")
def check_dependencies(auto_fix=True):
    """Check required Python packages are installed."""
    deps = {
        "langchain_core": "langchain-core",
        "langchain_openai": "langchain-openai",
        "langchain_community": "langchain-community",
    }
    optional_deps = {
        "piper": "piper-tts",
        "faiss": "faiss-cpu",
    }

    missing = []
    for module, package in deps.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    missing_optional = []
    for module, package in optional_deps.items():
        try:
            __import__(module)
        except ImportError:
            missing_optional.append(package)

    if missing:
        if auto_fix:
            import subprocess
            for pkg in missing:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"], timeout=120)
                except Exception:
                    pass

            still_missing = []
            for module, package in deps.items():
                try:
                    __import__(module)
                except ImportError:
                    still_missing.append(package)

            if still_missing:
                return {"status": "error", "message": f"Could not install: {', '.join(still_missing)}"}
            return {"status": "fixed", "message": f"Installed: {', '.join(missing)}"}

        return {"status": "error", "message": f"Missing: {', '.join(missing)}. Run: pip install {' '.join(missing)}"}

    msg = "All required packages installed"
    if missing_optional:
        msg += f" (optional missing: {', '.join(missing_optional)})"
    return {"status": "ok", "message": msg}


@register_check("SSE Streaming", "chat")
def check_sse(auto_fix=True):
    """Verify SSE streaming has the frappe.init() fix."""
    try:
        import inspect
        from niv_ai.niv_core.api import stream
        source = inspect.getsource(stream)

        has_init_fix = "frappe.init(" in source and "frappe.connect(" in source
        if not has_init_fix:
            return {"status": "error", "message": "stream.py missing frappe.init() fix — SSE will break. Update code."}

        return {"status": "ok", "message": "SSE streaming code has frappe.init() fix"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


@register_check("Discovery Context", "core")
def check_discovery(auto_fix=True):
    """Verify auto-discovery has run and context is saved."""
    try:
        settings = frappe.get_doc("Niv Settings")
        context = getattr(settings, "discovery_context", "") or ""

        if not context or len(context) < 50:
            if auto_fix:
                try:
                    from niv_ai.niv_core.discovery import auto_discover_system
                    result = auto_discover_system()
                    apps = len(result.get("apps", []))
                    return {"status": "fixed", "message": f"Re-ran discovery: {apps} apps found"}
                except Exception as e:
                    return {"status": "warning", "message": f"Discovery failed: {str(e)[:80]}"}
            return {"status": "warning", "message": "Discovery context empty — run bench niv-setup"}

        return {"status": "ok", "message": f"Discovery context: {len(context)} chars"}
    except Exception as e:
        return {"status": "ok", "message": f"Discovery check skipped: {str(e)[:60]}"}


@register_check("Billing System", "billing")
def check_billing(auto_fix=True):
    """Verify billing configuration."""
    try:
        settings = frappe.get_doc("Niv Settings")
        enabled = getattr(settings, "enable_billing", 0)

        if not enabled:
            return {"status": "ok", "message": "Billing disabled (optional)"}

        mode = getattr(settings, "billing_mode", "Shared Pool") or "Shared Pool"
        plan_count = frappe.db.count("Niv Credit Plan")
        if plan_count == 0:
            if auto_fix:
                from niv_ai.install import _seed_default_plans
                _seed_default_plans()
                frappe.db.commit()
                return {"status": "fixed", "message": f"Created default credit plans, mode: {mode}"}
            return {"status": "warning", "message": "Billing enabled but no credit plans exist"}

        return {"status": "ok", "message": f"Mode: {mode}, {plan_count} plans"}
    except Exception as e:
        return {"status": "ok", "message": f"Billing check skipped: {str(e)[:60]}"}


@register_check("Voice (Piper TTS)", "voice")
def check_voice(auto_fix=True):
    """Check Piper TTS availability (optional feature)."""
    try:
        try:
            import piper
        except ImportError:
            return {"status": "ok", "message": "Piper TTS not installed (optional — browser fallback available)"}

        try:
            from niv_ai.niv_core.api.voice import _get_piper_model_path
            model, config = _get_piper_model_path("en_US-lessac-medium")
            if model and os.path.exists(model):
                return {"status": "ok", "message": "Piper ready: en_US-lessac-medium"}
            return {"status": "warning", "message": "Piper installed but model not downloaded. Will download on first use."}
        except Exception as e:
            return {"status": "warning", "message": f"Piper installed, model check failed: {str(e)[:60]}"}
    except Exception:
        return {"status": "ok", "message": "Voice check skipped (optional feature)"}


@register_check("Telegram Bot", "integrations")
def check_telegram(auto_fix=True):
    """Check Telegram bot configuration (optional)."""
    try:
        settings = frappe.get_doc("Niv Settings")
        token = settings.get_password("telegram_bot_token", raise_exception=False)

        if not token:
            return {"status": "ok", "message": "Telegram not configured (optional)"}

        if ":" not in token:
            return {"status": "error", "message": "Telegram token format invalid (should be NUMBER:HASH)"}

        return {"status": "ok", "message": "Telegram bot token configured"}
    except Exception:
        return {"status": "ok", "message": "Telegram check skipped"}


@register_check("WhatsApp Bot", "integrations")
def check_whatsapp(auto_fix=True):
    """Check WhatsApp configuration (optional)."""
    try:
        settings = frappe.get_doc("Niv Settings")
        token = settings.get_password("whatsapp_token", raise_exception=False)

        if not token:
            return {"status": "ok", "message": "WhatsApp not configured (optional)"}

        phone_id = getattr(settings, "whatsapp_phone_number_id", "") or ""
        if not phone_id:
            return {"status": "warning", "message": "WhatsApp token set but phone_number_id missing"}

        return {"status": "ok", "message": "WhatsApp configured"}
    except Exception:
        return {"status": "ok", "message": "WhatsApp check skipped"}


@register_check("Nginx SSE Config", "deployment")
def check_nginx_sse(auto_fix=True):
    """Check if nginx has proxy_buffering off for SSE (Linux only)."""
    try:
        import platform
        if platform.system() == "Windows":
            return {"status": "ok", "message": "Skipped (Windows — no nginx)"}

        for path in ["/etc/nginx/conf.d/", "/etc/nginx/sites-enabled/",
                     f"/home/{os.environ.get('USER', 'frappe')}/frappe-bench/config/"]:
            if os.path.isdir(path):
                for f in os.listdir(path):
                    fpath = os.path.join(path, f)
                    if os.path.isfile(fpath):
                        try:
                            content = open(fpath).read()
                            if ("niv_ai" in content or "stream" in content):
                                if "proxy_buffering off" in content:
                                    return {"status": "ok", "message": f"Nginx SSE config OK: {fpath}"}
                                return {"status": "warning", "message": f"{fpath} may need 'proxy_buffering off' for SSE"}
                        except Exception:
                            pass

        return {"status": "ok", "message": "Nginx SSE config not checked (auto-detect limited)"}
    except Exception:
        return {"status": "ok", "message": "Nginx check skipped"}


@register_check("File Permissions", "deployment")
def check_file_permissions(auto_fix=True):
    """Check that Niv AI private directories exist and are writable."""
    try:
        private_path = frappe.get_site_path("private", "niv_ai")
        faiss_path = os.path.join(private_path, "faiss_index")

        if not os.path.exists(private_path):
            if auto_fix:
                os.makedirs(private_path, exist_ok=True)
                os.makedirs(faiss_path, exist_ok=True)
                return {"status": "fixed", "message": f"Created {private_path}"}
            return {"status": "error", "message": f"Missing directory: {private_path}"}

        test_file = os.path.join(private_path, ".health_check_test")
        try:
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
        except PermissionError:
            return {"status": "error", "message": f"Directory not writable: {private_path}"}

        return {"status": "ok", "message": "Private directories exist and writable"}
    except Exception as e:
        return {"status": "ok", "message": f"File permission check skipped: {str(e)[:60]}"}


# ─── Helpers ──────────────────────────────────────────────────────────────

def _create_default_settings():
    """Create Niv Settings with safe defaults."""
    from niv_ai.install import DEFAULT_SYSTEM_PROMPT
    doc = frappe.get_doc({
        "doctype": "Niv Settings",
        "default_model": "mistral-small-latest",
        "max_tokens_per_message": 4096,
        "max_messages_per_conversation": 50,
        "enable_tools": 1,
        "enable_billing": 0,
        "enable_widget": 1,
        "widget_position": "bottom-right",
        "widget_title": "Niv AI",
        "widget_color": "#5e64ff",
        "admin_allocation_only": 1,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()


def _print_result(name, result):
    status = result.get("status", "error")
    if status in ("ok", "fixed"):
        _ok(f"{name}: {result['message']}")
    elif status == "warning":
        _warn(f"{name}: {result['message']}")
    else:
        _err(f"{name}: {result['message']}")


# ─── Main Runners ─────────────────────────────────────────────────────────

def run_health_check(auto_fix=True, category=None, verbose=False):
    """Run all health checks and return summary."""
    results = {}
    counts = {"ok": 0, "fixed": 0, "warning": 0, "error": 0}

    for check in CHECKS:
        if category and check["category"] != category:
            continue

        name = check["name"]
        try:
            result = check["fn"](auto_fix=auto_fix)
        except Exception as e:
            result = {"status": "error", "message": f"Check crashed: {str(e)[:100]}"}

        results[name] = result
        status = result.get("status", "error")

        if status == "ok":
            _ok(f"{name}: {result['message']}")
        elif status == "fixed":
            _fix(f"{name}: {result['message']}")
        elif status == "warning":
            _warn(f"{name}: {result['message']}")
        else:
            _err(f"{name}: {result['message']}")
        counts[status] = counts.get(status, 0) + 1

    return results, counts


def run_setup():
    """Full first-time setup — idempotent."""
    _header("Niv AI Setup")
    click.echo()

    steps = [
        ("Step 1/5: Checking Python dependencies...", check_dependencies, "Dependencies"),
        ("Step 2/5: Creating/verifying Niv Settings...", check_settings, "Settings"),
        ("Step 3/5: Checking database tables...", check_database, "Database"),
        ("Step 4/5: Setting up directories...", check_file_permissions, "Directories"),
        ("Step 5/5: Running auto-discovery...", check_discovery, "Discovery"),
    ]

    for label, fn, name in steps:
        _info(label)
        result = fn(auto_fix=True)
        _print_result(name, result)

    click.echo()
    _header("Setup Complete!")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    1. Add an LLM provider in Niv Settings → Providers")
    click.echo("    2. Install frappe_assistant_core for 23 built-in MCP tools")
    click.echo("    3. Run 'bench niv-health' to verify everything works")
    click.echo()


# ─── API Endpoint (for UI health dashboard) ──────────────────────────────

@frappe.whitelist(allow_guest=False)
def api_health_check(auto_fix=False):
    """API: /api/method/niv_ai.niv_health.api_health_check
    Returns JSON health status for UI dashboard."""
    if not frappe.has_permission("Niv Settings", "read"):
        frappe.throw("Insufficient permissions", frappe.PermissionError)

    auto_fix = frappe.parse_json(auto_fix) if isinstance(auto_fix, str) else auto_fix
    results = {}

    for check in CHECKS:
        name = check["name"]
        try:
            results[name] = check["fn"](auto_fix=bool(auto_fix))
        except Exception as e:
            results[name] = {"status": "error", "message": str(e)[:100]}

    statuses = [r["status"] for r in results.values()]
    overall = "healthy"
    if "error" in statuses:
        overall = "degraded"
    if all(s == "error" for s in statuses):
        overall = "down"

    return {
        "overall": overall,
        "checks": results,
        "version": _get_version(),
    }


def _get_version():
    try:
        from niv_ai import __version__
        return __version__
    except Exception:
        return "0.5.1"