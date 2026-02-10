"""
LangChain Callbacks — streaming, billing, tool logging.
All side effects handled via callback hooks — clean separation.
"""
import json
import time
import frappe
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List, Optional
from uuid import UUID


class NivStreamingCallback(BaseCallbackHandler):
    """Collects streaming tokens and tool events for SSE delivery."""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.tokens: list = []
        self.events: list = []
        self._current_tool: Optional[str] = None

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.tokens.append(token)
        self.events.append({"type": "token", "content": token})

    def on_tool_start(self, serialized: Dict, input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name", "unknown")
        self._current_tool = tool_name
        self.events.append({
            "type": "tool_call",
            "tool": tool_name,
            "arguments": input_str[:2000],
        })

    def on_tool_end(self, output: str, **kwargs) -> None:
        self.events.append({
            "type": "tool_result",
            "tool": self._current_tool or "unknown",
            "result": (output or "")[:2000],
        })
        self._current_tool = None

    def on_tool_error(self, error: BaseException, **kwargs) -> None:
        self.events.append({
            "type": "tool_error",
            "tool": self._current_tool or "unknown",
            "error": str(error)[:500],
        })
        self._current_tool = None

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        self.events.append({
            "type": "error",
            "content": f"LLM error: {str(error)[:500]}",
        })

    def get_full_response(self) -> str:
        return "".join(self.tokens)


class NivBillingCallback(BaseCallbackHandler):
    """Auto-deducts tokens after each LLM call.

    Accumulates across multiple LLM calls (tool loops),
    commits once at the end via finalize().
    """

    def __init__(self, user: str, conversation_id: str):
        self.user = user
        self.conversation_id = conversation_id
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self._finalized = False

    def on_llm_end(self, response, **kwargs) -> None:
        """Accumulate token usage (don't commit yet — might be mid-tool-loop)."""
        try:
            token_usage = {}
            if hasattr(response, "llm_output") and response.llm_output:
                token_usage = response.llm_output.get("token_usage", {})

            self.total_prompt_tokens += token_usage.get("prompt_tokens", 0)
            self.total_completion_tokens += token_usage.get("completion_tokens", 0)
        except Exception as e:
            frappe.log_error(f"Billing callback accumulate error: {e}", "Niv AI Billing")

    def finalize(self):
        """Commit all accumulated token usage. Call once after agent completes."""
        if self._finalized:
            return
        self._finalized = True

        total = self.total_prompt_tokens + self.total_completion_tokens
        if total <= 0:
            return

        try:
            settings = frappe.get_cached_doc("Niv Settings")
            if not settings.enable_billing:
                return

            from niv_ai.niv_billing.api.billing import deduct_tokens
            deduct_tokens(
                user=self.user,
                tokens_used=total,
                prompt_tokens=self.total_prompt_tokens,
                completion_tokens=self.total_completion_tokens,
                conversation_id=self.conversation_id,
            )
        except Exception as e:
            frappe.log_error(f"Token deduction failed: {e}", "Niv AI Billing")

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens


class NivLoggingCallback(BaseCallbackHandler):
    """Logs tool calls to Niv Tool Log.

    Batches logs and commits once via finalize() — no mid-stream commits.
    """

    def __init__(self, user: str, conversation_id: str):
        self.user = user
        self.conversation_id = conversation_id
        self._tool_runs: Dict[str, dict] = {}
        self._pending_logs: list = []

    def on_tool_start(self, serialized: Dict, input_str: str, *, run_id: UUID, **kwargs) -> None:
        self._tool_runs[str(run_id)] = {
            "name": serialized.get("name", "unknown"),
            "input": input_str[:5000],
            "start": time.time(),
        }

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs) -> None:
        info = self._tool_runs.pop(str(run_id), {})
        elapsed = time.time() - info.get("start", time.time())
        self._pending_logs.append({
            "tool_name": info.get("name", "unknown"),
            "input_data": info.get("input", ""),
            "output_data": (str(output) or "")[:5000],
            "execution_time": round(elapsed, 3),
            "status": "Success",
        })

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        info = self._tool_runs.pop(str(run_id), {})
        elapsed = time.time() - info.get("start", time.time())
        self._pending_logs.append({
            "tool_name": info.get("name", "unknown"),
            "input_data": info.get("input", ""),
            "output_data": str(error)[:5000],
            "execution_time": round(elapsed, 3),
            "status": "Error",
        })

    def finalize(self):
        """Batch-insert all tool logs. Call once after agent completes."""
        if not self._pending_logs:
            return

        try:
            for log in self._pending_logs:
                frappe.get_doc({
                    "doctype": "Niv Tool Log",
                    "user": self.user,
                    "conversation": self.conversation_id,
                    **log,
                }).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Tool log batch insert error: {e}", "Niv AI")
        finally:
            self._pending_logs.clear()
