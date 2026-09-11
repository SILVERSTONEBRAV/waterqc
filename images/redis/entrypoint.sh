#!/usr/bin/env sh
set -e

echo "🧠 Starting Advanced Redis..."

# Ensure data directory exists
mkdir -p /data

# Fix permissions safely (only if root, otherwise ignore)
chown -R 999:999 /data || true

# Print memory config for debugging
echo "⚙️ Redis Memory Limit: 512mb"
echo "⚙️ Eviction Policy: allkeys-lru"

# Start Redis
exec "$@"