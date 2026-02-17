"""
Niv AI - Simple Single Agent
User Query → LLM (with tools) → Tool Execution → Response
"""
import frappe
import json
from typing import List, Dict, Any, AsyncGenerator, Optional
from dataclasses import dataclass

from .llm.provider import LLMProvider, StreamChunk, get_llm_provider, MCPTool
from .tools.mcp_loader import load_mcp_tools, execute_tool, get_tool_definitions_for_prompt
from .knowledge.unified_discovery import get_discovery_for_agent

@dataclass
class AgentResponse:
    """Response from agent run"""
    text: str
    tool_calls: List[Dict] = None
    error: str = None

class NivAgent:
    """
    Simple single agent with MCP tools.
    No multi-agent routing, no orchestrator.
    Just: Query → LLM → Tool (if needed) → Response
    """
    
    def __init__(self, user: str = None, site: str = None):
        self.user = user or frappe.session.user
        self.site = site or frappe.local.site
        self.tools: List[MCPTool] = []
        self.llm: LLMProvider = None
        self.system_knowledge: str = None
        self.initialized = False
        
    async def initialize(self):
        """
        Initialize agent with tools and knowledge.
        Call once per session.
        """
        if self.initialized:
            return
            
        # 1. Load MCP tools from FAC
        self.tools = load_mcp_tools(self.user)
        frappe.logger().info(f"[NivAgent] Loaded {len(self.tools)} tools for {self.user}")
        
        # 2. Get system knowledge (doctypes, workflows, domain knowledge)
        self.system_knowledge = get_discovery_for_agent()
        
        # 3. Build system prompt
        system_prompt = self._build_system_prompt()
        
        # 4. Initialize LLM with tools
        self.llm = get_llm_provider(
            tools=self.tools,
            system_prompt=system_prompt
        )
        await self.llm.initialize()
        
        self.initialized = True
        frappe.logger().info(f"[NivAgent] Initialized for {self.user}")
        
    def _build_system_prompt(self) -> str:
        """Build comprehensive system prompt"""
        tool_docs = get_tool_definitions_for_prompt(self.tools)
        
        return f"""You are Niv AI, an intelligent assistant for ERPNext/Frappe.

## Your Capabilities
- Query and analyze ERPNext data
- Create, update, and manage documents
- Run database queries and reports
- Perform domain-specific operations (NBFC, CRM, etc.)

## System Knowledge
{self.system_knowledge}

{tool_docs}

## Tool Selection Guide

### Data Queries
- "Show top 10 X" → list_documents(doctype="X", limit=10, order_by="...")
- "Get details of X" → get_document(doctype="X", name="...")
- "Search for X" → search_documents(doctype="X", query="...")
- "Count of X" → run_database_query("SELECT COUNT(*) FROM tabX WHERE ...")

### Data Modification
- "Create new X" → create_document(doctype="X", values={{...}})
- "Update X" → update_document(doctype="X", name="...", values={{...}})

### Analytics (NBFC specific)
- "Portfolio analysis" → nbfc_analytics(...)
- "Credit check" → nbfc_credit_scoring(...) or nbfc_loan_prequalification(...)

## Critical Rules
1. **ONE tool call per simple query** - Don't explore, just execute
2. **Use system knowledge first** - Don't call get_doctype_info if you already know the DocType
3. **Be direct** - For read operations, don't ask for confirmation
4. **Handle errors gracefully** - If a tool fails, explain why and suggest alternatives

## Response Style
- Be concise and helpful
- Format data in readable tables when appropriate
- Explain what you did briefly
- Don't repeat tool outputs verbatim - summarize intelligently
"""

    async def run(
        self,
        query: str,
        history: List[Dict] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Main execution loop.
        Query → LLM → Tool (if needed) → Response
        
        Yields text chunks for streaming.
        """
        if not self.initialized:
            await self.initialize()
            
        # Build messages
        messages = self._build_messages(query, history)
        
        # Track tool calls for this turn
        pending_tool_calls = []
        accumulated_text = ""
        
        # First LLM call
        async for chunk in self.llm.generate(messages, stream=stream):
            if chunk.type == "text":
                accumulated_text += chunk.text
                yield chunk.text
                
            elif chunk.type == "tool_call":
                pending_tool_calls.append(chunk.tool_call)
                
            elif chunk.type == "tool_calls_complete":
                # Execute all pending tool calls
                if pending_tool_calls:
                    # Add assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": accumulated_text if accumulated_text else None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments)
                                }
                            }
                            for tc in pending_tool_calls
                        ]
                    })
                    
                    # Execute tools and add results
                    for tc in pending_tool_calls:
                        tool = self._find_tool(tc.name)
                        if tool:
                            result = await execute_tool(tool, tc.arguments)
                            frappe.logger().info(f"[NivAgent] Tool {tc.name} result: {result[:200]}...")
                        else:
                            result = f"Error: Tool '{tc.name}' not found"
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result
                        })
                    
                    # Second LLM call with tool results
                    accumulated_text = ""
                    async for response_chunk in self.llm.generate(messages, stream=stream):
                        if response_chunk.type == "text":
                            accumulated_text += response_chunk.text
                            yield response_chunk.text
                        # Handle nested tool calls if needed
                        elif response_chunk.type == "tool_call":
                            # For now, limit to one round of tool calls
                            # Can be extended for multi-step
                            pass
                            
    def _build_messages(self, query: str, history: List[Dict] = None) -> List[Dict]:
        """Build messages array for LLM"""
        messages = []
        
        # Add history if exists
        if history:
            for msg in history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
                
        # Add current query
        messages.append({
            "role": "user",
            "content": query
        })
        
        return messages
        
    def _find_tool(self, name: str) -> Optional[MCPTool]:
        """Find tool by name"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None


# Convenience function for API
async def run_agent(
    query: str,
    user: str = None,
    session_id: str = None,
    stream: bool = True
) -> AsyncGenerator[str, None]:
    """
    Convenience function to run agent.
    Creates agent, initializes, and runs query.
    """
    agent = NivAgent(user=user)
    await agent.initialize()
    
    # Load history from session if provided
    history = None
    if session_id:
        history = _get_session_history(session_id)
        
    async for chunk in agent.run(query, history=history, stream=stream):
        yield chunk
        
    # Save to session
    if session_id:
        _save_to_session(session_id, query, "".join([c async for c in agent.run(query, history)]))


def _get_session_history(session_id: str) -> List[Dict]:
    """Get chat history from Redis session"""
    try:
        import redis
        r = redis.from_url(frappe.conf.redis_cache)
        history = r.get(f"niv_chat:{session_id}")
        if history:
            return json.loads(history)
    except:
        pass
    return []


def _save_to_session(session_id: str, query: str, response: str):
    """Save chat to Redis session"""
    try:
        import redis
        r = redis.from_url(frappe.conf.redis_cache)
        history = _get_session_history(session_id)
        history.extend([
            {"role": "user", "content": query},
            {"role": "assistant", "content": response}
        ])
        # Keep last 20 messages
        history = history[-20:]
        r.set(f"niv_chat:{session_id}", json.dumps(history), ex=86400)  # 24hr TTL
    except:
        pass
