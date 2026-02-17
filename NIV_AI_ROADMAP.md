# 🗺️ Niv AI — Roadmap to v1.0.0

> The journey from AI chat assistant to enterprise-grade AI platform for ERPNext.
> 
> **Current Version**: v0.3.1 | **Target**: v1.0.0 | **Total Features**: 160+

---

## ✅ Released

### v0.1.0 — "First Light" (2026-02-09)
The beginning. Pure Frappe app with AI chat, MCP tool calling, and billing.

- [x] Pure Frappe app — no LibreChat, no MongoDB, no Docker dependency
- [x] 12 DocTypes (Settings, Conversations, Messages, Billing, Tools)
- [x] OpenAI-compatible API (works with Mistral, GPT, Claude, Ollama)
- [x] MCP protocol for tool discovery & execution
- [x] FAC integration — 23 ERPNext tools via MCP
- [x] SSE streaming chat
- [x] Dual billing (Shared Pool + Per User)
- [x] Razorpay payments (demo mode when keys empty)
- [x] Embedded widget + fullscreen page
- [x] Voice mode (TTS/STT with browser fallback)
- [x] Piper TTS (fast, CPU-friendly)
- [x] Dark mode UI
- [x] 17 UX features (copy, regenerate, edit, search, shortcuts)
- [x] Mobile responsive CSS
- [x] GitHub repo: `https://github.com/kulharir7/niv_ai`

### v0.2.0 — "MCP Only" (2026-02-10)
Architecture pivot — removed all native tools, MCP-only.

- [x] Deleted 29 native Python tool implementations
- [x] MCP-only architecture (all tools from MCP servers)
- [x] Conversational voice mode with auto-interrupt
- [x] Frappe v14 compatibility
- [x] Duplicate message prevention
- [x] Premium UI redesign (~2800 lines CSS)

### v0.3.0 — "LangChain Engine" (2026-02-11)
Complete engine rewrite — LangChain/LangGraph powers everything.

- [x] LangGraph ReAct agent (auto tool calling, max 12 iterations)
- [x] Multi-provider auto-detection (OpenAI/Mistral/Claude/Gemini/Ollama)
- [x] MCP session caching (10 min TTL)
- [x] Token-aware memory truncation
- [x] RAG knowledge base (FAISS + HuggingFace)
- [x] Configurable rate limiting (per-hour, per-day)
- [x] `handle_tool_error=True` — agent never crashes on bad tool args
- [x] SSE via `werkzeug.wrappers.Response` (Frappe v15 compatible)
- [x] ToolMessage callback crash fix
- [x] Widget white line fix, navbar fix
- [x] 20 DocTypes total

### v0.3.1 — "Permission Isolation" (2026-02-11)
Per-user tool permissions — AI respects ERPNext roles.

- [x] Auto-generate API keys on first chat (zero manual setup)
- [x] MCP tool calls use user's own ERPNext credentials
- [x] Tool results respect user's role permissions
- [x] Thread-safe via `threading.local()`
- [x] Toggle in Niv Settings (default OFF, backward compatible)
- [x] Graceful fallback to admin key

---

## 🚧 Upcoming

---

### v0.4.0 — "Rock Solid" 🪨
*Fix everything. Stabilize. Role-based access. Organize.*

> **Focus**: No new user sees a bug. Every role gets the right experience.

| # | Feature | Status |
|---|---------|--------|
| 1 | User message bubble visibility fix | 🔴 |
| 2 | Empty/duplicate chat cleanup + prevention | 🔴 |
| 3 | Streaming reconnect on network drop | 🔴 |
| 4 | Auto-save draft messages (unsent text preserved on reload) | 🔴 |
| 5 | Better error messages (Hindi + English, user-friendly) | 🔴 |
| 6 | Chat scroll position memory (reload → same position) | 🔴 |
| 7 | Message retry with different model | 🔴 |
| 8 | Conversation auto-archive (30+ days old → archived section) | 🔴 |
| 9 | Message edit history (show previous versions) | 🔴 |
| 10 | Bulk delete conversations | 🔴 |
| 11 | **Role-based system prompts** (HR→HR prompt, Sales→Sales prompt, auto) | 🔴 |
| 12 | Department-based tool access restrictions | 🔴 |
| 13 | Per-user model assignment (CEO gets GPT-4, intern gets Mistral) | 🔴 |
| 14 | Per-role rate limits | 🔴 |
| 15 | User onboarding wizard (first chat welcome + setup) | 🔴 |
| 16 | User-level custom instructions ("always reply in Hindi") | 🔴 |
| 17 | Admin impersonation mode (test as another user) | 🔴 |
| 18 | Manager approval for sensitive queries (optional) | 🔴 |
| 19 | **Conversation folders & tags** | 🔴 |
| 20 | Pin conversations to top | 🔴 |
| 21 | Star/favorite messages | 🔴 |
| 22 | Sidebar search with filters (date, tool used, starred) | 🔴 |
| 23 | Conversation sort (recent, alphabetical, starred) | 🔴 |
| 24 | AI-generated smart titles (better than first message truncation) | 🔴 |
| 25 | Sidebar conversation count badge | 🔴 |

---

### v0.5.0 — "See & Read" 👁️📄
*Upload anything. AI understands images, PDFs, Excel, docs.*

> **Focus**: Drag a file → AI reads it. Paste an image → AI sees it.

| # | Feature | Status |
|---|---------|--------|
| 26 | **Image upload + Vision AI** (GPT-4V, Claude Vision compatible) | 🔴 |
| 27 | Multi-image upload in single message | 🔴 |
| 28 | Clipboard paste image (Ctrl+V → auto upload) | 🔴 |
| 29 | **PDF upload → AI reads & answers questions** | 🔴 |
| 30 | **Excel/CSV upload → AI analyzes data, finds patterns** | 🔴 |
| 31 | Word/DOCX upload → AI summarizes | 🔴 |
| 32 | Drag & drop file upload (anywhere in chat area) | 🔴 |
| 33 | File preview in chat (PDF viewer, image lightbox, data table) | 🔴 |
| 34 | OCR on uploaded images (Tesseract integration) | 🔴 |
| 35 | **Image generation** (DALL-E / Stable Diffusion) | 🔴 |
| 36 | Chart/graph generation from data (bar, line, pie auto-pick) | 🔴 |
| 37 | QR code generation | 🔴 |
| 38 | Export chat as PDF (with formatting, tables, images) | 🔴 |
| 39 | Export chat as Markdown | 🔴 |
| 40 | Export chat as shareable HTML | 🔴 |
| 41 | Configurable file size limits (per role) | 🔴 |
| 42 | Supported file types whitelist (admin configurable) | 🔴 |
| 43 | File virus scan hook (extensible for enterprise) | 🔴 |
| 44 | Uploaded file auto-cleanup (delete after X days) | 🔴 |
| 45 | Image compression before upload (save bandwidth) | 🔴 |

---

### v0.6.0 — "Big Brain" 🧠
*AI that remembers, learns, searches the web, and thinks deeply.*

> **Focus**: Not just Q&A — actual intelligence. Memory + knowledge + reasoning.

| # | Feature | Status |
|---|---------|--------|
| 46 | **Cross-conversation memory** (AI remembers past interactions) | 🔴 |
| 47 | User preference auto-learning (language, format, topics) | 🔴 |
| 48 | Conversation summarization (long chat → 1 paragraph on demand) | 🔴 |
| 49 | Smart context window (auto-include relevant old messages) | 🔴 |
| 50 | **Knowledge base RAG with file upload** (upload company docs → AI knows them) | 🔴 |
| 51 | Knowledge base auto-indexing (new Frappe docs → auto-added) | 🔴 |
| 52 | **Web search tool** (AI searches the internet when needed) | 🔴 |
| 53 | URL fetch & summarize ("summarize this article") | 🔴 |
| 54 | Wikipedia integration (quick facts) | 🔴 |
| 55 | Calculator / math solver (complex formulas) | 🔴 |
| 56 | Date/time/calendar awareness ("kal ka meeting kab hai") | 🔴 |
| 57 | ERPNext context awareness (knows user's role, department, recent activity) | 🔴 |
| 58 | Smart suggestions based on user's work pattern | 🔴 |
| 59 | Auto-detect intent (question vs command vs casual chat) | 🔴 |
| 60 | Conversation branching (fork chat from any message) | 🔴 |
| 61 | Related conversations suggestion ("you asked about this before") | 🔴 |
| 62 | Typo correction ("did you mean Sales Order?") | 🔴 |
| 63 | Fact-checking against ERPNext data (verify AI claims) | 🔴 |
| 64 | Multi-turn reasoning chains (show AI thinking process) | 🔴 |
| 65 | Confidence score on answers (low confidence → suggests verification) | 🔴 |

---

### v0.7.0 — "Power Tools" ⚡
*Templates, slash commands, automation, scheduled tasks, no-code tool builder.*

> **Focus**: Supercharge productivity. Automate repetitive work. Build custom tools without code.

| # | Feature | Status |
|---|---------|--------|
| 66 | **Prompt template library** (admin creates, users select) | 🔴 |
| 67 | **Slash commands** (`/sales` → sales report, `/hr` → leave balance) | 🔴 |
| 68 | Quick actions bar (one-click common tasks above input) | 🔴 |
| 69 | Prompt variables (`{{user_name}}`, `{{department}}`, `{{today}}`, `{{company}}`) | 🔴 |
| 70 | Prompt chaining (output of one prompt → auto-feeds next) | 🔴 |
| 71 | Prompt versioning & A/B testing | 🔴 |
| 72 | Saved responses / bookmarks (save useful AI answers for reuse) | 🔴 |
| 73 | Response templates (AI uses predefined output formats) | 🔴 |
| 74 | Custom persona creation ("be a strict chartered accountant") | 🔴 |
| 75 | **Scheduled reports** ("har Monday subah sales summary bhejo") | 🔴 |
| 76 | **Email integration** (AI reads inbox, drafts replies) | 🔴 |
| 77 | Webhook triggers (AI response → trigger external action) | 🔴 |
| 78 | ERPNext workflow triggers (AI starts approval workflows) | 🔴 |
| 79 | **Custom MCP Tool Builder** (no-code: name + API endpoint + params → tool ready) | 🔴 |
| 80 | MCP server health monitoring (status page, auto-reconnect) | 🔴 |
| 81 | Auto-retry failed tool calls (configurable retries) | 🔴 |
| 82 | Tool result caching (same query within 5 min → cached response) | 🔴 |
| 83 | Batch operations ("update all 50 draft Sales Orders to Submitted") | 🔴 |
| 84 | REST API endpoint for external apps (headless Niv AI) | 🔴 |
| 85 | Cron job support (scheduled AI tasks, recurring reports) | 🔴 |

---

### v0.8.0 — "Beautiful" 🎨
*Premium UI, themes, artifacts panel, mobile PWA, keyboard power.*

> **Focus**: Look and feel that rivals ChatGPT/Claude. Works beautifully on phone.

| # | Feature | Status |
|---|---------|--------|
| 86 | **6 chat themes** (Dark, Light, Midnight Blue, Ocean, Forest, Custom) | 🔴 |
| 87 | Custom accent color picker | 🔴 |
| 88 | Chat font size adjustment (small/medium/large) | 🔴 |
| 89 | Display density modes (compact/comfortable/cozy) | 🔴 |
| 90 | Code syntax highlighting (20+ languages, line numbers) | 🔴 |
| 91 | Code "Copy" + "Run" buttons (Python/JS execution) | 🔴 |
| 92 | **Artifacts/Canvas panel** (long outputs open in side panel — Claude-style) | 🔴 |
| 93 | Table sorting & filtering in chat (click column to sort) | 🔴 |
| 94 | **Clickable links in tables** (Sales Order name → opens in ERPNext) | 🔴 |
| 95 | Mermaid diagram rendering (flowcharts, sequence diagrams) | 🔴 |
| 96 | LaTeX/math formula rendering | 🔴 |
| 97 | **Keyboard shortcuts** (Ctrl+K palette, Ctrl+N new chat, Ctrl+/ help) | 🔴 |
| 98 | Command palette (search conversations, tools, settings — everything) | 🔴 |
| 99 | Split view (2 chats side by side for comparison) | 🔴 |
| 100 | Focus mode (hide everything except chat — zero distraction) | 🔴 |
| 101 | Smooth character-by-character streaming animation | 🔴 |
| 102 | Message timestamps toggle (hover to see, click to pin) | 🔴 |
| 103 | **Progressive Web App** (install Niv AI on phone home screen) | 🔴 |
| 104 | Push notifications (new responses, mentions, scheduled reports) | 🔴 |
| 105 | Offline chat history (read old chats without internet) | 🔴 |
| 106 | Mobile-optimized voice mode (full screen, large buttons) | 🔴 |
| 107 | Swipe gestures (left → delete, right → pin, down → refresh) | 🔴 |
| 108 | Camera → analyze (mobile: snap photo → AI analyzes) | 🔴 |
| 109 | Share from other apps → Niv AI (Android share intent) | 🔴 |
| 110 | Mobile dark/light auto-switch (follows system theme) | 🔴 |

---

### v0.9.0 — "Dashboard & Channels" 📊
*Admin analytics, billing v2, WhatsApp/Slack/Telegram bots.*

> **Focus**: Admin sees everything. AI reaches users where they already are.

| # | Feature | Status |
|---|---------|--------|
| 111 | **Real-time usage dashboard** (live counters, active users) | 🔴 |
| 112 | **Per-user cost tracking** (who spent how many tokens) | 🔴 |
| 113 | Per-model cost comparison (which model costs more) | 🔴 |
| 114 | Top queries report (most asked questions) | 🔴 |
| 115 | Tool usage analytics (which MCP tools used most) | 🔴 |
| 116 | Response time tracking (avg time per query) | 🔴 |
| 117 | User satisfaction analytics (thumbs up/down breakdown) | 🔴 |
| 118 | Auto-generated daily/weekly/monthly usage reports | 🔴 |
| 119 | Export analytics as CSV/PDF | 🔴 |
| 120 | Cost forecast (projected monthly spending) | 🔴 |
| 121 | Budget threshold alerts (email when 80% budget used) | 🔴 |
| 122 | Slow query detection & alerting | 🔴 |
| 123 | Error rate monitoring dashboard | 🔴 |
| 124 | Active users chart (hourly/daily/weekly) | 🔴 |
| 125 | Token usage heatmap (find peak usage hours) | 🔴 |
| 126 | **Billing v2 — Stripe support** (international payments) | 🔴 |
| 127 | Billing v2 — auto-invoice generation | 🔴 |
| 128 | Billing v2 — usage-based plans (not just token packs) | 🔴 |
| 129 | **WhatsApp bot integration** (chat with Niv AI on WhatsApp) | 🔴 |
| 130 | **Slack integration** (use Niv AI in Slack channels) | 🔴 |
| 131 | **Telegram bot integration** | 🔴 |
| 132 | Microsoft Teams integration | 🔴 |
| 133 | Calendar integration (meeting summaries, schedule queries) | 🔴 |
| 134 | MCP Marketplace (browse & install MCP servers from catalog) | 🔴 |
| 135 | Zapier/Make integration (connect to 5000+ apps) | 🔴 |

---

### v1.0.0 — "Enterprise Ready" 🏢
*Security hardened. Compliance ready. Performance tested. Production grade.*

> **Focus**: Ready for 1000+ users. Passes security audits. Ships with CI/CD.

| # | Feature | Status |
|---|---------|--------|
| 136 | **Full audit log** (who asked what, when, which tools, what data accessed) | 🔴 |
| 137 | **Data retention policies** (auto-delete conversations after X days) | 🔴 |
| 138 | PII detection & masking (auto-detect Aadhaar, PAN, phone numbers) | 🔴 |
| 139 | Conversation encryption at rest (AES-256) | 🔴 |
| 140 | IP-based access control (whitelist/blacklist) | 🔴 |
| 141 | Session timeout configuration (idle → auto-logout) | 🔴 |
| 142 | Sensitive data redaction in logs (no tokens/keys in frappe.log) | 🔴 |
| 143 | **GDPR data export** (user downloads all their data) | 🔴 |
| 144 | SOC2 compliance checklist & documentation | 🔴 |
| 145 | **Hindi UI translation** (complete Frappe translation) | 🔴 |
| 146 | Multi-language AI responses (auto-detect user language preference) | 🔴 |
| 147 | RTL support (Arabic, Hebrew, Urdu) | 🔴 |
| 148 | Screen reader compatibility (ARIA labels, semantic HTML) | 🔴 |
| 149 | High contrast mode (accessibility) | 🔴 |
| 150 | Keyboard-only navigation (tab through everything) | 🔴 |
| 151 | Regional date/number/currency formatting | 🔴 |
| 152 | Frappe translation system integration | 🔴 |
| 153 | **Load testing** (verified for 1000+ concurrent users) | 🔴 |
| 154 | Database query optimization (indexed, no N+1, explain analyzed) | 🔴 |
| 155 | Redis caching layer (conversation, tools, settings) | 🔴 |
| 156 | CDN for static assets (JS/CSS/fonts) | 🔴 |
| 157 | **Docker production compose** (one-command deploy) | 🔴 |
| 158 | Kubernetes Helm chart | 🔴 |
| 159 | **CI/CD pipeline** (GitHub Actions: lint, test, build, deploy) | 🔴 |
| 160 | **Automated test suite** (unit + integration + E2E, 80%+ coverage) | 🔴 |

---

## 📊 Version Summary

| Version | Codename | Features | Focus Area |
|---------|----------|----------|------------|
| ~~v0.1.0~~ ✅ | First Light | 15+ | Core app, chat, billing, MCP |
| ~~v0.2.0~~ ✅ | MCP Only | 6 | Architecture pivot |
| ~~v0.3.0~~ ✅ | LangChain Engine | 20+ | Engine rewrite, premium UI |
| ~~v0.3.1~~ ✅ | Permission Isolation | 7 | Per-user tool permissions |
| **v0.4.0** | Rock Solid 🪨 | 25 | Bugs + Roles + Organization |
| **v0.5.0** | See & Read 👁️📄 | 20 | Files + Images + Vision |
| **v0.6.0** | Big Brain 🧠 | 20 | Memory + Intelligence + Search |
| **v0.7.0** | Power Tools ⚡ | 20 | Templates + Automation + Builder |
| **v0.8.0** | Beautiful 🎨 | 25 | UI/UX + Mobile PWA |
| **v0.9.0** | Dashboard 📊 | 25 | Analytics + Billing v2 + Channels |
| **v1.0.0** | Enterprise 🏢 | 25 | Security + Performance + CI/CD |

**Total: 160+ features across 7 upcoming versions**

---

## 🎯 Timeline (Estimated)

```
v0.4.0  ████████░░░░░░░░░░░░  Week 1-2
v0.5.0  ░░░░░░░░████████░░░░  Week 2-3
v0.6.0  ░░░░░░░░░░░░████████  Week 3-4
v0.7.0  ░░░░░░░░░░░░░░░░████  Week 4-5
v0.8.0  ░░░░░░░░░░░░░░░░░░██  Week 5-6
v0.9.0  ░░░░░░░░░░░░░░░░░░░█  Week 6-7
v1.0.0  ░░░░░░░░░░░░░░░░░░░░  Week 7-8
```

> Timelines are estimates. Quality > speed. Each version is tagged, released, and deployed independently.

---

## 🤝 Contributing

Want to contribute? Pick any 🔴 feature and submit a PR.

- **GitHub**: https://github.com/kulharir7/niv_ai
- **Issues**: https://github.com/kulharir7/niv_ai/issues

---

*Last updated: 2026-02-11 | Maintained by the Niv AI team*
