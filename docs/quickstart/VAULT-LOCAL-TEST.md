# Quick Test with Vault Community Edition (Local)

## ⚠️ Current-State Notes

Use `python opencode_run.py` / `python claudecode_run.py` as the active launcher flow.

- Dev mode Vault: `http://localhost:8200` with token `root`
- Compose source-of-truth: `.docker-compose/docker-compose.base.yml`
- Production flow currently expects `VAULT_TOKEN` to be pre-set

Some lower examples still show legacy wrappers.

This guide covers two methods for testing with Vault locally:
1. **Containerized Vault (Recommended)** - Easiest setup using Docker Compose
2. **Host Vault Binary** - Manual setup using downloaded Vault executable

---

## Method 1: Containerized Vault (Recommended)

### Quick Start

The simplest way to test is using the included `vault-dev` container:

```powershell
# Build and start Vault container
docker compose up -d vault-dev

# Wait for Vault to be healthy
docker compose ps

# Initialize test secrets
docker exec opencode-vault /vault/scripts/init-secrets.sh

# Access Vault UI
# Browse to: http://localhost:8200
# Token: root
```

### What Gets Created

The initialization script creates:
- `secret/opencode/openai` - Test OpenAI API key
- `secret/opencode/anthropic` - Test Anthropic API key  
- `secret/opencode/github` - Test GitHub token
- `secret/opencode/database` - Test database credentials

### Configure secrets-config.yaml

```yaml
provider: vault

vault:
  # Container service name
  address: http://vault-dev:8200
  
  # Token authentication
  auth_method: token
  token: root
  
  # No namespace (Community Edition)
  namespace: ""
  skip_verify: false
  
  secrets:
    - path: secret/data/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
    
    - path: secret/data/opencode/anthropic
      key: api_key
      env_var: ANTHROPIC_API_KEY
```

### Run Full Test

```powershell
# Automated integration test
.\test-vault-container.ps1

# Or manually test the full stack
docker compose up
```

### Managing Secrets

```powershell
# Add new secret
docker exec opencode-vault vault kv put secret/opencode/myapi key="value"

# Read secret
docker exec opencode-vault vault kv get secret/opencode/openai

# List all secrets
docker exec opencode-vault vault kv list secret/opencode

# Delete secret
docker exec opencode-vault vault kv delete secret/opencode/myapi
```

---

## Method 2: Host Vault Binary

If you prefer to run Vault directly on your host machine:

### Setup Vault Dev Server

```powershell
# Start Vault in dev mode (not for production!)
vault server -dev

# In another terminal, note the root token and set environment
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "root"  # Dev server root token is always "root"
```

## Store Test Secrets

```powershell
# Store OpenAI API key
vault kv put secret/opencode/openai api_key="sk-test-openai-key"

# Store Anthropic API key
vault kv put secret/opencode/anthropic api_key="sk-ant-test-anthropic-key"

# Verify secrets were stored
vault kv get secret/opencode/openai
vault kv get secret/opencode/anthropic
```

## Configure secrets-config.yaml

For host-based Vault, use `host.docker.internal`:

```yaml
provider: vault

vault:
  # Access host from container
  address: http://host.docker.internal:8200
  
  # Use token auth with root token
  auth_method: token
  token: root
  
  # No namespace for Community Edition
  namespace: ""
  
  secrets:
    - path: secret/data/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
    
    - path: secret/data/opencode/anthropic
      key: api_key
      env_var: ANTHROPIC_API_KEY

security:
  strict_mode: true
  audit_log: true
  audit_log_path: /var/log/opencode/secrets-audit.log
```

## Test Secrets Fetcher

```powershell
# Set environment variables
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "root"

# Build the secrets fetcher
cd C:\Users\txsan\Desktop\open_code_project\opencode-sandbox
docker compose build secrets-fetcher

# Test fetching secrets (without starting OpenCode)
docker compose run --rm secrets-fetcher

# You should see:
# [INFO] Using Vault token authentication
# [INFO] Retrieved: OPENAI_API_KEY from secret/data/opencode/openai
# [INFO] Retrieved: ANTHROPIC_API_KEY from secret/data/opencode/anthropic
# [INFO] Secrets written to: /tmp/opencode-secrets.env
```

## Run OpenCode with Vault Secrets

```powershell
# Make sure Vault is running
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "root"

# Start OpenCode (it will fetch secrets automatically)
python opencode_run.py --workspace "C:\path\to\your\project" --dev-mode
```

## Docker Compose Adjustments for Local Vault

Legacy note: older setups used `docker-compose.yml` with a dedicated `secrets-fetcher` service. Current launcher flow does host-side secret fetch and uses `.docker-compose/docker-compose.base.yml`.

If you are maintaining a legacy setup, adjust `docker-compose.yml` as follows:

```yaml
services:
  secrets-fetcher:
    build:
      context: ./secrets-fetcher
    container_name: opencode-secrets
    network_mode: "host"  # Add this for local Vault access
    volumes:
      - ./secrets-config.yaml:/config/secrets-config.yaml:ro
      - secrets-data:/tmp
    environment:
      - SECRETS_CONFIG=/config/secrets-config.yaml
      - SECRETS_OUTPUT=/tmp/opencode-secrets.env
      - VAULT_ADDR=${VAULT_ADDR:-http://127.0.0.1:8200}
      - VAULT_TOKEN=${VAULT_TOKEN:-root}
```

Or use `extra_hosts` instead:

```yaml
services:
  secrets-fetcher:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

And update secrets-config.yaml:
```yaml
vault:
  addr: http://host.docker.internal:8200
```

## Troubleshooting Local Vault

### Connection Refused
```powershell
# Check Vault is running
vault status

# Test from Docker
docker run --rm curlimages/curl curl http://host.docker.internal:8200/v1/sys/health
```

### Certificate Errors (if using HTTPS)
For local dev with self-signed certs:
```yaml
vault:
  addr: https://127.0.0.1:8200
  
# In fetch-secrets.py, you might need to disable TLS verification (DEV ONLY!)
# Add environment variable:
environment:
  - VAULT_SKIP_VERIFY=true
```

### Secrets Not Found
```powershell
# Verify secret path (note: /data/ is auto-added for KV v2)
vault kv get secret/opencode/openai

# If using KV v1 (older Vault):
# Change path in secrets-config.yaml from:
#   path: secret/data/opencode/openai
# To:
#   path: secret/opencode/openai
```

## Minimal Test Configuration

**secrets-config.yaml** (absolute minimum):
```yaml
provider: vault
vault:
  addr: http://host.docker.internal:8200
  auth_method: token
  namespace: ""
  token:
    token: ${VAULT_TOKEN}
  secrets:
    - path: secret/data/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
security:
  strict_mode: false  # More forgiving for testing
```

**Environment**:
```powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "root"
```

## Production Notes

⚠️ **DO NOT use dev mode or root tokens in production!**

For production Vault Community Edition:
1. Use proper initialization with unseal keys
2. Create policies with minimum required permissions
3. Use AppRole or Kubernetes auth instead of tokens
4. Enable audit logging
5. Use TLS (HTTPS)

Example production policy:
```hcl
# opencode-policy.hcl
path "secret/data/opencode/*" {
  capabilities = ["read"]
}
```

Apply policy:
```powershell
vault policy write opencode-policy opencode-policy.hcl

# Create token with policy
vault token create -policy=opencode-policy -ttl=1h
```
