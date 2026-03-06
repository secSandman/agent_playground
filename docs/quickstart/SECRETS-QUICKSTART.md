# Secrets Management Quick Reference

## ⚠️ Current-State Notes

Use Python launchers (`opencode_run.py`, `claudecode_run.py`) rather than legacy `start-opencode.ps1` examples.

- Dev mode uses local Vault at `http://localhost:8200` with token `root`
- Prod mode expects `VAULT_TOKEN` already set in environment
- Compose file in use: `.docker-compose/docker-compose.base.yml`

## Choose Your Provider

| Provider | Best For | Auth Method | Complexity |
|----------|----------|-------------|------------|
| **Static** | Development, Testing | Environment variables | ⭐ Simple |
| **Vault (OIDC)** | Human developers | Browser SSO | ⭐⭐ Medium |
| **Vault (K8s)** | CI/CD, Production pods | Service account | ⭐⭐⭐ Advanced |
| **Vault (AppRole)** | Automation, Scripts | Role ID + Secret ID | ⭐⭐ Medium |
| **AWS Secrets** | AWS environments | IAM roles | ⭐⭐ Medium |

## Quick Start

### 1. Configure Provider

Edit `secrets-config.yaml`:

```yaml
provider: static  # or vault, aws-secrets-manager
```

### 2. Add Your Secrets

**Static:**
```yaml
static:
  openai_api_key: ${OPENAI_API_KEY}
  anthropic_api_key: ${ANTHROPIC_API_KEY}
```

**Vault:**
```yaml
vault:
  addr: https://vault.company.com:8200
  auth_method: oidc
  secrets:
    - path: secret/data/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
```

### 3. Run

```powershell
# Static
$env:OPENAI_API_KEY = "sk-..."
python opencode_run.py --workspace "C:\code" --dev-mode

# Vault
$env:VAULT_ADDR = "https://vault.company.com:8200"
$env:VAULT_TOKEN = "s.xxxxx"
python opencode_run.py --workspace "C:\code" --prod-mode

# AWS
$env:AWS_ACCESS_KEY_ID = "..."
python opencode_run.py --workspace "C:\code" --prod-mode
```

## Security Model

```
User/System → Authenticates → Secrets Provider
                               ↓
                    Fetches ONLY specified secrets
                               ↓
              Writes to temporary env file
                               ↓
                    OpenCode Container reads
                               ↓
              AGENT HAS NO DIRECT ACCESS TO VAULT
```

**Key Point**: The agent container cannot fetch additional secrets. It only receives what you explicitly configured.

## Common Tasks

### Add a New Secret

1. Store in provider (Vault/AWS)
2. Add to `secrets-config.yaml`:
   ```yaml
   secrets:
     - path: secret/data/opencode/github
       key: token
       env_var: GITHUB_TOKEN
   ```
3. Restart container

### Switch Providers

1. Change `provider` in `secrets-config.yaml`
2. Configure new provider section
3. No code changes needed

### Debug

```powershell
# Test secrets fetching
docker compose run --rm secrets-fetcher

# View logs
docker compose logs secrets-fetcher

# Check fetched secrets (debug only!)
docker exec opencode-sandbox env | grep API_KEY
```

### Rotate Secrets

1. Update in Vault/AWS
2. Restart container to refresh
3. For zero-downtime: use refresh_interval

## Vault Path Convention

Recommended structure:
```
secret/
  └── opencode/
      ├── dev/
      │   ├── openai      # Development API keys
      │   └── anthropic
      ├── staging/
      │   ├── openai
      │   └── anthropic
      └── prod/
          ├── openai      # Production API keys (restricted access)
          └── anthropic
```

Update config for environment:
```yaml
vault:
  secrets:
    - path: secret/data/opencode/prod/openai  # For production
      key: api_key
      env_var: OPENAI_API_KEY
```

## CI/CD Snippets

### GitHub Actions
```yaml
- name: Run OpenCode
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: ./start-opencode.sh ./workspace
```

### GitLab CI
```yaml
opencode:
  variables:
    VAULT_ADDR: $VAULT_ADDR
  script:
    - ./start-opencode.sh ./workspace
```

### Jenkins
```groovy
withCredentials([string(credentialsId: 'openai-key', variable: 'OPENAI_API_KEY')]) {
    sh './start-opencode.sh ./workspace'
}
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| "Vault authentication failed" | Check `VAULT_ADDR`, verify token/role |
| "No secrets retrieved" | Verify paths in config, check permissions |
| "AWS secret not found" | Check region, IAM permissions, secret ID |
| "Provider not supported" | Fix typo in `provider` field |
| "File not found" | Ensure `secrets-config.yaml` exists |

## Files

- `secrets-config.yaml` - Configuration (customize this)
- `fetch-secrets.py` - Fetcher script (don't modify)
- `secrets-fetcher/Dockerfile` - Fetcher container (don't modify)
- `SECRETS.md` - Full documentation

## Environment Variables

The secrets fetcher passes these through:

- `VAULT_ADDR`, `VAULT_NAMESPACE` - Vault server
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` - AWS credentials
- `VAULT_ROLE_ID`, `VAULT_SECRET_ID` - AppRole auth
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` - Static keys

## Next Steps

1. ✅ Configure `secrets-config.yaml` for your environment
2. ✅ Test with `docker compose run --rm secrets-fetcher`
3. ✅ Review [SECRETS.md](SECRETS.md) for detailed examples
4. ✅ Set up Vault/AWS if not using static keys
5. ✅ Enable audit logging for production
