# Host-Based Secrets Fetching

## Current State (Source of Truth)

The active host-based flow uses **in-memory environment variables only**.

- `fetch-secrets-host.ps1` fetches secrets on host
- Secrets are set via `Set-Item Env:` in the current process/session
- Docker receives only selected env vars at runtime
- Vault token remains on host
- No `opencode-secrets.env` file is created by this flow

## Security Model

**Your Vault token NEVER enters Docker containers.**

### Flow
1. Host authenticates to Vault (token/OIDC/etc.)
2. Host script fetches only configured secret keys
3. Host stores values in process memory (`env:`)
4. Launcher passes env vars to container runtime
5. Launcher clears secret env vars on exit

## Why This Matters

### Avoid (insecure)
```yaml
volumes:
  - ${HOME}/.vault-token:/home/user/.vault-token
```

### Current (secure)
- No host token mount
- No local secret file mount
- Least privilege: only configured API keys are passed

## Usage

### Dev mode
```powershell
.\start-opencode.ps1 -DevMode -WorkspacePath ".\my-project"
```

### Python launchers
```powershell
python .\opencode_run.py --workspace ".\my-project" --dev-mode
python .\claudecode_run.py --workspace ".\my-project" --dev-mode
```

## What Is Stored Where

| Resource | Location | Behavior |
|----------|----------|----------|
| Vault token | Host env / host vault login cache | Stays on host |
| Fetched API keys | Host process environment | Memory only |
| Secret mapping config | `config/*/secrets-config*.yaml` | Paths/placeholders only |

## Verification

Check that no local secret file is created:
```powershell
Remove-Item .\opencode-secrets.env -Force -ErrorAction SilentlyContinue
$before = Test-Path .\opencode-secrets.env
.\fetch-secrets-host.ps1 -DevMode
$after = Test-Path .\opencode-secrets.env
"before=$before after=$after"
```

Check in-memory env was set:
```powershell
[bool]$env:OPENAI_API_KEY
```

## Cleanup

Clear env vars after use:
```powershell
Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\VAULT_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\VAULT_ADDR -ErrorAction SilentlyContinue
```

## Note on Legacy Path

`fetch-secrets.py` still contains a legacy export path (`/tmp/opencode-secrets.env`) for container-side workflows.
The current host launchers do not rely on that local-file export behavior.
