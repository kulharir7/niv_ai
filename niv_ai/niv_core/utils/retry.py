"""
Retry logic with exponential backoff for AI API calls.
"""
import time
import requests
import frappe


def get_timeout_settings():
    """Get timeout/retry settings from Niv Settings."""
    try:
        settings = frappe.get_single("Niv Settings")
        return {
            "api_timeout": int(getattr(settings, "api_timeout", 0) or 60),
            "max_retries": int(getattr(settings, "max_retries", 0) or 3),
            "tool_timeout": 30,
        }
    except Exception:
        return {"api_timeout": 60, "max_retries": 3, "tool_timeout": 30}


def request_with_retry(method, url, retryable_codes=(429, 503), **kwargs):
    """
    Make an HTTP request with retry on transient errors.
    
    Args:
        method: 'get' or 'post'
        url: request URL
        retryable_codes: HTTP status codes to retry on
        **kwargs: passed to requests.request (headers, json, timeout, stream, etc.)
    
    Returns:
        requests.Response
    """
    config = get_timeout_settings()
    max_retries = config["max_retries"]
    
    # Set default timeout if not provided
    if "timeout" not in kwargs:
        kwargs["timeout"] = config["api_timeout"]

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.request(method, url, **kwargs)
            
            if response.status_code in retryable_codes and attempt < max_retries:
                # Get retry-after from header or use exponential backoff
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        wait = min(int(retry_after), 60)
                    except ValueError:
                        wait = _backoff(attempt)
                else:
                    wait = _backoff(attempt)
                
                frappe.logger("niv_ai").warning(
                    f"Retrying {url} after {response.status_code}, attempt {attempt+1}/{max_retries}, wait={wait}s"
                )
                time.sleep(wait)
                continue
            
            return response
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exception = e
            if attempt < max_retries:
                wait = _backoff(attempt)
                frappe.logger("niv_ai").warning(
                    f"Retrying {url} after {type(e).__name__}, attempt {attempt+1}/{max_retries}, wait={wait}s"
                )
                time.sleep(wait)
                continue
            raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


def _backoff(attempt):
    """Exponential backoff: 2, 4, 8 seconds (capped at 30)."""
    return min(2 ** (attempt + 1), 30)
