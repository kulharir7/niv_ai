# 🐛 Niv AI — Known Issues & Workarounds

> Last updated: 2026-02-10

---

## Critical

### [BUG-001] ~~`db_set_single_value` import error in billing~~ ✅ FIXED
- **Status**: Fixed in v0.1.1
- **Severity**: Critical
- **Description**: `billing.py` and `payment.py` imported `db_set_single_value` but `compat.py` only exported `set_single_value`. Caused ImportError on any billing operation.
- **Fix**: Added `db_set_single_value` as alias in `compat.py`, plus dict-syntax support.

### [BUG-002] ~~`@handle_errors` breaks Frappe whitelist~~ ✅ FIXED
- **Status**: Fixed in v0.1.1
- **Severity**: Critical
- **Description**: Stacking `@handle_errors` on `@frappe.whitelist()` caused Frappe to not recognize the function as whitelisted. All API calls returned 404 "not whitelisted".
- **Fix**: Removed `@handle_errors` from all `@frappe.whitelist()` functions.

---

## Medium

### [BUG-003] Piper TTS lost on Docker container restart
- **Status**: Workaround available
- **Severity**: Medium
- **Description**: `pip install piper-tts` is not persisted across Docker container restarts. TTS falls back to browser speechSynthesis.
- **Workaround**: Use `docker/startup.sh` via compose override to auto-install on start. See `docker/README.md`.
- **Fix ETA**: v0.2.0 (add to requirements.txt when cross-platform compatibility confirmed)

### [BUG-004] SSE nginx config lost on frontend container restart
- **Status**: Workaround available
- **Severity**: Medium
- **Description**: The custom nginx location block for SSE streaming is injected at runtime. Container restart regenerates nginx config from template, losing the block.
- **Workaround**: Run `docker/nginx-patch.sh` after frontend restart, or use compose override.
- **Non-Docker**: Not affected — standard Frappe nginx config works.

### [BUG-005] `analyze_business_data` tool not found warning
- **Status**: Cosmetic / Non-blocking
- **Severity**: Low
- **Description**: AI sometimes calls `analyze_business_data` which is a FAC MCP tool. If no MCP server is configured, it shows a brief error dialog but the AI usually falls back to `run_database_query` and returns correct data.
- **Workaround**: Configure FAC as an MCP server in Niv Settings to enable all 23 FAC tools.

### [BUG-006] `pytesseract` requires system binary
- **Status**: Documentation needed
- **Severity**: Low
- **Description**: `pytesseract` is in `requirements.txt` and pip-installs fine, but OCR fails at runtime without the `tesseract-ocr` system package.
- **Workaround**: Install system package: `apt install tesseract-ocr` (Debian/Ubuntu) or `brew install tesseract` (macOS).

---

## Low / Cosmetic

### [BUG-007] Empty "New Chat" entries in sidebar
- **Status**: Open
- **Severity**: Low
- **Description**: Creating a new conversation but not sending a message leaves "New Chat" entries in the sidebar. Multiple empty entries accumulate over time.
- **Workaround**: Delete unused conversations via the delete button.

### [BUG-008] Free plan recharge has no rate limit
- **Status**: Open
- **Severity**: Low
- **Description**: Users can claim free plans (₹0) unlimited times. No cooldown or limit per user.
- **Fix ETA**: v0.2.0

---

## Reporting New Issues

Please include:
1. **Frappe/ERPNext version** (`bench version`)
2. **Niv AI version** (check `hooks.py` → `app_version`)
3. **Browser** and OS
4. **Steps to reproduce**
5. **Error message** (browser console + Frappe error log)
6. **Docker or bare metal** setup

File issues at: [GitHub Issues](https://github.com/kulharir7/niv_ai/issues)
