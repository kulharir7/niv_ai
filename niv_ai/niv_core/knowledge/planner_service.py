
import frappe
import json

class PlannerService:
    """
    Handles multi-step project planning and execution tracking.
    """
    
    @staticmethod
    def create_plan(user: str, title: str, steps_list: list) -> str:
        """Create a new task plan in DB."""
        doc = frappe.new_doc("Niv Task Plan")
        doc.user = user
        doc.title = title
        doc.total_steps = len(steps_list)
        
        for i, s in enumerate(steps_list):
            doc.append("steps", {
                "step_number": i + 1,
                "description": s.get("description"),
                "assigned_agent": s.get("agent", "niv_orchestrator"),
                "status": "Pending"
            })
            
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    @staticmethod
    def get_plan_status(plan_id: str) -> str:
        """Get formatted plan status for the LLM."""
        try:
            doc = frappe.get_doc("Niv Task Plan", plan_id)
            status_text = f"PLAN: {doc.title} ({doc.status})\n"
            status_text += f"Progress: {doc.current_step_index}/{doc.total_steps} steps\n\n"
            
            for s in doc.steps:
                mark = "✅" if s.status == "Completed" else "⏳" if s.status == "In Progress" else "⭕"
                status_text += f"{mark} Step {s.step_number}: {s.description} (Agent: {s.assigned_agent})\n"
                if s.result:
                    status_text += f"   Result: {s.result[:100]}...\n"
                    
            return status_text
        except Exception as e:
            return f"Error fetching plan: {e}"

    @staticmethod
    def update_step(plan_id: str, step_num: int, status: str, result: str = None):
        """Update a specific step and advance the plan index."""
        doc = frappe.get_doc("Niv Task Plan", plan_id)
        for s in doc.steps:
            if s.step_number == step_num:
                s.status = status
                if result:
                    s.result = result
                break
        
        if status == "Completed" and step_num == doc.current_step_index:
            doc.current_step_index += 1
            
        if doc.current_step_index > doc.total_steps:
            doc.status = "Completed"
            
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return True

def create_plan(user: str, title: str, steps: list):
    return PlannerService.create_plan(user, title, steps)

def update_plan(plan_id: str, step_num: int, status: str, result: str = None):
    return PlannerService.update_step(plan_id, step_num, status, result)

def get_plan(plan_id: str):
    return PlannerService.get_plan_status(plan_id)
