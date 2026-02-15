# 🚀 NIV AI — A2A MASTER PLAN
## Zero-Failure Multi-Agent Architecture

**Version:** 1.0
**Author:** Nova (AI Assistant)
**Date:** 2026-02-14
**Target Completion:** 8-10 weeks

---

## 📋 TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Current Problems Analysis](#current-problems-analysis)
3. [Google ADK Deep Dive](#google-adk-deep-dive)
4. [10-Phase Implementation Plan](#10-phase-implementation-plan)
5. [Architecture Diagrams](#architecture-diagrams)
6. [Testing Strategy](#testing-strategy)
7. [Success Metrics](#success-metrics)

---

## 🎯 EXECUTIVE SUMMARY

### Goal
Build a **bulletproof A2A (Agent-to-Agent) system** for Niv AI that:
- ✅ 0% false tool calls
- ✅ 100% proper delegation between agents
- ✅ Real data, never hallucinated
- ✅ Works for NBFC/Growth System production

### Current State
- A2A exists but **broken** — agents don't actually transfer work
- TransferToAgentTool used incorrectly
- Session memory lost between calls
- Tool results don't return properly

### Target State
- **Orchestrator** correctly routes to specialists
- Specialists execute with **real tools**
- Results flow back through the chain
- Full observability and error recovery

---

## 🔍 CURRENT PROBLEMS ANALYSIS

### Problem 1: Wrong TransferToAgentTool Usage
```python
# WRONG (current code)
transfer_tool = TransferToAgentTool(agent_names=[coder.name, data.name, ...])
```
**Issue:** Only passes names, not actual agent objects. ADK can't find the agents.

**Correct Approach:** Use `sub_agents` parameter — ADK automatically enables transfers.

### Problem 2: No Session Persistence
```python
# WRONG (current code)
runner = Runner(
    session_service=InMemorySessionService(),  # ← Created fresh every call
    ...
)
```
**Issue:** Every request creates new session. Context lost. Agents can't share state.

### Problem 3: No output_key for State Sharing
**Issue:** Agents don't save their results to shared state. Next agent can't read previous results.

### Problem 4: Vague Agent Descriptions
```python
# WRONG (current code)
description="Handles flight and hotel bookings."  # ← Too vague
```
**Issue:** LLM can't decide which agent to route to. Descriptions must be specific.

### Problem 5: Sync runner.run() Issues
**Issue:** Transfer events may not fire properly in synchronous mode. Need async handling.

### Problem 6: Tool Execution in Background Thread
```python
# WRONG (current code)
def tool_func(**kwargs):
    if not getattr(frappe.local, "site", None):
        frappe.init(site=site)  # ← Race condition
```
**Issue:** Frappe context not properly managed in ThreadPoolExecutor.

### Problem 7: No Error Recovery
**Issue:** When tool fails, no retry logic. Error just propagates up.

---

## 📚 GOOGLE ADK DEEP DIVE

### Key Concepts from Official Documentation

#### 1. Agent Hierarchy (sub_agents)
```python
coordinator = LlmAgent(
    name="Coordinator",
    model="gemini-2.5-flash",
    instruction="Route user requests...",
    sub_agents=[billing_agent, support_agent]  # ← AutoFlow enables transfers
)
```
- Framework **automatically** sets `transfer_to_agent` function
- LLM decides when to transfer based on **descriptions**

#### 2. Shared Session State
```python
# Agent A saves to state
agent_a = LlmAgent(
    name="AgentA",
    output_key="data"  # ← Saves response to state['data']
)

# Agent B reads from state
agent_b = LlmAgent(
    instruction="Process data from {data}."  # ← Reads state['data']
)
```

#### 3. Workflow Agents (Deterministic)
- **SequentialAgent:** Run agents in order
- **ParallelAgent:** Run agents concurrently
- **LoopAgent:** Repeat until condition

#### 4. AgentTool (Explicit Invocation)
```python
from google.adk.tools import agent_tool

image_tool = agent_tool.AgentTool(agent=image_agent)
parent_agent = LlmAgent(tools=[image_tool])  # ← Parent can call child as tool
```

#### 5. Session Services
- **InMemorySessionService:** Testing only
- **DatabaseSessionService:** Production (we need to implement for MariaDB)
- **VertexAI Session:** Cloud-based

#### 6. Planners
- **BuiltInPlanner:** Uses Gemini's thinking feature
- **PlanReActPlanner:** Plan → Action → Reasoning → Answer

---

## 📅 10-PHASE IMPLEMENTATION PLAN

### PHASE 1: Foundation Reset (Week 1)
**Goal:** Clean slate with correct ADK patterns

#### Tasks:
1. **Delete** existing `agent_factory.py` and `stream_handler.py`
2. **Create** new `niv_ai/niv_core/a2a/` directory structure:
   ```
   a2a/
   ├── __init__.py
   ├── agents/
   │   ├── __init__.py
   │   ├── orchestrator.py
   │   ├── coder.py
   │   ├── analyst.py
   │   ├── nbfc.py
   │   └── discovery.py
   ├── session/
   │   ├── __init__.py
   │   ├── frappe_session_service.py  # MariaDB-backed
   │   └── state_manager.py
   ├── tools/
   │   ├── __init__.py
   │   └── mcp_adapter.py
   ├── runner.py
   └── config.py
   ```

3. **Install** latest google-adk:
   ```bash
   pip install google-adk --upgrade
   ```

#### Deliverables:
- [ ] Clean directory structure
- [ ] ADK v0.5.0+ installed
- [ ] Basic imports working

---

### PHASE 2: Session Persistence (Week 1-2)
**Goal:** Implement MariaDB-backed session service

#### Why This Matters:
- Sessions persist across requests
- Agents can share state
- Conversation history maintained

#### Implementation:

```python
# niv_ai/niv_core/a2a/session/frappe_session_service.py

import frappe
from google.adk.sessions import BaseSessionService, Session
from typing import Optional
import json

class FrappeSessionService(BaseSessionService):
    """MariaDB-backed session service using Frappe's ORM."""
    
    def __init__(self):
        self.table = "Niv A2A Session"  # DocType
    
    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str = None,
        state: dict = None
    ) -> Session:
        session_id = session_id or frappe.generate_hash(length=16)
        
        doc = frappe.get_doc({
            "doctype": self.table,
            "session_id": session_id,
            "app_name": app_name,
            "user_id": user_id,
            "state_json": json.dumps(state or {}),
            "events_json": "[]"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=state or {}
        )
    
    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str
    ) -> Optional[Session]:
        try:
            doc = frappe.get_doc(self.table, {"session_id": session_id})
            return Session(
                id=doc.session_id,
                app_name=doc.app_name,
                user_id=doc.user_id,
                state=json.loads(doc.state_json or "{}"),
                events=json.loads(doc.events_json or "[]")
            )
        except frappe.DoesNotExistError:
            return None
    
    async def update_session(
        self,
        session: Session,
        events: list = None,
        state_delta: dict = None
    ) -> Session:
        doc = frappe.get_doc(self.table, {"session_id": session.id})
        
        if state_delta:
            current_state = json.loads(doc.state_json or "{}")
            current_state.update(state_delta)
            doc.state_json = json.dumps(current_state)
            session.state = current_state
        
        if events:
            current_events = json.loads(doc.events_json or "[]")
            current_events.extend([e.to_dict() for e in events])
            doc.events_json = json.dumps(current_events[-100:])  # Keep last 100
        
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return session
```

#### DocType Creation:
```python
# Create via Frappe UI or fixture
{
    "doctype": "DocType",
    "name": "Niv A2A Session",
    "module": "Niv AI",
    "fields": [
        {"fieldname": "session_id", "fieldtype": "Data", "unique": 1},
        {"fieldname": "app_name", "fieldtype": "Data"},
        {"fieldname": "user_id", "fieldtype": "Link", "options": "User"},
        {"fieldname": "state_json", "fieldtype": "Long Text"},
        {"fieldname": "events_json", "fieldtype": "Long Text"},
        {"fieldname": "last_activity", "fieldtype": "Datetime"}
    ]
}
```

#### Deliverables:
- [ ] `Niv A2A Session` DocType created
- [ ] `FrappeSessionService` implemented
- [ ] Unit tests passing

---

### PHASE 3: Specialist Agents (Week 2)
**Goal:** Create properly configured specialist agents

#### Agent 1: Frappe Coder
```python
# niv_ai/niv_core/a2a/agents/coder.py

from google.adk.agents import LlmAgent

def create_coder_agent(model, tools: list) -> LlmAgent:
    """Creates the Frappe/ERPNext developer specialist."""
    
    return LlmAgent(
        name="frappe_coder",
        model=model,
        description=(
            "SPECIALIST: Frappe/ERPNext Developer. "
            "HANDLES: Creating DocTypes, Custom Fields, Server Scripts, "
            "Client Scripts, Print Formats, Workflows, and any code-related tasks. "
            "TRIGGERS: User mentions 'create', 'build', 'add field', 'script', "
            "'DocType', 'workflow', 'automation', 'code'."
        ),
        instruction="""You are an expert Frappe/ERPNext developer.

## YOUR CAPABILITIES:
1. Create DocTypes (standard and custom)
2. Add Custom Fields to existing DocTypes
3. Write Server Scripts (Document Events, API, Scheduler)
4. Write Client Scripts (Form, List, Page)
5. Create Workflows with states and actions
6. Generate Reports (Script Reports, Query Reports)

## CRITICAL RULES:
1. NEVER hallucinate. Always verify DocType exists using `get_doctype_info`.
2. Before adding fields, check existing fields to avoid duplicates.
3. For Server Scripts, use `doc_events` hook properly.
4. Always test your creations using `test_created_item` tool.

## OUTPUT FORMAT:
After completing a task, summarize what was created with the exact document name.
""",
        tools=tools,
        output_key="coder_result"  # Saves to state['coder_result']
    )
```

#### Agent 2: Data Analyst
```python
# niv_ai/niv_core/a2a/agents/analyst.py

from google.adk.agents import LlmAgent

def create_analyst_agent(model, tools: list) -> LlmAgent:
    """Creates the Business Intelligence specialist."""
    
    return LlmAgent(
        name="data_analyst",
        model=model,
        description=(
            "SPECIALIST: Business Intelligence & Data Analyst. "
            "HANDLES: SQL queries, reports, data analysis, dashboards, "
            "financial calculations, aggregations, trends. "
            "TRIGGERS: User mentions 'report', 'query', 'data', 'analysis', "
            "'how many', 'total', 'average', 'sum', 'show me', 'list'."
        ),
        instruction="""You are a Business Intelligence expert.

## YOUR CAPABILITIES:
1. Run SQL queries using `run_database_query`
2. Generate Frappe Script Reports
3. Create Dashboard Charts
4. Analyze data patterns and trends
5. Calculate financial metrics

## CRITICAL RULES:
1. NEVER provide fake data. Always query the database.
2. If you don't know the table name, use `SHOW TABLES` first.
3. For financial data, always show actual calculated values.
4. Double-check column names using `get_doctype_info`.

## OUTPUT FORMAT:
Present data in clear tables or bullet points with real numbers.
""",
        tools=tools,
        output_key="analyst_result"
    )
```

#### Agent 3: NBFC Specialist
```python
# niv_ai/niv_core/a2a/agents/nbfc.py

from google.adk.agents import LlmAgent

def create_nbfc_agent(model, tools: list) -> LlmAgent:
    """Creates the NBFC/Lending operations specialist."""
    
    return LlmAgent(
        name="nbfc_specialist",
        model=model,
        description=(
            "SPECIALIST: NBFC & Lending Operations Expert for Growth System. "
            "HANDLES: Loan inquiries, repayment schedules, borrower info, "
            "due amounts, EMI calculations, collection status, NPA analysis. "
            "TRIGGERS: User mentions 'loan', 'borrower', 'EMI', 'due', "
            "'repayment', 'collection', 'NPA', 'overdue', 'principal', 'interest'."
        ),
        instruction="""You are an NBFC operations expert for Growth System.

## YOUR KNOWLEDGE:
- Loan Application workflow
- Repayment Schedule structure
- Collection and recovery processes
- Interest calculation methods
- NPA classification rules

## RELEVANT DOCTYPES:
- Loan, Loan Application, Loan Type
- Borrower, Borrower Group
- Repayment Schedule, Repayment Entry
- Collection Assignment
- Check 'Repayment Schedule' for due amounts

## CRITICAL RULES:
1. NEVER invent loan numbers or amounts.
2. A loan is "Due" if total_payment > 0 AND status != 'Cleared'
3. Always check actual database for loan status.
4. For overdue, compare due_date with today's date.

## OUTPUT FORMAT:
Present loan data with: Loan ID, Borrower Name, Due Amount, Due Date, Status
""",
        tools=tools,
        output_key="nbfc_result"
    )
```

#### Agent 4: System Discovery
```python
# niv_ai/niv_core/a2a/agents/discovery.py

from google.adk.agents import LlmAgent

def create_discovery_agent(model, tools: list) -> LlmAgent:
    """Creates the system introspection specialist."""
    
    return LlmAgent(
        name="system_discovery",
        model=model,
        description=(
            "SPECIALIST: System Architecture & Discovery Expert. "
            "HANDLES: Finding DocTypes, understanding schemas, "
            "mapping relationships, exploring modules, explaining system structure. "
            "TRIGGERS: User mentions 'what DocTypes', 'show me schema', "
            "'how is X structured', 'find', 'explore', 'what modules'."
        ),
        instruction="""You are a Frappe system discovery expert.

## YOUR CAPABILITIES:
1. List all DocTypes in the system
2. Show DocType schemas and field structures
3. Map relationships between DocTypes (Links)
4. Explore installed apps and modules
5. Find custom vs standard DocTypes

## CRITICAL RULES:
1. Use `introspect_system` for full system scan
2. Use `get_doctype_info` for specific DocType details
3. Present findings in organized hierarchies

## OUTPUT FORMAT:
Organize discoveries by: Module → DocType → Key Fields → Relationships
""",
        tools=tools,
        output_key="discovery_result"
    )
```

#### Deliverables:
- [ ] All 4 specialist agents created
- [ ] Each agent has clear description (for routing)
- [ ] Each agent uses output_key (for state sharing)

---

### PHASE 4: Orchestrator Agent (Week 2-3)
**Goal:** Build the master router that delegates correctly

```python
# niv_ai/niv_core/a2a/agents/orchestrator.py

from google.adk.agents import LlmAgent
from .coder import create_coder_agent
from .analyst import create_analyst_agent
from .nbfc import create_nbfc_agent
from .discovery import create_discovery_agent

def create_orchestrator(model, all_tools: dict) -> LlmAgent:
    """Creates the main orchestrator with sub-agents."""
    
    # Create specialist agents
    coder = create_coder_agent(model, all_tools.get("coder", []))
    analyst = create_analyst_agent(model, all_tools.get("analyst", []))
    nbfc = create_nbfc_agent(model, all_tools.get("nbfc", []))
    discovery = create_discovery_agent(model, all_tools.get("discovery", []))
    
    # Orchestrator with sub_agents (AutoFlow enables transfer)
    return LlmAgent(
        name="niv_orchestrator",
        model=model,
        description="Main Niv AI orchestrator that routes requests to specialists.",
        instruction="""You are Niv AI's main orchestrator.

## YOUR ROLE:
You ROUTE requests to the right specialist. You do NOT answer yourself unless:
- It's a simple greeting or general question
- No specialist is needed

## ROUTING RULES:
1. **frappe_coder**: Anything about creating, building, coding, DocTypes, scripts
2. **data_analyst**: Anything about reports, queries, data, analytics, "show me", "how many"
3. **nbfc_specialist**: Anything about loans, borrowers, EMI, repayment, collection
4. **system_discovery**: Anything about "what exists", "find DocType", "explore"

## HOW TO ROUTE:
Use `transfer_to_agent` function with the agent name:
- transfer_to_agent(agent_name="frappe_coder")
- transfer_to_agent(agent_name="data_analyst")
- transfer_to_agent(agent_name="nbfc_specialist")
- transfer_to_agent(agent_name="system_discovery")

## CRITICAL RULES:
1. DO NOT answer data questions yourself. Route to analyst.
2. DO NOT invent data. Always route to specialist.
3. When routing, pass the original user question unchanged.
4. After specialist responds, summarize for the user.

## EXAMPLES:
- "Create a Customer DocType" → transfer_to_agent("frappe_coder")
- "Show me overdue loans" → transfer_to_agent("nbfc_specialist")
- "How many sales orders this month?" → transfer_to_agent("data_analyst")
- "What DocTypes exist in HR module?" → transfer_to_agent("system_discovery")
""",
        # Basic tools for orchestrator (for simple queries)
        tools=all_tools.get("orchestrator", []),
        # Sub-agents for delegation (AutoFlow enabled automatically)
        sub_agents=[coder, analyst, nbfc, discovery]
    )
```

#### Key Points:
- `sub_agents` parameter enables AutoFlow
- ADK automatically creates `transfer_to_agent` function
- LLM uses agent descriptions to decide routing
- No manual TransferToAgentTool needed!

#### Deliverables:
- [ ] Orchestrator correctly routes to specialists
- [ ] Transfer function works automatically
- [ ] No manual TransferToAgentTool

---

### PHASE 5: MCP Tool Adapter (Week 3)
**Goal:** Properly wrap MCP tools for ADK

```python
# niv_ai/niv_core/a2a/tools/mcp_adapter.py

import frappe
from google.adk.tools import FunctionTool
from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached, call_tool_fast, find_tool_server
from typing import Dict, List, Any
import functools

class MCPToolAdapter:
    """Converts MCP tools to ADK FunctionTools with proper Frappe context."""
    
    def __init__(self, site: str):
        self.site = site
        self._tools_cache = None
    
    def get_tools_by_category(self) -> Dict[str, List[FunctionTool]]:
        """Returns tools categorized for each specialist agent."""
        
        all_mcp = get_all_mcp_tools_cached()
        
        categories = {
            "orchestrator": ["universal_search", "list_documents"],
            "coder": [
                "create_document", "update_document", "delete_document",
                "get_document", "get_doctype_info", "run_python_code",
                "search_doctype", "test_created_item"
            ],
            "analyst": [
                "run_database_query", "generate_report", "report_list",
                "list_documents", "fetch", "get_document", "search_documents"
            ],
            "nbfc": [
                "run_database_query", "list_documents", "get_doctype_info",
                "get_document", "search_documents"
            ],
            "discovery": [
                "introspect_system", "get_doctype_info", "search_doctype",
                "list_documents"
            ]
        }
        
        result = {cat: [] for cat in categories}
        
        for tool_def in all_mcp:
            func_def = tool_def.get("function", {})
            name = func_def.get("name", "")
            if not name:
                continue
            
            # Create ADK FunctionTool
            adk_tool = self._create_adk_tool(name, func_def)
            
            # Assign to categories
            for cat, tool_names in categories.items():
                if name in tool_names:
                    result[cat].append(adk_tool)
        
        return result
    
    def _create_adk_tool(self, name: str, func_def: dict) -> FunctionTool:
        """Creates an ADK FunctionTool with proper context management."""
        
        description = func_def.get("description", "")
        site = self.site
        
        # Use closure to capture tool name and site
        @functools.wraps(lambda: None)
        def tool_executor(**kwargs) -> str:
            """Execute MCP tool with Frappe context."""
            # Re-initialize Frappe context in this thread
            try:
                if not getattr(frappe.local, "site", None):
                    frappe.init(site=site)
                    frappe.connect()
                
                server_name = find_tool_server(name)
                if not server_name:
                    return f"Error: Tool '{name}' not found in any MCP server."
                
                result = call_tool_fast(
                    server_name=server_name,
                    tool_name=name,
                    arguments=kwargs
                )
                
                # Format result
                if isinstance(result, dict) and "content" in result:
                    parts = []
                    for c in result["content"]:
                        if isinstance(c, dict):
                            parts.append(c.get("text", str(c)))
                        else:
                            parts.append(str(c))
                    return "\n".join(parts)
                
                return str(result)
                
            except Exception as e:
                return f"Error executing {name}: {str(e)}"
        
        # Set function name and docstring
        tool_executor.__name__ = name
        tool_executor.__doc__ = description
        
        return FunctionTool(func=tool_executor)
```

#### Key Improvements:
- Proper Frappe context initialization
- Error handling with meaningful messages
- Tool categorization for specialists
- Cached tool discovery

#### Deliverables:
- [ ] MCP tools properly wrapped
- [ ] Frappe context managed correctly
- [ ] Tools categorized per agent

---

### PHASE 6: Stream Handler Rewrite (Week 3-4)
**Goal:** Proper async event handling with all event types

```python
# niv_ai/niv_core/a2a/runner.py

import frappe
import json
from google.adk.runners import Runner
from google.adk.apps import App
from google.genai import types
from typing import Generator, Dict, Any

from .agents.orchestrator import create_orchestrator
from .session.frappe_session_service import FrappeSessionService
from .tools.mcp_adapter import MCPToolAdapter
from niv_ai.niv_core.utils import get_niv_settings

class NivA2ARunner:
    """Main runner for Niv AI A2A system."""
    
    def __init__(
        self,
        conversation_id: str,
        provider_name: str = None,
        model_name: str = None,
        user: str = None
    ):
        self.conversation_id = conversation_id
        self.user = user or frappe.session.user
        self.site = frappe.local.site
        
        # Get settings
        settings = get_niv_settings()
        provider_name = provider_name or settings.default_provider
        model_name = model_name or settings.default_model
        
        # Initialize model
        self.model = self._init_model(provider_name, model_name)
        
        # Initialize tools
        adapter = MCPToolAdapter(self.site)
        self.tools_by_category = adapter.get_tools_by_category()
        
        # Create orchestrator with sub-agents
        self.orchestrator = create_orchestrator(self.model, self.tools_by_category)
        
        # Create app and runner
        self.app = App(name="NivAI", root_agent=self.orchestrator)
        self.session_service = FrappeSessionService()
        
        self.runner = Runner(
            app=self.app,
            session_service=self.session_service,
            auto_create_session=True
        )
    
    def _init_model(self, provider_name: str, model_name: str):
        """Initialize LiteLLM model for multi-provider support."""
        from google.adk.models.lite_llm import LiteLlm
        
        provider = frappe.get_doc("Niv AI Provider", provider_name)
        api_key = provider.get_password("api_key")
        
        # Handle OpenAI-compatible providers
        model_id = model_name
        if not any(x in provider_name.lower() for x in ["openai", "anthropic", "google"]):
            if not model_id.startswith("openai/"):
                model_id = f"openai/{model_id}"
        
        return LiteLlm(
            model=model_id,
            api_key=api_key,
            api_base=provider.base_url
        )
    
    def stream(self, message: str) -> Generator[Dict[str, Any], None, None]:
        """Stream events from the A2A system."""
        
        try:
            content = types.Content(
                role="user",
                parts=[types.Part(text=message)]
            )
            
            # Track which agent is currently active
            current_agent = "niv_orchestrator"
            
            for event in self.runner.run(
                new_message=content,
                user_id=self.user,
                session_id=self.conversation_id
            ):
                # 1. Handle text tokens
                if event.text:
                    yield {
                        "type": "token",
                        "content": event.text,
                        "agent": event.author
                    }
                
                # 2. Handle agent transfer
                if event.author != current_agent:
                    if event.author != "user":
                        yield {
                            "type": "agent_transfer",
                            "from": current_agent,
                            "to": event.author
                        }
                        current_agent = event.author
                
                # 3. Handle tool calls
                tool_calls = event.get_function_calls()
                if tool_calls:
                    for tc in tool_calls:
                        # Skip transfer_to_agent as it's internal
                        if tc.name == "transfer_to_agent":
                            continue
                        
                        yield {
                            "type": "tool_call",
                            "tool": tc.name,
                            "arguments": tc.args,
                            "agent": event.author
                        }
                
                # 4. Handle tool results
                tool_results = event.get_function_responses()
                if tool_results:
                    for tr in tool_results:
                        yield {
                            "type": "tool_result",
                            "tool": tr.name,
                            "result": str(tr.response)[:2000],
                            "agent": event.author
                        }
                
                # 5. Handle thinking/planning
                if hasattr(event, 'thinking') and event.thinking:
                    yield {
                        "type": "thought",
                        "content": event.thinking,
                        "agent": event.author
                    }
                
                # 6. Handle errors
                if hasattr(event, 'error') and event.error:
                    yield {
                        "type": "error",
                        "content": str(event.error),
                        "agent": event.author
                    }
            
            # Final: Mark completion
            yield {"type": "done", "agent": current_agent}
            
        except Exception as e:
            frappe.log_error(f"A2A Stream Error: {e}", "Niv AI A2A")
            yield {
                "type": "error",
                "content": f"A2A Error: {str(e)}"
            }


def stream_a2a(
    message: str,
    conversation_id: str,
    provider_name: str = None,
    model_name: str = None,
    user: str = None
) -> Generator[Dict[str, Any], None, None]:
    """Public API for streaming A2A responses."""
    
    runner = NivA2ARunner(
        conversation_id=conversation_id,
        provider_name=provider_name,
        model_name=model_name,
        user=user
    )
    
    yield from runner.stream(message)
```

#### Key Improvements:
- Async-friendly event handling
- Tracks agent transfers
- Filters internal events (transfer_to_agent)
- Proper error handling
- Session persistence

#### Deliverables:
- [ ] All event types handled
- [ ] Agent transfers tracked
- [ ] Errors logged and returned

---

### PHASE 7: Testing Framework (Week 4)
**Goal:** Comprehensive test suite for A2A

```python
# niv_ai/niv_core/a2a/tests/test_a2a.py

import frappe
import unittest
from ..runner import stream_a2a

class TestA2ABasics(unittest.TestCase):
    """Test basic A2A functionality."""
    
    def setUp(self):
        self.conversation_id = f"test_{frappe.generate_hash(length=8)}"
    
    def test_simple_greeting(self):
        """Orchestrator should handle simple greetings."""
        events = list(stream_a2a("Hello", self.conversation_id))
        
        # Should have tokens
        tokens = [e for e in events if e["type"] == "token"]
        self.assertTrue(len(tokens) > 0)
        
        # Should complete
        done = [e for e in events if e["type"] == "done"]
        self.assertEqual(len(done), 1)
    
    def test_route_to_analyst(self):
        """Should route data questions to analyst."""
        events = list(stream_a2a(
            "How many customers do we have?",
            self.conversation_id
        ))
        
        # Should have agent transfer
        transfers = [e for e in events if e["type"] == "agent_transfer"]
        self.assertTrue(any(t["to"] == "data_analyst" for t in transfers))
    
    def test_route_to_coder(self):
        """Should route coding requests to coder."""
        events = list(stream_a2a(
            "Create a DocType called Test Item",
            self.conversation_id
        ))
        
        transfers = [e for e in events if e["type"] == "agent_transfer"]
        self.assertTrue(any(t["to"] == "frappe_coder" for t in transfers))
    
    def test_route_to_nbfc(self):
        """Should route loan queries to NBFC specialist."""
        events = list(stream_a2a(
            "Show me overdue loans",
            self.conversation_id
        ))
        
        transfers = [e for e in events if e["type"] == "agent_transfer"]
        self.assertTrue(any(t["to"] == "nbfc_specialist" for t in transfers))
    
    def test_tool_execution(self):
        """Tools should execute and return results."""
        events = list(stream_a2a(
            "List all modules in the system",
            self.conversation_id
        ))
        
        # Should have tool calls
        tool_calls = [e for e in events if e["type"] == "tool_call"]
        tool_results = [e for e in events if e["type"] == "tool_result"]
        
        self.assertTrue(len(tool_results) > 0)
    
    def test_no_hallucination(self):
        """Response should not contain obviously fake data."""
        events = list(stream_a2a(
            "What is the total sales amount today?",
            self.conversation_id
        ))
        
        full_response = "".join(
            e["content"] for e in events if e["type"] == "token"
        )
        
        # Should not contain placeholder data
        fake_indicators = ["$1,000,000", "example", "dummy", "test data"]
        for indicator in fake_indicators:
            self.assertNotIn(indicator.lower(), full_response.lower())


class TestA2ASession(unittest.TestCase):
    """Test session persistence."""
    
    def test_session_persists(self):
        """Session state should persist across calls."""
        conversation_id = f"test_{frappe.generate_hash(length=8)}"
        
        # First call
        list(stream_a2a("My name is Ravi", conversation_id))
        
        # Second call should remember
        events = list(stream_a2a("What is my name?", conversation_id))
        response = "".join(e["content"] for e in events if e["type"] == "token")
        
        self.assertIn("Ravi", response)


def run_tests():
    """Run all A2A tests."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestA2ABasics)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestA2ASession))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful()
    }
```

#### Test Coverage:
- [ ] Basic greeting (no transfer needed)
- [ ] Route to each specialist correctly
- [ ] Tool execution works
- [ ] No hallucination
- [ ] Session persistence

#### Deliverables:
- [ ] Test suite created
- [ ] All tests passing
- [ ] CI integration

---

### PHASE 8: UI Integration (Week 5)
**Goal:** Connect new A2A to existing UI

#### Update stream.py to use new A2A:
```python
# In niv_ai/niv_core/api/stream.py

# Add A2A import
from niv_ai.niv_core.a2a.runner import stream_a2a

# In stream_chat():
use_a2a = getattr(settings, "enable_a2a", 0)
if use_a2a:
    for event in stream_a2a(
        message=message,
        conversation_id=conversation_id,
        provider_name=provider,
        model_name=model,
        user=user
    ):
        # Map A2A events to existing SSE format
        event_type = event.get("type", "")
        
        if event_type == "token":
            yield _sse({"type": "token", "content": event["content"]})
        
        elif event_type == "agent_transfer":
            yield _sse({
                "type": "thought",
                "content": f"Handing off to {event['to']}..."
            })
        
        elif event_type == "tool_call":
            yield _sse({
                "type": "tool_call",
                "tool": event["tool"],
                "arguments": event["arguments"]
            })
        
        elif event_type == "tool_result":
            yield _sse({
                "type": "tool_result",
                "tool": event["tool"],
                "result": event["result"]
            })
        
        elif event_type == "error":
            yield _sse({"type": "error", "content": event["content"]})
    
    return  # Skip legacy flow
```

#### UI Updates for Agent Transfer:
```javascript
// In niv_chat.js, handle agent_transfer event

// Show agent badge when transfer happens
if (data.type === "thought" && data.content.includes("Handing off to")) {
    const agentName = data.content.match(/Handing off to (.+)\.\.\./)[1];
    this.show_agent_badge(agentName);
}

show_agent_badge(agentName) {
    const badgeHtml = `<span class="agent-badge">${agentName}</span>`;
    this.$chatArea.find(".niv-message.assistant:last .msg-content").prepend(badgeHtml);
}
```

#### Deliverables:
- [ ] A2A integrated with existing SSE stream
- [ ] UI shows agent transfers
- [ ] Backwards compatible with non-A2A mode

---

### PHASE 9: Error Recovery & Fallback (Week 5-6)
**Goal:** Graceful degradation when things fail

```python
# niv_ai/niv_core/a2a/recovery.py

import frappe
from typing import Dict, Any, Generator
import time

class A2ARecoveryHandler:
    """Handles errors and provides fallback mechanisms."""
    
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 5]  # seconds
    
    def __init__(self, runner):
        self.runner = runner
        self.error_count = 0
        self.last_error = None
    
    def stream_with_recovery(
        self,
        message: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream with automatic retry and fallback."""
        
        for attempt in range(self.MAX_RETRIES):
            try:
                yield from self.runner.stream(message)
                return  # Success, exit
                
            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                
                frappe.log_error(
                    f"A2A attempt {attempt + 1} failed: {e}",
                    "Niv AI A2A Recovery"
                )
                
                if attempt < self.MAX_RETRIES - 1:
                    # Retry with delay
                    yield {
                        "type": "thought",
                        "content": f"Retrying... (attempt {attempt + 2})"
                    }
                    time.sleep(self.RETRY_DELAYS[attempt])
                else:
                    # All retries failed, use fallback
                    yield from self._fallback_response(message)
    
    def _fallback_response(
        self,
        message: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Fallback to legacy LangGraph agent."""
        
        yield {
            "type": "thought",
            "content": "A2A failed, using backup system..."
        }
        
        try:
            # Import legacy agent
            from niv_ai.niv_core.langchain.agent import create_niv_agent
            
            agent = create_niv_agent(
                conversation_id=self.runner.conversation_id,
                provider_name=None,
                model_name=None
            )
            
            # Stream from legacy agent
            for event in agent.stream(message):
                yield event
                
        except Exception as fallback_error:
            yield {
                "type": "error",
                "content": (
                    f"Both A2A and backup failed.\n"
                    f"A2A Error: {self.last_error}\n"
                    f"Backup Error: {str(fallback_error)}"
                )
            }
```

#### Circuit Breaker Pattern:
```python
# niv_ai/niv_core/a2a/circuit_breaker.py

import frappe
import time
from typing import Callable

class CircuitBreaker:
    """Prevents cascading failures."""
    
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 60  # seconds
    
    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.RECOVERY_TIMEOUT:
                self.state = "HALF_OPEN"
            else:
                raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = func(*args, **kwargs)
            
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
            
            return result
            
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.failures >= self.FAILURE_THRESHOLD:
                self.state = "OPEN"
                frappe.log_error(
                    f"Circuit breaker {self.name} OPENED after {self.failures} failures",
                    "Niv AI Circuit Breaker"
                )
            
            raise
```

#### Deliverables:
- [ ] Automatic retry with exponential backoff
- [ ] Fallback to legacy LangGraph
- [ ] Circuit breaker prevents cascading failures
- [ ] All errors logged

---

### PHASE 10: Observability & Production (Week 6-8)
**Goal:** Full visibility and production readiness

#### Logging DocType:
```python
# Create Niv A2A Log DocType
{
    "doctype": "DocType",
    "name": "Niv A2A Log",
    "module": "Niv AI",
    "fields": [
        {"fieldname": "conversation_id", "fieldtype": "Data"},
        {"fieldname": "user", "fieldtype": "Link", "options": "User"},
        {"fieldname": "message", "fieldtype": "Long Text"},
        {"fieldname": "agents_invoked", "fieldtype": "Small Text"},
        {"fieldname": "tools_called", "fieldtype": "Small Text"},
        {"fieldname": "total_tokens", "fieldtype": "Int"},
        {"fieldname": "duration_ms", "fieldtype": "Int"},
        {"fieldname": "status", "fieldtype": "Select", "options": "Success\nError\nFallback"},
        {"fieldname": "error_message", "fieldtype": "Long Text"}
    ]
}
```

#### Metrics Dashboard:
```python
# niv_ai/niv_core/a2a/metrics.py

import frappe

def get_a2a_metrics(period: str = "today") -> dict:
    """Get A2A performance metrics."""
    
    filters = {}
    if period == "today":
        filters["creation"] = [">", frappe.utils.add_days(frappe.utils.today(), -1)]
    elif period == "week":
        filters["creation"] = [">", frappe.utils.add_days(frappe.utils.today(), -7)]
    
    logs = frappe.get_all(
        "Niv A2A Log",
        filters=filters,
        fields=["status", "agents_invoked", "tools_called", "duration_ms", "total_tokens"]
    )
    
    total = len(logs)
    success = sum(1 for l in logs if l.status == "Success")
    errors = sum(1 for l in logs if l.status == "Error")
    fallbacks = sum(1 for l in logs if l.status == "Fallback")
    
    avg_duration = sum(l.duration_ms or 0 for l in logs) / total if total > 0 else 0
    total_tokens = sum(l.total_tokens or 0 for l in logs)
    
    # Agent distribution
    agent_counts = {}
    for log in logs:
        for agent in (log.agents_invoked or "").split(","):
            agent = agent.strip()
            if agent:
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
    
    return {
        "total_requests": total,
        "success_rate": (success / total * 100) if total > 0 else 0,
        "error_rate": (errors / total * 100) if total > 0 else 0,
        "fallback_rate": (fallbacks / total * 100) if total > 0 else 0,
        "avg_duration_ms": avg_duration,
        "total_tokens": total_tokens,
        "agent_distribution": agent_counts
    }
```

#### Production Checklist:
- [ ] All DocTypes created (Niv A2A Session, Niv A2A Log)
- [ ] Error logging comprehensive
- [ ] Metrics dashboard working
- [ ] Circuit breaker tested
- [ ] Recovery fallback tested
- [ ] Load tested (100 concurrent requests)
- [ ] Growth System specific prompts added
- [ ] Documentation complete

---

## 🏗️ ARCHITECTURE DIAGRAMS

### High-Level Flow
```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   User      │────▶│   Orchestrator   │────▶│    Specialists    │
│  Message    │     │   (niv_orch)     │     │                  │
└─────────────┘     └────────┬────────┘     │ ┌──────────────┐ │
                             │              │ │ frappe_coder │ │
                    ┌────────▼────────┐     │ ├──────────────┤ │
                    │  Route Decision  │     │ │ data_analyst │ │
                    │  (LLM + Desc)    │     │ ├──────────────┤ │
                    └────────┬────────┘     │ │nbfc_specialist│ │
                             │              │ ├──────────────┤ │
                    ┌────────▼────────┐     │ │sys_discovery │ │
                    │ transfer_to_agent│────▶│ └──────────────┘ │
                    └─────────────────┘     └──────────────────┘
                                                      │
                                                      ▼
                                            ┌──────────────────┐
                                            │    MCP Tools      │
                                            │ (29 Frappe tools) │
                                            └──────────────────┘
```

### Session Flow
```
┌─────────────┐
│  Request 1  │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         FrappeSessionService              │
│  ┌────────────────────────────────────┐  │
│  │  MariaDB: Niv A2A Session          │  │
│  │  - session_id                      │  │
│  │  - state_json (shared state)       │  │
│  │  - events_json (history)           │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  Request 2  │  ◀── Reads previous state
└─────────────┘
```

---

## ✅ SUCCESS METRICS

### Zero-Failure Criteria
| Metric | Target | Measurement |
|--------|--------|-------------|
| Tool Call Success Rate | 100% | No failed tool calls due to context issues |
| Agent Transfer Accuracy | >95% | Correct specialist chosen |
| Hallucination Rate | 0% | No fake data in responses |
| Session Persistence | 100% | State maintained across requests |
| Error Recovery | 100% | Fallback works when A2A fails |

### Performance Targets
| Metric | Target |
|--------|--------|
| First Token Latency | <2 seconds |
| Full Response Time | <30 seconds |
| Concurrent Users | 50+ |
| Memory Usage | <500MB per worker |

---

## 📆 TIMELINE SUMMARY

| Phase | Week | Deliverable |
|-------|------|-------------|
| 1 | 1 | Foundation Reset |
| 2 | 1-2 | Session Persistence |
| 3 | 2 | Specialist Agents |
| 4 | 2-3 | Orchestrator |
| 5 | 3 | MCP Tool Adapter |
| 6 | 3-4 | Stream Handler |
| 7 | 4 | Testing Framework |
| 8 | 5 | UI Integration |
| 9 | 5-6 | Error Recovery |
| 10 | 6-8 | Production |

**Total: 8 weeks for full implementation**

---

## 🔗 REFERENCES

- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [ADK Multi-Agent Guide](https://google.github.io/adk-docs/agents/multi-agents/)
- [A2A Protocol](https://github.com/a2aproject/A2A)
- [ADK Python Samples](https://github.com/google/adk-samples)

---

**Created by Nova for Niv AI**
**Last Updated: 2026-02-14**
