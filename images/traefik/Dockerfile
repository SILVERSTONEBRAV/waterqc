# =========================================================
# 🧭 TRAEFIK - PRODUCTION EDGE ROUTER (LOCAL BUILD)
# =========================================================

FROM traefik:v3.1

# ---------------------------------------------------------
# 📦 Install minimal debugging tools (optional but useful)
# ---------------------------------------------------------
USER root

RUN apk add --no-cache \
    curl \
    bash \
    ca-certificates \
    tzdata \
    && rm -rf /var/cache/apk/*

# ---------------------------------------------------------
# 📁 Directory structure for dynamic config
# ---------------------------------------------------------
RUN mkdir -p /etc/traefik \
    /etc/traefik/dynamic \
    /etc/traefik/certs \
    /var/log/traefik

# ---------------------------------------------------------
# 📄 Copy static config
# ---------------------------------------------------------
COPY ./traefik.yml /etc/traefik/traefik.yml

# ---------------------------------------------------------
# 📄 Copy dynamic configs (routers, middlewares, etc.)
# ---------------------------------------------------------
COPY ./dynamic /etc/traefik/dynamic

# ---------------------------------------------------------
# 🔐 ACME storage (Let's Encrypt / staging safe fallback)
# ---------------------------------------------------------
RUN touch /etc/traefik/acme.json \
    && chmod 600 /etc/traefik/acme.json

# ---------------------------------------------------------
# 👤 Security: run as non-root
# ---------------------------------------------------------
USER 65532:65532

# ---------------------------------------------------------
# 🌍 Expose ports
# ---------------------------------------------------------
EXPOSE 80 443 8080

# ---------------------------------------------------------
# 🚀 Default entrypoint (Traefik binary already included)
# ---------------------------------------------------------
ENTRYPOINT ["/entrypoint.sh"]

CMD ["traefik"]