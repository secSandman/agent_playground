![Screenshot](images/Screenshot%202026-03-06%20121756.png)

# OpenCode Secure Sandbox

## Current State 

This repository has been reorganized; some lower sections in this file are legacy.
Use this section + launcher `--help` output as source-of-truth.

### License & Attribution
- Licensed under `RICKY SANDERS ATTRIBUTION LICENSE` (see `LICENSE`).
- Original author acknowledgement required: `Ricky Sanders (secsandman@gmail.com)`.
- Redistribution/derivatives should retain `NOTICE` and visible attribution.

### Entry points
- `python opencode_run.py ...` (primary OpenCode launcher)
- `python claudecode_run.py ...` (primary ClaudeCode launcher)
- `python run.py ...` (compatibility wrapper to `opencode_run.py`)

### Compose and build paths
- Compose file: `.docker-compose/docker-compose.base.yml`
- OpenCode image: `build/opencode/Dockerfile`
- ClaudeCode image: `build/claudecode/Dockerfile`

### Provider behavior (`claudecode_run.py`)
- `--provider claude`: requires `ANTHROPIC_API_KEY`
- `--provider openai`: OpenCode backend compatibility mode using `OPENAI_API_KEY`
- `--provider auto`: Anthropic if available, otherwise OpenAI compatibility mode

### Isolation options (both launchers)
- `--isolated`: no host mount + no network
- `--isolated-fs`: no host mount + proxied network for inference
- `--explicit-path`: override workspace path explicitly

### AppArmor options (both launchers)
- `--apparmor unconfined`: current behavior (no AppArmor confinement)
- `--apparmor dev`: maps to profile `agent-dev`
- `--apparmor restricted`: maps to profile `agent-restricted`
- `--apparmor <profile-name>`: use a custom preloaded Linux AppArmor profile

Profile files in repo:
- `.docker-compose/apparmor/agent-dev.profile`
- `.docker-compose/apparmor/agent-restricted.profile`

Compose wiring (already configured):
- OpenCode service reads `OPENCODE_APPARMOR_PROFILE`
- ClaudeCode service reads `CLAUDECODE_APPARMOR_PROFILE`

Note: AppArmor profiles must be loaded on the Linux host running Docker Engine.

### Secret handling
- Secrets are fetched on host from Vault and injected as env vars at runtime.
- Secrets are cleared from host process env on exit.
- Dev mode uses Vault `http://localhost:8200` + token `root`.
- Prod mode expects `VAULT_TOKEN` already set in environment.

### Recommended quick start

```
python start_vault.py
python opencode_run.py --workspace ".\test-workspace" --dev-mode --no-rebuild --apparmor dev --prompt "hello"
python claudecode_run.py --workspace ".\test-workspace" --dev-mode --no-rebuild --provider openai --strict --apparmor restricted --prompt "hello"
```

Hardened "Sort-Of" Docker container for running OpenCode CLI with network policy enforcement and filesystem isolation.

# Run OpenCode on your project
chmod +x start-opencode.sh
./start-opencode.sh /path/to/your/project
```

## Features

- **Secrets Management**: In-Progress - Multiple providers (Static, HashiCorp Vault, AWS Secrets Manager)
- **Least Privilege Access**: In-Progress - Agent only gets specified credentials from Vault, not full vault access
- **Network Policy Enforcement**: Squid proxy with FQDN-based allowlist - Demonstrates out-of-band blocks of malicous tools/skills
- **Filesystem Isolation**: Container mounts local your workspace, for human IDE development only. True containerized workload preffered. 
- **API Access**: Pre-configured with example for OpenAI and Anthropic APIs. Use your own internal inference engines. 
- **Host Integration**: Edit files in VS Code on host, changes sync instantly
- **Security Hardened**: Non-root user, dropped capabilities, resource limits
- **Audit Logging**:  network traffic logged in squid

## Architecture - Modes 

```
Mode A: Local Path (default)

Host (VS Code) ─── edits ───► Host Workspace
               │ bind mount
               ▼
OpenCode/Claude Container ───► Squid Proxy ───► Allowed APIs
     ▲
   Python launcher
```

- Host files are mounted into container workspace
- Editor sees agent file changes immediately
- Network egress is proxied/allowlisted

```
Mode B: --isolated-fs

Host Workspace (not mounted) ✖

OpenCode/Claude Container (ephemeral fs) ───► Squid Proxy ───► Allowed APIs
        ▲
      Python launcher
```

- No host filesystem mount
- Runtime uses isolated ephemeral filesystem
- Network remains enabled through proxy for inference

```
Mode C: --isolated

Host Workspace (not mounted)      Network (disabled)
    ✖                               ✖

  OpenCode/Claude Container (fully isolated runtime)
          ▲
        Python launcher
```

- No host filesystem mount
- No network egress
- Highest isolation mode

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams and explanations.

## Network Proxy
## This demonstrate speperate network control plane for limitting network / remote tool / mcp / data access. Although inconconvient, it is the last line of defense from a advasarial agent trying to form command and control or data exfiltration. 
### In reality, in this squid use case, the developer or developer local system agent/copilot could modify or remove this security. It is meant to illustrate a concept, not be a production solution. 

### Network Access
- `localhost` / `127.0.0.1` (always)
- `10.0.0.0/8` private networks (always)
- `api.openai.com` and `*.openai.com`
- `api.anthropic.com` and `*.anthropic.com`
-  `github.com`, `npmjs.org`, `pypi.org` (package repos)
- Everything else (blocked by default)

### Filesystem Access
- Your workspace directory (mounted read-write, no execute)
- The agent is constrained to the container environment, not hacking, modifyfing critical workstation system integrate with active directory and other human user tools.
- `/tmp` inside container (ephemeral)
- Host filesystem outside workspace
- Container root filesystem (read-only)

## Configuration

### Using HashiCorp Vault Instead of Static Keys

1. Copy example config:
   ```bash
   cp secrets-config.example.yaml secrets-config.yaml
   ```

2. Edit `secrets-config.yaml`:
   ```yaml
   provider: vault
   vault:
     addr: https://vault.company.com:8200
     auth_method: oidc
   ```

3. Run as normal - browser will open for authentication

See [SECRETS-QUICKSTART.md](SECRETS-QUICKSTART.md) and [SECRETS.md](SECRETS.md) for details.

### Adding Allowed Domains

Edit `squid-proxy/squid.conf`:

```conf
# Add your internal services
acl allowed_domains dstdomain .mycompany.internal
acl allowed_domains dstdomain api.myservice.com
```

Rebuild proxy:
```bash
docker compose build squid-proxy
```

### Changing Resource Limits

Edit `docker-compose.yml`:

```yaml
opencode:
  mem_limit: 4g        # Increase memory
  cpus: 4              # More CPU cores
  pids_limit: 200      # More processes
```

## Monitoring

### View Network Traffic
```bash
docker compose logs -f squid-proxy
```

### View Detailed Access Log
```bash
docker exec opencode-squid tail -f /var/log/squid/access.log
```

### Check Container Health
```bash
docker compose ps
docker stats opencode-sandbox
```

## Files

```
├── Dockerfile                 # OpenCode container image
├── start-opencode.ps1        # Windows launcher
├── squid-proxy/
```
See [SECURITY.md](SECURITY.md) for complete security documentation.
- Network proxied and logged

# OpenCode Secure Sandbox - Project Overview
### OpenCode can't access API
A hardened development environment for running OpenCode and ClaudeCode AI assistants with Vault-based secrets management and network-enforced proxy isolation.
1. Check proxy is running: `docker compose ps squid-proxy`
## 📁 Project Structure
2. Verify API key: `echo $OPENAI_API_KEY`
```
opencode-sandbox/
├── cmd/                          # Executable entry points
│   ├── opencode/                 # OpenCode launcher
│   ├── claudecode/               # ClaudeCode launcher (coming soon)
│   └── vault/                    # Vault utilities
│
├── lib/                          # Reusable Python libraries
│   ├── vault_client.py           # Vault secret fetching
│   ├── docker_compose_manager.py # Docker Compose wrapper
│   └── config_loader.py          # Configuration parsing
│
├── config/                       # Configuration files (environment-specific)
│   ├── dev/                      # Development environment
│   │   └── secrets-config.dev.yaml
│   ├── test/                     # Test environment configs
│   ├── prod/                     # Production environment
│   │   └── secrets-config.yaml
│   └── templates/                # Config templates
│       └── secrets-config.example.yaml
│
├── build/                        # Build artifacts and Dockerfiles
│   ├── opencode/                 # OpenCode container
│   │   ├── Dockerfile            # Hardened image
│   │   └── opencode.jsonc        # OpenCode security config
│   ├── claudecode/               # ClaudeCode container (coming soon)
│   └── squid/                    # Squid proxy container
│       └── config/               # Proxy configuration
│
├── .docker-compose/              # Docker Compose files
│   └── docker-compose.base.yml   # Services: Vault, Squid, OpenCode
│
├── scripts/                      # Utility and automation scripts
│   ├── dev/                      # Development setup
│   ├── test/                     # Test automation
│   ├── build/                    # Build scripts
│   └── ci/                       # CI/CD integration
│
├── testing/                      # Test suites
│   ├── e2e/                      # End-to-end tests
│   ├── integration/              # Integration tests
│   └── unit/                     # Unit tests
│
├── docs/                         # Documentation
│   ├── architecture/             # Architecture & design
│   ├── dev/                      # Developer guides
│   ├── api/                      # API documentation
│   ├── operations/               # Operations & deployment
│   └── quickstart/               # Quick start guides
│
├── examples/                     # Example configurations
│   ├── opencode/                 # OpenCode examples
│   ├── claudecode/               # ClaudeCode examples
│   └── vault/                    # Vault secret examples
│
├── vault-dev/                    # Local Vault server setup
├── test-workspace/               # Test environment for prompts
│
├── opencode_run.py               # OpenCode launcher wrapper (root)
├── claudecode_run.py             # ClaudeCode launcher wrapper (root)
├── start_vault.py                # Vault starter wrapper (root)
├── requirements.txt              # Python dependencies
├── Makefile                      # Development commands
└── README.md                     # This file
```
3. Check logs: `docker compose logs squid-proxy`
## Quick Start
4. Ensure domain in `squid.conf` allowlist
### 1. Setup

```bash
# Install Python dependencies
python -m pip install --only-binary :all: -r requirements.txt
### File permission errors
# Or use the Makefile
make setup
```
1. Ensure workspace path exists and is accessible
### 2. Start Development Mode
2. Check file ownership on host
```bash
# Start Vault
make vault-start
# or
python start_vault.py
3. OpenCode runs as UID 1001 - files must be readable/writable
# Then run OpenCode
make opencode
# or
python opencode_run.py --workspace ./test-workspace --dev-mode

# Then run ClaudeCode
make claudecode
# or
python claudecode_run.py --workspace ./test-workspace --dev-mode
```

### 3. Run a Prompt
### Network connection issues
Once OpenCode starts, enter prompts like:
```
write a hello world program in rust
```
1. Verify proxy health: `docker inspect opencode-squid`
## 🔧 Development Commands
2. Check containers on same network: `docker network inspect opencode-network`
Use the Makefile for common tasks:
3. Test proxy: `docker exec opencode-sandbox curl -x http://squid-proxy:3128 https://api.openai.com`
```bash
make help              # Show all available commands
make setup             # Install dependencies
make dev-start         # Start dev environment (Vault + Squid)
make opencode          # Run OpenCode CLI
make claudecode        # Run ClaudeCode CLI
make vault-start       # Start Vault server
make vault-stop        # Stop Vault server
make down              # Stop all containers
make proxy-logs        # View proxy logs
make clean             # Clean up test artifacts
make test              # Run all tests
make test-unit         # Run unit tests only
make test-e2e          # Run end-to-end tests
```

### Run both agents at the same time
Use two terminals:

```powershell
python opencode_run.py --workspace .\test-workspace --dev-mode --no-rebuild
```

```powershell
python claudecode_run.py --workspace .\test-workspace --dev-mode --no-rebuild
```

## Advanced Usage

### Run without launcher scripts
```bash
# Start proxy
docker compose up -d squid-proxy

# Run OpenCode with your workspace
docker compose run --rm \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e WORKSPACE_PATH="/path/to/workspace" \
  opencode

# Cleanup
docker compose down
```

### Use with VS Code Remote Containers
See [ARCHITECTURE.md](ARCHITECTURE.md) for devcontainer.json configuration.

### Custom OpenCode arguments
```bash
# Pass args after workspace path
.\start-opencode.ps1 -WorkspacePath "C:\code" -AdditionalArgs "--debug --verbose"
```

## Building

```bash
# Build OpenCode image
docker build -t opencode-sandbox:1.2.17 .

# Build proxy image
docker compose build squid-proxy

# Build everything
docker compose build
```

## Updating

To update to a new OpenCode version:

1. Update `OPENCODE_VERSION` in Dockerfile
2. Get new SHA256 hash:
   ```powershell
   Invoke-WebRequest -Uri "https://github.com/anomalyco/opencode/releases/download/v1.2.18/opencode-linux-x64.tar.gz" -OutFile "test.tar.gz"
   Get-FileHash -Algorithm SHA256 test.tar.gz
   Remove-Item test.tar.gz
   ```
3. Update `OPENCODE_SHA256_X64` in Dockerfile
4. Rebuild: `docker build -t opencode-sandbox:1.2.18 .`
5. Update version in `docker-compose.yml` and launcher scripts

## License

See LICENSE file.

## Contributing

Pull requests welcome. Please ensure:
- All security features remain enabled
- Network policies are deny-by-default
- Changes are documented in relevant .md files
