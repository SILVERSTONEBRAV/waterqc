#!/bin/bash
# ==========================================================
#nginx/entrypoint.sh
# 🟢 Nginx Entrypoint — Windows-proof, fallback SSL, dynamic template
# ==========================================================
set -euo pipefail

echo "═══════════════════════════════════════════════"
echo "🔐 [NGINX] Boot Sequence Started"
echo "📅 $(date)"
echo "═══════════════════════════════════════════════"

# -----------------------------
# Environment defaults
# -----------------------------
DOMAIN="${DOMAIN_NAME:-localhost}"
NGINX_TEMPLATE="${NGINX_TEMPLATE:-/etc/nginx/conf.d/nginx.template}"
NGINX_OUTPUT="${NGINX_OUTPUT:-/etc/nginx/conf.d/default.conf}"
SSL_DIR="${SSL_DIR:-/etc/letsencrypt}"
FALLBACK_DIR="${SSL_DIR}/fallback"

mkdir -p "$FALLBACK_DIR"
mkdir -p "$SSL_DIR/live/$DOMAIN"

# -----------------------------
# Generate fallback SSL if needed
# -----------------------------
echo "⚙️  Checking fallback SSL certificates..."
FALLBACK_CERT="$FALLBACK_DIR/fullchain.pem"
FALLBACK_KEY="$FALLBACK_DIR/privkey.pem"

if [ -x /docker-entrypoint.d/generate-fallback-certs.sh ]; then
    /docker-entrypoint.d/generate-fallback-certs.sh
elif [ ! -f "$FALLBACK_CERT" ] || [ ! -f "$FALLBACK_KEY" ]; then
    echo "⚡ Generating fallback self-signed certificate..."
    openssl req -x509 -nodes -newkey rsa:4096 \
        -days 3650 \
        -keyout "$FALLBACK_KEY" \
        -out "$FALLBACK_CERT" \
        -subj "/CN=$DOMAIN"
    chmod 600 "$FALLBACK_KEY"
fi

# -----------------------------
# Detect production SSL certs (without waiting)
# -----------------------------
PROD_CERT="$SSL_DIR/live/$DOMAIN/fullchain.pem"
PROD_KEY="$SSL_DIR/live/$DOMAIN/privkey.pem"

if [ -f "$PROD_CERT" ] && [ -f "$PROD_KEY" ]; then
    SSL_CERT_PATH="$PROD_CERT"
    SSL_KEY_PATH="$PROD_KEY"
    echo "✅ Using production SSL certificates"
else
    SSL_CERT_PATH="$FALLBACK_CERT"
    SSL_KEY_PATH="$FALLBACK_KEY"
    echo "⚠️ Using fallback self-signed certificates"
fi

# -----------------------------
# Render Nginx configuration
# -----------------------------
echo "🔧 Rendering Nginx configuration..."
envsubst '$DOMAIN_NAME $SSL_CERT_PATH $SSL_KEY_PATH' \
    < "$NGINX_TEMPLATE" > "$NGINX_OUTPUT"

# -----------------------------
# Test Nginx config
# -----------------------------
echo "🔍 Testing Nginx configuration..."
nginx -t

# -----------------------------
# Optional debug
# -----------------------------
if [ "${NGINX_DEBUG:-false}" = "true" ]; then
    echo "📢 Debug mode enabled — printing full Nginx config"
    nginx -T || true
fi

# -----------------------------
# Launch Nginx
# -----------------------------
echo "🚀 Launching Nginx..."
exec nginx -g 'daemon off;'
