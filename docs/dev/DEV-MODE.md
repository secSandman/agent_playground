# Development Mode Testing Guide

## ⚠️ Current-State Notes

Use Python launchers as source of truth:

```powershell
python opencode_run.py --help
python claudecode_run.py --help
```

- Primary dev flow: `python opencode_run.py --workspace ".\test-workspace" --dev-mode ...`
- Claude flow: `python claudecode_run.py --workspace ".\test-workspace" --dev-mode --provider openai ...`
- Compose file in use: `.docker-compose/docker-compose.base.yml`
- Dev Vault: `http://localhost:8200` with token `root`
- Production mode currently expects `VAULT_TOKEN` already exported

Some examples below still reference legacy PowerShell wrappers.

## Overview

The Python launcher dev flow automatically:
1. Starts a local containerized Vault server (`vault-dev`)
2. Initializes test secrets
3. Fetches secrets from the local Vault
4. Launches OpenCode with those secrets

## Quick Start

### Dev Mode (Local Testing)

```powershell
python opencode_run.py --workspace "C:\path\to\your\project" --dev-mode
```

This uses:
- **Vault**: Local containerized Vault at `http://localhost:8200`
- **Token**: `root` (dev mode)
- **Secrets**: Test secrets from `init-secrets.sh`
  - OpenAI API: `sk-test-openai-key-12345`
  - Anthropic API: `sk-ant-test-key-67890`
  - GitHub Token: `ghp_test_token_abcdefghijklmnopqrstuvwxyz`
- **Config**: `config/dev/secrets-config.dev.yaml`

### Production Mode

```powershell
python opencode_run.py --workspace "C:\path\to\your\project" --prod-mode
```

This uses:
- **Vault**: Your production Vault server (configured in `secrets-config.yaml`)
- **Auth**: OIDC, Kubernetes, AppRole, or Token (per config)
- **Secrets**: Real secrets from your Vault paths
- **Config**: `config/prod/secrets-config.yaml`

### Legacy Mode (Bypass Secrets Management)

```powershell
$env:OPENAI_API_KEY = "sk-real-key"
$env:ANTHROPIC_API_KEY = "sk-ant-real-key"
python opencode_run.py --workspace "C:\path\to\your\project" --dev-mode
```

This bypasses secrets management entirely and passes keys directly.

## Configuration Files

### secrets-config.dev.yaml (Dev Mode)
```yaml
provider: vault
vault:
  addr: http://vault-dev:8200
  auth_method: token
  namespace: ""
  secrets:
    - path: secret/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
    - path: secret/opencode/anthropic
      key: api_key
      env_var: ANTHROPIC_API_KEY
```

### secrets-config.yaml (Production)
```yaml
provider: vault
vault:
  addr: https://vault.company.com:8200
  auth_method: oidc  # or kubernetes, approle, token
  namespace: "your-namespace"  # if using Vault Enterprise
  oidc:
    role: "opencode-role"
    mount_path: oidc
  secrets:
    - path: secret/data/prod/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
    - path: secret/data/prod/opencode/anthropic
      key: api_key
      env_var: ANTHROPIC_API_KEY
```

## Testing the Full Flow

### 1. Test Containerized Vault Integration
```powershell
.\test-vault-container.ps1
```

This verifies:
- Vault container starts and is healthy
- Test secrets are initialized
- Secrets fetcher can retrieve secrets
- Secrets are written to the shared volume

### 2. Test Dev Mode Startup
```powershell
# Manual test
python opencode_run.py --workspace ".\test-workspace" --dev-mode

# Once OpenCode starts, you can verify secrets were loaded:
# Inside the OpenCode container:
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
```

### 3. Access Vault UI (Dev Mode)
When running in dev mode, access the Vault UI at:
- **URL**: http://localhost:8200
- **Token**: `root`

You can browse/edit secrets in real-time.

## Differences Between Dev and Production

| Feature | Dev Mode | Production Mode |
|---------|----------|-----------------|
| Vault Location | Container (vault-dev) | External server |
| Vault Protocol | HTTP | HTTPS |
| Authentication | Token (`root`) | OIDC/K8s/AppRole |
| Secrets | Test data | Real credentials |
| TLS Verification | Disabled | Enabled |
| Namespace | None (Community) | Optional (Enterprise) |
| Persistence | In-memory (lost on restart) | Persistent storage |

## Troubleshooting

### Check if Vault is running
```powershell
docker ps | Select-String vault
```

### View Vault logs
```powershell
docker logs opencode-vault
```

### Manually fetch secrets
```powershell
docker compose run --rm `
    -v "${PWD}/secrets-config.dev.yaml:/config/secrets-config.yaml:ro" `
    -e VAULT_ADDR=http://vault-dev:8200 `
    -e VAULT_TOKEN=root `
    secrets-fetcher
```

### Check secrets in volume
```powershell
docker run --rm -v opencode-sandbox_secrets-data:/data alpine cat /data/opencode-secrets.env
```

### Reset everything
```powershell
docker compose down -v
# This removes all containers and volumes
```

## Next Steps

1. Test dev mode with fake secrets
2. Configure `secrets-config.yaml` for your production Vault
3. Set up OIDC/Kubernetes authentication in Vault
4. Create secret paths in Vault for OpenCode
5. Run in production mode with real secrets
