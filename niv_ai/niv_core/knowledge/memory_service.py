"""
Niv AI — Advanced Memory Service

Features:
1. Auto-extract memories from conversations
2. Semantic search for relevant memories
3. Conversation summaries
4. Entity tracking (frequently accessed records)
5. Learning from corrections
6. Memory importance decay

Author: Niv AI Team
"""

import frappe
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any


class AdvancedMemoryService:
    """
    Advanced memory system with auto-extraction and semantic search.
    """
    
    # Memory categories with priorities
    CATEGORIES = {
        "Preference": {"priority": 1, "decay_days": 90},      # User preferences
        "Correction": {"priority": 2, "decay_days": 180},     # User corrections - important!
        "Entity": {"priority": 3, "decay_days": 30},          # Frequently accessed entities
        "Fact": {"priority": 4, "decay_days": 365},           # User facts (company, role)
        "Summary": {"priority": 5, "decay_days": 60},         # Conversation summaries
        "Habit": {"priority": 6, "decay_days": 45},           # Usage patterns
    }
    
    # Keywords for auto-extraction
    PREFERENCE_PATTERNS = {
        "language": ["hindi", "english", "hinglish", "भाषा"],
        "format": ["table", "list", "paragraph", "brief", "detailed"],
        "currency": ["₹", "rs", "inr", "rupees"],
    }
    
    CORRECTION_PATTERNS = [
        "nahi", "galat", "wrong", "correction", "actually", "सही नहीं",
        "not correct", "fix", "change", "update"
    ]
    
    # ─────────────────────────────────────────────────────────────
    # CORE MEMORY OPERATIONS
    # ─────────────────────────────────────────────────────────────
    
    @staticmethod
    def save_memory(
        user: str, 
        key: str, 
        value: str, 
        category: str = "Preference",
        importance: str = "Medium",
        metadata: dict = None
    ) -> str:
        """Save or update a memory."""
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
    
    @staticmethod
    def get_all_memories(user: str, limit: int = 50) -> List[Dict]:
        """Get all memories for a user, sorted by importance and recency."""
        return frappe.get_all(
            "Niv AI Memory",
            filters={"user": user},
            fields=["name", "category", "memory_key", "memory_value", "importance", "last_used"],
            order_by="importance desc, last_used desc",
            limit=limit
        )
    
    @staticmethod
    def get_memories_by_category(user: str, category: str) -> List[Dict]:
        """Get memories of a specific category."""
        return frappe.get_all(
            "Niv AI Memory",
            filters={"user": user, "category": category},
            fields=["memory_key", "memory_value", "importance"],
            order_by="importance desc, last_used desc"
        )
    
    @staticmethod
    def search_memories(user: str, query: str, limit: int = 10) -> List[Dict]:
        """Simple keyword search in memories."""
        query_lower = query.lower()
        all_memories = AdvancedMemoryService.get_all_memories(user, limit=100)
        
        relevant = []
        for m in all_memories:
            key_lower = (m.get("memory_key") or "").lower()
            value_lower = (m.get("memory_value") or "").lower()
            
            # Score based on keyword match
            score = 0
            for word in query_lower.split():
                if word in key_lower:
                    score += 2
                if word in value_lower:
                    score += 1
            
            if score > 0:
                m["relevance_score"] = score
                relevant.append(m)
        
        # Sort by relevance
        relevant.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return relevant[:limit]
    
    # ─────────────────────────────────────────────────────────────
    # AUTO-EXTRACTION
    # ─────────────────────────────────────────────────────────────
    
    @classmethod
    def extract_from_conversation(cls, user: str, user_message: str, ai_response: str) -> List[Dict]:
        """
        Automatically extract memories from a conversation turn.
        Called after each agent response.
        """
        extracted = []
        msg_lower = user_message.lower()
        
        # 1. Detect language preference
        if any(word in msg_lower for word in ["hindi", "हिंदी"]):
            cls.save_memory(user, "language_preference", "Hindi", "Preference", "High")
            extracted.append({"key": "language_preference", "value": "Hindi"})
        elif "english" in msg_lower and "only" in msg_lower:
            cls.save_memory(user, "language_preference", "English", "Preference", "High")
            extracted.append({"key": "language_preference", "value": "English"})
        
        # 2. Detect format preferences
        if "table" in msg_lower and ("format" in msg_lower or "dikhao" in msg_lower or "show" in msg_lower):
            cls.save_memory(user, "output_format", "Table", "Preference", "Medium")
            extracted.append({"key": "output_format", "value": "Table"})
        
        # 3. Detect corrections (important!)
        if any(word in msg_lower for word in cls.CORRECTION_PATTERNS):
            # User is correcting something - save this
            cls.save_memory(
                user, 
                f"correction_{datetime.now().strftime('%Y%m%d_%H%M')}", 
                f"User corrected: {user_message[:200]}", 
                "Correction", 
                "High"
            )
            extracted.append({"key": "correction", "value": user_message[:100]})
        
        # 4. Detect "yaad rakh" / "remember" explicit requests
        if any(word in msg_lower for word in ["yaad rakh", "remember", "save", "note"]):
            # This is handled by the remember_user_preference tool
            pass
        
        return extracted
    
    @classmethod
    def track_entity_access(cls, user: str, doctype: str, docname: str):
        """Track when user accesses specific entities."""
        key = f"entity_{doctype}_{docname}"
        
        existing = frappe.get_all(
            "Niv AI Memory",
            filters={"user": user, "memory_key": key},
            fields=["name", "memory_value"],
            limit=1
        )
        
        if existing:
            # Increment access count
            try:
                data = json.loads(existing[0].memory_value)
                data["access_count"] = data.get("access_count", 0) + 1
                data["last_access"] = datetime.now().isoformat()
            except:
                data = {"access_count": 1, "last_access": datetime.now().isoformat()}
            
            doc = frappe.get_doc("Niv AI Memory", existing[0].name)
            doc.memory_value = json.dumps(data)
            doc.last_used = datetime.now()
            doc.save(ignore_permissions=True)
        else:
            data = {
                "doctype": doctype,
                "docname": docname,
                "access_count": 1,
                "first_access": datetime.now().isoformat(),
                "last_access": datetime.now().isoformat()
            }
            cls.save_memory(user, key, json.dumps(data), "Entity", "Low")
        
        frappe.db.commit()
    
    # ─────────────────────────────────────────────────────────────
    # CONVERSATION SUMMARIES
    # ─────────────────────────────────────────────────────────────
    
    @classmethod
    def save_conversation_summary(cls, user: str, conversation_id: str, summary: str):
        """Save a summary of an important conversation."""
        key = f"conv_summary_{conversation_id[:8]}"
        cls.save_memory(user, key, summary, "Summary", "Medium")
    
    # ─────────────────────────────────────────────────────────────
    # MEMORY FORMATTING FOR LLM
    # ─────────────────────────────────────────────────────────────
    
    @classmethod
    def get_context_for_llm(cls, user: str, current_query: str = "") -> str:
        """
        Get formatted memory context for LLM system prompt.
        Includes relevant memories based on current query.
        """
        memories = cls.get_all_memories(user, limit=30)
        
        if not memories:
            return ""
        
        # Group by category
        by_category = {}
        for m in memories:
            cat = m.get("category", "Other")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(m)
        
        # Format output
        output = "\n=== USER LONG-TERM MEMORY ===\n"
        
        # Preferences first (most important)
        if "Preference" in by_category:
            output += "\n**Preferences:**\n"
            for m in by_category["Preference"][:5]:
                output += f"- {m['memory_key']}: {m['memory_value']}\n"
        
        # Corrections (very important - avoid repeating mistakes)
        if "Correction" in by_category:
            output += "\n**User Corrections (IMPORTANT - don't repeat these mistakes):**\n"
            for m in by_category["Correction"][:3]:
                output += f"- {m['memory_value']}\n"
        
        # Facts about user
        if "Fact" in by_category:
            output += "\n**User Facts:**\n"
            for m in by_category["Fact"][:3]:
                output += f"- {m['memory_key']}: {m['memory_value']}\n"
        
        # Recent conversation summaries
        if "Summary" in by_category:
            output += "\n**Recent Conversations:**\n"
            for m in by_category["Summary"][:2]:
                output += f"- {m['memory_value']}\n"
        
        # Frequently accessed entities
        if "Entity" in by_category:
            top_entities = sorted(
                by_category["Entity"], 
                key=lambda x: json.loads(x.get("memory_value", "{}")).get("access_count", 0),
                reverse=True
            )[:3]
            if top_entities:
                output += "\n**Frequently Accessed:**\n"
                for m in top_entities:
                    try:
                        data = json.loads(m["memory_value"])
                        output += f"- {data.get('doctype')}: {data.get('docname')} ({data.get('access_count')}x)\n"
                    except:
                        pass
        
        output += "\n=== END MEMORY ===\n"
        return output
    
    # ─────────────────────────────────────────────────────────────
    # MEMORY MAINTENANCE
    # ─────────────────────────────────────────────────────────────
    
    @classmethod
    def cleanup_old_memories(cls, user: str = None):
        """Remove old, unused memories based on decay settings."""
        filters = {}
        if user:
            filters["user"] = user
        
        memories = frappe.get_all(
            "Niv AI Memory",
            filters=filters,
            fields=["name", "category", "last_used", "importance"]
        )
        
        deleted = 0
        for m in memories:
            category_config = cls.CATEGORIES.get(m.get("category"), {"decay_days": 90})
            decay_days = category_config["decay_days"]
            
            # High importance memories don't decay
            if m.get("importance") == "High":
                continue
            
            last_used = m.get("last_used")
            if last_used:
                days_old = (datetime.now() - last_used).days
                if days_old > decay_days:
                    frappe.delete_doc("Niv AI Memory", m["name"], ignore_permissions=True)
                    deleted += 1
        
        frappe.db.commit()
        return deleted


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS (for easy import)
# ─────────────────────────────────────────────────────────────

def get_user_context(user: str, query: str = "") -> str:
    """Get memory context for LLM."""
    return AdvancedMemoryService.get_context_for_llm(user, query)

def remember(user: str, key: str, value: str, category: str = "Preference", importance: str = "Medium"):
    """Save a memory."""
    return AdvancedMemoryService.save_memory(user, key, value, category, importance)

def extract_memories(user: str, user_msg: str, ai_response: str):
    """Auto-extract memories from conversation."""
    return AdvancedMemoryService.extract_from_conversation(user, user_msg, ai_response)

def track_entity(user: str, doctype: str, docname: str):
    """Track entity access."""
    return AdvancedMemoryService.track_entity_access(user, doctype, docname)

def search_memory(user: str, query: str):
    """Search memories."""
    return AdvancedMemoryService.search_memories(user, query)
