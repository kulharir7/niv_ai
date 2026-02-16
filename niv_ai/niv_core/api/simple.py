"""
Niv AI Simple Mode — Direct LiteLLM + MCP Tools

No ADK, no orchestrator, no agent routing.
Just: User Query → LLM with Tools → Answer

Like Mistral's MCP integration — fast and reliable.
"""

import json
from datetime import date
from typing import Generator, Dict, Any, List

import frappe
from litellm import completion

from niv_ai.niv_core.mcp_client import (
    get_all_mcp_tools_cached,
    execute_mcp_tool,
)
from niv_ai.niv_core.utils import get_niv_settings
from niv_ai.niv_core.langchain.memory import get_system_prompt, get_conversation_history, save_message


# ─────────────────────────────────────────────────────────────────
# SIMPLE MODE SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────

SIMPLE_SYSTEM_PROMPT = f"""You are Niv AI, an intelligent assistant for Frappe/ERPNext systems.
Today is {date.today().strftime("%Y-%m-%d")}.

RULES:
1. USE TOOLS to get real data. Never make up data.
2. Call tools FIRST, then answer based on results.
3. For calculations (EMI, WRR, NPA, etc.) — fetch data with tools, then calculate yourself.
4. Present data in clean tables when appropriate.
5. Be concise and helpful.

You have access to MCP tools for:
- Listing documents (customers, loans, invoices, etc.)
- Running reports
- Creating/updating/deleting records
- Executing queries

When asked about data, USE THE TOOLS to fetch it, then present it clearly."""


# ─────────────────────────────────────────────────────────────────
# STREAM SIMPLE MODE
# ─────────────────────────────────────────────────────────────────

def stream_simple(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
    user: str = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Simple mode streaming — direct LiteLLM + MCP tools.
    
    No ADK overhead. Just like Mistral's MCP integration.
    """
    user = user or frappe.session.user
    
    try:
        # ─── 1. GET SETTINGS ───
        settings = get_niv_settings()
        provider_name = provider_name or settings.default_provider
        model_name = model_name or settings.default_model
        
        provider = frappe.get_doc("Niv AI Provider", provider_name)
        api_key = provider.get_password("api_key")
        base_url = provider.base_url
        
        # ─── 2. GET MCP TOOLS ───
        mcp_tools = get_all_mcp_tools_cached()
        
        if not mcp_tools:
            yield {"type": "error", "content": "No MCP tools available. Check Niv MCP Server configuration."}
            return
        
        yield {"type": "thought", "content": f"🔧 {len(mcp_tools)} tools available"}
        
        # ─── 3. BUILD MESSAGES ───
        messages = [
            {"role": "system", "content": SIMPLE_SYSTEM_PROMPT}
        ]
        
        # Add conversation history (last 10 messages)
        history = get_conversation_history(conversation_id, limit=10)
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        # Save user message
        save_message(conversation_id, "user", message, user)
        
        # ─── 4. TOOL LOOP (max 5 iterations) ───
        max_iterations = 5
        iteration = 0
        final_response = ""
        
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM
            response = completion(
                model=f"openai/{model_name}" if not model_name.startswith(("gpt-", "openai/")) else model_name,
                messages=messages,
                tools=mcp_tools if mcp_tools else None,
                api_key=api_key,
                api_base=base_url,
                stream=False,  # Non-streaming for tool calls
            )
            
            choice = response.choices[0]
            msg = choice.message
            
            # Check for tool calls
            if msg.tool_calls:
                # Process each tool call
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except:
                        tool_args = {}
                    
                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "arguments": tool_args,
                    }
                    
                    # Execute tool
                    result = execute_mcp_tool(tool_name, tool_args)
                    
                    # Format result
                    if isinstance(result, dict):
                        if result.get("error"):
                            result_str = f"Error: {result['error']}"
                        else:
                            result_str = result.get("result", json.dumps(result, default=str))
                    else:
                        result_str = str(result)
                    
                    # Truncate if too long
                    if len(result_str) > 10000:
                        result_str = result_str[:10000] + "\n... (truncated)"
                    
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result": result_str[:500] + "..." if len(result_str) > 500 else result_str,
                    }
                    
                    # Add to messages for next iteration
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc.model_dump()]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
            
            else:
                # No tool calls — this is the final response
                final_response = msg.content or ""
                break
        
        # ─── 5. STREAM FINAL RESPONSE ───
        if final_response:
            # Stream in chunks for better UX
            chunk_size = 50
            for i in range(0, len(final_response), chunk_size):
                chunk = final_response[i:i+chunk_size]
                yield {"type": "token", "content": chunk}
            
            # Save assistant message
            save_message(conversation_id, "assistant", final_response, user)
        
        yield {"type": "complete"}
        
    except Exception as e:
        frappe.log_error(f"Simple mode error: {e}\n{frappe.get_traceback()}", "Niv AI Simple")
        yield {"type": "error", "content": f"Error: {str(e)}"}


# ─────────────────────────────────────────────────────────────────
# API ENDPOINT
# ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def chat_simple(message: str, conversation_id: str = None):
    """
    Simple mode chat endpoint.
    
    Returns SSE stream directly.
    """
    import uuid
    
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    def generate():
        for event in stream_simple(message, conversation_id):
            yield f"data: {json.dumps(event)}\n\n"
    
    return frappe.make_response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
