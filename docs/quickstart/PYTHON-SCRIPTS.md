# OpenCode Secure Sandbox - Python Cross-Platform Scripts

## ⚠️ Current State (Authoritative)

This doc contains older examples below. Current runtime truth:
- Use `opencode_run.py` and `claudecode_run.py` (not legacy `start-opencode.ps1` flow).
- Compose file is `.docker-compose/docker-compose.base.yml`.
- `claudecode_run.py --provider openai` uses OpenCode backend with `OPENAI_API_KEY`.
- `claudecode_run.py --provider claude` requires `ANTHROPIC_API_KEY`.

Quick checks:

```bash
python opencode_run.py --help
python claudecode_run.py --help
```

This directory contains cross-platform (Windows/macOS/Linux) Python scripts to replace the PowerShell scripts.

## Installation

### Prerequisites
- Python 3.7+
- Docker and Docker Compose
- Vault CLI (optional, for manual secret management)

### Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Make scripts executable (macOS/Linux):
```bash
chmod +x opencode_run.py claudecode_run.py start_vault.py
```

## Usage

### Quick Start (Development Mode)

**Step 1: Start Vault**
```bash
python start_vault.py
```

This starts a Vault dev server that runs in the background.

**Step 2: Add Your API Key (in another terminal)**
```bash
docker exec opencode-vault vault kv put secret/opencode/openai api_key="sk-proj-..."
```

**Step 3: Run OpenCode**
```bash
python opencode_run.py --workspace ./test-workspace --dev-mode --prompt "write hello world in python"
```

### Development Mode Examples

Interactive mode (prompt for input):
```bash
python opencode_run.py --workspace ./test-workspace --dev-mode
```

One-shot mode (pass prompt):
```bash
python opencode_run.py --workspace ./test-workspace --dev-mode --prompt "your question"
```

Skip rebuild (faster):
```bash
python opencode_run.py --workspace ./test-workspace --dev-mode --no-rebuild --prompt "analyze this code"
```

View Squid proxy logs:
```bash
python opencode_run.py --workspace ./test-workspace --dev-mode --view-logs --prompt "your question"
```

### Production Mode

```bash
python opencode_run.py --workspace ./code --prod-mode --prompt "your question"
```

Production mode uses:
- OIDC authentication (via VAULT_TOKEN env var)
- `secrets-config.yaml` for secret paths
- Full cleanup on exit

## Architecture

### opencode_run.py
Main orchestrator script. Handles:
- Workspace validation
- Docker Compose orchestration
- Vault secret fetching on host machine
- Environment variable injection
- Container cleanup

### start_vault.py
Starts a Vault dev server for testing. Handles:
- Docker container startup
- Health checking
- Configuration hints

### vault_client.py
Vault interaction module using `hvac` SDK. Handles:
- Vault connection and authentication
- Secret fetching (with proper error handling)
- Secret writing (for setup)

### docker_compose_manager.py
Docker Compose wrapper. Handles:
- Container building
- Starting/stopping services
- Health checks
- Command execution

## Security Features

✅ **Vault Token Security**
- Token stays on host machine (never exposed to container)
- Secrets fetched before container startup
- Immediate cleanup on exit

✅ **Environment Variable Isolation**
- Secrets passed as environment variables only
- No secret files written to disk
- Automatic cleanup in finally block

✅ **Non-root Container**
- OpenCode runs as `opencodeuser` (UID 1001)
- Hardened `.npmrc` prevents script execution
- Hardened `opencode.json` restricts permissions

✅ **Network Policy**
- Squid proxy enforces allowlist-based network access
- Only approved domains can be reached

## Troubleshooting

### "Vault is not running"
Make sure to run `python start_vault.py` first in another terminal.

### "Failed to connect to Vault"
Check that Vault is running: `docker ps | grep vault`

### "Secret not found (optional)"
This is expected if you haven't added the secret yet. Add it with:
```bash
docker exec opencode-vault vault kv put secret/opencode/openai api_key="your-key"
```

### Port Already in Use
If ports 8200 (Vault) or 3128 (Squid) are in use:
```bash
# Stop all containers
docker compose down

# Check what's using the port (macOS/Linux)
lsof -i :8200
```

## Configuration Files

### secrets-config.dev.yaml
Development secrets configuration (used with `--dev-mode`)

### secrets-config.yaml
Production secrets configuration (used with `--prod-mode`)

### .docker-compose/docker-compose.base.yml
Container definitions for Vault, Squid, OpenCode, etc.

## Comparison with PowerShell Scripts

| Feature | PowerShell | Python |
|---------|-----------|--------|
| Cross-platform | ❌ (Windows/WSL only) | ✅ (Windows/macOS/Linux) |
| Dependencies | PowerShell 5+ | Python 3.7+, hvac, docker |
| Installation | Built-in | `pip install -r requirements.txt` |
| Error handling | Basic | Comprehensive with colorized output |
| Docker SDK | subprocess | docker-py + hvac |
| Maintenance | Windows-centric | Universal |

## Next Steps

After testing locally with `--dev-mode`, you can:

1. **Set up production Vault** with OIDC authentication
2. **Configure secrets-config.yaml** with production secret paths
3. **Run with `--prod-mode`** to use real authentication
4. **Deploy to CI/CD** (GitHub Actions, GitLab CI, etc.)

## Contributing

These scripts are fully cross-platform. When adding features:
- Use `pathlib.Path` instead of string path concatenation
- Use `subprocess` for external commands
- Test on Windows, macOS, and Linux
- Use `colorama` for output (cross-platform colors)
