#!/bin/bash
# ============================================================
# OpenCode Sandbox with Squid Proxy (Linux/Mac)
# Run OpenCode CLI in a container with controlled network access
# ============================================================

set -euo pipefail

WORKSPACE_PATH="${1:-}"
OPENAI_KEY="${OPENAI_API_KEY:-}"
ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"

echo "========================================"
echo "OpenCode Secure Sandbox Launcher"
echo "========================================"
echo ""

# Validate workspace path
if [ -z "$WORKSPACE_PATH" ]; then
    echo "Usage: $0 /path/to/workspace"
    echo ""
    echo "Example: $0 ~/projects/myproject"
    exit 1
fi

if [ ! -d "$WORKSPACE_PATH" ]; then
    echo "ERROR: Workspace path does not exist: $WORKSPACE_PATH"
    exit 1
fi

WORKSPACE_PATH=$(realpath "$WORKSPACE_PATH")
echo "Workspace: $WORKSPACE_PATH"

# Check API keys
if [ -z "$OPENAI_KEY" ] && [ -z "$ANTHROPIC_KEY" ]; then
    echo "WARNING: No API keys found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variables."
fi

# Build images
echo ""
echo "Building container images..."

cd "$(dirname "$0")"

# Build OpenCode image if not exists
if ! docker images | grep -q "opencode-sandbox.*1.2.17"; then
    echo "Building opencode-sandbox:1.2.17..."
    docker build -t opencode-sandbox:1.2.17 .
fi

# Build Squid proxy
echo "Building squid proxy..."
docker compose build squid-proxy

echo "Images ready"
echo ""

# Start squid proxy
echo "Starting Squid proxy for network policy enforcement..."
docker compose up -d squid-proxy

# Wait for proxy to be healthy
echo "Waiting for proxy to be ready..."
retries=30
while [ $retries -gt 0 ]; do
    health=$(docker inspect --format='{{.State.Health.Status}}' opencode-squid 2>/dev/null || echo "")
    if [ "$health" = "healthy" ]; then
        echo "Proxy ready"
        break
    fi
    sleep 1
    ((retries--))
done

if [ $retries -eq 0 ]; then
    echo "ERROR: Proxy failed to become healthy"
    docker compose down
    exit 1
fi

echo ""
echo "========================================"
echo "Starting OpenCode CLI"
echo "========================================"
echo ""
echo "Your code at: $WORKSPACE_PATH"
echo "Network: Proxied through Squid (see squid.conf for allowed domains)"
echo ""
echo "Commands:"
echo "  - Edit files in VS Code on your host"
echo "  - Changes are immediately visible in container"
echo "  - Use 'exit' or Ctrl+C to stop"
echo ""

# Export workspace path for docker-compose
export WORKSPACE_PATH

# Build docker compose run command
COMPOSE_ARGS=(compose run --rm --service-ports)

# Add API keys if available
[ -n "$OPENAI_KEY" ] && COMPOSE_ARGS+=(-e "OPENAI_API_KEY=$OPENAI_KEY")
[ -n "$ANTHROPIC_KEY" ] && COMPOSE_ARGS+=(-e "ANTHROPIC_API_KEY=$ANTHROPIC_KEY")

COMPOSE_ARGS+=(opencode)

# Run OpenCode
docker "${COMPOSE_ARGS[@]}"

echo ""
echo "OpenCode session ended"

# Optional: View logs
if [ "${VIEW_LOGS:-false}" = "true" ]; then
    echo ""
    echo "Proxy access logs:"
    docker compose logs squid-proxy
fi

# Cleanup
echo ""
echo "Cleaning up..."
docker compose down
echo "Done"
