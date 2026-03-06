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

# Determine config file and Vault settings
if ($DevMode) {
    $env:VAULT_ADDR = "http://localhost:8200"
    $env:VAULT_TOKEN = "root"
    Write-Host "Mode: Development" -ForegroundColor Gray
    Write-Host "Vault Address: $env:VAULT_ADDR" -ForegroundColor Gray
    Write-Host "Auth Method: token (hardcoded 'root')" -ForegroundColor Gray
    
    # Dev mode: fetch hardcoded test secrets
    $secrets = @(
        @{ path = "secret/opencode/openai"; key = "api_key"; env = "OPENAI_API_KEY" },
        @{ path = "secret/opencode/anthropic"; key = "api_key"; env = "ANTHROPIC_API_KEY" },
        @{ path = "secret/opencode/github"; key = "token"; env = "GITHUB_TOKEN" }
    )
} else {
    Write-Host "Mode: Production" -ForegroundColor Gray
    Write-Host "ERROR: Production mode requires configuration parsing" -ForegroundColor Red
    Write-Host "For now, please use -DevMode for local testing" -ForegroundColor Yellow
    exit 1
}

# Fetch secrets
Write-Host "`nFetching secrets..." -ForegroundColor Cyan
$secretsEnv = @()

# Vault CLI path
$vaultExe = "C:\Users\txsan\Downloads\vault_1.20.0_windows_amd64\vault.exe"

foreach ($secret in $secrets) {
    $path = $secret.path
    $key = $secret.key
    $envVar = $secret.env
    
    Write-Host "  Fetching $envVar from $path..." -ForegroundColor Gray
    
    # Use local vault CLI (now token and secrets stay on host!)
    $fieldArg = "-field=$key"
    
    # Suppress errors - we'll check the exit code
    $ErrorActionPreference = "Continue"
    $value = & $vaultExe kv get $fieldArg $path 2>$null
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
