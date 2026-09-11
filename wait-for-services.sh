#!/usr/bin/env bash

set -Eeuo pipefail

# =============================================================================
# GLOBALS
# =============================================================================
SCRIPT_NAME="$(basename "$0")"
START_TIME="$(date +%s)"

# =============================================================================
# COLORS
# =============================================================================
if [[ -t 1 ]]; then
    RED="\033[1;31m"
    GREEN="\033[1;32m"
    YELLOW="\033[1;33m"
    BLUE="\033[1;34m"
    MAGENTA="\033[1;35m"
    CYAN="\033[1;36m"
    RESET="\033[0m"
else
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    MAGENTA=""
    CYAN=""
    RESET=""
fi

# =============================================================================
# ENVIRONMENT LOADING
# =============================================================================
ENV_FILE="${ENV_FILE:-/app/.env}"

if [[ -f "$ENV_FILE" ]]; then
    set -o allexport
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +o allexport
fi

# =============================================================================
# CONFIGURATION
# =============================================================================
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"
WAIT_INTERVAL="${WAIT_INTERVAL:-2}"
MAX_WAIT_INTERVAL="${MAX_WAIT_INTERVAL:-10}"

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

POSTGRES_HOST="${POSTGRES_HOST:-pgbouncer}"
POSTGRES_PORT="${POSTGRES_PORT:-6432}"

WEB_HOST="${WEB_HOST:-web1}"
WEB_PORT="${WEB_PORT:-8000}"

DAPHNE_HOST="${DAPHNE_HOST:-daphne1}"
DAPHNE_PORT="${DAPHNE_PORT:-8001}"

APP_USER="${APP_USER:-appuser}"

AUTO_FIX_PERMISSIONS="${AUTO_FIX_PERMISSIONS:-true}"
VERIFY_DB_CONNECTION="${VERIFY_DB_CONNECTION:-false}"

# =============================================================================
# LOGGING
# =============================================================================
timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
}

log() {
    echo -e "${BLUE}[$(timestamp)] [INFO]${RESET} $*"
}

warn() {
    echo -e "${YELLOW}[$(timestamp)] [WARN]${RESET} $*"
}

success() {
    echo -e "${GREEN}[$(timestamp)] [OK]${RESET} $*"
}

error() {
    echo -e "${RED}[$(timestamp)] [ERROR]${RESET} $*" >&2
}

fatal() {
    error "$*"
    exit 1
}

# =============================================================================
# SIGNAL HANDLING
# =============================================================================
shutdown() {
    warn "Shutdown signal received"
    exit 0
}

trap shutdown SIGTERM SIGINT

# =============================================================================
# UTILITIES
# =============================================================================
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

resolve_host() {
    local host="$1"

    getent hosts "$host" >/dev/null 2>&1
}

show_runtime_info() {

    log "==============================================="
    log "QAD Runtime Diagnostics"
    log "==============================================="

    log "Hostname        : $(hostname)"
    log "User            : $(whoami)"
    log "UID:GID         : $(id -u):$(id -g)"
    log "Working Dir     : $(pwd)"
    log "Python Version  : $(python --version 2>&1)"
    log "Environment     : ${ENVIRONMENT:-unknown}"
    log "Django Settings : ${DJANGO_SETTINGS_MODULE:-unset}"

    if command_exists gunicorn; then
        log "Gunicorn        : $(gunicorn --version 2>&1 | head -n1)"
    fi

    if command_exists celery; then
        log "Celery          : $(celery --version 2>/dev/null || true)"
    fi

    log "==============================================="
}

# =============================================================================
# DIRECTORY BOOTSTRAP
# =============================================================================
bootstrap_directories() {

    log "Preparing runtime directories"

    mkdir -p \
        /app/media \
        /app/media/exports \
        /app/staticfiles \
        /app/logs \
        /app/run \
        /app/tmp \
        /var/log/qad \
        /var/run/qad

    if [[ "$AUTO_FIX_PERMISSIONS" == "true" ]]; then

        if [[ "$(id -u)" == "0" ]]; then

            chown -R "${APP_USER}:${APP_USER}" \
                /app/media \
                /app/staticfiles \
                /app/logs \
                /app/run \
                /app/tmp \
                /var/log/qad \
                /var/run/qad || true

        else
            warn "Skipping chown because container is running as non-root"
        fi
    fi

    chmod -R 775 \
        /app/media \
        /app/logs \
        /app/run \
        /app/tmp \
        /var/log/qad \
        /var/run/qad || true

    success "Runtime directories ready"
}

# =============================================================================
# TCP WAIT
# =============================================================================
wait_for_tcp() {

    local host="$1"
    local port="$2"
    local service_name="$3"

    local elapsed=0
    local sleep_time="$WAIT_INTERVAL"

    log "Waiting for ${service_name} -> ${host}:${port}"

    while true; do

        if ! resolve_host "$host"; then
            warn "DNS lookup failed for ${host}"
        fi

        if (echo > /dev/tcp/"$host"/"$port") >/dev/null 2>&1; then
            success "${service_name} is reachable"
            return 0
        fi

        sleep "$sleep_time"

        elapsed=$((elapsed + sleep_time))

        if (( elapsed >= WAIT_TIMEOUT )); then
            fatal "Timeout waiting for ${service_name} (${host}:${port})"
        fi

        sleep_time=$((sleep_time * 2))

        if (( sleep_time > MAX_WAIT_INTERVAL )); then
            sleep_time="$MAX_WAIT_INTERVAL"
        fi
    done
}

# =============================================================================
# DATABASE VALIDATION
# =============================================================================
verify_database_connection() {

    if [[ "$VERIFY_DB_CONNECTION" != "true" ]]; then
        return 0
    fi

    if ! command_exists python; then
        warn "Python not found; skipping DB verification"
        return 0
    fi

    log "Verifying Django database connectivity"

    python <<'PY'
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "qad.settings"))

django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT 1")

print("Database connectivity verified")
PY

    success "Django database connection verified"
}

# =============================================================================
# SERVICE WAITERS
# =============================================================================
wait_for_postgres() {
    wait_for_tcp \
        "$POSTGRES_HOST" \
        "$POSTGRES_PORT" \
        "PostgreSQL/PgBouncer"
}

wait_for_redis() {
    wait_for_tcp \
        "$REDIS_HOST" \
        "$REDIS_PORT" \
        "Redis"
}

wait_for_web() {
    wait_for_tcp \
        "$WEB_HOST" \
        "$WEB_PORT" \
        "Gunicorn"
}

wait_for_daphne() {
    wait_for_tcp \
        "$DAPHNE_HOST" \
        "$DAPHNE_PORT" \
        "Daphne"
}

# =============================================================================
# PRESTART VALIDATION
# =============================================================================
validate_environment() {

    log "Validating environment"

    [[ -n "${POSTGRES_HOST}" ]] || fatal "POSTGRES_HOST missing"
    [[ -n "${REDIS_HOST}" ]] || fatal "REDIS_HOST missing"

    success "Environment validation passed"
}

# =============================================================================
# MAIN
# =============================================================================
main() {

    show_runtime_info

    validate_environment

    bootstrap_directories

    log "==============================================="
    log "QAD Service Dependency Check"
    log "==============================================="

    wait_for_postgres
    wait_for_redis

    verify_database_connection

    success "Core infrastructure ready"

    log "==============================================="
    success "ALL REQUIRED SERVICES READY"
    log "==============================================="

    local end_time
    end_time="$(date +%s)"

    success "Bootstrap completed in $((end_time - START_TIME))s"

    if [[ $# -gt 0 ]]; then
        log "Starting command:"
        echo "--------------------------------------------------"
        echo "$*"
        echo "--------------------------------------------------"

        exec "$@"
    else
        warn "No command supplied. Opening shell."
        exec /bin/bash
    fi
}

main "$@"
