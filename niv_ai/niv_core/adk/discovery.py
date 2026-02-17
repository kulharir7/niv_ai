"""
Discovery Agent — Systems Introspection & RAG Seeding.
Scans Frappe metadata to make Niv AI "Smart from Start".
"""
import json
import frappe
from typing import List, Dict, Any

class DiscoveryEngine:
    def __init__(self):
        self.summary_key = "niv_system_discovery_map"

    def run_full_scan(self):
        """Perform a comprehensive system audit."""
        discovery_data = {
            "custom_doctypes": self._get_custom_doctypes(),
            "active_workflows": self._get_active_workflows(),
            "nbfc_related": self._get_nbfc_context(),
            "timestamp": frappe.utils.now_datetime()
        }
        
        # Save to Redis for fast access by all agents
        frappe.cache().set_value(self.summary_key, json.dumps(discovery_data, default=str))
        
        # Also log as a 'Lesson' for the RAG system
        self._log_to_brain(discovery_data)
        
        return discovery_data

    def _get_custom_doctypes(self) -> List[Dict]:
        """Fetch custom DocTypes and their primary purpose."""
        # Focus on DocTypes created by users or in 'Custom' module
        doctypes = frappe.get_all("DocType", 
            filters={"custom": 1}, 
            fields=["name", "module", "description"]
        )
        return doctypes

    def _get_active_workflows(self) -> List[Dict]:
        """Fetch all active workflows and the DocTypes they control."""
        workflows = frappe.get_all("Workflow", 
            filters={"is_active": 1},
            fields=["name", "document_type"]
        )
        return workflows

    def _get_nbfc_context(self) -> Dict:
        """Specific logic for NBFC/Growth System sites."""
        nbfc_keywords = ["Loan", "EMI", "Repayment", "Disbursement", "Collateral", "Borrower", "Interest", "LMS", "LOS"]
        all_dt = frappe.get_all("DocType", fields=["name", "module"])
        
        matches = [d.name for d in all_dt if any(k.lower() in d.name.lower() for k in nbfc_keywords)]
        
        # Identify core NBFC modules
        modules = list(set([d.module for d in all_dt if any(k.lower() in (d.module or "").lower() for k in nbfc_keywords)]))
        
        return {
            "relevant_doctypes": matches,
            "relevant_modules": modules
        }

    def _log_to_brain(self, data: Dict):
        """Convert raw data to a natural language summary for RAG."""
        summary = ["### System Discovery Summary"]
        
        if data.get("custom_doctypes"):
            summary.append("\n**Custom DocTypes Found:**")
            for dt in data["custom_doctypes"]:
                summary.append(f"- `{dt['name']}` (Module: {dt['module']})")
        
        if data.get("active_workflows"):
            summary.append("\n**Active Workflows:**")
            for wf in data["active_workflows"]:
                summary.append(f"- `{wf['name']}` controls `{wf['document_type']}`")

        if data.get("correction"):
            summary.append(f"\n**Correction/Learning:**\n{data['correction']}")

        # Push to Niv Brain Log (if exists) or just log
        try:
            # We will create this DocType in Phase 2 if it doesn't exist
            if frappe.db.exists("DocType", "Niv Brain Log"):
                frappe.get_doc({
                    "doctype": "Niv Brain Log",
                    "topic": "System Discovery",
                    "content": "\n".join(summary),
                    "tags": "discovery, system_map"
                }).insert(ignore_permissions=True)
                frappe.db.commit()
        except Exception:
            pass
        
        # For now, append to a static file for debugging
        # Path: niv_ai/niv_core/knowledge/system_discovery.md
        try:
            import os
            path = frappe.get_app_path("niv_ai", "niv_core", "knowledge", "system_discovery.md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(summary))
        except Exception:
            pass

def trigger_discovery():
    """Whitelisted function to manually start discovery."""
    engine = DiscoveryEngine()
    return engine.run_full_scan()
