# Niv AI — Redis Cache Monitor API
# File: niv_ai/niv_core/api/cache_monitor.py

import frappe
import json
from datetime import datetime


@frappe.whitelist()
def get_cache_stats():
    """Get Redis cache statistics for Niv AI.
    
    Returns cache keys, sizes, TTLs grouped by category.
    Only accessible to System Manager.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted", frappe.PermissionError)

    r = frappe.cache()
    stats = {
        "timestamp": datetime.now().isoformat(),
        "categories": {},
        "total_keys": 0,
        "total_size_bytes": 0,
    }

    # Category definitions: name -> key substring to match
    categories = {
        "mcp_tools": "niv_mcp_tools:",
        "unified_discovery": "niv_unified_discovery",
        "system_knowledge": "niv_system_knowledge_graph",
        "triggers": "niv_ai:triggers",
        "tool_tracking": "niv_tool_",
        "voice_tts": "niv_tts_",
        "rate_limiter": "niv_rate_",
        "conversations": "niv_conv_",
    }

    try:
        # Scan all niv keys
        all_keys = list(r.scan_iter(match="*niv*", count=200))

        # Categorize
        categorized = {cat: [] for cat in categories}
        uncategorized = []

        for key in all_keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Remove Frappe site prefix (e.g. "_06d2e6d1428c264c|")
            clean_key = key_str.split("|", 1)[-1] if "|" in key_str else key_str

            matched = False
            for cat, pattern in categories.items():
                if pattern in clean_key:
                    categorized[cat].append((key, clean_key))
                    matched = True
                    break
            if not matched:
                uncategorized.append((key, clean_key))

        # Build stats per category
        for cat, keys in categorized.items():
            cat_size = 0
            key_details = []
            for raw_key, clean_key in keys[:50]:
                try:
                    size = r.strlen(raw_key) or 0
                    ttl = r.ttl(raw_key)
                    cat_size += size
                    key_details.append({
                        "key": clean_key[:80],
                        "size_bytes": size,
                        "size_kb": round(size / 1024, 2),
                        "ttl_seconds": ttl if ttl > 0 else ("no expiry" if ttl == -1 else "expired"),
                    })
                except Exception:
                    pass

            stats["categories"][cat] = {
                "key_count": len(keys),
                "total_size_bytes": cat_size,
                "total_size_kb": round(cat_size / 1024, 2),
                "keys": sorted(key_details, key=lambda x: x.get("size_bytes", 0), reverse=True),
            }
            stats["total_keys"] += len(keys)
            stats["total_size_bytes"] += cat_size

        if uncategorized:
            stats["categories"]["other"] = {
                "key_count": len(uncategorized),
                "keys": [{"key": k[1][:80]} for k in uncategorized[:10]],
            }
            stats["total_keys"] += len(uncategorized)

    except Exception as e:
        stats["error"] = str(e)

    stats["total_size_kb"] = round(stats["total_size_bytes"] / 1024, 2)
    stats["total_size_mb"] = round(stats["total_size_bytes"] / (1024 * 1024), 4)

    return stats


@frappe.whitelist()
def clear_cache(category=None):
    """Clear Niv AI Redis cache by category.
    
    Args:
        category: mcp_tools | unified_discovery | system_knowledge | 
                  triggers | voice_tts | all
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted", frappe.PermissionError)

    patterns = {
        "mcp_tools": "niv_mcp_tools:",
        "unified_discovery": "niv_unified_discovery",
        "system_knowledge": "niv_system_knowledge_graph",
        "triggers": "niv_ai:triggers",
        "voice_tts": "niv_tts_",
    }

    if category and category != "all":
        if category not in patterns:
            frappe.throw(f"Unknown category: {category}")
        patterns = {category: patterns[category]}

    r = frappe.cache()
    cleared = 0
    for cat, pattern in patterns.items():
        try:
            keys = list(r.scan_iter(match=f"*{pattern}*", count=200))
            if keys:
                r.delete(*keys)
                cleared += len(keys)
        except Exception:
            pass

    return {"cleared_keys": cleared, "categories": list(patterns.keys())}
