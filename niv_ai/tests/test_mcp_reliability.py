"""
Tests for MCP reliability features: circuit breaker, retry, argument validation.
Self-contained — mocks frappe, no bench required.
Run: python test_mcp_reliability.py
"""

import json
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ─── Mock frappe before importing mcp_client ───────────────────────
_mock_frappe = MagicMock()
_mock_frappe.logger.return_value = MagicMock()
_mock_frappe.cache.return_value = MagicMock()
_mock_frappe.cache.return_value.get_value.return_value = None
_mock_frappe.local = MagicMock()
_mock_frappe.local.site = "test.localhost"
sys.modules["frappe"] = _mock_frappe

# Mock other imports that tools.py needs
for mod_name in [
    "langchain_core", "langchain_core.tools", "pydantic",
    "frappe_assistant_core", "frappe_assistant_core.api",
    "frappe_assistant_core.api.fac_endpoint",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Now import
from niv_ai.niv_core import mcp_client
from niv_ai.niv_core.mcp_client import (
    _circuit_breaker, _circuit_check, _circuit_record_success,
    _circuit_record_failure, _cache_lock,
    CIRCUIT_CLOSED, CIRCUIT_OPEN, CIRCUIT_HALF_OPEN,
    CIRCUIT_FAILURE_THRESHOLD, CIRCUIT_RECOVERY_TIMEOUT,
    _http_post, _is_retryable_error, MCPError,
    _RETRY_MAX,
)


def _reset_circuit(server="test-server"):
    """Reset circuit breaker state for a server."""
    with _cache_lock:
        _circuit_breaker.pop(server, None)


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        _reset_circuit()

    def test_closed_by_default(self):
        """Circuit is closed (not skipping) for unknown server."""
        self.assertFalse(_circuit_check("test-server"))

    def test_opens_after_threshold_failures(self):
        """Circuit opens after CIRCUIT_FAILURE_THRESHOLD consecutive failures."""
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit_record_failure("test-server")
        self.assertTrue(_circuit_check("test-server"))

    def test_does_not_open_before_threshold(self):
        """Circuit stays closed before threshold."""
        for _ in range(CIRCUIT_FAILURE_THRESHOLD - 1):
            _circuit_record_failure("test-server")
        self.assertFalse(_circuit_check("test-server"))

    def test_success_resets_circuit(self):
        """Recording success closes the circuit."""
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit_record_failure("test-server")
        self.assertTrue(_circuit_check("test-server"))
        _circuit_record_success("test-server")
        self.assertFalse(_circuit_check("test-server"))

    def test_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit_record_failure("test-server")
        # Simulate time passing
        with _cache_lock:
            _circuit_breaker["test-server"]["opened_at"] = time.time() - CIRCUIT_RECOVERY_TIMEOUT - 1
        # Should allow one call (half-open)
        self.assertFalse(_circuit_check("test-server"))
        with _cache_lock:
            self.assertEqual(_circuit_breaker["test-server"]["state"], CIRCUIT_HALF_OPEN)

    def test_half_open_failure_reopens(self):
        """Failure in HALF_OPEN state re-opens the circuit."""
        with _cache_lock:
            _circuit_breaker["test-server"] = {
                "state": CIRCUIT_HALF_OPEN, "failures": 3, "opened_at": time.time() - 100
            }
        _circuit_record_failure("test-server")
        with _cache_lock:
            self.assertEqual(_circuit_breaker["test-server"]["state"], CIRCUIT_OPEN)

    def test_half_open_success_closes(self):
        """Success in HALF_OPEN state closes the circuit."""
        with _cache_lock:
            _circuit_breaker["test-server"] = {
                "state": CIRCUIT_HALF_OPEN, "failures": 3, "opened_at": time.time() - 100
            }
        _circuit_record_success("test-server")
        self.assertFalse(_circuit_check("test-server"))
        with _cache_lock:
            self.assertEqual(_circuit_breaker["test-server"]["state"], CIRCUIT_CLOSED)


class TestRetryLogic(unittest.TestCase):
    def setUp(self):
        _reset_circuit()
        mcp_client._mcp_init_cache.clear()

    @patch("niv_ai.niv_core.mcp_client._get_http_session")
    def test_retries_on_502(self, mock_session_fn):
        """Retries on 502 and succeeds on second attempt."""
        import requests
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session

        # First call: 502 error
        resp_502 = MagicMock()
        resp_502.status_code = 502
        resp_502.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp_502)

        # Second call: success
        resp_ok = MagicMock()
        resp_ok.raise_for_status.return_value = None
        resp_ok.json.return_value = {"result": {"tools": []}}

        mock_session.post.side_effect = [resp_502, resp_ok]

        result = _http_post("http://test/api", {"test": 1}, server_name="test-server")
        self.assertEqual(result, {"result": {"tools": []}})
        self.assertEqual(mock_session.post.call_count, 2)

    @patch("niv_ai.niv_core.mcp_client._get_http_session")
    def test_no_retry_on_400(self, mock_session_fn):
        """Does NOT retry on 400 client error."""
        import requests
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session

        resp_400 = MagicMock()
        resp_400.status_code = 400
        http_err = requests.exceptions.HTTPError(response=resp_400)
        resp_400.raise_for_status.side_effect = http_err

        mock_session.post.side_effect = [resp_400]

        with self.assertRaises(requests.exceptions.HTTPError):
            _http_post("http://test/api", {"test": 1}, server_name="test-server")
        self.assertEqual(mock_session.post.call_count, 1)

    @patch("niv_ai.niv_core.mcp_client._get_http_session")
    def test_retries_exhaust_then_raises(self, mock_session_fn):
        """All retries fail → raises exception."""
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session

        mock_session.post.side_effect = ConnectionError("refused")

        with self.assertRaises(ConnectionError):
            _http_post("http://test/api", {"test": 1}, server_name="test-server")
        self.assertEqual(mock_session.post.call_count, _RETRY_MAX + 1)


class TestArgumentValidation(unittest.TestCase):
    def setUp(self):
        # Import after frappe is mocked
        from niv_ai.niv_core.langchain.tools import _validate_arguments
        self.validate = _validate_arguments

    def test_missing_required_field(self):
        schema = {
            "type": "object",
            "properties": {"doctype": {"type": "string"}},
            "required": ["doctype"],
        }
        err = self.validate("test_tool", {}, schema)
        self.assertIsNotNone(err)
        self.assertIn("doctype", err)
        self.assertIn("zaroori", err)

    def test_wrong_type(self):
        schema = {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        }
        err = self.validate("test_tool", {"limit": "abc"}, schema)
        self.assertIsNotNone(err)
        self.assertIn("type galat", err)

    def test_valid_args_pass(self):
        schema = {
            "type": "object",
            "properties": {
                "doctype": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["doctype"],
        }
        err = self.validate("test_tool", {"doctype": "Sales Order", "limit": 10}, schema)
        self.assertIsNone(err)

    def test_number_accepts_int_and_float(self):
        schema = {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
            "required": [],
        }
        self.assertIsNone(self.validate("t", {"amount": 10}, schema))
        self.assertIsNone(self.validate("t", {"amount": 10.5}, schema))

    def test_no_schema_passes(self):
        self.assertIsNone(self.validate("t", {"anything": "goes"}, {}))
        self.assertIsNone(self.validate("t", {"anything": "goes"}, None))


class TestIntegration(unittest.TestCase):
    """Circuit breaker + retry working together."""

    def setUp(self):
        _reset_circuit()
        mcp_client._mcp_init_cache.clear()

    @patch("niv_ai.niv_core.mcp_client._get_http_session")
    def test_retries_exhaust_feeds_circuit_breaker(self, mock_session_fn):
        """When retries exhaust, circuit breaker accumulates failures → opens."""
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_session.post.side_effect = ConnectionError("refused")

        # Each _http_post call will exhaust retries (3 attempts) and record 1 failure
        for i in range(CIRCUIT_FAILURE_THRESHOLD):
            try:
                _http_post("http://test/api", {}, server_name="test-server")
            except ConnectionError:
                pass

        # Circuit should now be open
        self.assertTrue(_circuit_check("test-server"))

    @patch("niv_ai.niv_core.mcp_client._get_http_session")
    def test_circuit_open_skips_http_in_call_tool_fast(self, mock_session_fn):
        """call_tool_fast raises MCPError when circuit is open."""
        # Force circuit open
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit_record_failure("test-server")

        # Mock server config
        mock_doc = MagicMock()
        mock_doc.transport_type = "streamable-http"
        mock_doc.server_url = "http://remote-server/api"
        mock_doc.api_key = None

        with patch("niv_ai.niv_core.mcp_client._get_server_config", return_value=mock_doc), \
             patch("niv_ai.niv_core.mcp_client._get_api_key", return_value=None), \
             patch("niv_ai.niv_core.mcp_client._is_same_server", return_value=False):
            with self.assertRaises(MCPError) as ctx:
                mcp_client.call_tool_fast("test-server", "some_tool", {})
            self.assertIn("Circuit breaker open", str(ctx.exception))

        # HTTP session should NOT have been called
        mock_session_fn.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
