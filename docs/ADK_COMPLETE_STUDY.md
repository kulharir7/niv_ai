# 🎓 ADK COMPLETE STUDY — What We're Doing Wrong & How to Fix It

**Study Date:** 2026-02-15
**Studied By:** Nova
**Purpose:** Deep dive into why A2A isn't working and exact fixes needed

---

## 📊 STUDY SUMMARY

| Aspect | Our Code | Official ADK | Status |
|--------|----------|--------------|--------|
| Agent Hierarchy | ❌ TransferToAgentTool | ✅ sub_agents param | **WRONG** |
| Session Service | ❌ InMemorySessionService (fresh each call) | ✅ Persistent service | **WRONG** |
| State Sharing | ❌ No output_key | ✅ output_key + {var} template | **MISSING** |
| Agent Description | ❌ Generic text | ✅ Specific, differentiating | **WEAK** |
| Runner | ❌ Sync runner.run() | ✅ runner.run_async() | **PROBLEMATIC** |
| Tool Execution | ❌ Frappe context broken | ✅ Proper context init | **BUGGY** |
| Event Handling | ❌ Missing event types | ✅ All 4 event types | **INCOMPLETE** |

---

## 🔴 CRITICAL BUG #1: Wrong Agent Delegation Method

### What We're Doing (WRONG)
```python
# agent_factory.py line 127-128
transfer_tool = TransferToAgentTool(agent_names=[coder.name, data.name, discovery.name, nbfc.name])

return LlmAgent(
    name="niv_orchestrator",
    tools=tools + [transfer_tool],  # ← WRONG!
    sub_agents=[coder, data, discovery, nbfc]  # ← We DO pass this but also use transfer_tool
)
```

### Why It's Wrong
1. **TransferToAgentTool is DEPRECATED** for LLM-driven delegation
2. When you pass `sub_agents`, ADK **AUTOMATICALLY** adds transfer capability
3. Using BOTH causes conflicts

### What Official Docs Say
> "You create a tree structure by passing a list of agent instances to the `sub_agents` argument when initializing a parent agent. ADK automatically sets the parent_agent attribute on each child agent."

### Correct Code
```python
# Just use sub_agents - NO TransferToAgentTool
return LlmAgent(
    name="niv_orchestrator",
    model=self.adk_model,
    instruction="...",
    description="Main coordinator that routes requests to specialists",
    tools=tools,  # ← Only regular tools
    sub_agents=[coder, data, discovery, nbfc]  # ← ADK handles transfers
)
```

---

## 🔴 CRITICAL BUG #2: Session Service Created Fresh Every Call

### What We're Doing (WRONG)
```python
# stream_handler.py line 22-26
runner = Runner(
    app=app,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),  # ← Created NEW every call!
    memory_service=InMemoryMemoryService(),
    auto_create_session=True
)
```

### Why It's Wrong
1. **InMemorySessionService is for testing only** — data lost on restart
2. Creating it **inside the function** means EVERY request gets a NEW service
3. Sessions cannot persist — agents have NO memory of previous turns

### What Official Docs Say
> "InMemorySessionService: Stores all session data directly in application's memory. Persistence: None. All conversation data is lost if the application restarts. Best for: Quick development, local testing."

### What We Need
```python
# Create ONCE at module level, reuse across calls
from niv_ai.niv_core.a2a.session import FrappeSessionService

# Module-level singleton
_session_service = None

def get_session_service():
    global _session_service
    if _session_service is None:
        _session_service = FrappeSessionService()  # MariaDB-backed
    return _session_service

def stream_agent_adk(...):
    runner = Runner(
        session_service=get_session_service(),  # ← REUSE
        ...
    )
```

---

## 🔴 CRITICAL BUG #3: No output_key = No State Sharing

### What We're Doing (WRONG)
```python
# agent_factory.py - All agents
return LlmAgent(
    name="data_analyst",
    model=self.adk_model,
    instruction="...",
    tools=tools
    # ← NO output_key!
)
```

### Why It's Wrong
1. Without `output_key`, agent's response is NOT saved to session state
2. Next agent cannot access previous agent's results
3. State sharing = BROKEN

### What Official Docs Say
> "SequentialAgent: Executes its sub_agents one after another. Passes the same InvocationContext sequentially, allowing agents to easily pass results via shared state."
>
> ```python
> step1 = LlmAgent(name="Step1_Fetch", output_key="data")  # Saves output to state['data']
> step2 = LlmAgent(name="Step2_Process", instruction="Process data from {data}.")
> ```

### Correct Code
```python
return LlmAgent(
    name="data_analyst",
    model=self.adk_model,
    instruction="...",
    output_key="analyst_result",  # ← CRITICAL: Save output to state
    tools=tools
)

# Orchestrator can then use {analyst_result} in instruction
```

---

## 🔴 CRITICAL BUG #4: Agent Descriptions Too Vague

### What We're Doing (WEAK)
```python
# agent_factory.py - orchestrator instruction
instruction=(
    "You are Niv Orchestrator. "
    "- For Coding/DocTypes: transfer to 'frappe_coder'. "
    ...
)
```

But the AGENTS themselves have **NO description** attribute!

### Why It's Wrong
1. `description` is what LLM reads to decide WHERE to route
2. Without proper descriptions, LLM cannot make informed decisions
3. Instructions tell agent WHAT to do, descriptions tell PARENT WHO the agent is

### What Official Docs Say
> "description (Optional, Recommended for Multi-Agent): Provide a concise summary of the agent's capabilities. This description is primarily used by OTHER LLM agents to determine if they should route a task to this agent. Make it specific enough to differentiate it from peers."

### Correct Code
```python
return LlmAgent(
    name="frappe_coder",
    model=self.adk_model,
    description=(  # ← CRITICAL for routing
        "EXPERT in Frappe/ERPNext development. "
        "Handles: DocType creation, Server Scripts, Client Scripts, "
        "Custom Fields, Workflows, Print Formats, Web Forms. "
        "DO NOT USE for data queries or reports."
    ),
    instruction="...",
    tools=tools
)
```

---

## 🟡 MODERATE BUG #5: Sync vs Async Runner

### What We're Doing
```python
# stream_handler.py line 40
for event in runner.run(
    new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ...
):
```

### Potential Issues
1. `runner.run()` is synchronous
2. Agent transfers might not yield events properly in sync mode
3. Long-running tool calls block the generator

### Better Approach
```python
# Use async runner if Frappe supports it
async for event in runner.run_async(...):
    yield transform_event(event)

# Or wrap sync in proper executor
import asyncio
loop = asyncio.get_event_loop()
for event in loop.run_until_complete(runner.run_async(...)):
    yield transform_event(event)
```

---

## 🟡 MODERATE BUG #6: Frappe Context in Thread Pool

### What We're Doing
```python
# agent_factory.py line 44-48
def make_executor(t_name, t_doc, site):
    def tool_func(**kwargs):
        if not getattr(frappe.local, "site", None):
            frappe.init(site=site)
            frappe.connect()
        # ... tool execution
```

### Potential Issues
1. `frappe.local` is thread-local
2. ADK may run tools in ThreadPoolExecutor
3. Race conditions possible if multiple tools run concurrently

### Better Approach
```python
def make_executor(t_name, t_doc, site):
    def tool_func(**kwargs):
        # Always re-init in tool context
        try:
            frappe.init(site=site)
            frappe.connect()
            
            result = call_tool_fast(...)
            return result
        finally:
            # Clean up to prevent leaks
            frappe.db.close()
    
    return tool_func
```

---

## 🟡 MODERATE BUG #7: Incomplete Event Handling

### What We're Doing
```python
# stream_handler.py line 48-69
for event in runner.run(...):
    if event.text:
        yield {"type": "token", "content": event.text}
    
    tool_calls = event.get_function_calls()
    if tool_calls:
        ...
    
    tool_results = event.get_function_responses()
    if tool_results:
        ...
    
    # Handle agent transfer
    if event.author != "user" and not event.text and not tool_calls:
        if event.author != "niv_orchestrator":
            yield {"type": "thought", "content": f"Handed control to {event.author}..."}
```

### What's Missing
1. **State delta events** — when state changes
2. **Agent switch events** — explicit transfer notifications
3. **Error events** — when things fail
4. **Completion events** — when agent finishes

### What Official Docs Say
> Event types: text, function_calls, function_responses, author changes, state deltas, artifacts

### Complete Event Handling
```python
for event in runner.run(...):
    # 1. Text content
    if event.text:
        yield {"type": "token", "content": event.text}
    
    # 2. Tool calls
    tool_calls = event.get_function_calls()
    if tool_calls:
        for tc in tool_calls:
            yield {"type": "tool_call", "tool": tc.name, "arguments": tc.args}
    
    # 3. Tool results
    tool_results = event.get_function_responses()
    if tool_results:
        for tr in tool_results:
            yield {"type": "tool_result", "tool": tr.name, "result": str(tr.response)}
    
    # 4. State changes (NEW)
    if hasattr(event, 'actions') and event.actions:
        state_delta = event.actions.state_delta
        if state_delta:
            yield {"type": "state_change", "delta": state_delta}
    
    # 5. Agent transfers (IMPROVED)
    if hasattr(event, 'transfer_to_agent'):
        yield {"type": "agent_transfer", "from": event.author, "to": event.transfer_to_agent}
    
    # 6. Errors (NEW)
    if hasattr(event, 'error') and event.error:
        yield {"type": "error", "message": str(event.error)}
    
    # 7. Completion (NEW)
    if hasattr(event, 'is_final') and event.is_final:
        yield {"type": "complete", "final_author": event.author}
```

---

## 🟢 WHAT WE'RE DOING RIGHT

### ✅ MCP Tool Conversion
```python
# agent_factory.py - This is correct!
def _convert_mcp_to_adk(self) -> Dict[str, FunctionTool]:
    for tool_def in self.all_mcp_tools:
        tool = FunctionTool(func=make_executor(name, description, self.site))
        adk_tools[name] = tool
```
We correctly wrap MCP tools as ADK FunctionTools.

### ✅ Categorized Tool Assignment
```python
# agent_factory.py - Good categorization
coder_tool_names = ["create_document", "update_document", ...]
data_tool_names = ["run_database_query", "analyze_business_data", ...]
```
We assign relevant tools to relevant agents.

### ✅ LiteLLM Integration
```python
# agent_factory.py - Correct
self.adk_model = LiteLlm(
    model=model_id,
    api_key=api_key,
    api_base=provider.base_url
)
```
We correctly use LiteLLM for multi-provider support.

### ✅ Discovery Engine Concept
The `discovery.py` pattern of scanning DocTypes is good — but needs proper integration with session state.

---

## 📋 EXACT FIXES CHECKLIST

### Phase 1: Immediate Fixes (1-2 days)
- [ ] Remove `TransferToAgentTool` — rely only on `sub_agents`
- [ ] Add `description` attribute to ALL specialist agents
- [ ] Add `output_key` to ALL agents
- [ ] Create singleton SessionService (even if InMemory for now)

### Phase 2: Session Persistence (3-5 days)
- [ ] Create `FrappeSessionService` class
- [ ] Create `Niv A2A Session` DocType
- [ ] Implement `create_session`, `get_session`, `update_session`, `delete_session`
- [ ] Wire into Runner

### Phase 3: Complete Event Handling (2-3 days)
- [ ] Handle state_delta events
- [ ] Handle explicit transfer events
- [ ] Handle error events
- [ ] Handle completion events

### Phase 4: Testing (2-3 days)
- [ ] Test single agent + tools
- [ ] Test agent-to-agent transfer
- [ ] Test state sharing between agents
- [ ] Test session persistence across requests

---

## 🧠 KEY LEARNINGS

### 1. sub_agents IS the Transfer Mechanism
> "Establishing Hierarchy: You create a tree structure by passing a list of agent instances to the sub_agents argument. ADK automatically sets the parent_agent attribute on each child agent."

### 2. Description is for Routing
> "description is primarily used by OTHER LLM agents to determine if they should route a task to this agent."

### 3. output_key Enables State Flow
> "step1 = LlmAgent(name="Step1_Fetch", output_key="data") — Saves output to state['data']"

### 4. InMemory is Testing Only
> "InMemorySessionService: Best for quick development, local testing, examples where persistence isn't required."

### 5. State Prefixes Matter
> - No prefix: Session-specific (current conversation)
> - `user:` prefix: User-wide (shared across sessions)
> - `app:` prefix: App-wide (shared across users)
> - `temp:` prefix: Current invocation only

---

## 📁 FILES TO MODIFY

1. **DELETE:** `niv_ai/niv_core/adk/agent_factory.py` (rewrite)
2. **DELETE:** `niv_ai/niv_core/adk/stream_handler.py` (rewrite)
3. **CREATE:** `niv_ai/niv_core/a2a/` (new directory structure)
4. **CREATE:** `Niv A2A Session` DocType
5. **MODIFY:** `niv_ai/niv_core/api/stream.py` (use new A2A)

---

## 📚 REFERENCES

- ADK Multi-Agent Systems: https://google.github.io/adk-docs/agents/multi-agents/
- ADK Sessions: https://google.github.io/adk-docs/sessions/
- ADK State: https://google.github.io/adk-docs/sessions/state/
- ADK LLM Agents: https://google.github.io/adk-docs/agents/llm-agents/
- A2A Master Plan: `niv_ai/docs/A2A_MASTER_PLAN.md`

---

*This study report is the foundation for fixing A2A. Follow the checklist in order.*

---

## 📚 OFFICIAL ADK SAMPLES ANALYSIS (Added 2026-02-15)

Source: https://github.com/google/adk-samples

### Samples Studied:
1. **RAG** — Vertex AI retrieval with `VertexAiRagRetrieval` tool
2. **customer-service** — Single agent with tools + callbacks
3. **data-science** — Multi-agent with `sub_agents` + dynamic tools
4. **travel-concierge** — Complex hierarchy with 6 sub-agents

### Key Patterns Discovered:

#### 1. Two Ways to Use Sub-Agents
```python
# Option A: sub_agents (LLM-driven transfer)
root = Agent(
    sub_agents=[agent1, agent2]  # LLM decides when to transfer
)

# Option B: AgentTool (Explicit invocation)
from google.adk.tools.agent_tool import AgentTool
root = Agent(
    tools=[AgentTool(agent=agent1)]  # Called as a tool
)
```

#### 2. Sub-Agent Pattern (from travel-concierge)
```python
place_agent = Agent(
    model="gemini-2.5-flash",
    name="place_agent",
    description="This agent suggests destinations given user preferences",
    instruction=prompt.PLACE_AGENT_INSTR,
    disallow_transfer_to_parent=True,  # Prevent returning mid-task
    disallow_transfer_to_peers=True,   # Prevent sibling transfers
    output_schema=DestinationIdeas,    # Pydantic model for structured output
    output_key="place",                # Saves to state['place']
)
```

#### 3. Root Agent Pattern (from data-science)
```python
agent = LlmAgent(
    model="gemini-2.5-flash",
    name="data_science_root_agent",
    instruction=return_instructions_root(),
    global_instruction="You are a Data Science Multi Agent System.",
    sub_agents=sub_agents,
    tools=tools,
    before_agent_callback=load_database_settings_in_context,
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)
```

### Features Our Implementation Has:
- ✅ `sub_agents` for hierarchy
- ✅ `description` for routing
- ✅ `output_key` for state sharing

### Features We Can Add:
- 🔄 `disallow_transfer_to_parent` — Prevent premature returns
- 🔄 `disallow_transfer_to_peers` — Prevent sibling transfers
- 🔄 `output_schema` — Pydantic models for structured output
- 🔄 `global_instruction` — Common context for all agents
- 🔄 `before_agent_callback` — State initialization
- 🔄 `generate_content_config` — Temperature control
