"""
Niv AI — Unified Discovery System (v2)

COMBINES all 3 discovery files into ONE reliable system:
1. Full system scan (apps, modules, doctypes, customizations, workflows)
2. DocType relationships mapping (links, child tables)
3. Domain detection (NBFC, Manufacturing, Healthcare etc.)
4. Redis caching for instant agent access
5. Auto-run on startup, manual trigger available

REPLACES:
- niv_core/discovery.py (partial)
- adk/discovery.py (duplicate)
- knowledge/system_map.py (relationships only)

Author: Niv AI Team
Version: 2.0.0
"""

import json
import frappe
from datetime import datetime
from typing import Dict, List, Any, Optional


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

CACHE_KEY = "niv_unified_discovery"
CACHE_TTL = 3600  # 1 hour
GRAPH_CACHE_KEY = "niv_system_knowledge_graph"  # Keep for backward compat

# Frappe core modules to exclude (internal framework stuff)
FRAPPE_CORE_MODULES = {
    "Core", "Desk", "Email", "Printing", "Workflow", "Website",
    "Integrations", "Automation", "Event Streaming", "Social",
    "Data Migration", "Contacts", "Geo"
}


# ═══════════════════════════════════════════════════════════════════
# MAIN DISCOVERY CLASS
# ═══════════════════════════════════════════════════════════════════

class UnifiedDiscovery:
    """
    Single source of truth for system knowledge.
    
    Usage:
        discovery = UnifiedDiscovery()
        data = discovery.run_full_scan()
        
        # Or get cached data (fast)
        data = discovery.get_cached()
    """
    
    def __init__(self):
        self.data = {
            "timestamp": None,
            "apps": [],
            "domain": {},
            "modules": {},
            "doctypes": {},
            "relationships": [],
            "customizations": {},
            "workflows": [],
            "data_summary": {},
            "prompt_context": ""
        }
    
    # ─────────────────────────────────────────────────────────────
    # PUBLIC METHODS
    # ─────────────────────────────────────────────────────────────
    
    def run_full_scan(self, force: bool = False) -> Dict:
        """
        Run comprehensive system scan.
        
        Args:
            force: If True, bypass cache and scan fresh
            
        Returns:
            Complete discovery data dict
        """
        # Check cache first (unless forced)
        if not force:
            cached = self.get_cached()
            if cached:
                return cached
        
        frappe.logger("niv_ai").info("Starting unified discovery scan...")
        
        try:
            # 1. Scan installed apps
            self.data["apps"] = self._scan_apps()
            
            # 2. Scan modules and DocTypes
            self._scan_modules_and_doctypes()
            
            # 3. Map DocType relationships (Links, Tables)
            self._map_relationships()
            
            # 4. Detect business domain
            self.data["domain"] = self._detect_domain()
            
            # 5. Scan customizations
            self.data["customizations"] = self._scan_customizations()
            
            # 6. Scan active workflows
            self.data["workflows"] = self._scan_workflows()
            
            # 7. Get data summary (record counts)
            self.data["data_summary"] = self._scan_data_summary()
            
            # 8. Build prompt context for agents
            self.data["prompt_context"] = self._build_prompt_context()
            
            # 9. Set timestamp
            self.data["timestamp"] = datetime.now().isoformat()
            
            # 10. Save to cache
            self._save_to_cache()
            
            frappe.logger("niv_ai").info("Unified discovery complete!")
            return self.data
            
        except Exception as e:
            frappe.log_error(f"Unified discovery failed: {e}", "Niv AI Discovery")
            return self.data
    
    def get_cached(self) -> Optional[Dict]:
        """Get cached discovery data (fast path)."""
        try:
            cached = frappe.cache().get_value(CACHE_KEY)
            if cached:
                if isinstance(cached, str):
                    return json.loads(cached)
                return cached
        except Exception:
            pass
        return None
    
    def get_for_agent(self) -> str:
        """
        Get discovery data formatted for agent system prompt.
        This is what agents should use.
        
        Returns:
            Formatted string for system prompt injection
        """
        data = self.get_cached()
        if not data:
            data = self.run_full_scan()
        
        return data.get("prompt_context", "System discovery not available.")
    
    def get_knowledge_graph(self) -> Dict:
        """
        Get data in knowledge graph format (for visualization).
        Backward compatible with system_map.py
        
        Returns:
            Dict with doctypes, links, modules keys
        """
        data = self.get_cached()
        if not data:
            data = self.run_full_scan()
        
        return {
            "doctypes": data.get("doctypes", {}),
            "links": data.get("relationships", []),
            "modules": data.get("modules", {})
        }
    
    def get_doctype_list(self, limit: int = 100) -> List[str]:
        """Get list of DocType names (for quick reference)."""
        data = self.get_cached()
        if not data:
            data = self.run_full_scan()
        
        doctypes = list(data.get("doctypes", {}).keys())
        return doctypes[:limit]
    
    # ─────────────────────────────────────────────────────────────
    # SCAN METHODS
    # ─────────────────────────────────────────────────────────────
    
    def _scan_apps(self) -> List[Dict]:
        """Scan installed Frappe apps."""
        apps = []
        for app_name in frappe.get_installed_apps():
            app_info = {"name": app_name, "version": "unknown"}
            try:
                import importlib
                mod = importlib.import_module(app_name)
                app_info["version"] = getattr(mod, "__version__", "unknown")
            except Exception:
                pass
            apps.append(app_info)
        return apps
    
    def _scan_modules_and_doctypes(self):
        """Scan all modules and their DocTypes with full metadata."""
        modules = {}
        doctypes = {}
        
        # Get all non-table, non-single DocTypes
        all_dt = frappe.get_all(
            "DocType",
            filters=[["istable", "=", 0]],
            fields=["name", "module", "istable", "issingle", "custom", "description"],
            limit_page_length=0
        )
        
        for dt in all_dt:
            dt_name = dt["name"]
            module = dt.get("module") or "Other"
            
            # Skip Frappe core modules (unless custom)
            if module in FRAPPE_CORE_MODULES and not dt.get("custom"):
                continue
            
            # Module grouping
            if module not in modules:
                modules[module] = {
                    "doctypes": [],
                    "total": 0,
                    "custom_count": 0
                }
            modules[module]["doctypes"].append(dt_name)
            modules[module]["total"] += 1
            if dt.get("custom"):
                modules[module]["custom_count"] += 1
            
            # DocType details
            try:
                meta = frappe.get_meta(dt_name)
                fields = []
                links = []
                child_tables = []
                
                for field in meta.fields:
                    field_info = {
                        "fieldname": field.fieldname,
                        "label": field.label or field.fieldname,
                        "fieldtype": field.fieldtype,
                        "reqd": field.reqd or 0
                    }
                    fields.append(field_info)
                    
                    # Track Link fields
                    if field.fieldtype == "Link" and field.options:
                        links.append({
                            "field": field.fieldname,
                            "target": field.options
                        })
                    
                    # Track Child Tables
                    if field.fieldtype in ("Table", "Table MultiSelect") and field.options:
                        child_tables.append({
                            "field": field.fieldname,
                            "target": field.options
                        })
                
                doctypes[dt_name] = {
                    "name": dt_name,
                    "module": module,
                    "custom": dt.get("custom", 0),
                    "issingle": dt.get("issingle", 0),
                    "description": dt.get("description") or "",
                    "field_count": len(fields),
                    "fields": fields[:30],  # Limit to avoid bloat
                    "links": links,
                    "child_tables": child_tables
                }
            except Exception as e:
                # Minimal info if meta fails
                doctypes[dt_name] = {
                    "name": dt_name,
                    "module": module,
                    "custom": dt.get("custom", 0),
                    "error": str(e)
                }
        
        self.data["modules"] = modules
        self.data["doctypes"] = doctypes
    
    def _map_relationships(self):
        """Build relationship graph from DocType links."""
        relationships = []
        
        for dt_name, dt_info in self.data["doctypes"].items():
            # Link relationships
            for link in dt_info.get("links", []):
                relationships.append({
                    "source": dt_name,
                    "target": link["target"],
                    "type": "link",
                    "field": link["field"]
                })
            
            # Child table relationships
            for child in dt_info.get("child_tables", []):
                relationships.append({
                    "source": dt_name,
                    "target": child["target"],
                    "type": "child_table",
                    "field": child["field"]
                })
        
        self.data["relationships"] = relationships
    
    def _detect_domain(self) -> Dict:
        """Auto-detect business domain."""
        apps = [a["name"].lower() for a in self.data.get("apps", [])]
        modules = list(self.data.get("modules", {}).keys())
        modules_lower = [m.lower() for m in modules]
        doctypes_lower = [d.lower() for d in self.data.get("doctypes", {}).keys()]
        
        all_text = " ".join(apps + modules_lower + doctypes_lower)
        
        domain = {
            "primary": "General Business",
            "tags": [],
            "industry": "general",
            "confidence": "low"
        }
        
        # NBFC / Lending detection
        nbfc_keywords = ["loan", "lending", "nbfc", "emi", "disbursement", "repayment", "borrower", "collateral", "lms", "los"]
        nbfc_score = sum(1 for k in nbfc_keywords if k in all_text)
        if nbfc_score >= 3:
            domain["primary"] = "NBFC / Lending"
            domain["tags"] = ["lending", "nbfc", "finance", "loan"]
            domain["industry"] = "financial_services"
            domain["confidence"] = "high" if nbfc_score >= 5 else "medium"
        
        # Manufacturing detection
        mfg_keywords = ["manufacturing", "bom", "work order", "production", "operation", "routing"]
        mfg_score = sum(1 for k in mfg_keywords if k in all_text)
        if mfg_score >= 2 and domain["primary"] == "General Business":
            domain["primary"] = "Manufacturing"
            domain["tags"] = ["manufacturing", "production", "bom"]
            domain["industry"] = "manufacturing"
            domain["confidence"] = "medium"
        
        # Healthcare detection
        if "healthcare" in all_text or "patient" in all_text:
            domain["primary"] = "Healthcare"
            domain["tags"] = ["healthcare", "patient", "medical"]
            domain["industry"] = "healthcare"
            domain["confidence"] = "medium"
        
        # Education detection
        if "education" in all_text or "student" in all_text:
            domain["primary"] = "Education"
            domain["tags"] = ["education", "student", "academic"]
            domain["industry"] = "education"
            domain["confidence"] = "medium"
        
        # Additional tags
        if "hrms" in all_text or "employee" in all_text:
            if "hr" not in domain["tags"]:
                domain["tags"].append("hr")
        
        if "ecommerce" in all_text or "webshop" in all_text:
            if "ecommerce" not in domain["tags"]:
                domain["tags"].append("ecommerce")
        
        return domain
    
    def _scan_customizations(self) -> Dict:
        """Scan custom fields, scripts, etc."""
        result = {
            "custom_fields": {},
            "custom_field_count": 0,
            "client_scripts": [],
            "server_scripts": [],
            "property_setters": 0,
            "print_formats": [],
            "custom_reports": [],
            "notifications": []
        }
        
        try:
            # Custom Fields grouped by DocType
            cf = frappe.get_all(
                "Custom Field",
                fields=["dt", "fieldname", "fieldtype", "label"],
                limit_page_length=0
            )
            cf_by_dt = {}
            for f in cf:
                dt = f.get("dt", "Unknown")
                if dt not in cf_by_dt:
                    cf_by_dt[dt] = []
                cf_by_dt[dt].append({
                    "fieldname": f["fieldname"],
                    "fieldtype": f["fieldtype"],
                    "label": f.get("label", "")
                })
            result["custom_fields"] = cf_by_dt
            result["custom_field_count"] = len(cf)
        except Exception:
            pass
        
        try:
            # Client Scripts
            cs = frappe.get_all(
                "Client Script",
                fields=["name", "dt", "enabled"],
                limit_page_length=0
            )
            result["client_scripts"] = [
                {"name": s["name"], "dt": s.get("dt", ""), "enabled": s.get("enabled", 0)}
                for s in cs
            ]
        except Exception:
            pass
        
        try:
            # Server Scripts
            ss = frappe.get_all(
                "Server Script",
                fields=["name", "reference_doctype", "script_type", "enabled"],
                limit_page_length=0
            )
            result["server_scripts"] = [
                {"name": s["name"], "doctype": s.get("reference_doctype", ""), "type": s.get("script_type", ""), "enabled": s.get("enabled", 0)}
                for s in ss
            ]
        except Exception:
            pass
        
        try:
            # Property Setters count
            ps_count = frappe.db.count("Property Setter")
            result["property_setters"] = ps_count
        except Exception:
            pass
        
        try:
            # Custom Print Formats
            pf = frappe.get_all(
                "Print Format",
                filters={"standard": "No"},
                fields=["name", "doc_type"],
                limit_page_length=0
            )
            result["print_formats"] = [{"name": p["name"], "dt": p.get("doc_type", "")} for p in pf]
        except Exception:
            pass
        
        try:
            # Custom Reports
            rp = frappe.get_all(
                "Report",
                filters={"is_standard": "No"},
                fields=["name", "ref_doctype", "report_type"],
                limit_page_length=0
            )
            result["custom_reports"] = [{"name": r["name"], "dt": r.get("ref_doctype", ""), "type": r.get("report_type", "")} for r in rp]
        except Exception:
            pass
        
        return result
    
    def _scan_workflows(self) -> List[Dict]:
        """Scan active workflows with states and transitions."""
        workflows = []
        try:
            wf_list = frappe.get_all(
                "Workflow",
                filters={"is_active": 1},
                fields=["name", "document_type"],
                limit_page_length=0
            )
            
            for wf in wf_list:
                states = frappe.get_all(
                    "Workflow Document State",
                    filters={"parent": wf["name"]},
                    fields=["state", "doc_status"],
                    order_by="idx",
                    limit_page_length=0
                )
                
                transitions = frappe.get_all(
                    "Workflow Transition",
                    filters={"parent": wf["name"]},
                    fields=["state", "action", "next_state", "allowed"],
                    order_by="idx",
                    limit_page_length=0
                )
                
                workflows.append({
                    "name": wf["name"],
                    "doctype": wf.get("document_type", ""),
                    "states": [s["state"] for s in states],
                    "transitions": [
                        f"{t['state']} --({t['action']})--> {t['next_state']}"
                        for t in transitions
                    ]
                })
        except Exception:
            pass
        
        return workflows
    
    def _scan_data_summary(self) -> Dict:
        """Get record counts for key DocTypes."""
        key_doctypes = [
            "Customer", "Supplier", "Item", "Sales Order", "Purchase Order",
            "Sales Invoice", "Purchase Invoice", "Stock Entry", "Journal Entry",
            "Employee", "Lead", "Opportunity", "Quotation", "Delivery Note",
            "Payment Entry", "BOM", "Work Order", "Project", "Task",
            "Loan", "Loan Application", "Repayment Schedule"  # NBFC
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
    
    # ─────────────────────────────────────────────────────────────
    # PROMPT CONTEXT
    # ─────────────────────────────────────────────────────────────
    
    def _build_prompt_context(self) -> str:
        """Build concise context string for agent system prompts."""
        lines = []
        lines.append("=== SYSTEM KNOWLEDGE (Live Scan) ===")
        
        # Apps
        apps = self.data.get("apps", [])
        if apps:
            app_list = ", ".join(f"{a['name']}({a['version']})" for a in apps[:10])
            lines.append(f"Apps: {app_list}")
        
        # Domain
        domain = self.data.get("domain", {})
        lines.append(f"Domain: {domain.get('primary', 'General')} [{domain.get('confidence', 'low')}]")
        if domain.get("tags"):
            lines.append(f"Tags: {', '.join(domain['tags'])}")
        
        # DocTypes summary
        doctypes = self.data.get("doctypes", {})
        modules = self.data.get("modules", {})
        total_dt = len(doctypes)
        custom_dt = sum(1 for d in doctypes.values() if d.get("custom"))
        lines.append(f"DocTypes: {total_dt} total ({custom_dt} custom) in {len(modules)} modules")
        
        # Top modules
        top_modules = sorted(modules.items(), key=lambda x: x[1]["total"], reverse=True)[:8]
        if top_modules:
            mod_list = ", ".join(f"{m}({d['total']})" for m, d in top_modules)
            lines.append(f"Modules: {mod_list}")
        
        # Key DocTypes by module (business relevant)
        lines.append("\nKey DocTypes:")
        for mod_name, mod_data in list(modules.items())[:5]:
            dt_list = mod_data.get("doctypes", [])[:5]
            if dt_list:
                lines.append(f"  {mod_name}: {', '.join(dt_list)}")
        
        # Customizations
        customs = self.data.get("customizations", {})
        cf_count = customs.get("custom_field_count", 0)
        cs_count = len(customs.get("client_scripts", []))
        ss_count = len(customs.get("server_scripts", []))
        if cf_count or cs_count or ss_count:
            lines.append(f"\nCustomizations: {cf_count} fields, {cs_count} client scripts, {ss_count} server scripts")
        
        # Workflows
        workflows = self.data.get("workflows", [])
        if workflows:
            lines.append(f"\nActive Workflows ({len(workflows)}):")
            for wf in workflows[:5]:
                states = " → ".join(wf.get("states", [])[:5])
                lines.append(f"  {wf['doctype']}: {states}")
        
        # Data summary
        data_summary = self.data.get("data_summary", {})
        if data_summary:
            data_parts = [f"{dt}:{count}" for dt, count in sorted(data_summary.items(), key=lambda x: x[1], reverse=True)[:10]]
            lines.append(f"\nRecords: {', '.join(data_parts)}")
        
        lines.append("\n=== END SYSTEM KNOWLEDGE ===")
        return "\n".join(lines)
    
    # ─────────────────────────────────────────────────────────────
    # CACHE
    # ─────────────────────────────────────────────────────────────
    
    def _save_to_cache(self):
        """Save discovery data to Redis cache."""
        try:
            # Main cache
            frappe.cache().set_value(
                CACHE_KEY,
                json.dumps(self.data, default=str),
                expires_in_sec=CACHE_TTL
            )
            
            # Backward compatible graph cache (for old code)
            graph_data = {
                "doctypes": self.data.get("doctypes", {}),
                "links": self.data.get("relationships", []),
                "modules": self.data.get("modules", {})
            }
            frappe.cache().set_value(
                GRAPH_CACHE_KEY,
                json.dumps(graph_data, default=str),
                expires_in_sec=CACHE_TTL
            )
            
            frappe.logger("niv_ai").info("Discovery data cached successfully")
        except Exception as e:
            frappe.log_error(f"Failed to cache discovery: {e}", "Niv AI Discovery")


# ═══════════════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS (for easy import)
# ═══════════════════════════════════════════════════════════════════

def run_discovery(force: bool = False) -> Dict:
    """Run full system discovery."""
    discovery = UnifiedDiscovery()
    return discovery.run_full_scan(force=force)


def get_discovery_for_agent() -> str:
    """Get discovery context for agent system prompt."""
    discovery = UnifiedDiscovery()
    return discovery.get_for_agent()


def get_knowledge_graph() -> Dict:
    """Get knowledge graph (backward compatible)."""
    discovery = UnifiedDiscovery()
    return discovery.get_knowledge_graph()


def get_doctype_list(limit: int = 100) -> List[str]:
    """Get list of DocType names."""
    discovery = UnifiedDiscovery()
    return discovery.get_doctype_list(limit=limit)


def get_cached_discovery() -> Optional[Dict]:
    """Get cached discovery data."""
    discovery = UnifiedDiscovery()
    return discovery.get_cached()


# ═══════════════════════════════════════════════════════════════════
# WHITELISTED API
# ═══════════════════════════════════════════════════════════════════

@frappe.whitelist()
def trigger_discovery():
    """API endpoint to trigger discovery (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can run discovery")
    
    data = run_discovery(force=True)
    
    return {
        "success": True,
        "timestamp": data.get("timestamp"),
        "domain": data.get("domain", {}).get("primary", "Unknown"),
        "doctypes": len(data.get("doctypes", {})),
        "modules": len(data.get("modules", {})),
        "workflows": len(data.get("workflows", [])),
        "customizations": data.get("customizations", {}).get("custom_field_count", 0)
    }


@frappe.whitelist()
def get_discovery_summary():
    """Get discovery summary (cached, fast)."""
    data = get_cached_discovery()
    if not data:
        return {"cached": False, "message": "Run discovery first"}
    
    return {
        "cached": True,
        "timestamp": data.get("timestamp"),
        "domain": data.get("domain", {}),
        "doctype_count": len(data.get("doctypes", {})),
        "module_count": len(data.get("modules", {})),
        "workflow_count": len(data.get("workflows", []))
    }
