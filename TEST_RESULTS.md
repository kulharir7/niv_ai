# Niv AI — Comprehensive Test Results
Date: 2026-02-10

## Summary
- **Total Tested:** 22/50 (testing halted due to persistent browser redirect bug)
- **Passed:** 15
- **Failed:** 3
- **Partial:** 4
- **Critical Bug Found:** Browser tab redirects from localhost:8081 to mdfc-test.growthsystem.in after several interactions

## Critical Bug: Page Redirect
**After ~5-8 messages in a chat session, the browser tab silently redirects from `http://localhost:8081/app/niv-chat` to `https://mdfc-test.growthsystem.in/app/niv-chat`.** This happened consistently across multiple browser tabs, making extended testing impossible. This appears to be a JavaScript-level redirect in the Niv AI chat app — possibly related to shared session/cookie state or a hardcoded URL in the frontend code.

## Known Tool Errors
1. **`analyze_data`**: Always fails with `"module 'niv_ai.niv_tools.tools.report_tools' has no attribute 'analyze_data'"` — the tool is registered but the underlying function doesn't exist in the module.
2. **`get_doctype_info`**: Consistently errors with `"'Meta' object has no attribute 'name_case'"` — a code bug in the tool implementation.
3. **400 API Error**: After extended conversation context, the AI backend returns `"Assistant message must have either content or tool_call"` — likely a context window or message formatting issue.

## UI Observations
- ✅ Chat UI is polished with sidebar, conversation history, suggested follow-ups
- ✅ Tool call accordions appear above responses showing which tools were called
- ✅ Token count displayed per response
- ✅ Suggested follow-up questions (3 buttons) after each response
- ✅ Markdown rendering with tables, bold, code blocks, lists, links
- ✅ Document links are clickable (e.g., links to Customer/Invoice forms)
- ⚠️ Tool error results are shown raw JSON in accordion (could be prettier)
- ⚠️ "New Chat" button sometimes loads a pre-existing conversation from the sidebar instead of creating a truly new one
- ❌ Redirect bug (see above)

---

## Detailed Results

### Category 1: Document CRUD (10 queries)

#### Query 1: "List all Sales Orders from last month"
- **Tools Called:** `list_documents`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Correctly used list_documents with date filters. Returned "no Sales Orders from June 2024." Provided helpful follow-up suggestions (check different period, search drafts, create new). Suggested actions as clickable buttons.

#### Query 2: "Show me details of the latest Purchase Invoice"
- **Tools Called:** `list_documents`
- **Result:** ✅ SUCCESS
- **Response Quality:** Excellent
- **Notes:** Found ACC-PINV-2026-00005 from Summit Traders Ltd. Showed Invoice No (with clickable link), Supplier, Posting Date, Due Date, Total Amount (₹105,000), Outstanding Amount, Status (⚠️ Overdue). Very well formatted.

#### Query 3: "Create a new Customer named 'Test Company ABC'"
- **Tools Called:** `create_document`
- **Result:** ✅ SUCCESS
- **Response Quality:** Excellent
- **Notes:** Successfully created Customer with Customer Group "Commercial" and Territory "India". Provided a clickable link to the customer form. Suggested next steps (add contact, create Sales Order, set credit limits).

#### Query 4: "Update the phone number of Customer 'Test Company ABC' to 9876543210"
- **Tools Called:** `update_document`
- **Result:** ✅ SUCCESS
- **Response Quality:** Excellent
- **Notes:** Successfully updated phone number. Showed confirmation with customer name and new phone number in code format. Suggested adding email, creating Sales Order, viewing full details.

#### Query 5: "How many Items are there in the system?"
- **Tools Called:** `analyze_data` (failed x2), `list_documents`
- **Result:** ⚠️ PARTIAL
- **Response Quality:** Partial
- **Notes:** `analyze_data` failed twice with module error, then fell back to `list_documents`. Eventually reported "1,000+ Items" in the system. The fallback recovery worked but wasted tokens and time on failed tool calls.

#### Query 6: "Show me all Quotations with status Draft"
- **Tools Called:** `list_documents`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Correctly queried with status filter. Returned 0 results (no draft quotations). Provided alternatives: check other statuses, create new, search by other filters.

#### Query 7: "What are the fields in the Sales Order doctype?"
- **Tools Called:** `get_doctype_info` (failed), `run_python_code` (x3)
- **Result:** ⚠️ PARTIAL
- **Response Quality:** Good (despite errors)
- **Notes:** `get_doctype_info` failed with "'Meta' object has no attribute 'name_case'". AI then tried `run_python_code` 3 times to get the data. Eventually provided a comprehensive table of fields organized by category (Basic Info, Items Table, Pricing & Taxes, Status & Workflow, Shipping, Payment Terms, References). Response was knowledge-based rather than data-driven.

#### Query 8: "List all Suppliers with their city"
- **Tools Called:** `list_documents`, `get_document` (x3)
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Found 3 suppliers (Summit Traders Ltd., MA Inc., Zuckerman Security Ltd.). Then fetched each document individually to check for city data. Presented a table showing all suppliers have no city set. Suggested updating addresses.

#### Query 9: "Show me the last 5 Stock Entries"
- **Tools Called:** `list_documents`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Returned 0 results (no stock entries in system). Suggested creating a stock entry, checking related documents (Purchase Receipts, Delivery Notes), or verifying warehouse setup.

#### Query 10: "Delete Customer 'Test Company ABC'"
- **Tools Called:** `delete_document`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Successfully deleted the test customer. Clean response confirming deletion with next step suggestions.

### Category 2: Search & Discovery (8 queries)

#### Query 11: "Search for anything related to 'delivery'"
- **Tools Called:** `search` (MCP)
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Used the MCP `search` tool. Found delivery-related DocTypes including Delivery Note, Delivery Note Item, etc. with URLs.

#### Query 12: "Find all documents mentioning 'payment'"
- **Tools Called:** `search` (MCP)
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Found payment-related documents. Explained differences between Payment Request and Payment Entry.

#### Query 13: "What DocTypes are available in the Selling module?"
- **Tools Called:** `list_documents`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Listed DocTypes in the Selling module with descriptions and explanations of workflows.

#### Query 14: "Search for Customer names starting with 'A'"
- **Tools Called:** `search_doctype` (MCP)
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Used MCP `search_doctype` tool to find customers. Found results including Palmer Productions Ltd. and West View Software Ltd.

#### Query 15: "What reports are available for Accounts?"
- **Tools Called:** `report_list` or `list_reports`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Listed accounting reports including Trial Balance, Balance Sheet, Aging Analysis. Well-categorized response.

#### Query 16: "List all available reports in Stock module"
- **Tools Called:** `report_list` (MCP)
- **Result:** ✅ SUCCESS
- **Response Quality:** Excellent
- **Notes:** Found **46 reports** in the Stock module, beautifully categorized into 9 sections: Inventory & Stock Balance, Batch & Serial Number, Stock Integrity & Validation, Analytics & Trends, Reorder & Shortage, Valuation & Financial, Production & BOM, Delay & Pending, Specialized Reports. Included report type breakdown (38 Script, 6 Query, 3 Report Builder). Best response in the entire test.

#### Query 17: "Search link for Item"
- **Tools Called:** `analyze_data` (failed), `list_documents` (failed multiple times)
- **Result:** ❌ FAIL
- **Response Quality:** Bad
- **Notes:** The query was misinterpreted. Instead of using the `search_link` tool, it tried `analyze_data` and `list_documents` for unrelated data. The response talked about loans (cross-contamination from shared sessions). The `search_link` tool was never called.

#### Query 18: "What is the structure of the Item DocType?"
- **Tools Called:** `get_doctype_info` (failed)
- **Result:** ⚠️ PARTIAL
- **Response Quality:** Good (knowledge-based)
- **Notes:** `get_doctype_info` errored with name_case bug. AI provided a knowledge-based response about Item DocType structure including fields, autoname, item groups, etc.

### Category 3: Reports & Analytics (4 queries tested)

#### Query 19: "Show me a summary of Sales Orders this month"
- **Tools Called:** `analyze_data` (failed)
- **Result:** ⚠️ PARTIAL
- **Response Quality:** Partial
- **Notes:** `analyze_data` failed with module error. AI provided a generic response. The tool error prevented actual data retrieval.

#### Query 20: "What is the total revenue from all Sales Invoices?"
- **Tools Called:** `run_database_query` or `list_documents`
- **Result:** ✅ SUCCESS (on retry in new chat)
- **Response Quality:** Good
- **Notes:** First attempt failed with 400 error due to long context. In a new chat, successfully retrieved revenue data mentioning ₹316,000 outstanding amount. Provided breakdown suggestions.

#### Query 21: "Generate a report of top 10 Items by quantity sold"
- **Result:** ❌ FAIL
- **Notes:** 400 error - "Assistant message must have either content or tool_call". Context overflow issue.

#### Query 22: "How many open Purchase Orders are there?"
- **Tools Called:** `list_documents`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Found 4 open Purchase Orders. Mentioned specific totals (₹104,600) and provided follow-up about delivery dates and outstanding amounts per supplier.

### Category 4: Database Queries (1 query tested)

#### Query 27: "Run SQL: SELECT count(*) FROM tabItem"
- **Tools Called:** `run_database_query`
- **Result:** ✅ SUCCESS
- **Response Quality:** Good
- **Notes:** Successfully ran SQL query and returned item count. Suggested checking stock quantities, items below reorder level, filtering by stock value.

### Category 5: System & User Info (1 query tested)

#### Query 33: "What version of ERPNext is installed?"
- **Result:** ❌ FAIL (page redirected before response)
- **Notes:** Browser tab redirected to mdfc-test.growthsystem.in before response could be captured. This was the final straw for testing.

### Queries Not Tested (28 remaining)
Queries 21, 23-26, 28-32, 34-50 were not tested due to the persistent browser redirect bug that made sustained testing impossible.

---

## Tool Usage Summary

| Tool | Called | Success | Failed | Notes |
|------|--------|---------|--------|-------|
| `list_documents` | 12 | 10 | 2 | Most reliable tool |
| `create_document` | 1 | 1 | 0 | Works perfectly |
| `update_document` | 1 | 1 | 0 | Works perfectly |
| `delete_document` | 1 | 1 | 0 | Works perfectly |
| `search` (MCP) | 2 | 2 | 0 | Works well for discovery |
| `search_doctype` (MCP) | 1 | 1 | 0 | Works well |
| `report_list` (MCP) | 1 | 1 | 0 | Excellent results |
| `get_doctype_info` | 3 | 0 | 3 | **BROKEN** - 'Meta' name_case error |
| `analyze_data` | 4 | 0 | 4 | **BROKEN** - module attribute error |
| `run_python_code` | 3 | 1 | 2 | Mixed results |
| `run_database_query` | 1 | 1 | 0 | Works for SQL |
| `get_document` | 3 | 3 | 0 | Works well |
| `search_link` | 0 | - | - | Never called (should have been for Q17) |

## Tool Categories Not Tested
- `submit_document` - Not tested
- `global_search` - Not tested
- `search_documents` - Not tested
- `generate_report` - Not tested
- `list_reports` - Not tested
- `get_workflow_state` / `run_workflow_action` - Not tested
- `search_emails` / `get_recent_emails` / `draft_email` / `send_email` - Not tested
- `describe_image` / `generate_image` - Not tested
- `get_system_info` / `get_user_info` - Not tested
- `create_number_card` / `create_dashboard` - Not tested
- `extract_file_content` / `fetch_url` - Not tested

---

## Key Issues Found

### P0 - Critical
1. **Browser Redirect Bug**: The Niv AI chat page redirects from `localhost:8081` to `mdfc-test.growthsystem.in` after several interactions. This may be a JavaScript redirect in the frontend code or a shared session state issue. **This makes the app unusable for extended sessions on localhost.**

### P1 - High
2. **`analyze_data` tool is broken**: Every call fails with `"module 'niv_ai.niv_tools.tools.report_tools' has no attribute 'analyze_data'"`. The function needs to be implemented or the tool registration removed.
3. **`get_doctype_info` tool is broken**: Every call fails with `"'Meta' object has no attribute 'name_case'"`. The Meta object API has changed and the tool code needs updating.
4. **400 Error on long conversations**: After ~5-6 messages in a single chat, the AI backend starts returning `"Assistant message must have either content or tool_call"`. This is likely a context window management issue.

### P2 - Medium
5. **Tool selection sometimes wrong**: For "Search link for Item" (Q17), the AI didn't call `search_link` but instead tried unrelated tools. Tool routing needs improvement.
6. **Cross-session contamination**: New Chat sometimes loads content from unrelated conversations (loan applications from mdfc-test site).
7. **Error recovery wastes tokens**: When `analyze_data` fails, the AI retries it 2-3 times before falling back, consuming tokens unnecessarily.

### P3 - Low
8. **Raw JSON in tool error accordions**: Tool errors display raw JSON which isn't user-friendly.
9. **Date context confusion**: Query 1 interpreted "last month" as June 2024 (the date was Feb 2026), suggesting date resolution logic may be off.

---

## Positive Highlights

1. **Document CRUD is excellent**: Create, Read, Update, Delete all work flawlessly.
2. **Response quality is high**: Well-formatted markdown with tables, bold, links, code blocks.
3. **Suggested follow-ups are smart**: 3 contextual follow-up buttons after each response.
4. **MCP tools work well**: `search`, `search_doctype`, `report_list` all produce great results.
5. **Error recovery**: When one tool fails, the AI attempts alternatives (though sometimes wastefully).
6. **Token transparency**: Token count shown per response helps monitor usage.
7. **Stock module report listing (Q16)**: Finding and categorizing 46 reports was outstanding.
8. **Link integration**: Document names are clickable links to their forms.

---

## Recommendations

1. **Fix the redirect bug** — check frontend JS for any URL rewriting logic
2. **Fix `analyze_data`** — implement the function or remove the tool
3. **Fix `get_doctype_info`** — update Meta object attribute access (name_case → ?)
4. **Add context window management** — truncate old messages before hitting the limit
5. **Improve tool selection** — ensure `search_link` is called for link search queries
6. **Add retry limits** — don't retry the same failed tool more than once
7. **Format tool errors** — show user-friendly error messages instead of raw JSON
8. **Fix New Chat** — ensure it truly creates a blank conversation
