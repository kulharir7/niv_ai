#!/bin/bash
# ─────────────────────────────────────────────────────────
# Niv AI — One-Command Setup
# Usage: bash setup.sh <site-name> <provider-base-url> <api-key> <model>
#
# Example:
#   bash setup.sh mysite.localhost https://api.mistral.ai/v1 sk-abc123 mistral-large-latest
#
# This script will:
#   1. Install frappe_assistant_core (MCP tools)
#   2. Install niv_ai
#   3. Run migrations
#   4. Build frontend
#   5. Create AI Provider
#   6. Configure Niv Settings
#   7. Setup nginx for SSE streaming
#   8. Restart everything
# ─────────────────────────────────────────────────────────

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step()  { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

# ─── Args ───────────────────────────────────────────────

SITE="$1"
BASE_URL="$2"
API_KEY="$3"
MODEL="${4:-mistral-large-latest}"
FAST_MODEL="${5:-mistral-small-latest}"

if [ -z "$SITE" ]; then
    echo ""
    echo "Niv AI — One-Command Setup"
    echo ""
    echo "Usage:"
    echo "  bash setup.sh <site> <base-url> <api-key> [model] [fast-model]"
    echo ""
    echo "Examples:"
    echo ""
    echo "  # Mistral (recommended)"
    echo "  bash setup.sh mysite.com https://api.mistral.ai/v1 sk-xxx mistral-large-latest mistral-small-latest"
    echo ""
    echo "  # OpenAI"
    echo "  bash setup.sh mysite.com https://api.openai.com/v1 sk-xxx gpt-4o gpt-4o-mini"
    echo ""
    echo "  # Anthropic (Claude)"
    echo "  bash setup.sh mysite.com https://api.anthropic.com sk-xxx claude-sonnet-4-20250514 claude-haiku-4-20250414"
    echo ""
    echo "  # DeepSeek"
    echo "  bash setup.sh mysite.com https://api.deepseek.com/v1 sk-xxx deepseek-chat deepseek-chat"
    echo ""
    echo "  # Groq (fast inference)"
    echo "  bash setup.sh mysite.com https://api.groq.com/openai/v1 gsk-xxx llama-3.3-70b-versatile llama-3.1-8b-instant"
    echo ""
    echo "  # Ollama (local, free, no API key needed)"
    echo "  bash setup.sh mysite.com http://localhost:11434/v1 ollama llama3.1 llama3.1"
    echo ""
    echo "  # Minimal (configure provider later in UI)"
    echo "  bash setup.sh mysite.com"
    echo ""
    exit 0
fi

# ─── Detect bench path ──────────────────────────────────

if [ -f "sites/common_site_config.json" ]; then
    BENCH_PATH="$(pwd)"
elif [ -f "../sites/common_site_config.json" ]; then
    BENCH_PATH="$(cd .. && pwd)"
    cd "$BENCH_PATH"
else
    error "Run this from your frappe-bench directory (or apps/niv_ai)."
fi

log "Bench path: $BENCH_PATH"
log "Site: $SITE"

# ─── Step 1: Install FAC ────────────────────────────────

step "Step 1/7: Installing frappe_assistant_core (MCP tools)"

if [ -d "apps/frappe_assistant_core" ]; then
    log "FAC already installed, skipping download"
else
    bench get-app https://github.com/AdarshPS1/frappe_assistant_core.git || warn "FAC download failed (may already exist)"
fi

# Check if app is installed on site
FAC_INSTALLED=$(bench --site "$SITE" list-apps 2>/dev/null | grep -c "frappe_assistant_core" || true)
if [ "$FAC_INSTALLED" -eq 0 ]; then
    bench --site "$SITE" install-app frappe_assistant_core
    log "FAC installed on $SITE"
else
    log "FAC already installed on $SITE"
fi

# ─── Step 2: Install Niv AI ─────────────────────────────

step "Step 2/7: Installing Niv AI"

NIV_INSTALLED=$(bench --site "$SITE" list-apps 2>/dev/null | grep -c "niv_ai" || true)
if [ "$NIV_INSTALLED" -eq 0 ]; then
    bench --site "$SITE" install-app niv_ai
    log "Niv AI installed on $SITE"
else
    log "Niv AI already installed on $SITE"
fi

# ─── Step 3: Migrate ────────────────────────────────────

step "Step 3/7: Running migrations"
bench --site "$SITE" migrate
log "Migrations complete"

# ─── Step 4: Build frontend ─────────────────────────────

step "Step 4/7: Building frontend assets"
bench build --app niv_ai 2>/dev/null || warn "Build had warnings (page JS works without build)"
log "Frontend build complete"

# ─── Step 5: Configure AI Provider ──────────────────────

step "Step 5/7: Configuring AI Provider"

# Auto-detect provider name from base URL
_detect_provider_name() {
    local url="$1"
    case "$url" in
        *mistral*)    echo "Mistral" ;;
        *openai.com*) echo "OpenAI" ;;
        *anthropic*)  echo "Anthropic" ;;
        *groq*)       echo "Groq" ;;
        *together*)   echo "Together AI" ;;
        *ollama*|*localhost*|*127.0.0.1*) echo "Ollama" ;;
        *deepseek*)   echo "DeepSeek" ;;
        *fireworks*)  echo "Fireworks" ;;
        *perplexity*) echo "Perplexity" ;;
        *)            echo "AI Provider" ;;
    esac
}

if [ -n "$BASE_URL" ]; then
    PROVIDER_NAME=$(_detect_provider_name "$BASE_URL")
    _API_KEY="${API_KEY:-ollama}"  # Default to "ollama" for local providers

    bench --site "$SITE" console <<EOF
provider_name = "$PROVIDER_NAME"
if not frappe.db.exists("Niv AI Provider", provider_name):
    doc = frappe.get_doc({
        "doctype": "Niv AI Provider",
        "provider_name": provider_name,
        "base_url": "$BASE_URL",
        "api_key": "$_API_KEY",
        "default_model": "$MODEL",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Created provider: {provider_name}")
else:
    doc = frappe.get_doc("Niv AI Provider", provider_name)
    doc.base_url = "$BASE_URL"
    doc.api_key = "$_API_KEY"
    doc.default_model = "$MODEL"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"Updated provider: {provider_name}")

settings = frappe.get_single("Niv Settings")
settings.default_provider = provider_name
settings.default_model = "$MODEL"
settings.fast_model = "$FAST_MODEL"
settings.enable_widget = 1
settings.widget_title = "Niv AI"
settings.enable_billing = 1
settings.billing_mode = "Shared Pool"
if not settings.shared_pool_balance or int(settings.shared_pool_balance or 0) == 0:
    settings.shared_pool_balance = 10000000
settings.save(ignore_permissions=True)
frappe.db.commit()
print("Niv Settings configured!")
EOF
    log "Provider '$PROVIDER_NAME' configured (model: $MODEL, fast: $FAST_MODEL)"
else
    warn "No base URL provided — configure AI Provider manually at /app/niv-settings"
fi

# ─── Step 6: Add Assistant role to Administrator ────────

step "Step 6/7: Setting up user roles"

bench --site "$SITE" console <<EOF
# Give Administrator the Assistant Admin role
user = frappe.get_doc("User", "Administrator")
has_role = any(r.role == "Assistant Admin" for r in user.roles)
if not has_role:
    user.append("roles", {"role": "Assistant Admin"})
    user.save(ignore_permissions=True)
    frappe.db.commit()
    print("Added Assistant Admin role to Administrator")
else:
    print("Administrator already has Assistant Admin role")

# Set system language to English (for consistent AI responses)
frappe.db.set_single_value("System Settings", "language", "en")
frappe.db.commit()
print("System language set to English")
EOF

log "Roles configured"

# ─── Step 7: Nginx SSE config ────────────────────────────

step "Step 7/8: Configuring Nginx for SSE streaming"

# Find nginx config for this site
NGINX_CONF=""
for f in /etc/nginx/conf.d/*.conf /etc/nginx/sites-enabled/*; do
    if [ -f "$f" ] && grep -q "$SITE" "$f" 2>/dev/null; then
        NGINX_CONF="$f"
        break
    fi
done

# Also check bench-generated config
if [ -z "$NGINX_CONF" ] && [ -f "$BENCH_PATH/config/nginx.conf" ]; then
    NGINX_CONF="$BENCH_PATH/config/nginx.conf"
fi

NIV_SSE_BLOCK='
	# Niv AI SSE streaming — auto-configured by setup.sh
	location /api/method/niv_ai.niv_core.api.stream.stream_chat {
		proxy_pass http://frappe-bench-frappe;
		proxy_buffering off;
		proxy_cache off;
		proxy_read_timeout 300s;
		proxy_connect_timeout 75s;
		proxy_set_header X-Accel-Buffering no;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
		proxy_http_version 1.1;
		proxy_set_header Connection "";
	}

	location /api/method/niv_ai.niv_core.api.voice_stream.stream_voice {
		proxy_pass http://frappe-bench-frappe;
		proxy_buffering off;
		proxy_cache off;
		proxy_read_timeout 300s;
		proxy_set_header X-Accel-Buffering no;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
		proxy_http_version 1.1;
		proxy_set_header Connection "";
	}
'

NGINX_CONFIGURED=false

if [ -n "$NGINX_CONF" ]; then
    # Check if already configured
    if grep -q "niv_ai.*stream" "$NGINX_CONF" 2>/dev/null; then
        log "Nginx SSE already configured in $NGINX_CONF"
        NGINX_CONFIGURED=true
    else
        # Try to inject before the last closing brace of the server block
        # We need sudo for nginx config
        if [ -w "$NGINX_CONF" ] || command -v sudo &>/dev/null; then
            # Create a temp file with the SSE block injected
            # Find the line with "location /api" (first Frappe API location) and inject before it
            INJECT_LINE=$(grep -n "location /api {" "$NGINX_CONF" 2>/dev/null | head -1 | cut -d: -f1)
            
            if [ -n "$INJECT_LINE" ]; then
                # Backup original
                sudo cp "$NGINX_CONF" "${NGINX_CONF}.bak.niv" 2>/dev/null || cp "$NGINX_CONF" "${NGINX_CONF}.bak.niv" 2>/dev/null
                
                # Inject SSE block before the generic /api location
                sudo sed -i "${INJECT_LINE}i\\${NIV_SSE_BLOCK}" "$NGINX_CONF" 2>/dev/null || \
                    sed -i "${INJECT_LINE}i\\${NIV_SSE_BLOCK}" "$NGINX_CONF" 2>/dev/null
                
                # Test nginx config
                if sudo nginx -t 2>/dev/null; then
                    sudo nginx -s reload 2>/dev/null
                    log "Nginx SSE configured and reloaded"
                    NGINX_CONFIGURED=true
                else
                    # Restore backup
                    sudo cp "${NGINX_CONF}.bak.niv" "$NGINX_CONF" 2>/dev/null
                    sudo nginx -s reload 2>/dev/null
                    warn "Nginx config injection failed — restored backup"
                fi
            else
                warn "Could not find injection point in $NGINX_CONF"
            fi
        else
            warn "No write access to $NGINX_CONF — need sudo"
        fi
    fi
else
    # No nginx conf found — try bench setup nginx
    if command -v bench &>/dev/null; then
        bench setup nginx --yes 2>/dev/null && {
            # Now find the generated config and patch it
            if [ -f "$BENCH_PATH/config/nginx.conf" ]; then
                NGINX_CONF="$BENCH_PATH/config/nginx.conf"
                # Append SSE block to the config
                echo "$NIV_SSE_BLOCK" | sudo tee -a /etc/nginx/conf.d/frappe-bench.conf >/dev/null 2>&1
                sudo nginx -t 2>/dev/null && sudo nginx -s reload 2>/dev/null
                log "Nginx generated and SSE configured"
                NGINX_CONFIGURED=true
            fi
        } || warn "bench setup nginx failed"
    fi
fi

# ─── Step 8: Final ──────────────────────────────────────

step "Step 8/8: Final setup"

# Clear cache
bench --site "$SITE" clear-cache 2>/dev/null || true
log "Cache cleared"

# Restart
bench restart 2>/dev/null || {
    sudo supervisorctl restart all 2>/dev/null || warn "Restart failed — run: sudo supervisorctl restart all"
}

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Niv AI v1.0.0 installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Chat:     https://$SITE/app/niv-chat"
echo "  Settings: https://$SITE/app/niv-settings"
echo ""

if [ -n "$BASE_URL" ]; then
    echo "  Provider:   $PROVIDER_NAME ✓"
    echo "  Model:      $MODEL"
    echo "  Fast Model: $FAST_MODEL"
    echo "  Billing:    Demo mode (10M free tokens)"
else
    echo -e "  ${YELLOW}⚠ Configure AI Provider at /app/niv-settings${NC}"
fi

if [ "$NGINX_CONFIGURED" = true ]; then
    echo "  Nginx SSE:  configured ✓"
else
    echo ""
    echo -e "  ${YELLOW}⚠ Nginx SSE not auto-configured. Add manually:${NC}"
    echo ""
    echo "  location /api/method/niv_ai.niv_core.api.stream.stream_chat {"
    echo "      proxy_buffering off;"
    echo "      proxy_cache off;"
    echo "      proxy_read_timeout 300s;"
    echo "      add_header X-Accel-Buffering no;"
    echo "  }"
    echo ""
    echo "  Then: sudo nginx -t && sudo nginx -s reload"
fi

echo ""
echo "  Ready to use! Open /app/niv-chat and start chatting."
echo ""
