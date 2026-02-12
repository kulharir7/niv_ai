"""
Structured logging for Niv AI.
"""
import frappe
import time
import functools


def get_logger():
    """Get the Niv AI logger instance."""
    return frappe.logger("niv_ai", allow_site=True)


def log_api_call(endpoint, user=None, **kwargs):
    """Log an API call."""
    logger = get_logger()
    user = user or frappe.session.user
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items() if v)
    logger.info(f"API_CALL endpoint={endpoint} user={user} {extra}".strip())


def log_ai_request(provider, model, tokens=None, response_time_ms=None, error=None):
    """Log AI provider API call with timing."""
    logger = get_logger()
    parts = [f"AI_REQUEST provider={provider} model={model}"]
    if tokens:
        parts.append(f"tokens={tokens}")
    if response_time_ms is not None:
        parts.append(f"time_ms={response_time_ms}")
    if error:
        parts.append(f"error={error}")
    logger.info(" ".join(parts))


def log_tool_execution(tool_name, user, exec_time_ms=None, error=None):
    """Log tool execution."""
    logger = get_logger()
    parts = [f"TOOL_EXEC tool={tool_name} user={user}"]
    if exec_time_ms is not None:
        parts.append(f"time_ms={exec_time_ms}")
    if error:
        parts.append(f"error={error}")
        logger.warning(" ".join(parts))
    else:
        logger.info(" ".join(parts))


def log_billing_event(event, user, **kwargs):
    """Log billing events."""
    logger = get_logger()
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items() if v)
    logger.info(f"BILLING {event} user={user} {extra}".strip())


def log_auth_failure(user, reason, ip=None):
    """Log authentication/authorization failures."""
    logger = get_logger()
    parts = [f"AUTH_FAIL user={user} reason={reason}"]
    if ip:
        parts.append(f"ip={ip}")
    logger.warning(" ".join(parts))


def timed(label=None):
    """Decorator to log execution time of a function."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = int((time.time() - start) * 1000)
                get_logger().debug(f"TIMED {label or func.__name__} time_ms={elapsed}")
                return result
            except Exception:
                elapsed = int((time.time() - start) * 1000)
                get_logger().debug(f"TIMED {label or func.__name__} time_ms={elapsed} status=error")
                raise
        return wrapper
    return decorator
