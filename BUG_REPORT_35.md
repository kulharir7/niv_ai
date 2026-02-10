# Niv AI — 35 Bug Report (Feb 10, 2026)

Source: External audit by Chetan (MDFC Financiers)

## Summary: 35 bugs total
- Critical Security: 5
- Critical Logic: 5  
- High: 10
- Medium: 9
- Low: 6

## Fix Status Tracking

### 🔴 Critical Security (Fix ASAP)
| # | Bug | File | Status |
|---|-----|------|--------|
| 1 | SQL Injection in knowledge base search | knowledge.py | ❌ TODO |
| 2 | Arbitrary code exec via automation conditions | automation.py | ❌ TODO |
| 3 | Path traversal in voice file handling | voice.py | ❌ TODO |
| 4 | Unvalidated file upload content | chat.py | ❌ TODO |
| 5 | Demo mode payment bypass (unlimited free tokens) | payment.py | ❌ TODO |

### 🔴 Critical Logic
| # | Bug | File | Status |
|---|-----|------|--------|
| 6 | Race condition in billing token deduction | billing.py | ❌ TODO |
| 7 | Infinite tool calling loop (10 iterations) | chat.py | ❌ TODO |
| 8 | Inaccurate token estimation fallback | stream.py | ❌ TODO |
| 9 | Dedup blocks legitimate repeat messages | chat.py | ❌ TODO |
| 10 | Conversation title race condition | chat.py | ❌ TODO |

### 🟠 High Priority
| # | Bug | File | Status |
|---|-----|------|--------|
| 11 | N+1 query in tool registry | tool_registry.py | ❌ TODO |
| 12 | Unbounded history fetch (oldest 50 not newest) | chat.py | ❌ TODO |
| 13 | MCP cache doesn't cache errors | mcp_client.py | ❌ TODO |
| 14 | Piper model download blocks HTTP request | voice.py | ❌ TODO |
| 15 | Missing transaction rollback on AI error | chat.py | ❌ TODO |
| 16 | Tool index rebuild on every cache miss | mcp_client.py | ❌ TODO |
| 17 | Shared pool daily limit not enforced during streaming | stream.py | ❌ TODO |
| 25 | Potential markdown XSS | niv_chat.js | ❌ TODO |

### 🟡 Medium Priority
| # | Bug | File | Status |
|---|-----|------|--------|
| 18 | Voice file cleanup never happens automatically | voice.py | ❌ TODO |
| 19 | HTTP session memory leak in MCP client | mcp_client.py | ❌ TODO |
| 20 | Stdio process zombie leak | mcp_client.py | ❌ TODO |
| 21 | Message count not atomically updated | niv_conversation.py | ❌ TODO |
| 24 | Widget double initialization | niv_widget.js | ❌ TODO |
| 26 | EventSource not closed on error | niv_chat.js | ❌ TODO |
| 28 | Missing database index on niv_message.conversation | niv_message.json | ❌ TODO |
| 29 | No rate limit on free plan claims | payment.py | ❌ TODO |
| 32 | Redis failure = fail-open (no rate limiting) | rate_limiter.py | ❌ TODO |

### 🟢 Low Priority
| # | Bug | File | Status |
|---|-----|------|--------|
| 22 | Tool execution log failures silently ignored | tool_executor.py | ❌ TODO |
| 23 | Recharge balance_after set before credit | payment.py | ❌ TODO |
| 27 | System prompt hardcoded in install.py | install.py | ❌ TODO |
| 30 | Piper voice download fails silently | install.py | ❌ TODO |
| 31 | Hardcoded retry backoff maximum | retry.py | ❌ TODO |
| 33 | Knowledge base chunk size not validated | knowledge.py | ❌ TODO |
| 34 | Voice API key fallback uses wrong provider | voice.py | ❌ TODO |
| 35 | Tool aliases hardcoded in executor | tool_executor.py | ❌ TODO |
