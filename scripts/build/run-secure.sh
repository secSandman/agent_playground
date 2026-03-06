#!/bin/bash
# ============================================================
# Secure OpenCode Container Runner
# Applies defense-in-depth security controls
# ============================================================

set -euo pipefail

IMAGE="opencode-sandbox:1.2.17"
CONTAINER_NAME="opencode-secure-$(date +%s)"
WORKSPACE_DIR="${1:-.}"

echo "🔒 Starting hardened OpenCode container..."
echo "   Workspace: $WORKSPACE_DIR"

docker run -it --rm \
  --name "$CONTAINER_NAME" \
  \
  `# Security: User namespace remapping - run as non-root` \
  --user 1001:1001 \
  \
  `# Security: Prevent privilege escalation` \
  --security-opt=no-new-privileges:true \
  \
  `# Security: Drop all Linux capabilities` \
  --cap-drop=ALL \
  \
  `# Security: Read-only root filesystem` \
  --read-only \
  \
  `# Security: Writable /tmp with security restrictions` \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=100m \
  \
  `# Security: Writable workspace with security restrictions` \
  --tmpfs /home/opencodeuser/workspace:rw,noexec,nosuid,nodev,size=500m \
  \
  `# Security: Disable network access (remove if network needed)` \
  --network=none \
  \
  `# Security: Resource limits to prevent DoS` \
  --memory=2g \
  --memory-swap=2g \
  --cpus=2 \
  --pids-limit=100 \
  \
  `# Security: AppArmor/SELinux profile (use if available)` \
  `# --security-opt apparmor=docker-default` \
  `# --security-opt label=type:container_runtime_t` \
  \
  `# Mount workspace as volume (comment out tmpfs above if using this)` \
  # -v "$(realpath "$WORKSPACE_DIR"):/home/opencodeuser/workspace:rw" \
  \
  "$IMAGE" \
  "$@"

echo "✅ Container exited cleanly"
