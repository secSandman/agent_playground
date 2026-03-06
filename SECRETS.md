# Secrets Management Guide

## Overview

OpenCode Sandbox supports multiple secrets management approaches with least-privilege access:

- **Static API Keys**: Simple environment variables (development/testing)
- **HashiCorp Vault**: Enterprise-grade secrets management with multiple auth methods
- **AWS Secrets Manager**: AWS-native secrets storage
- **Kubernetes Auth**: For CI/CD and container-native deployments

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Host Launcher (PowerShell / Python)                      │
│ 1. Read secrets-config*.yaml (paths/placeholders only)   │
│ 2. Authenticate to secrets provider on host              │
│ 3. Fetch ONLY specified secrets                          │
│ 4. Set env vars in host process memory                   │
│ 5. Launch container with selected env vars               │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ OpenCode / ClaudeCode Container                          │
│ - Receives selected runtime env vars only                │
│ - Has NO direct access to host vault token               │
│ - Does not require local opencode-secrets.env            │
└──────────────────────────────────────────────────────────┘
```

## Key Security Features

1. **Least Privilege**: Agent only gets specified credentials, not full Vault access
2. **Separation of Concerns**: Secrets fetcher runs separately from agent
3. **Audit Trail**: All secret access is logged
4. **Temporary Credentials**: Secrets can be refreshed on a schedule
5. **No Credential Storage**: Secrets exist only in container memory

## Configuration Examples

### 1. Static API Keys (Simplest)

**secrets-config.yaml**:
```yaml
provider: static

static:
  openai_api_key: ${OPENAI_API_KEY}
  anthropic_api_key: ${ANTHROPIC_API_KEY}

security:
  strict_mode: true
  clear_on_exit: true
```

**Usage**:
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
.\start-opencode.ps1 -WorkspacePath "C:\code\myproject"
```

### 2. HashiCorp Vault with OIDC (Human Users)

**secrets-config.yaml**:
```yaml
provider: vault

vault:
  addr: https://vault.company.com:8200
  auth_method: oidc
  namespace: ""  # Leave empty for Vault OSS
  
  oidc:
    role: opencode-user
    mount_path: oidc
  
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

**Vault Setup**:
```bash
# Store secrets in Vault
vault kv put secret/opencode/openai api_key="sk-..."
vault kv put secret/opencode/anthropic api_key="sk-ant-..."

# Create policy for opencode-user role
vault policy write opencode-user - <<EOF
path "secret/data/opencode/*" {
  capabilities = ["read"]
}
EOF

# Configure OIDC role
vault write auth/oidc/role/opencode-user \
    bound_audiences="your-audience" \
    allowed_redirect_uris="http://localhost:8250/oidc/callback" \
    user_claim="email" \
    policies="opencode-user" \
    ttl=1h
```

**Usage**:
```bash
export VAULT_ADDR="https://vault.company.com:8200"
.\start-opencode.ps1 -WorkspacePath "C:\code\myproject"
# Browser will open for OIDC authentication
```

### 3. HashiCorp Vault with Kubernetes Auth (CI/CD)

**secrets-config.yaml**:
```yaml
provider: vault

vault:
  addr: https://vault.company.com:8200
  auth_method: kubernetes
  
  kubernetes:
    role: opencode-agent
    mount_path: kubernetes
    service_account_token_path: /var/run/secrets/kubernetes.io/serviceaccount/token
  
  secrets:
    - path: secret/data/ci/openai
      key: api_key
      env_var: OPENAI_API_KEY

security:
  strict_mode: true
```

**Vault Setup**:
```bash
# Enable Kubernetes auth
vault auth enable kubernetes

# Configure Kubernetes auth
vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443" \
    kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

# Create policy
vault policy write opencode-agent - <<EOF
path "secret/data/ci/*" {
  capabilities = ["read"]
}
EOF

# Create Kubernetes role
vault write auth/kubernetes/role/opencode-agent \
    bound_service_account_names=opencode-sa \
    bound_service_account_namespaces=default \
    policies=opencode-agent \
    ttl=1h
```

**Kubernetes Deployment**:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: opencode-sa
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opencode
spec:
  template:
    spec:
      serviceAccountName: opencode-sa
      containers:
      - name: opencode
        image: opencode-sandbox:1.2.17
        volumeMounts:
        - name: secrets-config
          mountPath: /config
      volumes:
      - name: secrets-config
        configMap:
          name: opencode-secrets-config
```

### 4. HashiCorp Vault with AppRole (Automation)

**secrets-config.yaml**:
```yaml
provider: vault

vault:
  addr: https://vault.company.com:8200
  auth_method: approle
  
  approle:
    role_id: ${VAULT_ROLE_ID}
    secret_id: ${VAULT_SECRET_ID}
    mount_path: approle
  
  secrets:
    - path: secret/data/automation/openai
      key: api_key
      env_var: OPENAI_API_KEY

security:
  strict_mode: true
```

**Vault Setup**:
```bash
# Enable AppRole
vault auth enable approle

# Create policy
vault policy write opencode-automation - <<EOF
path "secret/data/automation/*" {
  capabilities = ["read"]
}
EOF

# Create AppRole
vault write auth/approle/role/opencode-automation \
    policies="opencode-automation" \
    secret_id_ttl=24h \
    token_ttl=1h \
    token_max_ttl=4h

# Get role ID (store securely)
vault read auth/approle/role/opencode-automation/role-id

# Generate secret ID (use once, store securely)
vault write -f auth/approle/role/opencode-automation/secret-id
```

**Usage**:
```bash
export VAULT_ADDR="https://vault.company.com:8200"
export VAULT_ROLE_ID="your-role-id"
export VAULT_SECRET_ID="your-secret-id"
.\start-opencode.ps1 -WorkspacePath "C:\code\myproject"
```

### 5. AWS Secrets Manager

**secrets-config.yaml**:
```yaml
provider: aws-secrets-manager

aws_secrets_manager:
  region: us-east-1
  
  secrets:
    - secret_id: prod/opencode/openai-key
      key: api_key
      env_var: OPENAI_API_KEY
    
    - secret_id: prod/opencode/anthropic-key
      key: api_key
      env_var: ANTHROPIC_API_KEY

security:
  strict_mode: true
  refresh_interval: 3600  # Refresh every hour
```

**AWS Setup**:
```bash
# Create secrets
aws secretsmanager create-secret \
    --name prod/opencode/openai-key \
    --secret-string '{"api_key":"sk-..."}'

aws secretsmanager create-secret \
    --name prod/opencode/anthropic-key \
    --secret-string '{"api_key":"sk-ant-..."}'

# Create IAM policy
cat > opencode-secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:*:secret:prod/opencode/*"
      ]
    }
  ]
}
EOF

aws iam create-policy \
    --policy-name OpenCodeSecretsRead \
    --policy-document file://opencode-secrets-policy.json

# Attach to IAM role or user
aws iam attach-user-policy \
    --user-name opencode-user \
    --policy-arn arn:aws:iam::123456789012:policy/OpenCodeSecretsRead
```

**Usage**:
```bash
# Using AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
.\start-opencode.ps1 -WorkspacePath "C:\code\myproject"

# Or using IAM instance profile (EC2/ECS)
# No credentials needed, uses instance metadata
.\start-opencode.ps1 -WorkspacePath "C:\code\myproject"
```

## Testing Secrets Configuration

```bash
# Test secrets fetching without starting OpenCode
docker compose run --rm secrets-fetcher

# View fetched secrets (for debugging only!)
docker compose run --rm secrets-fetcher python3 -c "
import yaml
config = yaml.safe_load(open('/config/secrets-config.yaml'))
print(config)
"

# View audit log
docker exec opencode-secrets cat /var/log/opencode/secrets-audit.log
```

## Troubleshooting

### "Vault authentication failed"
1. Check VAULT_ADDR is correct
2. Verify token/OIDC/AppRole credentials
3. Check Vault policies allow reading secret paths
4. Review Vault audit log: `vault audit list`

### "AWS secret not found"
1. Verify AWS credentials: `aws sts get-caller-identity`
2. Check secret exists: `aws secretsmanager describe-secret --secret-id <id>`
3. Verify IAM permissions
4. Check region matches configuration

### "No secrets retrieved"
1. Verify secrets-config.yaml syntax: `python3 -c "import yaml; yaml.safe_load(open('secrets-config.yaml'))"`
2. Check environment variables are set for static provider
3. Review secrets-fetcher logs: `docker compose logs secrets-fetcher`
4. Ensure strict_mode is false for testing

### "Permission denied on secrets file"
1. Check volume permissions
2. Verify secrets-fetcher created the file
3. Check user IDs match (both should be 1001)

## Security Best Practices

1. **Never commit secrets-config.yaml with actual credentials**
   - Use environment variable placeholders
   - Add to .gitignore

2. **Use most restrictive secrets provider available**
   - Vault/AWS > Static keys
   - OIDC/Kubernetes > AppRole > Token

3. **Minimize secret scope**
   - Only request secrets you need
   - Use separate paths for dev/staging/prod
   - Enable strict_mode in production

4. **Enable audit logging**
   - Track all secret access
   - Review logs regularly
   - Alert on unusual patterns

5. **Rotate secrets regularly**
   - Use Vault dynamic secrets when possible
   - Implement automatic rotation
   - Set short TTLs

6. **Secure the secrets-config.yaml**
   - Restrict file permissions: `chmod 600 secrets-config.yaml`
   - Store in secure location
   - Encrypt at rest if possible

## CI/CD Integration

### GitHub Actions with Vault

```yaml
name: Run OpenCode
on: [push]

jobs:
  opencode:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Authenticate to Vault
        uses: hashicorp/vault-action@v2
        with:
          url: ${{ secrets.VAULT_ADDR }}
          method: jwt
          role: github-actions
          jwtGithubAudience: sigstore
          secrets: |
            secret/data/ci/openai api_key | OPENAI_API_KEY
      
      - name: Run OpenCode
        run: |
          echo "provider: static" > secrets-config.yaml
          echo "static:" >> secrets-config.yaml
          echo "  openai_api_key: \${OPENAI_API_KEY}" >> secrets-config.yaml
          ./start-opencode.sh ./workspace
```

### GitLab CI with Vault

```yaml
opencode:
  image: docker:latest
  services:
    - docker:dind
  variables:
    VAULT_ADDR: "https://vault.company.com:8200"
  script:
    - export VAULT_TOKEN=$(vault write -field=token auth/gitlab/login role=opencode jwt=$CI_JOB_JWT)
    - ./start-opencode.sh ./workspace
```

## Future Enhancements

- [ ] Azure Key Vault support
- [ ] Google Cloud Secret Manager support
- [ ] Vault dynamic secrets (short-lived credentials)
- [ ] Secret rotation without container restart
- [ ] Multi-secret provider support (fallback chain)
- [ ] Secret caching with encryption
- [ ] Integration with SPIFFE/SPIRE for workload identity
