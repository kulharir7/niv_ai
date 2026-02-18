"""
OAuth API for Niv AI — Claude (Anthropic) subscription auth.
Implements PKCE OAuth flow for Claude Pro/Max subscriptions.

Flow:
1. get_auth_url() → Returns claude.ai auth URL for user to login
2. exchange_code() → Exchanges auth code for access + refresh tokens
3. refresh_token() → Auto-refreshes expired tokens (called by llm.py)

Based on Anthropic's OAuth implementation (same as Claude Code CLI).
"""
import frappe
import hashlib
import base64
import os
import time
import json
from frappe import _

# Anthropic OAuth constants (same as Claude Code CLI)
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
SCOPES = "org:create_api_key user:profile user:inference"

# Buffer: refresh 5 min before actual expiry
EXPIRY_BUFFER_MS = 5 * 60 * 1000


def _generate_pkce():
    """Generate PKCE code verifier and challenge (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge_bytes = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")
    return verifier, challenge


@frappe.whitelist()
def get_auth_url(provider_name: str):
    """Generate OAuth authorization URL for Claude login.
    
    Returns: { url: "https://claude.ai/oauth/authorize?...", verifier: "xxx" }
    User opens URL, logs in, gets code to paste back.
    """
    frappe.only_for("System Manager")
    
    if not provider_name:
        frappe.throw(_("Provider name is required"))
    
    provider = frappe.get_doc("Niv AI Provider", provider_name)
    if provider.auth_type != "Setup Token":
        frappe.throw(_("OAuth login is only for Setup Token auth type"))
    
    verifier, challenge = _generate_pkce()
    
    # Store verifier temporarily in provider (needed for code exchange)
    # Using a cache key since we don't want to add another field
    cache_key = f"niv_oauth_verifier_{provider_name}"
    frappe.cache().set_value(cache_key, verifier, expires_in_sec=600)  # 10 min
    
    params = {
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": verifier,
    }
    
    query_string = "&".join(f"{k}={frappe.utils.cstr(v)}" for k, v in params.items())
    auth_url = f"{AUTHORIZE_URL}?{query_string}"
    
    return {"url": auth_url}


@frappe.whitelist()
def exchange_code(provider_name: str, auth_code: str):
    """Exchange authorization code for access + refresh tokens.
    
    Args:
        provider_name: Niv AI Provider name
        auth_code: Code from Claude login (format: "code#state" or just "code")
    
    Returns: { success: True, message: "..." }
    """
    frappe.only_for("System Manager")
    
    if not provider_name or not auth_code:
        frappe.throw(_("Provider name and authorization code are required"))
    
    provider = frappe.get_doc("Niv AI Provider", provider_name)
    
    # Parse code#state format
    auth_code = auth_code.strip()
    parts = auth_code.split("#")
    code = parts[0]
    state = parts[1] if len(parts) > 1 else ""
    
    # Get stored verifier
    cache_key = f"niv_oauth_verifier_{provider_name}"
    verifier = frappe.cache().get_value(cache_key)
    
    if not verifier:
        frappe.throw(_("OAuth session expired. Please click 'Login with Claude' again."))
    
    # Exchange code for tokens
    import requests
    
    try:
        response = requests.post(TOKEN_URL, json={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "state": state,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }, headers={"Content-Type": "application/json"}, timeout=30)
        
        if not response.ok:
            error_text = response.text
            frappe.log_error(f"OAuth token exchange failed: {error_text}", "Niv AI OAuth")
            frappe.throw(_(f"Token exchange failed: {response.status_code}. Please try again."))
        
        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        
        if not access_token or not refresh_token:
            frappe.throw(_("Invalid response from Claude. Missing tokens."))
        
        # Calculate expiry (now + expires_in - 5min buffer)
        expires_at = int(time.time() * 1000) + (expires_in * 1000) - EXPIRY_BUFFER_MS
        
        # Save to provider
        provider.api_key = access_token
        provider.refresh_token = refresh_token
        provider.token_expires = expires_at
        provider.oauth_status = "✅ Connected"
        provider.base_url = "https://api.anthropic.com/v1"
        provider.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Clear cache
        frappe.cache().delete_value(cache_key)
        
        return {"success": True, "message": "Successfully connected to Claude!"}
        
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"OAuth request error: {e}", "Niv AI OAuth")
        frappe.throw(_(f"Network error: {str(e)}"))


def refresh_if_needed(provider_name: str) -> str:
    """Check if token is expired and refresh if needed.
    
    Called by llm.py before each LLM call.
    Returns the current valid access token (api_key).
    
    This function does NOT use @frappe.whitelist — it's internal only.
    """
    provider = frappe.get_doc("Niv AI Provider", provider_name)
    
    # Only for Setup Token auth type with refresh token
    if provider.auth_type != "Setup Token":
        return provider.get_password("api_key")
    
    refresh_tok = provider.get_password("refresh_token") if provider.refresh_token else None
    if not refresh_tok:
        # No refresh token — just use api_key as-is (manual setup-token paste)
        return provider.get_password("api_key")
    
    token_expires = provider.token_expires or 0
    now_ms = int(time.time() * 1000)
    
    # Token still valid
    if now_ms < token_expires:
        return provider.get_password("api_key")
    
    # Token expired — refresh
    frappe.logger().info(f"Niv AI: Refreshing OAuth token for provider '{provider_name}'")
    
    import requests
    
    try:
        response = requests.post(TOKEN_URL, json={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_tok,
        }, headers={"Content-Type": "application/json"}, timeout=30)
        
        if not response.ok:
            error_text = response.text
            frappe.log_error(f"OAuth refresh failed for {provider_name}: {error_text}", "Niv AI OAuth")
            provider.oauth_status = "❌ Refresh failed — re-authenticate"
            provider.save(ignore_permissions=True)
            frappe.db.commit()
            # Return old token anyway — might still work
            return provider.get_password("api_key")
        
        data = response.json()
        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        
        if not new_access:
            frappe.log_error("OAuth refresh returned no access_token", "Niv AI OAuth")
            return provider.get_password("api_key")
        
        # Update provider with new tokens
        expires_at = int(time.time() * 1000) + (expires_in * 1000) - EXPIRY_BUFFER_MS
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
        # Return old token as fallback
        return provider.get_password("api_key")
