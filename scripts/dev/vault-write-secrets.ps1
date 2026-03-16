# vault-write-secrets.ps1
# ─────────────────────────────────────────────────────────────────────────────
# One-time CLI commands to write static KV v2 secrets to the HCP Vault cluster.
# Run this once per secret rotation. Requires vault CLI in PATH (or set $vaultExe).
#
# Prerequisites:
#   - vault CLI installed (https://developer.hashicorp.com/vault/install)
#   - Azure Entra account with access to the Vault OIDC role "entra"
#   - Your API keys ready in env vars or ready to paste
#
# Usage:
#   $env:OPENAI_API_KEY     = "sk-..."
#   $env:ANTHROPIC_API_KEY  = "sk-ant-..."
#   .\scripts\dev\vault-write-secrets.ps1
# ─────────────────────────────────────────────────────────────────────────────

$VaultExe       = "C:\Users\txsan\Downloads\vault_1.20.0_windows_amd64\vault.exe"
$VaultAddr      = "https://vault-cluster-public-vault-6bdb9cb5.d4c0296b.z1.hashicorp.cloud:8200"
$VaultNamespace = "admin/secsandman"
$KvMount        = "Secrets/kv"

# ── 1. Point vault CLI at the cluster ────────────────────────────────────────
$env:VAULT_ADDR      = $VaultAddr
$env:VAULT_NAMESPACE = $VaultNamespace
Write-Host "[+] VAULT_ADDR      = $env:VAULT_ADDR" -ForegroundColor Cyan
Write-Host "[+] VAULT_NAMESPACE = $env:VAULT_NAMESPACE" -ForegroundColor Cyan

# ── 2. OIDC login via Entra ID (opens browser) ───────────────────────────────
Write-Host "`n[*] Logging in via OIDC (Entra ID)..." -ForegroundColor Yellow
$loginJson = & $VaultExe login -method=oidc -path=oidc role=entra -no-store -format=json
if ($LASTEXITCODE -ne 0 -or -not $loginJson) {
    Write-Error "Vault OIDC login failed. Aborting."
    exit 1
}

try {
    $loginObj = $loginJson | ConvertFrom-Json
    $env:VAULT_TOKEN = $loginObj.auth.client_token
    if (-not $env:VAULT_TOKEN) {
        throw "Missing auth.client_token"
    }
} catch {
    Write-Error "Vault OIDC login succeeded but token parsing failed: $($_.Exception.Message)"
    exit 1
}

Write-Host "[OK] Login successful.`n" -ForegroundColor Green

# ── 3. Write secrets (KV v2) ─────────────────────────────────────────────────
# vault kv put -mount=<mount> <path> <key>=<value>
# KV v2 mount: Secrets/kv
# Secret paths: opencode/openai, opencode/anthropic

Write-Host "[*] Writing OpenAI API key..." -ForegroundColor Yellow
& $VaultExe kv put -mount="$KvMount" opencode/openai `
    api_key="$env:OPENAI_API_KEY"
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to write opencode/openai"; exit 1 }
Write-Host "[OK] opencode/openai written.`n" -ForegroundColor Green

Write-Host "[*] Writing Anthropic API key..." -ForegroundColor Yellow
& $VaultExe kv put -mount="$KvMount" opencode/anthropic `
    api_key="$env:ANTHROPIC_API_KEY"
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to write opencode/anthropic"; exit 1 }
Write-Host "[OK] opencode/anthropic written.`n" -ForegroundColor Green

# ── Optional: GitHub token ────────────────────────────────────────────────────
# & $VaultExe kv put -mount="$KvMount" opencode/github `
#     token="$env:GITHUB_TOKEN"

# ── 4. Verify reads ───────────────────────────────────────────────────────────
Write-Host "[*] Verifying secrets (metadata only)..." -ForegroundColor Yellow
& $VaultExe kv get -mount="$KvMount" opencode/openai
& $VaultExe kv get -mount="$KvMount" opencode/anthropic

Write-Host "`n[DONE] All secrets written to $KvMount in namespace $VaultNamespace" -ForegroundColor Green
