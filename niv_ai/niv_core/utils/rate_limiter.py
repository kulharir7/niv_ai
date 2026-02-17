"""
Redis-based rate limiting for Niv AI API endpoints.
Uses Frappe's Redis cache with sliding window counters.
"""
import frappe
import time
import math


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    def __init__(self, message, retry_after=60):
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


def _get_limits():
    """Get rate limits from Niv Settings with defaults."""
    try:
        settings = frappe.get_single("Niv Settings")
        return {
            "per_minute": int(getattr(settings, "rate_limit_per_minute", 0) or 30),
            "per_hour": int(getattr(settings, "rate_limit_per_hour", 0) or 500),
            "per_day": int(getattr(settings, "rate_limit_per_day", 0) or 5000),
            "guest_per_minute": 10,
        }
    except Exception:
        return {"per_minute": 30, "per_hour": 500, "per_day": 5000, "guest_per_minute": 10}


def _get_cache():
    """Get Frappe Redis cache."""
    return frappe.cache()


def check_rate_limit(user=None):
    """
    Check rate limits for a user or IP. Raises RateLimitExceeded if exceeded.
    
    Uses Redis sorted sets with timestamp-based sliding windows.
    """
    user = user or frappe.session.user
    limits = _get_limits()
    cache = _get_cache()
    now = time.time()

    if user == "Guest":
        # IP-based limiting for guests
        ip = frappe.local.request.remote_addr if hasattr(frappe.local, "request") and frappe.request else "unknown"
        key = f"niv_rate:ip:{ip}"
        _check_window(cache, key, now, limits["guest_per_minute"], 60, "Too many requests. Please wait.")
        return

    # Per-user limits
    windows = [
        (f"niv_rate:user:{user}:min", limits["per_minute"], 60, "Rate limit exceeded. Please wait a moment."),
        (f"niv_rate:user:{user}:hour", limits["per_hour"], 3600, "Hourly limit reached. Please try again later."),
        (f"niv_rate:user:{user}:day", limits["per_day"], 86400, "Daily limit reached. Try again tomorrow."),
    ]

    for key, limit, window, msg in windows:
        _check_window(cache, key, now, limit, window, msg)


def _check_window(cache, key, now, limit, window_seconds, message):
    """Check a single sliding window rate limit using Redis."""
    try:
        # Clean old entries and count current
        window_start = now - window_seconds
        
        # Use pipeline for atomicity
        pipe = cache.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = pipe.execute()
        
        count = results[1] if len(results) > 1 else 0

        if count >= limit:
            # Calculate retry-after from oldest entry in window
            oldest = cache.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(oldest[0][1] + window_seconds - now))
            else:
                retry_after = int(window_seconds / 2)
            raise RateLimitExceeded(message, retry_after=retry_after)

        # Add current request
        pipe2 = cache.pipeline()
        pipe2.zadd(key, {str(now): now})
        pipe2.expire(key, window_seconds + 10)
        pipe2.execute()

    except RateLimitExceeded:
        raise
    except Exception:
        # If Redis fails, allow the request (fail-open)
        pass


def record_request(user=None):
    """Record a request without checking (for endpoints that check separately)."""
    # check_rate_limit already records, this is a no-op alias
    pass
