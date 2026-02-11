# Niv AI Bug Status Tracker
Updated: 2026-02-11

## Already Fixed ✅

| Bug | Severity | Description | Fixed In |
|-----|----------|-------------|----------|
| BUG-007 | HIGH | Circuit breaker per-worker only | `876dbf1` — already has circuit breaker (Redis upgrade needed) |
| BUG-006 | HIGH | Redis bytes vs str | Already handled in `_redis_get()` — checks isinstance |

## Partially Fixed ⚡

| Bug | Severity | Description | Status |
|-----|----------|-------------|--------|
| BUG-003 | CRITICAL | MCP Session ID not persisted | Init cache exists but no session ID capture |
| BUG-009 | HIGH | hash() cache keys | Uses `hash()` — needs sha256 |
| BUG-015 | MEDIUM | v14 cache TTL compat | Verified v14 supports `expires_in_sec` — may be OK |

## Needs Fix 🔴

### Phase 1: Core Tool Calling (CRITICAL — fixes 80% of failures)

| Bug | Severity | Description | Effort |
|-----|----------|-------------|--------|
| BUG-001 | CRITICAL | EventSource GET → URL truncation | 2-3 days |
| BUG-002 | CRITICAL | CSRF bypass on v14 / GET fails v15 | Paired with BUG-001 |
| BUG-004 | HIGH | Tool call chunks drop arguments | 0.5 day |
| BUG-005 | HIGH | niv_mcp_tool missing input_schema | 0.5 day |
| BUG-008 | HIGH | Messages exposed in server logs via URL | Fixed by BUG-001 |

### Phase 2: Reliability

| Bug | Severity | Description | Effort |
|-----|----------|-------------|--------|
| BUG-007 | HIGH | Circuit breaker → Redis shared | 1 day |
| BUG-009 | HIGH | hash() → sha256 cache keys | 0.5 day |
| BUG-013 | MEDIUM | Stdio new process per call | 1 day |
| BUG-014 | MEDIUM | HTTP sessions not properly closed | 0.5 day |

### Phase 3: Polish

| Bug | Severity | Description | Effort |
|-----|----------|-------------|--------|
| BUG-010 | MEDIUM | System prompt fragile logic | 0.5 day |
| BUG-011 | MEDIUM | Token counting approximate | 0.5 day |
| BUG-012 | MEDIUM | Description truncated to 200 chars | 0.5 day |
| BUG-015 | MEDIUM | v14 cache TTL compat | 0.5 day |
| BUG-016 | LOW | Billing empty string check | 0.5 day |
| BUG-017 | LOW | No audit trail for API key access | 0.5 day |
| BUG-018 | LOW | Race condition API key creation | 0.5 day |
