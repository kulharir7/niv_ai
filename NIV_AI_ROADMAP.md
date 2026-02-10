# Niv AI — Product Roadmap

## ✅ Done
- [x] Core AI chat with tool calling (23 native + FAC adapter)
- [x] SSE streaming responses
- [x] Admin-controlled token billing
- [x] Full chat page (`/app/niv-chat`) — LibreChat-style UI
- [x] 17 UX features (copy, edit, regen, reactions, search, export, shortcuts etc.)
- [x] Voice mode (ChatGPT-style orb, browser + OpenAI TTS/STT)
- [x] Model selector with provider-colored badge
- [x] Dark sidebar + modern typography
- [x] File upload + voice input

## 🔨 Phase 1: Floating Widget (In Progress)
- [ ] Floating icon on ERPNext sidebar (left, purple gradient)
- [ ] Mini chat popup (380×520px) with streaming
- [ ] Expand to fullscreen (`/app/niv-chat`)
- [ ] Conversation continuity between widget and full page
- [ ] Don't show on `/app/niv-chat` (avoid duplicate)

## 📐 Phase 2: UI Polish
- [ ] Smooth message slide-in animations
- [ ] Image/file thumbnails in chat
- [ ] Drag & drop file upload
- [ ] Emoji picker in input
- [ ] Dark/Light mode toggle in sidebar
- [ ] Message formatting toolbar (bold, italic, code)
- [ ] Conversation last message preview in sidebar
- [ ] Better mobile experience

## 🧠 Phase 3: Smart Features
- [ ] AI-generated follow-up suggestions after each response
- [ ] Pinned/starred conversations
- [ ] Chat folders/tags
- [ ] Quick actions ("/create invoice", "/list customers")
- [ ] Context awareness (detect current ERPNext page → include in AI context)
- [ ] Multi-language support (Hindi/English toggle)
- [ ] Slash commands system

## 📊 Phase 4: Admin Dashboard
- [ ] Usage analytics (tokens/user/day, charts)
- [ ] Cost tracking dashboard
- [ ] User token management UI
- [ ] Tool usage statistics
- [ ] System prompt A/B testing
- [ ] Rate limiting controls
- [ ] Audit logs

## 🚀 Phase 5: Advanced Features
- [ ] Image generation (DALL-E/Stable Diffusion)
- [ ] PDF/Excel export from AI responses
- [ ] Scheduled AI tasks ("Every Monday send sales summary")
- [ ] Plugin system (custom tools installable via UI)
- [ ] Webhook triggers (AI on ERPNext events)
- [ ] Multi-model per conversation (done ✅)
- [ ] RAG — upload company docs, AI searches them
- [ ] MCP protocol support
- [ ] WhatsApp/Telegram integration
- [ ] Team shared conversations

## 🏗️ Technical Debt
- [ ] Proper test suite
- [ ] GitHub CI/CD
- [ ] Documentation site
- [ ] PyPI/npm packaging
- [ ] Docker container restart persistence (pip install in Dockerfile)
