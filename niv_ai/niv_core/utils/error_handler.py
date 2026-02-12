"""
Structured error handling for Niv AI.
Wraps API endpoints with consistent error responses.
"""
import frappe
import traceback
import functools
from niv_ai.niv_core.utils.rate_limiter import RateLimitExceeded


# Error codes
class ErrorCode:
    RATE_LIMITED = "RATE_LIMITED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    BILLING_ERROR = "BILLING_ERROR"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    AI_PROVIDER_UNAVAILABLE = "AI_PROVIDER_UNAVAILABLE"
    TOOL_ERROR = "TOOL_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def niv_error_response(code, message, status_code=400, details=None, retry_after=None):
    """Create a structured error response dict."""
    resp = {
        "error": True,
        "error_code": code,
        "message": message,
    }
    if details:
        resp["details"] = details
    if retry_after:
        resp["retry_after"] = retry_after
    return resp


def handle_errors(func):
    """
    Decorator for API endpoints. Catches exceptions and returns
    structured error responses without leaking stack traces.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RateLimitExceeded as e:
            _log_warning(f"Rate limit exceeded for {frappe.session.user}: {e.message}")
            frappe.local.response["http_status_code"] = 429
            if hasattr(frappe.local, "response"):
                frappe.local.response["headers"] = frappe.local.response.get("headers", {})
                frappe.local.response["headers"]["Retry-After"] = str(e.retry_after)
            frappe.throw(e.message, title="Rate Limited")
        except frappe.PermissionError:
            raise  # Let Frappe handle permission errors natively
        except frappe.DoesNotExistError:
            raise  # Let Frappe handle not found natively
        except frappe.ValidationError:
            raise  # Let Frappe handle validation errors natively
        except Exception as e:
            error_id = frappe.generate_hash(length=8)
            _log_error(
                f"[{error_id}] {func.__name__}: {str(e)}",
                traceback.format_exc(),
            )
            # Return friendly message, not stack trace
            friendly = _get_friendly_message(e)
            frappe.throw(f"{friendly} (ref: {error_id})")

    return wrapper


def handle_stream_errors(func):
    """
    Decorator for SSE streaming endpoints. Returns errors as SSE events.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RateLimitExceeded as e:
            _log_warning(f"Rate limit exceeded for {frappe.session.user}: {e.message}")
            frappe.throw(e.message)
        except frappe.PermissionError:
            raise
        except frappe.DoesNotExistError:
            raise
        except frappe.ValidationError:
            raise
        except Exception as e:
            error_id = frappe.generate_hash(length=8)
            _log_error(
                f"[{error_id}] {func.__name__}: {str(e)}",
                traceback.format_exc(),
            )
            friendly = _get_friendly_message(e)
            frappe.throw(f"{friendly} (ref: {error_id})")

    return wrapper


def _get_friendly_message(exception):
    """Map exception types to user-friendly messages."""
    err_str = str(exception).lower()

    if "timeout" in err_str or "timed out" in err_str:
        return "The AI service took too long to respond. Please try again."
    if "connection" in err_str or "connect" in err_str:
        return "Could not reach the AI service. Please try again in a moment."
    if "api key" in err_str or "authentication" in err_str or "401" in err_str:
        return "AI service authentication failed. Please contact your administrator."
    if "rate limit" in err_str or "429" in err_str:
        return "The AI service is busy. Please wait a moment and try again."
    if "insufficient" in err_str or "balance" in err_str or "credit" in err_str:
        return "Insufficient credits. Please recharge your wallet."
    if "503" in err_str or "unavailable" in err_str:
        return "The AI service is temporarily unavailable. Please try again shortly."

    return "Something went wrong. Please try again."


def _log_error(title, details):
    """Log error with full context."""
    try:
        frappe.log_error(
            message=details,
            title=f"Niv AI: {title}",
        )
    except Exception:
        pass


def _log_warning(message):
    """Log warning."""
    try:
        frappe.logger("niv_ai").warning(message)
    except Exception:
        pass
