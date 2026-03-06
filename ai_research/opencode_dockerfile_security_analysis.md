# OpenCode Dockerfile — Supply Chain Security Analysis & Hardened Build

**Date:** March 2026  
**Scope:** Replaces Step 2 in opencode_container_install_guide.txt

---

## The Short Answer

The original Dockerfile using `curl -fsSL https://opencode.ai/install | bash` is **the least secure approach possible**. It executes an unauthenticated shell script from a remote server with no integrity check of any kind.

There are better options, but with important caveats explained below.

---

## What Verification Does OpenCode Actually Provide?

### ✅ SHA256 Hashes — Available, on GitHub Releases only

OpenCode publishes per-binary SHA256 hashes as part of every GitHub release:

```
https://github.com/anomalyco/opencode/releases/tag/v1.2.17
```

Every asset (e.g., `opencode-linux-x64`, `opencode-linux-arm64`) has an explicit
SHA256 hash listed in the release. Example from the v1.2.17 release:

```
opencode-linux-x64
sha256: d4c9e3...  (varies per release — always fetch from the releases page)
```

This is the most reliable verification mechanism currently available.
**You must pin a specific version and manually record the hash from the releases page.**

---

### ⚠️ Desktop .sig files — Not for the CLI binary

The `.sig` files seen in GitHub releases (e.g., `opencode-desktop-darwin-aarch64.app.tar.gz.sig`)
are Tauri auto-updater signatures for the **desktop GUI application only**.
They are **not** applicable to the CLI binary used in containers.

---

### ❌ npm Provenance / Sigstore — Not present

The `opencode-ai` npm package does **not** currently publish Sigstore provenance
attestations. The npm package page shows no provenance badge.

What npm *does* provide is lockfile integrity: when you run `npm install`, the
`package-lock.json` stores a SHA-512 SRI hash for each package as downloaded.
Running `npm ci` (not `npm install`) enforces that hash on reinstall.

**However:** the `opencode-ai` npm package is a thin wrapper that downloads the
platform-specific compiled binary at install time via a postinstall script. The
lockfile verifies the *wrapper*, not the *binary*. The binary itself is fetched
from GitHub at install time with no hash verification in the postinstall script.

This is a meaningful supply chain gap and a known pattern of risk in the npm
ecosystem (the "binary downloader" pattern). The npm lockfile integrity gives
false confidence here.

---

### ❌ Reproducible builds — Not confirmed

There is no published reproducible build attestation or SLSA provenance for
OpenCode binaries. Builds run in GitHub Actions CI, but there is no published
in-toto attestation or SLSA build level claim.

---

## Comparison of Installation Methods — Security Ranking

| Method | What Is Verified | Trust Anchor | Recommendation |
|---|---|---|---|
| `curl opencode.ai/install \| bash` | Nothing | CDN operator | ❌ Never use in containers |
| `npm install -g opencode-ai` (no lockfile) | Nothing | npm registry | ❌ Avoid |
| `npm ci` with lockfile | npm wrapper SHA-512 | npm registry | ⚠️ Partial — binary is still unverified |
| GitHub Releases binary + SHA256 check | Binary SHA256 | GitHub releases page | ✅ Best available |
| GitHub Releases binary + SHA256 + commit pinning | Binary + source commit | GitHub + your own pin | ✅ Best available + auditable |

---

## Hardened Dockerfile — GitHub Releases with SHA256 Verification

This approach:
1. Downloads the binary directly from GitHub Releases (not via npm or curl script)
2. Pins an exact version
3. Verifies the SHA256 hash before installation
4. Fails loudly if the hash does not match
5. Runs as a non-root user
6. Minimizes the image surface area

**IMPORTANT — Before using this Dockerfile:**
- Visit https://github.com/anomalyco/opencode/releases
- Find the release you want to pin (e.g., v1.2.17)
- Copy the SHA256 hash for `opencode-linux-x64` (or arm64 for ARM hosts)
- Replace the placeholder values in the Dockerfile below

```dockerfile
# ============================================================
# OpenCode — Hardened Container Build
# Uses direct GitHub Releases binary download with SHA256 verification
# Update OPENCODE_VERSION and OPENCODE_SHA256_X64 for each upgrade
# ============================================================

FROM ubuntu:24.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# ---- PIN THESE VALUES ON EACH UPGRADE ----
# Version to install — always use an exact release tag, never "latest"
ARG OPENCODE_VERSION=1.2.17

# SHA256 hash of the linux-x64 binary for this exact version
# Source: https://github.com/anomalyco/opencode/releases/tag/v${OPENCODE_VERSION}
# Replace this with the actual hash from the releases page
ARG OPENCODE_SHA256_X64=REPLACE_WITH_ACTUAL_SHA256_FROM_GITHUB_RELEASES

# SHA256 hash of the linux-arm64 binary (for ARM hosts / Apple Silicon via --platform)
ARG OPENCODE_SHA256_ARM64=REPLACE_WITH_ACTUAL_SHA256_FROM_GITHUB_RELEASES
# ------------------------------------------

# Install minimal runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash -u 1001 opencodeuser

# Switch to non-root for download and verification
USER opencodeuser
WORKDIR /home/opencodeuser

# Detect architecture and download the appropriate binary
# sha256sum -c will exit non-zero and abort the build if the hash does not match
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        BINARY_NAME="opencode-linux-x64" && \
        EXPECTED_HASH="${OPENCODE_SHA256_X64}"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        BINARY_NAME="opencode-linux-arm64" && \
        EXPECTED_HASH="${OPENCODE_SHA256_ARM64}"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    DOWNLOAD_URL="https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/${BINARY_NAME}" && \
    echo "Downloading ${DOWNLOAD_URL}" && \
    curl -fsSL -o /home/opencodeuser/opencode "${DOWNLOAD_URL}" && \
    echo "Verifying SHA256..." && \
    echo "${EXPECTED_HASH}  /home/opencodeuser/opencode" | sha256sum -c - && \
    echo "SHA256 verification passed." && \
    chmod +x /home/opencodeuser/opencode

# Add binary to PATH
ENV PATH="/home/opencodeuser:${PATH}"

# Workspace for project files
RUN mkdir -p /home/opencodeuser/workspace
WORKDIR /home/opencodeuser/workspace

# Do not expose any ports — the HTTP server on 4096 is not needed for CLI use
# If you need the HTTP server, explicitly EXPOSE 4096 and bind to 127.0.0.1 only

ENTRYPOINT ["/home/opencodeuser/opencode"]
```

---

## How to Get the Correct SHA256 Hash

Every time you update the version pin, do this:

**Step 1** — Visit the releases page for your target version:
```
https://github.com/anomalyco/opencode/releases/tag/v1.2.17
```

**Step 2** — Find the asset named `opencode-linux-x64` (or `opencode-linux-arm64`).
The SHA256 is listed next to each asset.

**Step 3** — Alternatively, download and hash it yourself as an independent check:
```bash
curl -fsSL -o /tmp/opencode-linux-x64 \
  https://github.com/anomalyco/opencode/releases/download/v1.2.17/opencode-linux-x64

sha256sum /tmp/opencode-linux-x64
```
Compare the output against what GitHub shows. If they match, copy it into the ARG.

---

## Build Commands

Standard build (x86_64 host):
```bash
docker build \
  --build-arg OPENCODE_SHA256_X64=<hash-from-releases-page> \
  -t opencode-sandbox:1.2.17 .
```

For ARM64 (Apple Silicon, Graviton):
```bash
docker build \
  --platform linux/arm64 \
  --build-arg OPENCODE_SHA256_ARM64=<hash-from-releases-page> \
  -t opencode-sandbox:1.2.17-arm64 .
```

Tag with the version number, not `latest`, so you know exactly what is running:
```bash
docker tag opencode-sandbox:1.2.17 opencode-sandbox:latest
```

---

## What This Does NOT Protect Against

Even with SHA256 verification, the following risks remain:

1. **Compromised upstream release** — If an attacker gains write access to the
   `anomalyco/opencode` GitHub repository and publishes a malicious binary, the
   SHA256 you copied from the releases page would match the malicious binary.
   SHA256 proves integrity (no transit tampering), not authenticity (no proof of
   who built it).

2. **No Sigstore/SLSA attestation** — There is no cryptographic proof that the
   binary was built from the published source code by the official CI pipeline.
   The gap between source and binary is unaudited.

3. **Bun runtime inside the binary** — OpenCode compiles to a self-contained Bun
   executable. The Bun runtime is embedded in the binary. Vulnerabilities in Bun
   (such as CVE-2026-24910) affect this binary and cannot be patched separately.

4. **No code signing** — The Linux binary has no Authenticode or GPG signature.
   Contrast with, for example, the Homebrew formula, which does include SHA256
   checksums generated by the automated release pipeline.

---

## Upgrade Process

When upgrading OpenCode versions:
1. Visit the new release page and record the new SHA256 hashes
2. Update `OPENCODE_VERSION` and the hash ARGs
3. Rebuild the image with the new version tag
4. Test before promoting to production

Never auto-update opencode inside a running container or via `npm update` inside
the build. Always rebuild from a pinned version with a verified hash.

---

## References

- OpenCode GitHub Releases: https://github.com/anomalyco/opencode/releases
- OpenCode build pipeline: packages/opencode/script/publish.ts (sst/opencode repo)
- npm provenance / Sigstore: https://docs.npmjs.com/generating-provenance-statements
- SLSA framework: https://slsa.dev
- Binary downloader pattern risks: Palo Alto Networks Unit 42, Sept 2025 npm supply
  chain attack report
```
