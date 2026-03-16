# Security Architecture Summary
## OpenCode / Claude Code Secure Sandbox
March 2026

---

## 1. What Problem This Solves

AI coding agents (OpenCode, Claude Code) run with developer-level access:
they read files, execute shell commands, make outbound API calls, and can be
influenced by the content they process (prompt injection, CLAUDE.md hijack,
malicious MCP tools). When something goes sideways — a rogue tool call, an
injected instruction, a compromised dependency — the blast radius without
controls is everything the developer's shell session can reach.

This repo prototypes a **layered security architecture** that places controls
at each level of that stack: secrets, network, container runtime, OS, and
agent policy — so that no single failure propagates to full host compromise.

---

## 2. Defense-in-Depth Layer Map

```
┌──────────────────────────────────────────────────────────────────┐
│ LAYER 1 — SECRETS FETCHING                                       │
│  Host authenticates to Vault. Secrets injected as env vars.     │
│  Vault token never enters Docker. No secret files on disk.      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│ LAYER 2 — NETWORK EGRESS CONTROL                                 │
│  Squid proxy enforces FQDN allowlist. All traffic logged.        │
│  Isolated mode: network disabled entirely.                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│ LAYER 3 — CONTAINER ISOLATION                                    │
│  Three modes: Local Path / Isolated-FS / Fully Isolated.         │
│  Docker network, no host network namespace.                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│ LAYER 4 — CONTAINER HARDENING                                    │
│  Non-root user (UID 1001). All capabilities dropped.             │
│  Resource limits. no-new-privileges. AppArmor profiles.          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│ LAYER 5 — AGENT-LEVEL HARDENING                                  │
│  --strict flag. Denied command/file patterns. Tool restrictions. │
│  Provider selection. Prompt logging.                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1 — Secrets Fetching Architecture

**Goal:** Agent containers never hold Vault tokens, cloud IAM credentials, or
full secrets configuration. Only the specific API keys the agent needs for its
session are passed in, and only in memory.

### Flow

```
Host Machine
┌────────────────────────────────────────────────────┐
│  1. fetch-secrets-host.ps1 (or fetch-secrets.py)   │
│     - Reads secrets-config*.yaml (paths only)       │
│     - Authenticates to Vault / AWS / static env     │
│     - Fetches only configured secret keys           │
│     - Sets values via Set-Item Env: (memory only)   │
│     - Vault token STAYS on host                     │
│                                                      │
│  2. Python launcher (opencode_run.py)               │
│     - Reads env vars from host process              │
│     - Passes ONLY API keys to container at launch   │
│     - Clears host env vars on exit                  │
└────────────────────────┬───────────────────────────┘
                         │ --env OPENAI_API_KEY=...
                         ▼
              OpenCode / ClaudeCode Container
              (receives selected env vars only)
```

### Supported Providers

| Provider | Auth Method | When to Use |
|---|---|---|
| Static env vars | `$env:OPENAI_API_KEY` | Dev / quick testing |
| HashiCorp Vault (dev) | Token `root`, `http://localhost:8200` | Local dev mode |
| HashiCorp Vault (prod) | OIDC / AppRole / K8s SA | Production |
| AWS Secrets Manager | AWS credential chain | AWS-hosted deployments |

### What Is Never Mounted Into Docker

| Item | Location | Behavior |
|---|---|---|
| Vault token | Host env / host vault login cache | Stays on host |
| AWS IAM credentials | Host credential chain | Stays on host |
| Fetched API keys | Host process `env:` | Memory only, cleared on exit |
| secrets-config.yaml | `config/*/secrets-config*.yaml` | Paths/placeholders only |

**Verification:**
```powershell
# Confirm no secret file is written to disk
$before = Test-Path .\opencode-secrets.env
.\fetch-secrets-host.ps1 -DevMode
$after = Test-Path .\opencode-secrets.env
"before=$before after=$after"   # Expected: before=False after=False

# Confirm in-memory injection worked
[bool]$env:OPENAI_API_KEY       # Expected: True
```

---

## 4. Layer 2 — Network Egress Control

**Goal:** Prevent agent-initiated outbound connections to untrusted hosts,
reduce C2 callback risk, block untrusted package fetches, and log all traffic
for post-session review.

### Architecture

```
Agent Container
     │
     │ HTTP_PROXY=http://squid-proxy:3128
     ▼
┌──────────────────────────────────┐
│  Squid Proxy (opencode-squid)    │
│  - FQDN-based allowlist          │
│  - Logs all access to            │
│    /var/log/squid/access.log     │
│  - Denies everything not listed  │
└────────────────┬─────────────────┘
                 │ allowed only
                 ▼
    api.openai.com
    api.anthropic.com
    10.x.x.x (internal networks)
    [other explicitly listed FQDNs]
```

All outbound HTTP/HTTPS from the agent container routes through Squid.
`HTTP_PROXY` and `HTTPS_PROXY` are injected as container environment
variables at launch time; no agent-side configuration is required.

### Viewing Traffic

```bash
# Live stream
docker compose logs -f squid-proxy

# Detailed access log
docker exec opencode-squid tail -f /var/log/squid/access.log
```

### Adding Allowed Domains

Edit `squid-proxy/squid.conf`:
```conf
acl allowed_domains dstdomain .example.com
acl allowed_domains dstdomain api.myservice.io
```

---

## 5. Layer 3 — Container Isolation Modes

**Goal:** Provide tiered isolation options matching the task's risk profile.
Higher isolation reduces attack surface and host exposure; lower isolation
enables live host-editor integration.

### Mode Comparison

```
MODE A — Local Path (default)
─────────────────────────────
Host Workspace ──(bind mount rw)──► Agent Container ──► Squid Proxy ──► APIs
Lowest isolation. Host files live-synced. Best for normal dev workflows.

MODE B — Isolated Filesystem (--isolated-fs)
─────────────────────────────────────────────
Host Workspace ──✖ (not mounted)
                   Agent Container (ephemeral fs) ──► Squid Proxy ──► APIs
No host file access. Network via proxy. Use for untrusted repo exploration
or when host file exposure is unacceptable.

MODE C — Fully Isolated (--isolated)
──────────────────────────────────────
Host Workspace ──✖    Network ──✖
                   Agent Container (ephemeral fs, no egress)
Maximum isolation. No host mount, no outbound network. Use for strict
offline analysis, untrusted code review, or air-gapped evaluation.
```

### Launch Commands

```powershell
# Mode A — live host workspace
python opencode_run.py --workspace "C:\code\myproject" --dev-mode

# Mode B — isolated filesystem, proxy network
python opencode_run.py --workspace "C:\code\myproject" --dev-mode --isolated-fs

# Mode C — fully isolated
python opencode_run.py --workspace "C:\code\myproject" --dev-mode --isolated

# ClaudeCode with explicit provider and strict mode
python claudecode_run.py --workspace "C:\code\myproject" --dev-mode --provider openai --strict
```

---

## 6. Layer 4 — Container Hardening

**Goal:** Ensure that even if an agent is compromised inside the container,
it cannot escalate privileges, escape to the host, or exhaust host resources.

### Runtime Security Configuration (docker-compose.base.yml)

```yaml
user: "1001:1001"                          # Non-root; no password login
security_opt:
  - no-new-privileges:true                 # Block setuid/privilege escalation
  - apparmor=${APPARMOR_PROFILE:-unconfined}  # Kernel MAC enforcement
cap_drop:
  - ALL                                    # Drop every Linux capability
mem_limit: 2g                              # Memory DoS cap
cpus: 2                                    # CPU DoS cap
pids_limit: 100                            # Fork bomb prevention
```

### Hardening Checklist

| Control | Mechanism | Status |
|---|---|---|
| Non-root runtime user | UID 1001, locked account, no sudo | ✓ |
| No privilege escalation | `--security-opt=no-new-privileges:true` | ✓ |
| All Linux caps dropped | `--cap-drop=ALL` | ✓ |
| Memory limit | `mem_limit: 2g` | ✓ |
| CPU limit | `cpus: 2` | ✓ |
| PID limit | `pids_limit: 100` | ✓ |
| No privileged mode | not set in compose | ✓ |
| FQDN-filtered egress | Squid proxy allowlist | ✓ |
| API keys in env only | host-side fetch, cleared on exit | ✓ |
| No host network namespace | bridge network only | ✓ |
| Setuid/setgid binaries removed | stripped during image build | ✓ |
| AppArmor MAC | profile selectable at launch | ✓ |

### AppArmor Profiles

Two profiles ship in `.docker-compose/apparmor/`:

**`agent-dev` profile** — development use, less restrictive:
- Allows `file`, `capability`, full inet TCP/UDP
- Denies `mount`, `pivot_root`, `/sys/**`, `/proc/sys/**`, `/proc/*/mem`
- Denies `/root/**`, `/etc/shadow`, `/etc/sudoers`
- Suitable for trusted local dev sessions needing broad file access

**`agent-restricted` profile** — tighter, closer to production:
- Adds: deny raw/packet network sockets
- Adds: deny execute from `/tmp`, `/var/tmp`, `/dev/shm` (no drop-and-run)
- Adds: deny execute from workspace (`/home/**/workspace/** x`)
- Adds: deny `curl`, `wget`, `nc`, `ncat` execution
- Suitable for running against untrusted repositories or third-party code

**Selecting a profile at launch:**

```powershell
# Development profile
python opencode_run.py --workspace ".\project" --dev-mode --apparmor dev

# Restricted profile
python claudecode_run.py --workspace ".\project" --dev-mode --apparmor restricted

# No profile (default, Windows/unloaded Linux)
python opencode_run.py --workspace ".\project" --dev-mode --apparmor unconfined
```

> **Note:** AppArmor profiles must be loaded on the Linux host running Docker Engine.
> On Windows (Docker Desktop), profiles are passed but not enforced; use `--isolated`
> or `--isolated-fs` modes for isolation on Windows hosts.

---

## 7. Layer 5 — Agent-Level Hardening & Best Practices

**Goal:** Reduce what the agent is willing to do even before any container
control has a chance to act. Defense at the agent policy layer means fewer
dangerous actions are attempted, not just blocked.

### `--strict` Flag (claudecode_run.py)

Enables conservative agent behavior:
- Restricts tool access scope
- Reduces autonomous file modification without confirmation
- Reduces shell command execution surface

### Provider Selection

```powershell
# Use Claude API (ANTHROPIC_API_KEY required)
python claudecode_run.py --provider claude ...

# Use OpenAI compatibility mode (OPENAI_API_KEY; Claude Code via OpenAI bridge)
python claudecode_run.py --provider openai ...

# Auto-detect: Anthropic if key present, otherwise OpenAI
python claudecode_run.py --provider auto ...
```

Choosing a provider that does not have a key set prevents accidental
credential exposure when the wrong key is in the environment.

### CLAUDE.md Awareness

`CLAUDE.md` files in project roots are treated as high-trust operator
instructions by Claude Code. They are read automatically and given elevated
weight in the agent's reasoning context.

**Risk:** An attacker who can write to `CLAUDE.md` (via PR, malicious submodule,
or compromised dependency) can inject persistent instructions into every
Claude Code session that opens the project.

**Best practices:**
- Review `CLAUDE.md` changes in PRs with the same scrutiny as shell scripts
- Use `--isolated-fs` or `--isolated` when opening untrusted repositories
- Never add `CLAUDE.md` to `.gitignore`; it must be version-controlled and
  auditable

### MCP Server Hygiene

When using MCP extensions with Claude Code:
- Load only servers you have manually inspected
- Never load an untrusted server alongside a server that handles sensitive
  data (email, calendar, source control tokens)
- Be aware that cross-server tool shadowing means one loaded server can
  override another's behavior without user notification
- Pin MCP server versions; tool descriptions can change post-approval (rug pull)

### Recommended Command Patterns

```powershell
# Standard dev session — dev vault, dev AppArmor, skip rebuild
python opencode_run.py --workspace ".\test-workspace" --dev-mode --no-rebuild --apparmor dev --prompt "hello"

# Stricter session — restricted AppArmor, isolated filesystem
python claudecode_run.py --workspace ".\test-workspace" --dev-mode --no-rebuild --provider openai --strict --apparmor restricted --isolated-fs --prompt "review this code"

# Maximum isolation — no network, no host mount
python opencode_run.py --workspace ".\test-workspace" --dev-mode --isolated --prompt "analyze for vulnerabilities"
```

---

## 8. Isolation Mode × Hardening Matrix

| | Local Path | `--isolated-fs` | `--isolated` |
|---|:---:|:---:|:---:|
| Host workspace mounted | ✓ | ✗ | ✗ |
| Network (via proxy) | ✓ | ✓ | ✗ |
| Squid egress filter | ✓ | ✓ | N/A |
| Non-root user | ✓ | ✓ | ✓ |
| `cap_drop: ALL` | ✓ | ✓ | ✓ |
| Resource limits | ✓ | ✓ | ✓ |
| `no-new-privileges` | ✓ | ✓ | ✓ |
| AppArmor (Linux) | selectable | selectable | selectable |
| Risk profile | dev / trusted | untrusted repos | offline / air-gap |

---

## 9. Known Gaps and Production Considerations

This is a **prototype**. The following gaps are acknowledged:

- **AppArmor not enforced on Windows** — Docker Desktop does not load Linux
  AppArmor profiles. On Windows hosts, use `--isolated` or `--isolated-fs`
  as the primary containment strategy.

- **Squid is app-layer only** — Squid filters at the HTTP/HTTPS layer. A
  compromised agent can attempt raw TCP, UDP, or DNS exfiltration outside
  the proxy. Kernel-level egress enforcement (iptables, eBPF, or a dedicated
  network policy engine) is required for stronger production guarantees.

- **CLAUDE.md is a persistent injection surface** — No runtime control
  prevents a malicious CLAUDE.md from influencing agent behavior. Review
  is the only current mitigation.

- **MCP rug pulls are undetected** — Tool descriptions can change post-approval
  with no client-side diff or alert. Pin server versions and restrict loaded
  servers to a verified minimal set.

- **Node.js v18 EOL** — If running Claude Code on Node.js 18, all January
  2026 Node.js CVEs (CVE-2025-55131, -55130, -59465 et al.) are permanently
  unpatched. Upgrade to 22.x or 24.x.

For stronger production controls, see:
- **[NONO](https://github.com/always-further/nono)** — deny-first command-control patterns
- **[Veto](https://ona.com/stories/introducing-veto-security-for-the-next-era-of-software)** — hash-based kernel-layer execution enforcement
- **[NVIDIA AI Red Team sandboxing guidance](https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/)**

---

## 10. File Reference Map

| File / Path | Purpose |
|---|---|
| `opencode_run.py` | Primary OpenCode launcher (all modes) |
| `claudecode_run.py` | Primary ClaudeCode launcher (all modes, provider select) |
| `run.py` | Compatibility wrapper → `opencode_run.py` |
| `fetch-secrets-host.ps1` | Host-side Vault fetch → in-memory env injection |
| `fetch-secrets.py` | Python equivalent of host secrets fetch |
| `start_vault.py` | Start local dev Vault container |
| `.docker-compose/docker-compose.base.yml` | Compose source of truth (all services) |
| `.docker-compose/apparmor/agent-dev.profile` | AppArmor dev profile |
| `.docker-compose/apparmor/agent-restricted.profile` | AppArmor restricted profile |
| `build/opencode/Dockerfile` | OpenCode container image |
| `build/claudecode/Dockerfile` | ClaudeCode container image |
| `config/dev/secrets-config.dev.yaml` | Dev secrets config (paths only) |
| `config/prod/secrets-config.yaml` | Prod secrets config (paths only) |
| `docs/architecture/ARCHITECTURE.md` | Runtime mode diagrams and usage |
| `docs/architecture/SECURITY.md` | Container hardening reference |
| `HOST-BASED-SECRETS.md` | Host secrets fetch flow (source of truth) |
| `SECRETS.md` | Full secrets management guide (all providers) |
| `VAULT-LOCAL-TEST.md` | Local Vault dev testing guide |
| `ai_research/opencode_stack_vulnerabilities.txt` | OpenCode runtime CVE research |
| `ai_research/claudecode_stack_vulnerabilities.txt` | Claude Code runtime CVE research |
