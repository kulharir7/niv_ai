# 🐛 Niv AI — Known Issues & Workarounds

> Last updated: 2026-02-11

---

## ✅ Fixed (v0.3.0)

| Bug | Description | Fix |
|-----|-------------|-----|
| BUG-001 | `db_set_single_value` import error in billing | Added alias in `compat.py` |
| BUG-002 | `@handle_errors` breaks Frappe whitelist | Removed decorator from all APIs |
| BUG-005 | `analyze_business_data` tool not found | MCP-only architecture — all tools via MCP |
| BUG-009 | `ToolMessage object is not subscriptable` callback crash | Fixed `on_tool_end` to handle ToolMessage objects |
| BUG-010 | `INVALID_CHAT_HISTORY` LangGraph crash | Added `handle_tool_error=True` on all tools |
| BUG-011 | SSE streaming returns 500 (`KeyError: 'generator'`) | Switched to `werkzeug.wrappers.Response` |
| BUG-012 | Widget white line artifact | Dark `#212121` background on panel + iframe |
| BUG-013 | Navbar disappears after leaving niv-chat | Added `on_page_hide`/`on_page_show` handlers |
| BUG-014 | Billing not deducting tokens | Token estimation fallback + correct param names |

---

## Open

### [BUG-003] Piper TTS lost on Docker container restart
- **Severity**: Medium
- **Description**: `pip install piper-tts` not persisted across restarts. Falls back to browser TTS.
- **Workaround**: Use `docker/startup.sh` via compose override.

### [BUG-004] SSE nginx config lost on frontend container restart
- **Severity**: Medium
- **Description**: Custom nginx SSE location block lost on restart.
- **Workaround**: Run `docker/nginx-patch.sh` after frontend restart.
- **Non-Docker**: Not affected.

### [BUG-006] `pytesseract` requires system binary
- **Severity**: Low
- **Description**: OCR fails without `tesseract-ocr` system package.
- **Workaround**: `apt install tesseract-ocr`

### [BUG-007] Empty "New Chat" entries in sidebar
- **Severity**: Low
- **Description**: Creating a conversation without sending a message leaves empty entries.
- **Workaround**: Delete unused conversations.

### [BUG-008] Free plan recharge has no rate limit
- **Severity**: Low
- **Description**: Users can claim ₹0 plans unlimited times.

---

## Reporting Issues

Include:
1. Frappe/ERPNext version (`bench version`)
2. Niv AI version (`hooks.py` → `app_version`)
3. Browser + OS
4. Steps to reproduce
5. Error message (console + Frappe error log)
6. Docker or bare metal setup

File issues at: [GitHub Issues](https://github.com/kulharir7/niv_ai/issues)
