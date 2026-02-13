"""
Bench commands for Niv AI Health System.

Usage:
  bench niv-setup    → First-time setup (idempotent)
  bench niv-health   → Full health check + auto-fix
  bench niv-doctor   → Quick diagnosis
"""
import click


@click.command("niv-setup")
def niv_setup():
    """🚀 Niv AI Setup — first-time configuration (safe to re-run)."""
    import frappe
    frappe.init(site=get_site())
    frappe.connect()
    try:
        from niv_ai.niv_health import run_setup
        run_setup()
    finally:
        frappe.destroy()


@click.command("niv-health")
@click.option("--no-fix", is_flag=True, help="Check only, don't auto-fix")
@click.option("--category", type=str, default=None,
              help="Filter: core, tools, rag, chat, billing, voice, integrations, deployment")
@click.option("--verbose", is_flag=True, help="Show extra details")
def niv_health(no_fix, category, verbose):
    """🏥 Niv AI Health Check — diagnose and auto-fix all subsystems."""
    import frappe
    frappe.init(site=get_site())
    frappe.connect()
    try:
        from niv_ai.niv_health import run_health_check, _header, _info
        _header("Niv AI Health Check")
        auto_fix = not no_fix
        if auto_fix:
            _info("Auto-fix: ON (use --no-fix to disable)")
        else:
            _info("Auto-fix: OFF (check only)")
        click.echo()

        results, counts = run_health_check(auto_fix=auto_fix, category=category, verbose=verbose)

        # Summary
        click.echo()
        _header("Summary")
        total = sum(counts.values())
        parts = []
        if counts["ok"]:
            parts.append(click.style(f"{counts['ok']} ok", fg="green"))
        if counts["fixed"]:
            parts.append(click.style(f"{counts['fixed']} fixed", fg="blue"))
        if counts["warning"]:
            parts.append(click.style(f"{counts['warning']} warnings", fg="yellow"))
        if counts["error"]:
            parts.append(click.style(f"{counts['error']} errors", fg="red"))

        click.echo(f"  {total} checks: {', '.join(parts)}")

        if counts["error"] == 0:
            click.echo()
            click.echo(click.style("  🎉 Niv AI is healthy!", fg="green", bold=True))
        else:
            click.echo()
            click.echo(click.style(f"  ⚠️  {counts['error']} issue(s) need manual attention", fg="red"))
        click.echo()
    finally:
        frappe.destroy()


@click.command("niv-doctor")
@click.option("--deep", is_flag=True, help="Include LLM connectivity test (slower)")
def niv_doctor(deep):
    """🩺 Quick diagnosis — skips slow checks unless --deep."""
    import frappe
    frappe.init(site=get_site())
    frappe.connect()
    try:
        from niv_ai.niv_health import CHECKS, _header, _ok, _fix, _warn, _err
        _header("Niv AI Quick Diagnosis")
        click.echo()

        skip = set() if deep else {"LLM Connectivity"}
        counts = {"ok": 0, "fixed": 0, "warning": 0, "error": 0}

        for check in CHECKS:
            name = check["name"]
            if name in skip:
                continue
            try:
                result = check["fn"](auto_fix=True)
            except Exception as e:
                result = {"status": "error", "message": str(e)[:100]}

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

        click.echo()
        if counts.get("error", 0) == 0:
            click.echo(click.style("  🎉 All good!", fg="green", bold=True))
        else:
            click.echo(click.style("  Run 'bench niv-health' for full diagnosis", fg="yellow"))
        click.echo()
    finally:
        frappe.destroy()


def get_site():
    """Get current site from bench context."""
    import os
    # Bench sets this environment variable
    site = os.environ.get("FRAPPE_SITE")
    if site:
        return site
    # Try to get from current_site.txt
    try:
        import frappe
        sites_path = os.path.join(frappe.get_app_path("frappe"), "..", "..", "currentsite.txt")
        if os.path.exists(sites_path):
            with open(sites_path) as f:
                return f.read().strip()
    except Exception:
        pass
    # Fallback to default site
    return "erp024.growthsystem.in"


commands = [niv_setup, niv_health, niv_doctor]