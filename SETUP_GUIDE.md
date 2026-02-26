# Chanakya Ai — Complete Setup Guide

> Step-by-step guide to install Chanakya Ai on a new ERPNext server

---

## Prerequisites

- ERPNext v15+ running on a server (bench setup)
- Python 3.10+
- SSH access to the server
- An AI provider API key (Mistral / OpenAI / Ollama Cloud)

---

## Step 1: Install the Apps

SSH into your server and switch to bench user:

```bash
ssh user@your-server-ip
sudo su frappe   # or your bench user
cd /path/to/frappe-bench
```

### 1.1 Install frappe_assistant_core (MCP Tools)
```bash
bench get-app https://github.com/AdarshPS1/frappe_assistant_core.git
bench --site your-site.local install-app frappe_assistant_core
```

### 1.2 Install Niv AI (Chanakya Ai)
```bash
bench get-app https://github.com/kulharir7/niv_ai.git
bench --site your-site.local install-app niv_ai
bench --site your-site.local migrate
```

### 1.3 Build Frontend Assets
```bash
bench build --app niv_ai
```

### 1.4 Restart Services
```bash
sudo supervisorctl restart all
# OR
bench restart
```

> **Note:** `install-app` automatically runs `install.py` which creates Niv Settings with default values (widget, billing, prompts, plans).

---

## Step 2: Configure AI Provider

### Option A: Quick Setup (Recommended)
```bash
# Mistral (recommended for production):
bash apps/niv_ai/setup.sh your-site.local https://api.mistral.ai/v1 YOUR_API_KEY

# Ollama Cloud:
bash apps/niv_ai/setup.sh your-site.local https://api.ollama.com/v1 YOUR_API_KEY mistral-large-3:675b mistral-small-3:24b

# OpenAI:
bash apps/niv_ai/setup.sh your-site.local https://api.openai.com/v1 YOUR_API_KEY gpt-4o gpt-4o-mini
```

### Option B: Manual Setup via UI
1. Go to **Niv AI Provider** → **+ New**
2. Fill in:
   - **Provider Name:** `ollama-cloud` (or any name)
   - **Base URL:** `https://api.ollama.com/v1`
   - **API Key:** Your key
   - **Default Model:** `mistral-large-3:675b`
3. Save
4. Go to **Niv Settings** → Set:
   - **Default Provider:** Select the provider you just created
   - **Default Model:** `mistral-large-3:675b`
   - **Fast Model:** `mistral-small-3:24b` (for two-model optimization)

---

## Step 3: Configure Niv Settings

Go to **Niv Settings** (`/app/niv-settings`) and configure these sections:

### 3.1 AI Configuration (Required)
| Setting | Value | Notes |
|---------|-------|-------|
| Default Provider | Your AI provider | Created in Step 2 |
| Default Model | `mistral-large-3:675b` | Main reasoning model |
| Fast Model | `mistral-small-3:24b` | Tool selection model (faster, cheaper) |
| Max Tokens per Message | `4096` | Max response length |
| Max Messages in Context | `50` | Chat history window |
| Enable Tools | ✅ | Must be ON for MCP tools |
| Tool Priority | `MCP First` | Use MCP tools from FAC |

### 3.2 Widget & Branding (Optional)
| Setting | Value | Notes |
|---------|-------|-------|
| Enable Floating Widget | ✅ | Shows chat button on all pages |
| Widget Title | `Chanakya Ai` | Name shown in header |
| Widget Logo | Upload image | Shows in chat header + FAB button |
| Widget Position | `bottom-right` | FAB button position |
| Widget Color | `#7C3AED` | Purple accent color |
| Auto-Open Artifacts | ✅ or ☐ | Auto-open code preview panel |

### 3.3 Billing (Required)
| Setting | Value | Notes |
|---------|-------|-------|
| Enable Billing | ✅ | Token tracking |
| Billing Mode | `Shared Pool` | All users share one pool |
| Shared Pool Balance | `10000000` | 1 Crore tokens (starting balance) |
| Per User Daily Limit | `0` | 0 = unlimited |
| Admin Allocation Only | ✅ | Only admin can add tokens |
| Cost per 1K Input Tokens | `1` | For billing calculation |
| Cost per 1K Output Tokens | `3` | For billing calculation |
| Payment Currency | `INR` | Your currency |

### 3.4 Rate Limits
| Setting | Value | Notes |
|---------|-------|-------|
| Messages per Hour | `500` | Per user limit |
| Messages per Day | `5000` | Per user limit |
| Rate Limit Message | Custom message | Shown when limit hit |

### 3.5 Voice (Optional)
| Setting | Value | Notes |
|---------|-------|-------|
| Enable Voice | ✅ | Voice input/output |
| STT Engine | `auto` | Auto-detect best |
| TTS Engine | `auto` | Auto-detect best |
| TTS Language | `auto` | Detects Hindi/English |
| Default TTS Voice | `auto` | |
| **ElevenLabs API Key** | Your key | Premium voice (optional) |
| ElevenLabs Voice ID (EN) | Voice ID | From ElevenLabs dashboard |
| ElevenLabs Voice ID (HI) | Voice ID | From ElevenLabs dashboard |

### 3.6 Vision/OCR (Optional)
| Setting | Value | Notes |
|---------|-------|-------|
| Enable Vision | ✅ | Image/document understanding |
| Vision Model | `gemma3:27b` | OCR model (must support vision) |
| Vision Max Tokens | `2048` | Max OCR response |

### 3.7 Telegram Bot (Optional)
| Setting | Value | Notes |
|---------|-------|-------|
| Bot Token | From @BotFather | Telegram bot token |
| Webhook URL | `https://your-domain.com/api/method/niv_ai.niv_core.api.telegram.webhook` | Auto-registered |
| Bot Username | `your_bot` | Without @ |
| Secret Token | Any random string | Webhook verification |
| Live Stream | ✅ | Stream responses to Telegram |

After setting token, register webhook:
```bash
bench --site your-site.local execute niv_ai.niv_core.api.telegram.register_webhook
```

### 3.8 Growth Billing Server (Optional)
Only needed if using centralized billing via `niv_billing_server` app.

| Setting | Value | Notes |
|---------|-------|-------|
| Vendor ERPNext URL | `https://billing.example.com` | Billing server URL |
| API Key | `nivsync_admin` | Billing server API key |
| API Secret | Secret | Billing server API secret |
| Customer Name | Your company name | Customer on billing server |
| Item Code | `NIV-AI-TOKEN` | Token item code |
| Webhook Secret | Shared secret | Must match billing server |

---

## Step 4: System Prompt

The default system prompt works well for NBFC/lending businesses. To customize:

1. Go to **Niv Settings** → **Default System Prompt**
2. Edit the prompt for your business domain
3. Key rules to keep:
   - Max 3 tool calls per response
   - Never fabricate data
   - Respond in user's language
   - Use tables for data

---

## Step 5: Allowed Roles

By default, all users can access Niv Chat. To restrict:

1. Go to **Niv Settings** → **Allowed Roles** table
2. Add roles (e.g., `System Manager`, `Niv AI User`)
3. Only users with these roles can access chat

---

## Step 6: Verify Installation

### 6.1 Open Chat
Navigate to `/app/niv-chat` — you should see the chat interface.

### 6.2 Test Chat
Type "hi" and send. You should get a response within 5-10 seconds.

### 6.3 Test Tools
Type "show top 5 sales orders" — should return real data from your ERP.

### 6.4 Test Widget
Go to any page (e.g., `/app`) — you should see the Chanakya Ai floating button (bottom-right).

### 6.5 Health Check
Navigate to `/app/niv-chat` → Settings (⚙️) → Run health check.

Or via API:
```bash
bench --site your-site.local execute niv_ai.niv_core.api.health.quick_check
```

---

## Step 7: Nginx Configuration for SSE

Streaming (Server-Sent Events) needs nginx proxy buffering disabled. Add to your nginx site config:

```nginx
location /api/method/niv_ai.niv_core.api.stream.stream_agent {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    chunked_transfer_encoding off;
}
```

Then reload nginx:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

> **Note:** `setup.sh` does this automatically.

---

## Step 8: Remove gunicorn --preload (Important!)

If your supervisor config has `--preload` for gunicorn, remove it. Otherwise, code changes won't reflect without full restart.

```bash
# Check
grep "preload" /etc/supervisor/conf.d/frappe-bench.conf

# If found, edit and remove --preload
sudo nano /etc/supervisor/conf.d/frappe-bench.conf
sudo supervisorctl reread
sudo supervisorctl update
```

---

## Quick Reference: File Locations

| What | Path |
|------|------|
| Niv Settings | `/app/niv-settings` (UI) |
| Chat Page | `/app/niv-chat` |
| AI Provider | `/app/niv-ai-provider` |
| Credit Plans | `/app/niv-credit-plan` |
| Widget JS | `apps/niv_ai/niv_ai/public/js/niv_widget.js` |
| Widget CSS | `apps/niv_ai/niv_ai/public/css/niv_widget.css` |
| Chat JS | `apps/niv_ai/niv_ai/niv_ui/page/niv_chat/niv_chat.js` |
| Billing API | `apps/niv_ai/niv_ai/niv_billing/api/billing.py` |
| Agent | `apps/niv_ai/niv_ai/niv_core/langchain/agent.py` |
| Stream | `apps/niv_ai/niv_ai/niv_core/api/stream.py` |
| Voice | `apps/niv_ai/niv_ai/niv_core/api/voice.py` |
| Telegram | `apps/niv_ai/niv_ai/niv_core/api/telegram.py` |
| FAB Logo | `apps/niv_ai/niv_ai/public/images/niv_fab_logo.png` |

---

## Troubleshooting

### Chat shows "No credits remaining"
→ Go to Niv Settings → Shared Pool Balance → Set to `10000000`

### Tools not working / empty tool list
→ Check `frappe_assistant_core` is installed: `bench --site your-site list-apps`
→ Restart workers: `sudo supervisorctl restart frappe-bench-workers:*`

### Streaming not working (response comes all at once)
→ Check nginx SSE config (Step 7)
→ Check `--preload` is removed (Step 8)

### Voice not working
→ Enable Voice in Niv Settings
→ Site must be HTTPS (browser STT needs secure context)
→ Check microphone permissions in browser

### Widget not showing
→ Enable Widget in Niv Settings
→ Check browser console for JS errors
→ Run `bench build --app niv_ai`

### Hindi/Urdu responses when expecting English
→ System language may be set to Hindi
→ Go to Setup → System Settings → Language → English

### Telegram bot not responding
→ Check bot token in Niv Settings
→ Run: `bench --site your-site execute niv_ai.niv_core.api.telegram.register_webhook`
→ Check Error Log for webhook errors

---

## Updating

```bash
cd /path/to/frappe-bench
bench update --apps niv_ai
bench --site your-site.local migrate
bench build --app niv_ai
sudo supervisorctl restart all
```

---

## Billing Server (Optional)

For centralized billing across multiple Niv AI instances, install the billing server app:

```bash
# On your BILLING server (not the Niv ERP server):
bench get-app https://github.com/kulharir7/niv_billing_server
bench --site billing-site install-app niv_billing_server
bench --site billing-site migrate
```

Then configure **Growth Billing** section in Niv Settings (Step 3.8).

---

<p align="center">🚀 That's it! Your Chanakya Ai is ready. Open <code>/app/niv-chat</code> and start chatting!</p>
