#!/bin/sh
# ==========================================================
# nginx/generate-fallback-certs.sh
# Idempotent SSL certificate generator for Alpine Nginx
# With SAN support and full production/fallback logic
# ==========================================================

set -euo pipefail

DOMAIN="${DOMAIN_NAME:-localhost}"

echo "🔐 Using DOMAIN=${DOMAIN}"

# -----------------------------
# Certificate paths
# -----------------------------
PROD_LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"
PROD_CERT="${PROD_LIVE_DIR}/fullchain.pem"
PROD_KEY="${PROD_LIVE_DIR}/privkey.pem"

FALLBACK_DIR="/etc/letsencrypt/fallback"
FALLBACK_CERT="${FALLBACK_DIR}/fullchain.pem"
FALLBACK_KEY="${FALLBACK_DIR}/privkey.pem"

# -----------------------------
# 1️⃣ If production certs exist → skip fallback
# -----------------------------
if [ -f "$PROD_CERT" ] && [ -f "$PROD_KEY" ]; then
    echo "✅ Production SSL certificates found — fallback not needed"
    exit 0
fi

echo "⚠️ Production certificates missing — enabling fallback SSL"

# -----------------------------
# 2️⃣ Ensure fallback directory exists
# -----------------------------
mkdir -p "$FALLBACK_DIR"

# -----------------------------
# 3️⃣ Decide whether to generate a new fallback certificate
# -----------------------------
NEED_GEN=false

if ! [ -f "$FALLBACK_CERT" ] || ! [ -f "$FALLBACK_KEY" ]; then
    NEED_GEN=true
else
    # Check expiration (30 days)
    if ! openssl x509 -checkend $((30*86400)) -noout -in "$FALLBACK_CERT"; then
        echo "⛔ Fallback certificate expiring soon — regenerating"
        NEED_GEN=true
    fi
fi

# -----------------------------
# 4️⃣ Generate fallback certificate if required
# -----------------------------
if [ "$NEED_GEN" = true ]; then
    echo "⚡ Generating fallback self-signed cert for CN=${DOMAIN}"

    # Create SAN config (important for modern browsers)
    SAN_CONFIG="${FALLBACK_DIR}/san.cnf"
    cat > "$SAN_CONFIG" <<EOF
[req]
default_bits = 4096
distinguished_name = dn
req_extensions = req_ext
x509_extensions = req_ext
prompt = no

[dn]
CN = ${DOMAIN}

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = localhost
EOF

    # Generate self-signed cert
    openssl req -x509 -nodes -newkey rsa:4096 \
        -days 3650 \
        -keyout "$FALLBACK_KEY" \
        -out "$FALLBACK_CERT" \
        -config "$SAN_CONFIG"

    chmod 600 "$FALLBACK_KEY"

    echo "✅ Fallback certificate generated:"
    echo "   → $FALLBACK_CERT"
    echo "   → $FALLBACK_KEY"
else
    echo "🟢 Existing fallback certificate is still valid — no regeneration needed"
fi

exit 0
