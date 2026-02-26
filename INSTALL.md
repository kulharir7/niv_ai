# Niv AI — Complete Installation & Setup Guide

> Step-by-step guide to get Niv AI running on your Growth System instance.

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| **Growth System** | v15+ (v14 partially supported) |
| **Frappe** | v15+ |
| **Python** | 3.10+ |
| **MariaDB** | 10.6+ |
| **Node.js** | 18+ |
| **wkhtmltopdf** | Any (for PDF export) |

You also need an AI API key from one of:
- **Mistral AI** (recommended) — https://console.mistral.ai
- OpenAI — https://platform.openai.com
- Anthropic — https://console.anthropic.com
- Any OpenAI-compatible provider (Ollama, Groq, Together, etc.)

---

## Step 1: Install frappe_assistant_core (FAC)

FAC provides the MCP tools that Niv AI uses to read/write Growth System data.

```bash
cd /path/to/frappe-bench

# Get FAC
bench get-app https://github.com/AdarshPS1/frappe_assistant_core.git

# Install on your site
bench --site yoursite.com install-app frappe_assistant_core

# Migrate
bench --site yoursite.com migrate
```

**Verify:** Go to `/app/assistant-tool` — you should see 30+ tools listed.

---

## Step 2: Install Niv AI

```bash
# Get Niv AI
bench get-app https://github.com/kulharir7/niv_ai.git

# Install on your site
bench --site yoursite.com install-app niv_ai

# Migrate (creates DocTypes, adds fields)
bench --site yoursite.com migrate

# Build frontend assets
bench build --app niv_ai

# Restart
bench restart
# OR if using supervisor:
sudo supervisorctl restart all
```

**Verify:** Open `/app/niv-chat` — you should see the chat interface.

---

## Step 3: Configure AI Provider

1. Go to **Niv Settings**: `/app/niv-settings`

2. **Create an AI Provider** — click "AI Providers" link or go to `/app/niv-ai-provider/new`:
   | Field | Value |
   |-------|-------|
   | Provider Name | `Mistral` (or any name) |
   | Base URL | `https://api.mistral.ai/v1` |
   | API Key | Your Mistral API key |
   | Default Model | `mistral-large-latest` |

3. **Back in Niv Settings**, set:
   | Field | Value |
   |-------|-------|
   | Default Provider | `Mistral` (the provider you just created) |
   | Default Model | `mistral-large-latest` |
   | Fast Model | `mistral-small-latest` (for two-model speed optimization) |
   | Enable Widget | ✅ |
   | Widget Title | `Niv AI` |

4. **Save** Niv Settings.

---

## Step 4: Configure Billing

Niv AI tracks token usage per request. Two billing modes:

### Option A: Demo Mode (Free, for testing)
- In Niv Settings:
  - **Enable Billing** → ✅
  - **Billing Mode** → `Shared Pool`
  - **Shared Pool Balance** → set to a large number (e.g., `10000000`)
- Leave Payment Mode empty or set to `demo`
- Users can "buy" tokens for free (demo checkout)

### Option B: Growth Billing (Production)
- Set **Payment Mode** → `growth`
- Configure Growth Billing fields:
  - **Growth Billing URL** — Your billing Growth System instance URL
  - **Growth API Key** / **Growth API Secret** — API credentials for the billing site
  - **Growth Billing Customer** — Default customer name (e.g., `Niv AI Customer`)
  - **Growth Billing Item** — Item code for token recharge (e.g., `Niv AI Token Recharge`)
- Set up a Server Script on the billing Growth System to handle callbacks (see Growth Billing Setup section below)

---

## Step 5: Enable for Users

By default, only users with **Assistant User** or **Assistant Admin** role can access Niv AI.

### Add roles to users:
```
Role                  | Access
──────────────────────┼──────────────────────
Assistant User        | Chat, voice, export
Assistant Admin       | Chat + settings + analytics
System Manager        | Full access
```

To enable for a user:
1. Go to `/app/user/username@email.com`
2. Add role: **Assistant User**
3. Save

### Enable widget globally:
In Niv Settings → **Enable Widget** → ✅

This adds a floating chat button on every Growth System page.

---

## Step 6: Nginx Configuration (Important!)

SSE streaming requires nginx to not buffer responses. Add this to your nginx site config:

```nginx
# Inside your server {} block, add:

# Niv AI SSE streaming — MUST disable buffering
location /api/method/niv_ai.niv_core.api.stream.stream_chat {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;
    proxy_set_header X-Accel-Buffering no;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}

# Niv AI voice streaming
location /api/method/niv_ai.niv_core.api.voice_stream.stream_voice {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    proxy_set_header X-Accel-Buffering no;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}
```

Then reload nginx:
```bash
sudo nginx -t && sudo nginx -s reload
```

**Without this, chat will appear to hang** — responses come all at once instead of streaming.

---

## Step 7: Test

1. Open `/app/niv-chat`
2. Type: **"hi"** — should get a greeting response
3. Type: **"show me all customers"** — should call tools and show a table
4. If table appears, you should see **Excel / CSV / PDF** buttons below it
5. Try voice: click the microphone icon, speak in Hindi or English

---

## Optional: Voice Setup

### Edge TTS (Free, recommended)
- Works out of the box — no configuration needed
- Indian accent: English (`en-IN-NeerjaExpressiveNeural`), Hindi (`hi-IN-SwaraNeural`)

### ElevenLabs (Premium)
- Get API key from https://elevenlabs.io
- In Niv Settings → **ElevenLabs API Key** → paste your key
- Uses `eleven_multilingual_v2` model with auto language detection

### Voxtral STT (Server-side speech-to-text)
- Uses Mistral's Voxtral Mini model
- Works automatically if your Mistral API key supports Voxtral
- Fallback: Browser's built-in Web Speech API (hi-IN)

---

## Optional: Telegram Bot

1. Create a bot via [@BotFather](https://t.me/botfather) → get the bot token
2. In Niv Settings → **Telegram Bot Token** → paste token
3. Set webhook URL:
   ```
   https://yoursite.com/api/method/niv_ai.niv_core.api.telegram.webhook
   ```
4. Register webhook:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://yoursite.com/api/method/niv_ai.niv_core.api.telegram.webhook"
   ```
5. Users link their Telegram to Growth System account via `/link` command in the bot

---

## Optional: Developer Mode

For Growth System developers who want to create DocTypes, scripts, and workflows via chat:

1. In Niv Settings → **Enable Developer Mode** → ✅
2. In chat, type: `/dev` to toggle developer mode per conversation
3. The assistant will:
   - Ask for confirmation before creating/modifying anything
   - Show impact analysis (which other DocTypes depend on changes)
   - Support undo for recently created documents

---

## Troubleshooting

### "No AI provider configured"
→ Create a provider in `/app/niv-ai-provider/new` and set it as default in Niv Settings.

### Chat loads but no response / infinite loading
→ Check nginx SSE config (Step 6). Without it, streaming doesn't work.

### "0 MCP tools loaded"
→ FAC not installed or no tools registered. Go to `/app/assistant-tool` — should show 30+ tools.
→ If empty: `bench --site yoursite.com migrate` and restart.

### Blank page on /app/niv-chat
```bash
bench build --app niv_ai
# Clear browser cache: Ctrl+Shift+R
```

### Token billing shows 0
→ Check Niv Settings → **Enable Billing** is ON and pool balance > 0.

### Voice not working
→ Browser must allow microphone access (HTTPS required).
→ Edge TTS needs internet (it's a Microsoft cloud service).

### pip packages missing after server restart
```bash
cd /path/to/frappe-bench
./env/bin/pip install -e apps/niv_ai
bench restart
```

---

## Growth Billing Setup (for production)

If you want to charge users for token usage via a separate Growth System instance:

### On the billing Growth System:

1. Create an **Item**: `Niv AI Token Recharge` (non-stock)
2. Create a **Customer**: `Niv AI Customer`
3. Create a **Server Script** (DocEvent, Before Save on Sales Invoice):

```python
# Niv AI Token Callback
# Triggers when a Sales Invoice for token recharge is submitted

if doc.custom_niv_callback_url and doc.docstatus == 1:
    import requests
    try:
        requests.post(doc.custom_niv_callback_url, json={
            "recharge_id": doc.custom_niv_recharge_id,
            "amount": doc.grand_total,
            "status": "Paid",
        }, timeout=10)
    except:
        pass
```

### On the Niv AI Growth System:

1. In Niv Settings, set:
   - Payment Mode: `growth`
   - Growth Billing URL: `https://billing-erpnext.com`
   - Growth API Key / Secret: API credentials for the billing site
   - Growth Billing Customer: `Niv AI Customer`
   - Growth Billing Item: `Niv AI Token Recharge`

---

## Updating

```bash
cd /path/to/frappe-bench/apps/niv_ai
git pull origin main

cd /path/to/frappe-bench
bench --site yoursite.com migrate
bench build --app niv_ai
bench restart
```

---

## Support

- **GitHub Issues**: https://github.com/kulharir7/niv_ai/issues
- **Author**: Ravindra Kulhari ([@kulharir7](https://github.com/kulharir7))
