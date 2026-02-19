# Niv AI — A2A Multi-Agent Workflow

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                      USER                            │
│            (Chat UI / Telegram / WhatsApp)            │
└─────────────────┬───────────────────────────────────┘
                  │ message
                  ▼
┌─────────────────────────────────────────────────────┐
│              🎯 ORCHESTRATOR                         │
│         (The Brain — Routes Requests)                │
│                                                      │
│  Tools: universal_search, list_documents,            │
│         get_doctype_info, save_to_user_memory        │
│                                                      │
│  Logic:                                              │
│  ┌─────────────────────────────────────────────┐    │
│  │ 1. Read user message                         │    │
│  │ 2. Check user memory (preferences)           │    │
│  │ 3. Decide: simple? → answer directly          │    │
│  │    Complex? → pick specialist agent           │    │
│  │ 4. Read specialist result from state          │    │
│  │ 5. Send final answer to user                  │    │
│  └─────────────────────────────────────────────┘    │
└───────┬───────┬───────┬───────┬───────┬─────────────┘
        │       │       │       │       │
   ┌────┘  ┌────┘  ┌────┘  ┌────┘  ┌────┘
   ▼       ▼       ▼       ▼       ▼
┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
│💻    ││📊    ││🏦    ││🔍    ││✅    ││📋    │
│CODER ││ANALYST││NBFC  ││DISC- ││CRITI-││PLAN- │
│      ││      ││SPEC. ││OVERY ││QUE   ││NER   │
└──┬───┘└──┬───┘└──┬───┘└──┬───┘└──────┘└──┬───┘
   │       │       │       │                │
   └───────┴───────┴───────┴────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│              🔧 MCP TOOLS (29 total)                 │
│                                                      │
│  FAC (23): create_document, get_document,            │
│    update_document, list_documents, delete_document,  │
│    run_database_query, generate_report, get_doctype_  │
│    info, search_documents, run_python_code, etc.      │
│                                                      │
│  niv_tools (6): universal_search, explore_fields,    │
│    test_created_item, monitor_errors, rollback,       │
│    introspect_system                                  │
│                                                      │
│  Native (5): knowledge_graph, save_memory,           │
│    create_plan, update_plan, visualize_map            │
│                                                      │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│              📦 ERPNext (Frappe Database)             │
│         DocTypes, Reports, Workflows, Scripts         │
└─────────────────────────────────────────────────────┘
```

---

## 🔄 Request Flow — Step by Step

### Simple Query: "How many customers?"
```
1. User → "How many customers?"
2. Orchestrator reads message
3. Orchestrator decides: DATA query → transfer to data_analyst
4. ─── A2A Transfer ──→ data_analyst activates
5. data_analyst calls: run_database_query("SELECT COUNT(*) FROM tabCustomer")
6. MCP tool executes → returns: {"count": 9}
7. after_tool_callback stores result in state["tool_result_run_database_query"]
8. data_analyst formats: "You have 9 customers"
9. Result saved to state["analyst_result"]
10. ─── A2A Transfer Back ──→ Orchestrator reads state["analyst_result"]
11. Orchestrator sends final answer to User
12. SSE stream: thought → tool_call → tool_result → agent_transfer → token → done
```

### Complex Query: "Loan DocType banao with workflow"
```
1. User → "Loan DocType banao with approval workflow"
2. Orchestrator: Complex task → transfer to niv_planner
3. ─── A2A Transfer ──→ niv_planner activates
4. Planner creates plan:
   Step 1: Create Loan Application DocType (→ frappe_coder)
   Step 2: Create Repayment Schedule child (→ frappe_coder)
   Step 3: Create Approval Workflow (→ frappe_coder)
5. Plan saved to state["planner_result"]
6. ─── A2A Transfer Back ──→ Orchestrator reads plan
7. Orchestrator → transfer to frappe_coder for Step 1
8. ─── A2A Transfer ──→ frappe_coder activates
9. Coder calls: get_doctype_info → create_document → test_created_item
10. Result saved to state["coder_result"]
11. ─── Back to Orchestrator ──→ reads result, executes next step
12. ... repeat for each step ...
13. Final answer sent to User
```

---

## 🔧 What Each Agent Does

### 🎯 Orchestrator (niv_orchestrator)
- **Role:** Traffic controller — routes to right specialist
- **Tools:** universal_search, list_documents, get_doctype_info, save_to_user_memory
- **State reads:** ALL *_result keys from specialists
- **Temperature:** 0.05 (very strict routing)

### 💻 Frappe Coder (frappe_coder)
- **Role:** Creates DocTypes, Scripts, Fields, Workflows
- **Tools:** create_document, update_document, delete_document, get_document, get_doctype_info, search_doctype, run_python_code
- **Output:** state["coder_result"]

### 📊 Data Analyst (data_analyst)
- **Role:** SQL queries, Reports, Analytics
- **Tools:** run_database_query, generate_report, report_list, report_requirements, list_documents, fetch, get_document
- **Output:** state["analyst_result"]

### 🏦 NBFC Specialist (nbfc_specialist)
- **Role:** Loan operations for Growth System
- **Tools:** run_nbfc_audit, run_database_query, list_documents, get_doctype_info, get_document, search_documents
- **Output:** state["nbfc_result"]

### 🔍 System Discovery (system_discovery)
- **Role:** Scan system, find DocTypes, relationships
- **Tools:** get_system_knowledge_graph, visualize_system_map, introspect_system, get_doctype_info, search_doctype, list_documents
- **Output:** state["discovery_result"]

### ✅ Critique (niv_critique)
- **Role:** Quality check — verify no hallucinations
- **Tools:** None (review only)
- **Output:** state["critique_result"] → "PASSED" or "FAILED: reason"

### 📋 Planner (niv_planner)
- **Role:** Break complex tasks into steps
- **Tools:** create_task_plan
- **Output:** state["planner_result"]

---

## 🔴 Current Bugs & Fixes

### Bug #1: Response Text Blank ← CRITICAL
- **Symptom:** Tools run ✅, agent badges show ✅, but NO text response
- **Root Cause:** Runner only yielded `orchestrator_result`, not specialist results
- **Fix:** Changed to yield ANY `*_result` as token event
- **Status:** Fix pushed, needs testing

### Bug #2: No Streaming
- **Symptom:** Response appears all at once, not character by character
- **Root Cause:** `runner.run()` is synchronous, returns complete response
- **Fix:** Use `runner.run_async()` with async generator
- **Status:** TODO

### Bug #3: API Timeout
- **Symptom:** Sometimes no response for 30-60 seconds
- **Root Cause:** LLM provider (ollama-cloud/mistral) slow or rate limited
- **Fix:** Add timeout handling, retry logic, loading indicator
- **Status:** TODO

### Bug #4: `Default value not supported` Warning
- **Symptom:** Console warning on every request
- **Root Cause:** Tool params with `None` defaults → Google AI schema error
- **Fix:** Remove default values from tool function signatures
- **Status:** TODO (non-breaking)

### Bug #5: Docker Restart Kills Everything
- **Symptom:** After PC restart, nothing works
- **Root Cause:** pip install + nginx SSE config lost
- **Fix:** `scripts/full_restore.ps1` exists but needs automation
- **Status:** Script exists, needs auto-run

---

## ✅ Fix Priority Order

```
Week 1: STABILITY
  Day 1: Fix Bug #1 (response text) — TEST thoroughly
  Day 2: Fix Bug #2 (streaming) — run_async
  Day 3: Fix Bug #3 (timeout) — error handling
  Day 4: Fix Bug #4 (default values) — clean signatures

Week 2: FEATURES
  Day 5: Test all 7 agents with real queries
  Day 6: Growth System deployment
  Day 7: Demo to Mahaveer
```

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `a2a/agents/factory.py` | All 7 agent definitions |
| `a2a/runner.py` | Event stream handler |
| `a2a/session/frappe_session.py` | MariaDB session storage |
| `api/stream.py` | SSE endpoint (A2A branch) |
| `mcp_client.py` | MCP tool discovery + execution |
| `niv_chat.js` | UI event rendering |
| `niv_chat_premium.css` | Agent badges + thought styling |
