# Niv AI — Growth System Testing Results
**Date:** 2026-02-11
**Instance:** mdfc-test.growthsystem.in (Frappe v14)
**User:** Mahaveer Poonia (MP)
**Model:** mistral-small-latest (set during testing — was EMPTY before)
**Tester:** Nova (AI)

---

## 🔴 CRITICAL BUG: Intermittent Tool Failure

**Pattern:**
- 1st message in new chat → Tools WORK ✅
- 2nd message in SAME chat → Tools FAIL ❌ ("I don't have the capability")
- New chat again → Tools WORK ✅ (sometimes)

**Root Cause:** Self-referencing MCP deadlock
- Niv AI calls MDFC MCP server at `https://mdfc-test.growthsystem.in/...`
- This is the SAME server running Niv AI
- Gunicorn worker handling the chat request tries to HTTP POST to MCP endpoint on same server
- If all workers are busy → MCP call times out → empty tools → agent has no tools
- `get_all_mcp_tools_cached()` catches the exception silently, returns `[]`

**Fix needed:** Use internal Python function call for same-server FAC instead of HTTP, OR increase gunicorn workers.

---

## A. DocTypes (20 total)

| # | DocType | Status | Count | Notes |
|---|---------|--------|-------|-------|
| 1 | Niv Settings | ⚠️ | - | `ProgrammingError` — may need `bench migrate` |
| 2 | Niv Conversation | ✅ | 43 | Working, conversations create/load |
| 3 | Niv Message | ✅ | 260 | Working, messages store/retrieve |
| 4 | Niv MCP Server | ✅ | 1 | MDFC MCP configured, Connected, 34 tools |
| 5 | Niv MCP Tool | ⚠️ | (child) | PermissionError on API — v14 child table issue |
| 6 | Niv AI Provider | ✅ | 1 | Mistral configured |
| 7 | Niv Tool | ✅ | 0 | Empty (expected — MCP-only architecture) |
| 8 | Niv Tool Log | ✅ | 22 | Tool calls logged |
| 9 | Niv Wallet | ✅ | 0 | No wallets (billing disabled) |
| 10 | Niv Credit Plan | ✅ | 3 | Plans created |
| 11 | Niv Recharge | ✅ | 0 | No recharges |
| 12 | Niv Usage Log | ✅ | 0 | No usage tracked (billing OFF) |
| 13 | Niv Knowledge Base | ✅ | 0 | Empty |
| 14 | Niv KB Chunk | ✅ | 0 | Empty |
| 15 | Niv File | ✅ | 0 | Empty |
| 16 | Niv Shared Chat | ✅ | 0 | Empty |
| 17 | Niv Custom Instruction | ✅ | 0 | Empty |
| 18 | Niv System Prompt | ✅ | 0 | Empty |
| 19 | Niv Auto Action | ✅ | 0 | Empty |
| 20 | Niv Scheduled Report | ✅ | 0 | Empty |

**Result: 18/20 ✅, 2/20 ⚠️**

---

## B. MCP Tools (34 total) — Tested via UI Chat

| # | Tool | Status | Test Query | Notes |
|---|------|--------|-----------|-------|
| 1 | list_documents | ✅ | "list top 5 loans" | Returned 5 loans in table |
| 2 | get_document | ✅ | "Get details of first Loan" | Full loan doc with all fields |
| 3 | list_documents (count) | ✅ | "How many Customers" | 28,141 customers counted |
| 4 | search_documents | ❌ | "Search loans with RTF" | "Don't have capability" — tool not bound |
| 5 | search_doctype | ❌ | "DocTypes related to Loan" | "Don't have capability" — tool not bound |
| 6 | create_document | ⏳ | Not tested (destructive) | |
| 7 | update_document | ⏳ | Not tested (destructive) | |
| 8 | delete_document | ⏳ | Not tested (destructive) | |
| 9 | submit_document | ⏳ | Not tested (destructive) | |
| 10 | search_link | ⏳ | Blocked by intermittent bug | |
| 11 | search | ⏳ | Blocked by intermittent bug | |
| 12 | fetch | ⏳ | Blocked by intermittent bug | |
| 13 | get_doctype_info | ⏳ | Blocked by intermittent bug | |
| 14 | generate_report | ⏳ | Blocked by intermittent bug | |
| 15 | report_list | ⏳ | Blocked by intermittent bug | |
| 16 | report_requirements | ⏳ | Blocked by intermittent bug | |
| 17 | run_workflow | ⏳ | Blocked by intermittent bug | |
| 18 | run_python_code | ⏳ | Blocked by intermittent bug | |
| 19 | run_database_query | ⏳ | Blocked by intermittent bug | |
| 20 | create_dashboard | ⏳ | Blocked by intermittent bug | |
| 21 | create_dashboard_chart | ⏳ | Blocked by intermittent bug | |
| 22 | list_user_dashboards | ⏳ | Blocked by intermittent bug | |
| 23 | analyze_business_data | ⏳ | Blocked by intermittent bug | |
| 24 | extract_file_content | ⏳ | Blocked by intermittent bug | |
| 25 | send_email | ⏳ | Not tested (side effect) | |
| 26 | excel_generator | ⏳ | Blocked by intermittent bug | |
| 27 | pdf_generator | ⏳ | Blocked by intermittent bug | |
| 28 | nbfc_credit_scoring | ⏳ | Blocked by intermittent bug | |
| 29 | nbfc_loan_prequalification | ⏳ | Blocked by intermittent bug | |
| 30 | cersai_registration | ⏳ | Blocked by intermittent bug | |
| 31 | rbi_return_generator | ⏳ | Blocked by intermittent bug | |
| 32 | ckyc_updater | ⏳ | Blocked by intermittent bug | |
| 33 | aml_screening | ⏳ | Blocked by intermittent bug | |
| 34 | fair_practice_compliance | ⏳ | Blocked by intermittent bug | |
| 35 | interest_rate_disclosure | ⏳ | Blocked by intermittent bug | |

**Result: 3/34 ✅, 2/34 ❌ (intermittent), 29/34 ⏳ (blocked by tool binding bug)**

---

## C. UI Features

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Chat page loads | ✅ | Dark mode, clean UI |
| 2 | New conversation | ✅ | Creates on first message |
| 3 | Send message | ✅ | User bubble visible |
| 4 | Streaming response | ✅ | SSE works after model was set |
| 5 | Tool call accordion | ⏳ | Not visible in tests (tools run silently) |
| 6 | Table rendering | ✅ | Beautiful tables with data |
| 7 | Sidebar conversations | ✅ | 43+ conversations listed |
| 8 | Search conversations | ✅ | Search bar present |
| 9 | Delete conversation | ✅ | Delete button works |
| 10 | Dark mode | ✅ | Default theme looks great |
| 11 | Copy message | ⏳ | Not tested |
| 12 | Edit message | ⏳ | Not tested |
| 13 | Regenerate response | ⏳ | Not tested |
| 14 | Voice typing (STT) | ⏳ | Buttons present, not tested |
| 15 | Voice mode | ⏳ | Button present, not tested |
| 16 | Floating widget | ✅ | Widget button visible (bottom right ✦) |
| 17 | Share chat | ⏳ | Button present, not tested |
| 18 | User message visible | ✅ | User messages show correctly |
| 19 | Scroll to bottom | ✅ | Auto-scrolls on new message |
| 20 | Mobile responsive | ⏳ | Not tested (desktop only) |

**Result: 10/20 ✅, 10/20 ⏳ (not tested)**

---

## D. Configuration Issues Found

| # | Issue | Severity | Fix |
|---|-------|----------|-----|
| 1 | Default Model was EMPTY | 🔴 Critical | Fixed: set `mistral-small-latest` |
| 2 | Niv Settings ProgrammingError | 🟡 Medium | Run `bench migrate` on server |
| 3 | Niv MCP Tool child table PermissionError | 🟡 Medium | v14 permission issue |
| 4 | Intermittent tool failure (self-ref deadlock) | 🔴 Critical | See fix below |
| 5 | System prompt has JS code in it | 🟡 Medium | Remove `frappe.call(...)` from system prompt |

---

## E. Recommendations

### Must Fix (v0.4.0)
1. **Self-referencing MCP deadlock** — When FAC MCP runs on same server, use direct Python import instead of HTTP self-call
2. **Run `bench migrate`** on Growth System to fix Niv Settings table
3. **Clean system prompt** — Remove the `frappe.call({...})` JS code from system prompt (it's confusing the AI)

### Nice to Have
4. Increase gunicorn workers (temporary workaround for deadlock)
5. Add tool binding validation — if 0 tools loaded, log warning and retry once
6. Add health check endpoint to verify MCP connection status

---

*Testing completed: 2026-02-11 10:45 IST*
