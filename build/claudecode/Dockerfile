# ============================================================
# ClaudeCode — Hardened Container Build
# Installs pinned Claude Code CLI via npm with non-root runtime
# ============================================================

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Pin exact Claude Code package version
ARG CLAUDECODE_VERSION=1.0.98

# Minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged runtime user
RUN useradd -m -s /bin/bash -u 1001 claudeuser && \
    usermod -L claudeuser

# Remove setuid/setgid binaries to reduce privilege escalation surface
RUN find / -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Harden npm defaults to reduce supply-chain risk
RUN printf 'ignore-scripts=true\nsave-exact=true\naudit=false\nfund=false\n' > /root/.npmrc && \
    chmod 600 /root/.npmrc

# Install pinned Claude Code CLI version globally as root
# NOTE: ignore-scripts is enabled via /root/.npmrc to avoid arbitrary postinstall execution
RUN npm install -g @anthropic-ai/claude-code@${CLAUDECODE_VERSION} && \
    claude --version

USER claudeuser
WORKDIR /home/claudeuser

# Apply hardened npm defaults for runtime user too
RUN printf 'ignore-scripts=true\nsave-exact=true\naudit=false\nfund=false\n' > /home/claudeuser/.npmrc && \
    chmod 600 /home/claudeuser/.npmrc

# Create locked-down Claude settings
RUN mkdir -p /home/claudeuser/.claude && \
    printf '{\n  "autoupdate": false,\n  "permissions": {\n    "allow": [],\n    "deny": [\n      "Bash(curl:*)",\n      "Bash(wget:*)",\n      "Bash(nc:*)",\n      "Bash(base64:*)",\n      "Bash(python -c:*)",\n      "Bash(node -e:*)",\n      "Bash(bash -c:*)",\n      "Bash(eval:*)",\n      "Bash(sudo:*)"\n    ]\n  }\n}\n' > /home/claudeuser/.claude/settings.json

# Prevent in-container mutation of security defaults
RUN chmod 400 /home/claudeuser/.claude/settings.json

# Workspace mount point
RUN mkdir -p /home/claudeuser/workspace
WORKDIR /home/claudeuser/workspace

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=1 \
  CMD ["claude", "--version"] || exit 1

ENTRYPOINT ["claude"]
