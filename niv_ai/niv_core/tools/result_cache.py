"""
Tool Result Cache for read-only MCP tools.

Problem: get_doctype_info, search_doctype, report_list return the same data every time,
but are called fresh on every request (wastes ~200ms per call).

Solution: Short-lived worker-memory cache for read-only tools.
Cache keys include tool_name + args hash. TTL = 2 minutes.

Usage: Called by langchain/tools.py in _make_mcp_executor()
"""
import hashlib
import json
import time
import threading


# Read-only tools safe to cache (no side effects)
CACHEABLE_TOOLS = {
    "get_doctype_info",
    "search_doctype",
    "report_list",
    "report_requirements",
    "search_link",
}

# Cache storage: {cache_key: (result_string, expires_timestamp)}
_result_cache = {}
_cache_lock = threading.Lock()

# Cache configuration
CACHE_TTL = 120  # 2 minutes
MAX_CACHE_SIZE = 200  # Maximum entries before cleanup


def get_cached_result(tool_name: str, arguments: dict) -> str:
    """Get a cached result for a read-only tool call.
    
    Returns:
        Cached result string, or None if not cached or expired.
    """
    if tool_name not in CACHEABLE_TOOLS:
        return None
    
    key = _make_key(tool_name, arguments)
    
    with _cache_lock:
        entry = _result_cache.get(key)
        if entry is None:
            return None
        
        result, expires = entry
        if time.time() > expires:
            # Expired — remove and return None
            _result_cache.pop(key, None)
            return None
        
        return result


def set_cached_result(tool_name: str, arguments: dict, result: str):
    """Cache a result for a read-only tool call.
    
    Only caches if:
    - Tool is in CACHEABLE_TOOLS
    - Result is not an error
    - Result is not too large (< 10KB)
    """
    if tool_name not in CACHEABLE_TOOLS:
        return
    
    # Don't cache errors
    if '"error"' in result[:100]:
        return
    
    # Don't cache very large results (schema tools should be small)
    if len(result) > 10000:
        return
    
    key = _make_key(tool_name, arguments)
    
    with _cache_lock:
        # Cleanup if cache is getting too large
        if len(_result_cache) >= MAX_CACHE_SIZE:
            _evict_expired()
        
        _result_cache[key] = (result, time.time() + CACHE_TTL)


def clear_cache():
    """Clear all cached results. Call when tools change."""
    with _cache_lock:
        _result_cache.clear()


def _make_key(tool_name: str, arguments: dict) -> str:
    """Generate a cache key from tool name + arguments."""
    args_str = json.dumps(arguments, sort_keys=True, default=str)
    args_hash = hashlib.md5(args_str.encode()).hexdigest()
    return f"{tool_name}:{args_hash}"


def _evict_expired():
    """Remove expired entries from cache. Called with lock held."""
    now = time.time()
    expired_keys = [k for k, (_, exp) in _result_cache.items() if exp < now]
    for k in expired_keys:
        _result_cache.pop(k, None)
    
    # If still too large after removing expired, remove oldest entries
    if len(_result_cache) >= MAX_CACHE_SIZE:
        # Sort by expiry and remove oldest half
        sorted_entries = sorted(_result_cache.items(), key=lambda x: x[1][1])
        to_remove = len(_result_cache) // 2
        for key, _ in sorted_entries[:to_remove]:
            _result_cache.pop(key, None)
