# Host-Based Secrets Fetching

## ⚠️ Current-State Notes

Current primary launchers are `opencode_run.py` and `claudecode_run.py`.

- Dev mode: local Vault (`http://localhost:8200`, token `root`)
- Prod mode: `VAULT_TOKEN` must already exist in host environment
- Launchers fetch secrets on host, inject env vars into runtime, then clear process env

## Security Model

**Your Vault token NEVER enters Docker containers.**

### Flow:
1. **Host machine**: You authenticate to Vault (OIDC, token, etc.)
2. **Host machine**: `fetch-secrets-host.ps1` reads your token and fetches secrets
3. **Host machine**: Writes `opencode-secrets.env` to local filesystem
4. **Docker**: Only receives the actual API keys/secrets via env_file mount
5. **Docker**: Never has access to your Vault token

## Why This Matters

### OLD (Insecure) Approach:
```yaml
volumes:
  - ${HOME}/.vault-token:/home/user/.vault-token  # ❌ BAD
```
- Container has your personal Vault token
- Compromised code can read **ANY** secrets you have access to
- Token could be exfiltrated
- No least-privilege principle

### NEW (Secure) Approach:
```yaml
env_file:
  - ./opencode-secrets.env  # ✅ GOOD
```
- Container only gets specific API keys configured in `secrets-config.yaml`
- No Vault token exposure
- Least-privilege: only the secrets needed for OpenCode
- Token stays on your trusted host machine

## Usage

### Dev Mode (Local Testing):
```powershell
python opencode_run.py --workspace ".\my-project" --dev-mode
```
- Uses local Vault dev server (http://localhost:8200)
- Hardcoded token "root" for testing
- Fetches secrets on host, passes to Docker

### Production Mode (Real Vault):
```powershell
# Token auth (current launcher expectation)
$env:VAULT_TOKEN = "s.xxxxxx"
python opencode_run.py --workspace ".\my-project" --prod-mode
```

## What Gets Mounted:

| Resource | Location | Contains |
|----------|----------|----------|
| **Vault Token** | `~/.vault-token` | ✅ Stays on HOST |
| **Fetched Secrets** | `opencode-secrets.env` | ✅ Mounted to container |
| **Config** | `secrets-config.yaml` | ✅ Mounted read-only |

## Secrets File Format

`opencode-secrets.env` (created by host script):
```bash
OPENAI_API_KEY="sk-proj-xxxxx"
ANTHROPIC_API_KEY="sk-ant-xxxxx"
GITHUB_TOKEN="ghp_xxxxx"
```

This file is:
- Generated on your host
- In `.gitignore` (never committed)
- Mounted read-only into container
- Only contains the specific secrets configured

## Benefits

1. **Token Security**: Your Vault token never leaves your machine
2. **Least Privilege**: Container only gets specified secrets
3. **Audit Trail**: Vault logs show YOU fetched secrets, not a container
4. **No Exfiltration Risk**: Compromised container can't steal your token
5. **Separation of Concerns**: Auth on host, execution in container

## Verification

Check what's mounted:
```powershell
# Host secrets file (what Docker sees)
cat .\opencode-secrets.env

# Your Vault token (what Docker NEVER sees)
cat $env:USERPROFILE\.vault-token
```

Check container has no token access:
```powershell
docker exec opencode-sandbox sh -c "ls -la /home/opencodeuser/.vault-token 2>&1"
# Should show: No such file or directory ✅
```

## Cleanup

The secrets file is temporary:
```powershell
# Remove secrets after use
Remove-Item opencode-secrets.env -Force

# Or clean entire environment
docker compose down
Remove-Item opencode-secrets.env -Force
```

## For Production

Consider using **AppRole** instead of personal tokens:
```yaml
vault:
  addr: https://vault.company.com:8200
  auth_method: approle
  approle:
    role_id: "${VAULT_ROLE_ID}"     # Machine identity
    secret_id: "${VAULT_SECRET_ID}"  # Short-lived credential
```

Even with AppRole, the authentication happens on the **host**, so the credentials never enter containers.
