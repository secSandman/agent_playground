# ============================================================
# OpenCode — Hardened Container Build
# Uses direct GitHub Releases binary download with SHA256 verification
# Update OPENCODE_VERSION and OPENCODE_SHA256_X64 for each upgrade
# ============================================================

FROM ubuntu:24.04 AS base

# Security: Use a minimal base with security updates
# Pin the base image digest for reproducibility in production
# Example: FROM ubuntu:24.04@sha256:d1e2e92c075e5ca139d5aa8063b610c9f21a880838ffcd506bd8858c5b3dd57c

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# ---- PIN THESE VALUES ON EACH UPGRADE ----
# Version to install — always use an exact release tag, never "latest"
ARG OPENCODE_VERSION=1.2.17

# SHA256 hash of the linux-x64 binary for this exact version
# Source: https://github.com/anomalyco/opencode/releases/tag/v${OPENCODE_VERSION}
# Replace this with the actual hash from the releases page (without sha256: prefix)
ARG OPENCODE_SHA256_X64=dbfe556df45ac999eff95248269ccdd06ee2052983bb03b9501fe9dda2d1f695

# SHA256 hash of the linux-arm64 binary (for ARM hosts / Apple Silicon via --platform)
ARG OPENCODE_SHA256_ARM64=cd8b3cd13bef12e29f32e0f32e5ca48e29159cf6cd32ddee8b3be97438a0242c
# ------------------------------------------

# Install minimal runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user with no sudo/root access
# Explicitly set no password and lock the account
RUN useradd -m -s /bin/bash -u 1001 opencodeuser && \
    usermod -L opencodeuser

# Remove setuid/setgid binaries that could be abused for privilege escalation
RUN find / -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Switch to non-root for download and verification
USER opencodeuser
WORKDIR /home/opencodeuser

# Detect architecture and download the appropriate binary
# sha256sum -c will exit non-zero and abort the build if the hash does not match
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        BINARY_NAME="opencode-linux-x64.tar.gz" && \
        EXPECTED_HASH="${OPENCODE_SHA256_X64}"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        BINARY_NAME="opencode-linux-arm64.tar.gz" && \
        EXPECTED_HASH="${OPENCODE_SHA256_ARM64}"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    DOWNLOAD_URL="https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/${BINARY_NAME}" && \
    echo "Downloading ${DOWNLOAD_URL}" && \
    curl -fsSL -o /home/opencodeuser/opencode.tar.gz "${DOWNLOAD_URL}" && \
    echo "Verifying SHA256..." && \
    echo "${EXPECTED_HASH}  /home/opencodeuser/opencode.tar.gz" | sha256sum -c - && \
    echo "SHA256 verification passed." && \
    tar -xzf /home/opencodeuser/opencode.tar.gz -C /home/opencodeuser && \
    rm /home/opencodeuser/opencode.tar.gz && \
    chmod +x /home/opencodeuser/opencode

# Add binary to PATH
ENV PATH="/home/opencodeuser:${PATH}"

# Security: Create hardened .npmrc to prevent plugin ecosystem attacks
RUN mkdir -p /home/opencodeuser && \
    printf 'ignore-scripts=true\nsave-exact=true\naudit=true\n' > /home/opencodeuser/.npmrc && \
    chmod 600 /home/opencodeuser/.npmrc

# Security: Create hardened opencode.json with strict permission policies
RUN mkdir -p /home/opencodeuser/.config/opencode && \
    cat > /home/opencodeuser/.config/opencode/opencode.json << 'EOF'
{
  "autoupdate": false,
  "permission": {
    "webfetch": "deny",
    "external_directory": {
      "*": "deny"
    },
    "bash": {
      "curl*": "deny",
      "wget*": "deny",
      "nc*": "deny",
      "base64*": "deny",
      "python -c*": "deny",
      "node -e*": "deny",
      "bash -c*": "deny",
      "eval*": "deny",
      "sudo*": "deny"
    },
    "read": {
      "**/.env*": "deny",
      "**/*.key": "deny",
      "**/*.pem": "deny",
      "**/.ssh/**": "deny",
      "**/.aws/**": "deny",
      "**/auth.json": "deny"
    },
    "edit": {
      "**/opencode.json": "deny"
    }
  }
}
EOF

# Workspace for project files
RUN mkdir -p /home/opencodeuser/workspace
WORKDIR /home/opencodeuser/workspace

# Security: Drop all capabilities and run read-only where possible
# Apply these runtime flags when running the container:
# --security-opt=no-new-privileges:true (prevent privilege escalation)
# --cap-drop=ALL (drop all Linux capabilities)
# --read-only (make root filesystem read-only, except /tmp and workspace)
# --tmpfs /tmp:rw,noexec,nosuid,size=100m (writable tmp with restrictions)
# --network=none (disable network access if not needed)
# --memory=2g --cpus=2 (resource limits)
# --pids-limit=100 (limit number of processes)

# Health check: Verify opencode binary is executable
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=1 \
    CMD ["/home/opencodeuser/opencode", "--version"] || exit 1

# Do not expose any ports — the HTTP server on 4096 is not needed for CLI use
# If you need the HTTP server, explicitly EXPOSE 4096 and bind to 127.0.0.1 only

# ============================================================
# Recommended docker run flags for production hardened execution:
# ============================================================
# docker run \
#   --rm \
#   --security-opt no-new-privileges:true \
#   --cap-drop ALL \
#   --read-only \
#   --tmpfs /tmp:rw,noexec,nosuid,size=100m \
#   --memory 2g \
#   --cpus 2 \
#   --pids-limit 100 \
#   -v $(pwd):/home/opencodeuser/workspace:rw \
#   -v ~/.local/share/opencode/auth.json:/home/opencodeuser/.local/share/opencode/auth.json:ro \
#   <image-name>:<tag>
# ============================================================

ENTRYPOINT ["/home/opencodeuser/opencode"]