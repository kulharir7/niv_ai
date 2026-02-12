"""
Auto-Discovery Engine — Scans the ERPNext instance and builds system knowledge.
Runs on install and periodically to keep knowledge updated.
"""
import frappe
import json
from datetime import datetime


def auto_discover_system():
    """Main discovery function — scans entire system and builds knowledge."""
    frappe.logger().info("Niv AI: Starting auto-discovery...")

    knowledge = {}

    # 1. Installed Apps
    knowledge["apps"] = _scan_apps()

    # 2. Modules & DocTypes
    knowledge["modules"] = _scan_modules()

    # 3. Customizations
    knowledge["customizations"] = _scan_customizations()

    # 4. Workflows
    knowledge["workflows"] = _scan_workflows()

    # 5. Domain Detection
    knowledge["domain"] = _detect_domain(knowledge)

    # 6. Data Summary
    knowledge["data_summary"] = _scan_data_summary()

    # 7. Build and save system prompt context
    prompt_context = _build_prompt_context(knowledge)
    _save_knowledge(knowledge, prompt_context)

    frappe.logger().info("Niv AI: Auto-discovery complete!")
    return knowledge


def _scan_apps():
    """Scan installed apps."""
    apps = frappe.get_installed_apps()
    result = []
    for app in apps:
        try:
            app_info = {"name": app}
            # Get version
            try:
                import importlib
                mod = importlib.import_module(app)
                app_info["version"] = getattr(mod, "__version__", "unknown")
            except Exception:
                app_info["version"] = "unknown"
            result.append(app_info)
        except Exception:
            result.append({"name": app, "version": "unknown"})
    return result


def _scan_modules():
    """Scan all modules and their DocTypes."""
    modules = {}
    doctypes = frappe.get_all("DocType", fields=["name", "module", "istable", "issingle", "custom"], limit_page_length=0)

    for dt in doctypes:
        mod = dt.get("module") or "Other"
        if mod not in modules:
            modules[mod] = {"doctypes": [], "custom_count": 0, "total": 0}
        modules[mod]["doctypes"].append({
            "name": dt["name"],
            "istable": dt.get("istable", 0),
            "issingle": dt.get("issingle", 0),
            "custom": dt.get("custom", 0),
        })
        modules[mod]["total"] += 1
        if dt.get("custom"):
            modules[mod]["custom_count"] += 1

    return modules


def _scan_customizations():
    """Scan Custom Fields, Client Scripts, Server Scripts, Property Setters."""
    result = {}

    # Custom Fields
    cf = frappe.get_all("Custom Field", fields=["dt", "fieldname", "fieldtype", "label"], limit_page_length=0)
    cf_by_dt = {}
    for f in cf:
        dt = f.get("dt", "Unknown")
        if dt not in cf_by_dt:
            cf_by_dt[dt] = []
        cf_by_dt[dt].append({"fieldname": f["fieldname"], "fieldtype": f["fieldtype"], "label": f.get("label", "")})
    result["custom_fields"] = cf_by_dt
    result["custom_field_count"] = len(cf)

    # Client Scripts
    try:
        cs = frappe.get_all("Client Script", fields=["name", "dt", "enabled"], limit_page_length=0)
        result["client_scripts"] = [{"name": s["name"], "dt": s.get("dt", ""), "enabled": s.get("enabled", 0)} for s in cs]
    except Exception:
        result["client_scripts"] = []

    # Server Scripts
    try:
        ss = frappe.get_all("Server Script", fields=["name", "reference_doctype", "doctype_event", "enabled"], limit_page_length=0)
        result["server_scripts"] = [{"name": s["name"], "doctype": s.get("reference_doctype", ""), "event": s.get("doctype_event", ""), "enabled": s.get("enabled", 0)} for s in ss]
    except Exception:
        result["server_scripts"] = []

    # Property Setters
    ps = frappe.get_all("Property Setter", fields=["doc_type", "field_name", "property", "value"], limit_page_length=0)
    result["property_setters"] = len(ps)
    result["property_setter_doctypes"] = list(set(p.get("doc_type", "") for p in ps))

    # Print Formats
    pf = frappe.get_all("Print Format", filters={"standard": "No"}, fields=["name", "doc_type"], limit_page_length=0)
    result["print_formats"] = [{"name": p["name"], "dt": p.get("doc_type", "")} for p in pf]

    # Custom Reports
    rp = frappe.get_all("Report", filters={"is_standard": "No"}, fields=["name", "ref_doctype", "report_type"], limit_page_length=0)
    result["custom_reports"] = [{"name": r["name"], "dt": r.get("ref_doctype", ""), "type": r.get("report_type", "")} for r in rp]

    # Notifications
    notif = frappe.get_all("Notification", fields=["name", "document_type", "event", "enabled"], limit_page_length=0)
    result["notifications"] = [{"name": n["name"], "dt": n.get("document_type", ""), "event": n.get("event", ""), "enabled": n.get("enabled", 0)} for n in notif]

    return result


def _scan_workflows():
    """Scan active workflows."""
    workflows = frappe.get_all("Workflow", fields=["name", "document_type", "is_active"], limit_page_length=0)
    result = []
    for wf in workflows:
        states = frappe.get_all("Workflow Document State", filters={"parent": wf["name"]}, fields=["state", "doc_status", "allow_edit"], order_by="idx", limit_page_length=0)
        transitions = frappe.get_all("Workflow Transition", filters={"parent": wf["name"]}, fields=["state", "action", "next_state", "allowed"], order_by="idx", limit_page_length=0)
        result.append({
            "name": wf["name"],
            "doctype": wf.get("document_type", ""),
            "active": wf.get("is_active", 0),
            "states": [s["state"] for s in states],
            "transitions": ["{0} --({1})--> {2}".format(t["state"], t["action"], t["next_state"]) for t in transitions],
        })
    return result


def _detect_domain(knowledge):
    """Auto-detect business domain based on installed apps and DocTypes."""
    apps = [a["name"].lower() for a in knowledge.get("apps", [])]
    modules = list(knowledge.get("modules", {}).keys())
    modules_lower = [m.lower() for m in modules]

    domain = {"primary": "General Business", "tags": [], "industry": "unknown"}

    # NBFC / Lending
    lending_signals = ["lending", "loan", "nbfc"]
    if any(s in " ".join(apps) for s in lending_signals) or any(s in " ".join(modules_lower) for s in lending_signals):
        domain["primary"] = "NBFC / Lending"
        domain["tags"].extend(["lending", "nbfc", "finance", "loan"])
        domain["industry"] = "financial_services"

    # Manufacturing
    mfg_signals = ["manufacturing", "bom", "work order", "production"]
    if any(s in " ".join(modules_lower) for s in mfg_signals):
        domain["primary"] = "Manufacturing"
        domain["tags"].extend(["manufacturing", "production", "bom"])
        domain["industry"] = "manufacturing"

    # Healthcare
    if "healthcare" in " ".join(apps) or "healthcare" in " ".join(modules_lower):
        domain["primary"] = "Healthcare"
        domain["tags"].extend(["healthcare", "patient", "medical"])
        domain["industry"] = "healthcare"

    # Education
    if "education" in " ".join(apps) or "education" in " ".join(modules_lower):
        domain["primary"] = "Education"
        domain["tags"].extend(["education", "student", "academic"])
        domain["industry"] = "education"

    # Retail / POS
    if "pos" in " ".join(modules_lower) or "retail" in " ".join(modules_lower):
        domain["tags"].append("retail")

    # HR heavy
    if "hrms" in " ".join(apps) or "hr" in " ".join(apps):
        domain["tags"].append("hr")

    # E-commerce
    if "webshop" in " ".join(apps) or "e_commerce" in " ".join(modules_lower):
        domain["tags"].append("ecommerce")

    return domain


def _scan_data_summary():
    """Get record counts for key DocTypes."""
    key_doctypes = [
        "Customer", "Supplier", "Item", "Sales Order", "Purchase Order",
        "Sales Invoice", "Purchase Invoice", "Stock Entry", "Journal Entry",
        "Employee", "Lead", "Opportunity", "Quotation", "Delivery Note",
        "Payment Entry", "BOM", "Work Order", "Project", "Task",
    ]
    summary = {}
    for dt in key_doctypes:
        try:
            count = frappe.db.count(dt)
            if count > 0:
                summary[dt] = count
        except Exception:
            pass
    return summary


def _build_prompt_context(knowledge):
    """Build concise system prompt context from discovered knowledge."""
    lines = []
    lines.append("=== SYSTEM KNOWLEDGE (Auto-Discovered) ===")

    # Apps
    apps = knowledge.get("apps", [])
    app_names = ["{0} ({1})".format(a["name"], a["version"]) for a in apps]
    lines.append("Installed Apps: {0}".format(", ".join(app_names)))

    # Domain
    domain = knowledge.get("domain", {})
    lines.append("Business Domain: {0}".format(domain.get("primary", "General")))
    if domain.get("tags"):
        lines.append("Domain Tags: {0}".format(", ".join(domain["tags"])))

    # Modules summary
    modules = knowledge.get("modules", {})
    total_dt = sum(m["total"] for m in modules.values())
    custom_dt = sum(m["custom_count"] for m in modules.values())
    lines.append("DocTypes: {0} total ({1} custom) across {2} modules".format(total_dt, custom_dt, len(modules)))

    # Top modules by DocType count
    top_modules = sorted(modules.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
    lines.append("Key Modules: {0}".format(", ".join("{0} ({1})".format(m, d["total"]) for m, d in top_modules)))

    # Customizations
    customs = knowledge.get("customizations", {})
    lines.append("Customizations: {0} Custom Fields, {1} Client Scripts, {2} Server Scripts, {3} Property Setters, {4} Print Formats, {5} Custom Reports, {6} Notifications".format(
        customs.get("custom_field_count", 0),
        len(customs.get("client_scripts", [])),
        len(customs.get("server_scripts", [])),
        customs.get("property_setters", 0),
        len(customs.get("print_formats", [])),
        len(customs.get("custom_reports", [])),
        len(customs.get("notifications", [])),
    ))

    # Custom Fields by DocType (top 5)
    cf_by_dt = customs.get("custom_fields", {})
    if cf_by_dt:
        top_cf = sorted(cf_by_dt.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        for dt, fields in top_cf:
            field_names = [f["fieldname"] for f in fields[:5]]
            lines.append("  {0}: {1} custom fields ({2})".format(dt, len(fields), ", ".join(field_names)))

    # Workflows
    workflows = knowledge.get("workflows", [])
    if workflows:
        lines.append("Active Workflows:")
        for wf in workflows:
            if wf.get("active"):
                lines.append("  {0} on {1}: {2}".format(wf["name"], wf["doctype"], " → ".join(wf.get("states", []))))

    # Data summary
    data = knowledge.get("data_summary", {})
    if data:
        data_parts = ["{0}: {1}".format(dt, count) for dt, count in sorted(data.items(), key=lambda x: x[1], reverse=True)]
        lines.append("Record Counts: {0}".format(", ".join(data_parts)))

    lines.append("=== END SYSTEM KNOWLEDGE ===")
    return "\n".join(lines)


def _save_knowledge(knowledge, prompt_context):
    """Save discovery results to Niv Settings."""
    try:
        settings = frappe.get_doc("Niv Settings")

        # Save full JSON for tools/API
        if hasattr(settings, "discovery_json"):
            settings.discovery_json = json.dumps(knowledge, default=str, indent=2)

        # Save prompt context for system prompt injection
        if hasattr(settings, "discovery_context"):
            settings.discovery_context = prompt_context

        # Save timestamp
        if hasattr(settings, "last_discovery"):
            settings.last_discovery = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        settings.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger().info("Niv AI: Knowledge saved to Niv Settings")
    except Exception as e:
        frappe.logger().error("Niv AI: Failed to save knowledge: {0}".format(str(e)))
        # Fallback — save to file
        try:
            import os
            path = frappe.get_site_path("private", "niv_ai_knowledge.json")
            with open(path, "w") as f:
                json.dump({"knowledge": knowledge, "prompt_context": prompt_context}, f, default=str, indent=2)
            frappe.logger().info("Niv AI: Knowledge saved to file: {0}".format(path))
        except Exception:
            pass


def get_discovery_context():
    """Get the discovery context for system prompt injection."""
    try:
        settings = frappe.get_cached_doc("Niv Settings")
        ctx = getattr(settings, "discovery_context", "") or ""
        if ctx:
            return ctx
    except Exception:
        pass

    # Try file fallback
    try:
        import os
        path = frappe.get_site_path("private", "niv_ai_knowledge.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                return data.get("prompt_context", "")
    except Exception:
        pass

    return ""


@frappe.whitelist()
def run_discovery():
    """API endpoint to trigger discovery manually."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can run discovery")
    result = auto_discover_system()
    return {
        "apps": len(result.get("apps", [])),
        "modules": len(result.get("modules", {})),
        "domain": result.get("domain", {}).get("primary", "Unknown"),
        "customizations": result.get("customizations", {}).get("custom_field_count", 0),
        "workflows": len(result.get("workflows", [])),
        "data_records": sum(result.get("data_summary", {}).values()),
    }
