# Changelog

## v0.1.1 (2026-02-10)
### Fixed
- `@handle_errors` decorator removed from all whitelisted APIs (was breaking Frappe route resolution)
- `db_set_single_value` import error in billing/payment modules (added alias in compat.py)
- Piper TTS `synthesize()` → `synthesize_wav()` (wave params not set by old method)
- TTS file folder changed from "Home/Niv AI" to "Home" (folder didn't exist)
- Tool calls now render ABOVE response text in chat history (was reversed)
- Fresh welcome screen on page load instead of auto-opening last conversation
- `niv-dashboard` page added to hooks.py `page_modules`
- Stale `niv-recharge` route fixed to `niv-credits` in hooks.py
- Voice mode interrupt: tapping orb during speech now immediately starts listening
- Browser `speechSynthesis.cancel()` added to stop voice playback properly

### Improved
- Table CSS: rounded corners, uppercase headers, hover effects, dark mode
- Markdown: blockquote styling, HR lines, link colors, heading borders, better spacing
- Output formatting: improved line-height, nested list support

## v0.1.0 (2026-02-09)
### Initial Release
- Complete AI chat assistant for ERPNext
- 26 built-in tools (documents, search, reports, workflows, database, email, utilities)
- SSE streaming responses
- Voice mode (Piper TTS + browser STT)
- Dual billing modes (Shared Pool / Per-User Wallets)
- Razorpay integration with demo mode
- MCP protocol support (stdio, SSE, HTTP streamable)
- FAC adapter for Frappe Assistant Core
- Embedded widget + full-page chat
- 6 color themes + dark mode
- Admin analytics dashboard
- Knowledge base (RAG)
- Auto-actions, scheduled reports, custom instructions
- Mobile responsive with touch gestures
