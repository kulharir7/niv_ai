"""
OAuth API for Niv AI — Claude (Anthropic) + ChatGPT (OpenAI) subscription auth.
Implements PKCE OAuth flow for both providers.

Supported auth types:
- "Setup Token" → Anthropic/Claude subscription
- "ChatGPT Login" → OpenAI/ChatGPT Plus/Pro subscription

Flow:
1. get_auth_url() → Returns auth URL for user to login
2. exchange_code() → Exchanges auth code for access + refresh tokens
3. refresh_if_needed() → Auto-refreshes expired tokens (called by llm.py)
"""
import frappe
import hashlib
import base64
import os
import time
import json
from frappe import _
from urllib.parse import urlencode

# ─── Anthropic (Claude) OAuth Constants ──────────────────────────────
ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
ANTHROPIC_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
ANTHROPIC_SCOPES = "org:create_api_key user:profile user:inference"

# ─── OpenAI (ChatGPT) OAuth Constants ───────────────────────────────
OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_REDIRECT_URI = "http://localhost:1455/auth/callback"
OPENAI_SCOPE = "openid profile email offline_access"

# Buffer: refresh 5 min before actual expiry
EXPIRY_BUFFER_MS = 5 * 60 * 1000


def _generate_pkce():
    """Generate PKCE code verifier and challenge (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge_bytes = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _get_oauth_config(auth_type):
    """Get OAuth config based on auth type."""
    if auth_type == "ChatGPT Login":
        return {
            "client_id": OPENAI_CLIENT_ID,
            "authorize_url": OPENAI_AUTHORIZE_URL,
            "token_url": OPENAI_TOKEN_URL,
            "redirect_uri": OPENAI_REDIRECT_URI,
            "scope": OPENAI_SCOPE,
            "content_type": "application/x-www-form-urlencoded",
            "provider_type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
        }
    else:  # Setup Token (Anthropic)
        return {
            "client_id": ANTHROPIC_CLIENT_ID,
            "authorize_url": ANTHROPIC_AUTHORIZE_URL,
            "token_url": ANTHROPIC_TOKEN_URL,
            "redirect_uri": ANTHROPIC_REDIRECT_URI,
            "scope": ANTHROPIC_SCOPES,
            "content_type": "application/json",
            "provider_type": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
        }


@frappe.whitelist()
def get_auth_url(provider_name: str):
    """Generate OAuth authorization URL for login.
    
    Returns: { url: "https://...", provider_type: "anthropic"|"openai" }
    """
    frappe.only_for("System Manager")
    
    if not provider_name:
        frappe.throw(_("Provider name is required"))
    
    provider = frappe.get_doc("Niv AI Provider", provider_name)
    if provider.auth_type not in ("Setup Token", "ChatGPT Login"):
        frappe.throw(_("OAuth login is only for Setup Token or ChatGPT Login auth type"))
    
    config = _get_oauth_config(provider.auth_type)
    verifier, challenge = _generate_pkce()
    
    # Store verifier temporarily (needed for code exchange)
    cache_key = f"niv_oauth_verifier_{provider_name}"
    frappe.cache().set_value(cache_key, verifier, expires_in_sec=600)
    
    if provider.auth_type == "ChatGPT Login":
        # OpenAI uses state parameter separately
        state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
        cache_state_key = f"niv_oauth_state_{provider_name}"
        frappe.cache().set_value(cache_state_key, state, expires_in_sec=600)
        
        params = {
            "response_type": "code",
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "scope": config["scope"],
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "niv",
        }
    else:
        # Anthropic
        params = {
            "code": "true",
            "client_id": config["client_id"],
            "response_type": "code",
            "redirect_uri": config["redirect_uri"],
            "scope": config["scope"],
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": verifier,
        }
    
    auth_url = f"{config['authorize_url']}?{urlencode(params)}"
    
    return {"url": auth_url, "provider_type": provider.auth_type}


@frappe.whitelist()
def exchange_code(provider_name: str, auth_code: str):
    """Exchange authorization code for access + refresh tokens.
    
    Args:
        provider_name: Niv AI Provider name
        auth_code: Code from login (format varies by provider)
    
    Returns: { success: True, message: "..." }
    """
    frappe.only_for("System Manager")
    
    if not provider_name or not auth_code:
        frappe.throw(_("Provider name and authorization code are required"))
    
    provider = frappe.get_doc("Niv AI Provider", provider_name)
    config = _get_oauth_config(provider.auth_type)
    
    # Parse code
    auth_code = auth_code.strip()
    
    # Get stored verifier
    cache_key = f"niv_oauth_verifier_{provider_name}"
    verifier = frappe.cache().get_value(cache_key)
    
    if not verifier:
        frappe.throw(_("OAuth session expired. Please click the login button again."))
    
    import requests
    
    try:
        if provider.auth_type == "ChatGPT Login":
            # OpenAI: parse code from URL or direct paste
            code = auth_code
            if "code=" in auth_code:
                from urllib.parse import urlparse, parse_qs
                try:
                    parsed = urlparse(auth_code)
                    code = parse_qs(parsed.query).get("code", [auth_code])[0]
                except Exception:
                    pass
            elif "#" in auth_code:
                code = auth_code.split("#")[0]
            
            # OpenAI uses form-encoded
            response = requests.post(config["token_url"], data={
                "grant_type": "authorization_code",
                "client_id": config["client_id"],
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": config["redirect_uri"],
            }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        else:
            # Anthropic: parse code#state
            parts = auth_code.split("#")
            code = parts[0]
            state = parts[1] if len(parts) > 1 else ""
            
            response = requests.post(config["token_url"], json={
                "grant_type": "authorization_code",
                "client_id": config["client_id"],
                "code": code,
                "state": state,
                "redirect_uri": config["redirect_uri"],
                "code_verifier": verifier,
            }, headers={"Content-Type": "application/json"}, timeout=30)
        
        if not response.ok:
            error_text = response.text
            frappe.log_error(f"OAuth token exchange failed ({provider.auth_type}): {error_text}", "Niv AI OAuth")
            frappe.throw(_(f"Token exchange failed: {response.status_code}. Please try again."))
        
        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        
        if not access_token or not refresh_token:
            frappe.throw(_("Invalid response. Missing tokens."))
        
        # Calculate expiry
        expires_at = str(int(time.time() * 1000) + (expires_in * 1000) - EXPIRY_BUFFER_MS)
        
        # Save to provider
        provider.api_key = access_token
        provider.refresh_token = refresh_token
        provider.token_expires = expires_at
        provider.oauth_status = "✅ Connected"
        provider.base_url = config["base_url"]
        provider.provider_type = config["provider_type"]
        provider.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Clear cache
        frappe.cache().delete_value(cache_key)
        
        provider_label = "ChatGPT" if provider.auth_type == "ChatGPT Login" else "Claude"
        return {"success": True, "message": f"Successfully connected to {provider_label}!"}
        
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"OAuth request error: {e}", "Niv AI OAuth")
        frappe.throw(_(f"Network error: {str(e)}"))


def refresh_if_needed(provider_name: str) -> str:
    """Check if token is expired and refresh if needed.
    
    Called by llm.py before each LLM call.
    Returns the current valid access token.
    """
    provider = frappe.get_doc("Niv AI Provider", provider_name)
    
    # Only for OAuth auth types with refresh token
    if provider.auth_type not in ("Setup Token", "ChatGPT Login"):
        return provider.get_password("api_key")
    
    refresh_tok = provider.get_password("refresh_token") if provider.refresh_token else None
    if not refresh_tok:
        return provider.get_password("api_key")
    
    token_expires = int(provider.token_expires or 0)
    now_ms = int(time.time() * 1000)
    
    # Token still valid
    if now_ms < token_expires:
        return provider.get_password("api_key")
    
    # Token expired — refresh
    config = _get_oauth_config(provider.auth_type)
    frappe.logger().info(f"Niv AI: Refreshing OAuth token for '{provider_name}' ({provider.auth_type})")
    
    import requests
    
    try:
        if provider.auth_type == "ChatGPT Login":
            # OpenAI uses form-encoded
            response = requests.post(config["token_url"], data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
                "client_id": config["client_id"],
            }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        else:
            # Anthropic uses JSON
            response = requests.post(config["token_url"], json={
                "grant_type": "refresh_token",
                "client_id": config["client_id"],
                "refresh_token": refresh_tok,
            }, headers={"Content-Type": "application/json"}, timeout=30)
        
        if not response.ok:
            error_text = response.text
            frappe.log_error(f"OAuth refresh failed for {provider_name}: {error_text}", "Niv AI OAuth")
            provider.oauth_status = "❌ Refresh failed — re-authenticate"
            provider.save(ignore_permissions=True)
            frappe.db.commit()
            return provider.get_password("api_key")
        
        data = response.json()
        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        
        if not new_access:
            frappe.log_error("OAuth refresh returned no access_token", "Niv AI OAuth")
            return provider.get_password("api_key")
        
        # Update provider
        expires_at = str(int(time.time() * 1000) + (expires_in * 1000) - EXPIRY_BUFFER_MS)
        provider.api_key = new_access
        if new_refresh:
            provider.refresh_token = new_refresh
        provider.token_expires = expires_at
        provider.oauth_status = "✅ Connected"
        provider.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Niv AI: OAuth token refreshed for '{provider_name}', expires in {expires_in}s")
        return new_access
        
    except Exception as e:
        frappe.log_error(f"OAuth refresh error for {provider_name}: {e}", "Niv AI OAuth")
        return provider.get_password("api_key")
