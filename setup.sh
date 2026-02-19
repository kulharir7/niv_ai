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
    echo "  # Mistral (recommended)"
    echo "  bash setup.sh mysite.localhost https://api.mistral.ai/v1 sk-xxx mistral-large-latest mistral-small-latest"
    echo ""
    echo "  # OpenAI"
    echo "  bash setup.sh mysite.localhost https://api.openai.com/v1 sk-xxx gpt-4o gpt-4o-mini"
    echo ""
    echo "  # Ollama (local, free)"
    echo "  bash setup.sh mysite.localhost http://localhost:11434/v1 ollama llama3.1 llama3.1"
    echo ""
    echo "  # Minimal (configure later in UI)"
    echo "  bash setup.sh mysite.localhost"
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

if [ -n "$API_KEY" ] && [ "$API_KEY" != "ollama" ]; then
    bench --site "$SITE" execute niv_ai.install.setup_provider --kwargs "{
        \"base_url\": \"$BASE_URL\",
        \"api_key\": \"$API_KEY\",
        \"model\": \"$MODEL\",
        \"fast_model\": \"$FAST_MODEL\"
    }" 2>/dev/null || {
        # Fallback: create via console
        bench --site "$SITE" console <<EOF
provider_name = "AI Provider"
if not frappe.db.exists("Niv AI Provider", provider_name):
    doc = frappe.get_doc({
        "doctype": "Niv AI Provider",
        "provider_name": provider_name,
        "base_url": "$BASE_URL",
        "api_key": "$API_KEY",
        "default_model": "$MODEL",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Created provider: {provider_name}")
else:
    print(f"Provider already exists: {provider_name}")

# Update Niv Settings
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
    }
    log "AI Provider configured (model: $MODEL, fast: $FAST_MODEL)"
else
    if [ "$API_KEY" = "ollama" ]; then
        bench --site "$SITE" console <<EOF
provider_name = "Ollama"
if not frappe.db.exists("Niv AI Provider", provider_name):
    doc = frappe.get_doc({
        "doctype": "Niv AI Provider",
        "provider_name": provider_name,
        "base_url": "$BASE_URL",
        "api_key": "ollama",
        "default_model": "$MODEL",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
settings = frappe.get_single("Niv Settings")
settings.default_provider = provider_name
settings.default_model = "$MODEL"
settings.fast_model = "$FAST_MODEL"
settings.enable_widget = 1
settings.enable_billing = 1
settings.billing_mode = "Shared Pool"
settings.shared_pool_balance = 99999999
settings.save(ignore_permissions=True)
frappe.db.commit()
print("Ollama provider configured!")
EOF
        log "Ollama provider configured (free, local)"
    else
        warn "No API key provided — configure manually at /app/niv-settings"
    fi
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

# ─── Step 7: Nginx SSE config hint ──────────────────────

step "Step 7/7: Final setup"

# Clear cache
bench --site "$SITE" clear-cache 2>/dev/null || true
log "Cache cleared"

# Restart
bench restart 2>/dev/null || {
    warn "bench restart failed (may need sudo). Try: sudo supervisorctl restart all"
}

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Niv AI v1.0.0 installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Open:  https://$SITE/app/niv-chat"
echo "  Settings: https://$SITE/app/niv-settings"
echo ""

if [ -n "$API_KEY" ]; then
    echo "  Provider: configured ✓"
    echo "  Model: $MODEL"
    echo "  Fast Model: $FAST_MODEL"
    echo "  Billing: Demo mode (10M tokens)"
else
    echo -e "  ${YELLOW}⚠ Configure AI Provider at /app/niv-settings${NC}"
fi

echo ""
echo -e "  ${YELLOW}⚠ IMPORTANT: Add this to your nginx config for streaming:${NC}"
echo ""
echo "  location /api/method/niv_ai.niv_core.api.stream.stream_chat {"
echo "      proxy_buffering off;"
echo "      proxy_cache off;"
echo "      proxy_read_timeout 300s;"
echo "      add_header X-Accel-Buffering no;"
echo "  }"
echo ""
echo "  Then: sudo nginx -t && sudo nginx -s reload"
echo ""
