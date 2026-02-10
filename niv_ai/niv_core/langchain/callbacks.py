"""
LangChain Callbacks — streaming, billing, tool logging.
All side effects (SSE, token deduction, logging) handled here.
"""
import json
import time
import frappe
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List, Optional
from uuid import UUID


class NivStreamingCallback(BaseCallbackHandler):
    """Streams tokens to browser via SSE generator."""
    
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.tokens = []
        self.events = []  # Collected SSE events
        self._current_tool_call = None
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.tokens.append(token)
        self.events.append({
            "type": "token",
            "content": token,
        })
    
    def on_tool_start(self, serialized: Dict, input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name", "unknown")
        self._current_tool_call = tool_name
        self.events.append({
            "type": "tool_call",
            "tool": tool_name,
            "arguments": input_str,
        })
    
    def on_tool_end(self, output: str, **kwargs) -> None:
        self.events.append({
            "type": "tool_result",
            "tool": self._current_tool_call or "unknown",
            "result": output[:2000],  # Truncate large results
        })
        self._current_tool_call = None
    
    def on_tool_error(self, error: BaseException, **kwargs) -> None:
        self.events.append({
            "type": "tool_error",
            "tool": self._current_tool_call or "unknown",
            "error": str(error)[:500],
        })
        self._current_tool_call = None
    
    def get_full_response(self) -> str:
        return "".join(self.tokens)


class NivBillingCallback(BaseCallbackHandler):
    """Auto-deducts tokens after each LLM call."""
    
    def __init__(self, user: str, conversation_id: str):
        self.user = user
        self.conversation_id = conversation_id
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
    
    def on_llm_end(self, response, **kwargs) -> None:
        try:
            token_usage = {}
            if hasattr(response, "llm_output") and response.llm_output:
                token_usage = response.llm_output.get("token_usage", {})
            
            prompt_tokens = token_usage.get("prompt_tokens", 0)
            completion_tokens = token_usage.get("completion_tokens", 0)
            total = token_usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
            
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            
            if total > 0:
                self._deduct(total, prompt_tokens, completion_tokens)
        except Exception as e:
            frappe.log_error(f"Billing callback error: {e}", "Niv AI Billing")
    
    def _deduct(self, total: int, prompt: int, completion: int):
        """Deduct tokens from wallet/pool."""
        try:
            from niv_ai.niv_billing.api.billing import deduct_tokens
            deduct_tokens(
                user=self.user,
                tokens_used=total,
                prompt_tokens=prompt,
                completion_tokens=completion,
                conversation_id=self.conversation_id,
            )
        except Exception as e:
            frappe.log_error(f"Token deduction failed: {e}", "Niv AI Billing")


class NivLoggingCallback(BaseCallbackHandler):
    """Logs tool calls to Niv Tool Log."""
    
    def __init__(self, user: str, conversation_id: str):
        self.user = user
        self.conversation_id = conversation_id
        self._tool_start_times = {}
    
    def on_tool_start(self, serialized: Dict, input_str: str, *, run_id: UUID, **kwargs) -> None:
        self._tool_start_times[str(run_id)] = {
            "name": serialized.get("name", "unknown"),
            "input": input_str,
            "start": time.time(),
        }
    
    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs) -> None:
        rid = str(run_id)
        info = self._tool_start_times.pop(rid, {})
        elapsed = time.time() - info.get("start", time.time())
        
        try:
            frappe.get_doc({
                "doctype": "Niv Tool Log",
                "tool_name": info.get("name", "unknown"),
                "user": self.user,
                "conversation": self.conversation_id,
                "input_data": str(info.get("input", ""))[:5000],
                "output_data": str(output)[:5000],
                "execution_time": round(elapsed, 3),
                "status": "Success",
            }).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Tool log error: {e}", "Niv AI")
    
    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        rid = str(run_id)
        info = self._tool_start_times.pop(rid, {})
        elapsed = time.time() - info.get("start", time.time())
        
        try:
            frappe.get_doc({
                "doctype": "Niv Tool Log",
                "tool_name": info.get("name", "unknown"),
                "user": self.user,
                "conversation": self.conversation_id,
                "input_data": str(info.get("input", ""))[:5000],
                "output_data": str(error)[:5000],
                "execution_time": round(elapsed, 3),
                "status": "Error",
            }).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Tool log error: {e}", "Niv AI")
