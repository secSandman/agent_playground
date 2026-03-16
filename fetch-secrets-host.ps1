#!/usr/bin/env pwsh
#
# Fetch secrets on HOST (not in container)
# This keeps your Vault token on your machine only
#

param(
    [switch]$DevMode = $false
)

$ErrorActionPreference = "Stop"

if (-not $env:HOME) {
    $env:HOME = $env:USERPROFILE
}

Write-Host "Fetching secrets from Vault..." -ForegroundColor Cyan

# Vault CLI path
$vaultExe = "C:\Users\txsan\Downloads\vault_1.20.0_windows_amd64\vault.exe"

# Determine config file and Vault settings
# ── Vault connection constants ────────────────────────────────────────────────
$VAULT_PROD_ADDR      = "https://vault-cluster-public-vault-6bdb9cb5.d4c0296b.z1.hashicorp.cloud:8200"
$VAULT_PROD_NAMESPACE = "admin/secsandman"
$VAULT_OIDC_ROLE      = "entra"
$VAULT_OIDC_MOUNT     = "oidc"
$VAULT_KV_MOUNT       = "kv"
# ──────────────────────────────────────────────────────────────────────────────

if ($DevMode) {
    $env:VAULT_ADDR  = "http://localhost:8200"
    $env:VAULT_TOKEN = "root"
    Remove-Item Env:\VAULT_NAMESPACE -ErrorAction SilentlyContinue
    Write-Host "Mode: Development" -ForegroundColor Gray
    Write-Host "Vault Address: $env:VAULT_ADDR" -ForegroundColor Gray
    Write-Host "Auth Method: token (hardcoded 'root')" -ForegroundColor Gray

    # Dev mode: local vault paths (KV v1 engine named 'secret')
    $secrets = @(
        @{ path = "secret/opencode/openai";     key = "api_key"; env = "OPENAI_API_KEY" },
        @{ path = "secret/opencode/anthropic";  key = "api_key"; env = "ANTHROPIC_API_KEY" },
        @{ path = "secret/opencode/github";     key = "token";   env = "GITHUB_TOKEN" }
    )
} else {
    # Production: HCP Vault Dedicated, OIDC via Entra ID
    $env:VAULT_ADDR      = $VAULT_PROD_ADDR
    $env:VAULT_NAMESPACE = $VAULT_PROD_NAMESPACE
    Write-Host "Mode: Production" -ForegroundColor Gray
    Write-Host "Vault Address:   $env:VAULT_ADDR" -ForegroundColor Gray
    Write-Host "Namespace:       $env:VAULT_NAMESPACE" -ForegroundColor Gray
    Write-Host "Auth Method:     OIDC (role=$VAULT_OIDC_ROLE, mount=$VAULT_OIDC_MOUNT)" -ForegroundColor Gray

    # OIDC login — opens browser for Entra ID authentication
    Write-Host "`nOpening browser for Entra ID login..." -ForegroundColor Cyan
    $loginJson = & $vaultExe login `
        -method=oidc `
        -path=$VAULT_OIDC_MOUNT `
        -no-store `
        -format=json `
        role=$VAULT_OIDC_ROLE

    if ($LASTEXITCODE -ne 0 -or -not $loginJson) {
        Write-Host "[ERROR] Vault OIDC login failed." -ForegroundColor Red
        exit 1
    }

    try {
        $loginObj = $loginJson | ConvertFrom-Json
        $env:VAULT_TOKEN = $loginObj.auth.client_token
        if (-not $env:VAULT_TOKEN) {
            throw "Missing auth.client_token"
        }
    } catch {
        Write-Host "[ERROR] OIDC login succeeded but token parsing failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }

    # Token is kept in-memory in this process only
    Write-Host "[OK] OIDC login successful" -ForegroundColor Green

    # Production KV v2 paths — short paths only, mount is passed via -mount flag
    $secrets = @(
        @{ path = "opencode/openai";    key = "api_key"; env = "OPENAI_API_KEY" },
        @{ path = "opencode/anthropic"; key = "api_key"; env = "ANTHROPIC_API_KEY" },
        @{ path = "opencode/github";    key = "token";   env = "GITHUB_TOKEN" }
    )
}

# Fetch secrets
Write-Host "`nFetching secrets..." -ForegroundColor Cyan
$secretsEnv = @()

foreach ($secret in $secrets) {
    $path = $secret.path
    $key = $secret.key
    $envVar = $secret.env
    
    Write-Host "  Fetching $envVar from $path..." -ForegroundColor Gray
    
    # Use local vault CLI (now token and secrets stay on host!)
    $fieldArg = "-field=$key"
    
    # Suppress errors - we'll check the exit code
    $ErrorActionPreference = "Continue"
    $value = & $vaultExe kv get -mount=$VAULT_KV_MOUNT $fieldArg $path 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    
    if ($exitCode -eq 0 -and $value) {
        $secretsEnv += "$envVar=`"$value`""
        Write-Host "  [OK] Retrieved $envVar" -ForegroundColor Green
    } else {
        Write-Host "  [SKIP] Secret not found (optional): $path" -ForegroundColor Yellow
    }
}

# Set secrets as environment variables (temporary, in memory only)
Write-Host "`nSetting secrets as environment variables..." -ForegroundColor Green

foreach ($secretLine in $secretsEnv) {
    if ($secretLine -match '^(.+?)="(.+)"$') {
        $varName = $matches[1]
        $varValue = $matches[2]
        Set-Item -Path "env:$varName" -Value $varValue
        Write-Host "  Set: $varName" -ForegroundColor Gray
    }
}

Write-Host "`nSecrets loaded into environment (memory only)" -ForegroundColor Green
Write-Host "These will be passed to Docker and then cleared" -ForegroundColor Gray

Write-Host "`nIMPORTANT:" -ForegroundColor Yellow
Write-Host "  - Your Vault token stays on your host machine" -ForegroundColor White
Write-Host "  - Secrets are in memory only (no files created)" -ForegroundColor White
Write-Host "  - Secrets will be cleared when script exits" -ForegroundColor White
Write-Host ""

exit 0
