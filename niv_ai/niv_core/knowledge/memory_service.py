
import frappe
import json
from datetime import datetime

class MemoryService:
    """
    Handles persistent memory for Niv AI users.
    """
    
    @staticmethod
    def get_user_memory(user: str) -> str:
        """Fetch all memories for a user as a formatted string for LLM."""
        memories = frappe.get_all(
            "Niv AI Memory",
            filters={"user": user},
            fields=["category", "memory_key", "memory_value", "importance"],
            order_by="importance desc, modified desc"
        )
        
        if not memories:
            return "No prior user preferences or memories found."
            
        formatted = "USER LONG-TERM MEMORY:\n"
        for m in memories:
            formatted += f"- [{m.category}] {m.memory_key}: {m.memory_value} (Importance: {m.importance})\n"
        
        return formatted

    @staticmethod
    def save_memory(user: str, key: str, value: str, category: str = "Preference", importance: str = "Medium"):
        """Save or update a memory for a user."""
        existing = frappe.get_all(
            "Niv AI Memory",
            filters={"user": user, "memory_key": key},
            limit=1
        )
        
        if existing:
            doc = frappe.get_doc("Niv AI Memory", existing[0].name)
            doc.memory_value = value
            doc.category = category
            doc.importance = importance
            doc.last_used = datetime.now()
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.new_doc("Niv AI Memory")
            doc.user = user
            doc.memory_key = key
            doc.memory_value = value
            doc.category = category
            doc.importance = importance
            doc.last_used = datetime.now()
            doc.insert(ignore_permissions=True)
            
        frappe.db.commit()
        return doc.name

def get_memories(user: str):
    return MemoryService.get_user_memory(user)

def remember(user: str, key: str, value: str, category: str = "Preference"):
    return MemoryService.save_memory(user, key, value, category)
