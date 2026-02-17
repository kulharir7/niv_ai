# Niv AI — Installation Guide

## Requirements
- **ERPNext** v14 or v15
- **Frappe** v14 or v15
- **Python** 3.8+
- **MariaDB** 10.3+

## Installation

```bash
# 1. Get the app
bench get-app https://github.com/your-org/niv_ai

# 2. Install on your site
bench --site your-site install-app niv_ai

# 3. Run migrations
bench migrate

# 4. Build frontend assets
bench build --app niv_ai
```

## Configuration

1. **Go to** `/app/niv-settings`
2. **Add AI Provider:**
   - Name: `mistral` (or `openai`, `ollama`, etc.)
   - Base URL: `https://api.mistral.ai/v1` (or your provider's URL)
   - API Key: your key
   - Default Model: `mistral-medium-2508` (or your model)
3. **Set defaults:**
   - Default Provider → your provider name
   - Default Model → your model name
   - Enable Widget → ✅
   - Widget Title → `Niv AI`
4. **Billing (optional):**
   - Billing Mode → `Shared Pool` or `Per User`
   - Shared Pool Balance → set initial tokens
5. **Razorpay (optional):**
   - Leave keys empty → Demo mode (fake payments)
   - Add real keys → Real Razorpay checkout

## Usage

- **Full page chat:** `/app/niv-chat`
- **Widget:** Purple ✦ button on bottom-right of every ERPNext page
- **Recharge:** `/app/niv-credits` or Settings ⚙️ → Recharge
- **Admin dashboard:** `/app/niv-dashboard`

## Supported AI Providers

Any OpenAI-compatible API:
- **Mistral AI** — `https://api.mistral.ai/v1`
- **OpenAI** — `https://api.openai.com/v1`
- **Ollama** (local) — `http://localhost:11434/v1`
- **Azure OpenAI** — your Azure endpoint
- **Google Gemini** — via OpenAI-compatible proxy
- **Any other** OpenAI-compatible endpoint

## Optional Dependencies

These are auto-installed but some may need system packages:

| Package | Purpose | Required? |
|---------|---------|-----------|
| openai | AI API client | Yes |
| tiktoken | Token counting | Yes |
| pdfplumber | PDF file reading | Optional |
| python-docx | Word file reading | Optional |
| Pillow | Image processing | Optional |
| pytesseract | OCR (needs tesseract binary) | Optional |
| piper-tts | Local TTS (CPU-friendly) | Optional |
| razorpay | Real payments | Only if using Razorpay |

## Troubleshooting

### Blank page on /app/niv-chat
```bash
bench build --app niv_ai
bench migrate
# Clear browser cache (Ctrl+Shift+R)
```

### SSE streaming not working
Add to your nginx config inside the `server {}` block:
```nginx
location /api/method/niv_ai.niv_core.api.stream.chat_stream {
    proxy_pass http://your-backend;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300;
    add_header X-Accel-Buffering no;
}
```

### pip packages missing after restart (Docker)
```bash
/home/frappe/frappe-bench/env/bin/pip install -e apps/niv_ai
```
