#!/bin/bash
# Niv AI - Frontend nginx SSE patch wrapper
# Patches nginx config for SSE streaming, then runs nginx-entrypoint.sh
set -e

# First run the original entrypoint to generate the config
# We replicate what nginx-entrypoint.sh does, then patch before starting nginx

# Set defaults (same as nginx-entrypoint.sh)
export BACKEND="${BACKEND:-0.0.0.0:8000}"
export SOCKETIO="${SOCKETIO:-0.0.0.0:9000}"
export UPSTREAM_REAL_IP_ADDRESS="${UPSTREAM_REAL_IP_ADDRESS:-127.0.0.1}"
export UPSTREAM_REAL_IP_HEADER="${UPSTREAM_REAL_IP_HEADER:-X-Forwarded-For}"
export UPSTREAM_REAL_IP_RECURSIVE="${UPSTREAM_REAL_IP_RECURSIVE:-off}"
export FRAPPE_SITE_NAME_HEADER="${FRAPPE_SITE_NAME_HEADER:-\$host}"
export PROXY_READ_TIMEOUT="${PROXY_READ_TIMEOUT:-120}"
export CLIENT_MAX_BODY_SIZE="${CLIENT_MAX_BODY_SIZE:-50m}"

# Generate nginx config from template (same as original entrypoint)
envsubst '${BACKEND}
  ${SOCKETIO}
  ${UPSTREAM_REAL_IP_ADDRESS}
  ${UPSTREAM_REAL_IP_HEADER}
  ${UPSTREAM_REAL_IP_RECURSIVE}
  ${FRAPPE_SITE_NAME_HEADER}
  ${PROXY_READ_TIMEOUT}
	${CLIENT_MAX_BODY_SIZE}' \
  </templates/nginx/frappe.conf.template >/etc/nginx/conf.d/frappe.conf

# Inject SSE location block before the closing brace of the server block
SSE_BLOCK='
    # Niv AI SSE streaming
    location /api/method/niv_ai.niv_core.api.stream.stream_message {
        proxy_pass http://backend-server;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '"'"''"'"';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_read_timeout 300s;
    }
'

CONF="/etc/nginx/conf.d/frappe.conf"
if ! grep -q "niv_ai.*stream" "$CONF" 2>/dev/null; then
    # Insert before the last closing brace
    sed -i "/^}/i\\${SSE_BLOCK}" "$CONF"
    echo "[niv_ai] SSE location block injected into nginx config."
else
    echo "[niv_ai] SSE location block already present."
fi

# Start nginx
exec nginx -g 'daemon off;'
