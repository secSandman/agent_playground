#!/usr/bin/env pwsh
#
# Quick test script for containerized Vault integration
# Tests the vault-dev container and secrets fetching
#

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Vault Container Integration Test" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Step 1: Build vault-dev image
Write-Host "[1/6] Building vault-dev image..." -ForegroundColor Yellow
docker compose build vault-dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to build vault-dev image" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Vault image built successfully`n" -ForegroundColor Green

# Step 2: Start vault-dev
Write-Host "[2/6] Starting vault-dev container..." -ForegroundColor Yellow
docker compose up -d vault-dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start vault-dev" -ForegroundColor Red
    exit 1
}

# Wait for Vault to be healthy
Write-Host "Waiting for Vault to be healthy..." -ForegroundColor Yellow
$maxRetries = 30
$retryCount = 0
while ($retryCount -lt $maxRetries) {
    $health = docker inspect --format='{{.State.Health.Status}}' opencode-vault 2>$null
    if ($health -eq "healthy") {
        Write-Host "[OK] Vault is healthy`n" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 1
    $retryCount++
}

if ($retryCount -eq $maxRetries) {
    Write-Host "ERROR: Vault did not become healthy in time" -ForegroundColor Red
    docker logs opencode-vault
    exit 1
}

# Step 3: Initialize test secrets
Write-Host "[3/6] Initializing test secrets..." -ForegroundColor Yellow
docker exec opencode-vault /vault/scripts/init-secrets.sh
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to initialize secrets" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Test secrets initialized`n" -ForegroundColor Green

# Step 4: Verify secrets are accessible
Write-Host "[4/6] Verifying secrets..." -ForegroundColor Yellow
$secrets = docker exec opencode-vault vault kv list secret/opencode
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to list secrets" -ForegroundColor Red
    exit 1
}
Write-Host "Available secrets:" -ForegroundColor Cyan
Write-Host $secrets
Write-Host "[OK] Secrets verified`n" -ForegroundColor Green

# Step 5: Test secret retrieval
Write-Host "[5/6] Testing secret retrieval..." -ForegroundColor Yellow
$openaiKey = docker exec opencode-vault vault kv get -field=api_key secret/opencode/openai
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Retrieved OpenAI key: $openaiKey" -ForegroundColor Green
} else {
    Write-Host "ERROR: Failed to retrieve OpenAI key" -ForegroundColor Red
    exit 1
}

$anthropicKey = docker exec opencode-vault vault kv get -field=api_key secret/opencode/anthropic
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Retrieved Anthropic key: $anthropicKey`n" -ForegroundColor Green
} else {
    Write-Host "ERROR: Failed to retrieve Anthropic key" -ForegroundColor Red
    exit 1
}

# Step 6: Test with secrets-config pointing to vault-dev
Write-Host "[6/6] Testing secrets-fetcher with vault-dev..." -ForegroundColor Yellow

# Create test config
$testConfig = @"
provider: "vault"

vault:
  addr: "http://vault-dev:8200"
  auth_method: "token"
  namespace: ""
  skip_verify: false
  
  secrets:
    - path: "secret/opencode/openai"
      key: "api_key"
      env_var: "OPENAI_API_KEY"
    
    - path: "secret/opencode/anthropic"
      key: "api_key"
      env_var: "ANTHROPIC_API_KEY"
"@

$testConfig | Out-File -FilePath "secrets-config-test.yaml" -Encoding utf8 -NoNewline
Write-Host "Created test configuration" -ForegroundColor Cyan

# Run secrets-fetcher
docker compose run --rm `
    -v "${PWD}/secrets-config-test.yaml:/config/secrets-config.yaml:ro" `
    -e VAULT_ADDR=http://vault-dev:8200 `
    -e VAULT_TOKEN=root `
    secrets-fetcher

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Secrets fetcher completed successfully`n" -ForegroundColor Green
    
    # Check if secrets were written to the volume
    Write-Host "Checking secrets in volume..." -ForegroundColor Cyan
    $secretsContent = docker run --rm -v opencode-sandbox_secrets-data:/data alpine cat /data/opencode-secrets.env 2>$null
    if ($LASTEXITCODE -eq 0 -and $secretsContent) {
        Write-Host "Generated secrets file:" -ForegroundColor Cyan
        Write-Host $secretsContent
        Write-Host "`n[OK] All tests passed!`n" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Secrets file not found in volume" -ForegroundColor Yellow
        Write-Host "Volume contents:" -ForegroundColor Cyan
        docker run --rm -v opencode-sandbox_secrets-data:/data alpine ls -la /data
    }
} else {
    Write-Host "ERROR: Secrets fetcher failed" -ForegroundColor Red
    exit 1
}

# Cleanup
Remove-Item "secrets-config-test.yaml" -ErrorAction SilentlyContinue

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Integration Test Complete" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Update your secrets-config.yaml to use vault-dev" -ForegroundColor White
Write-Host "  2. Run: docker compose up -d" -ForegroundColor White
Write-Host "  3. Access Vault UI: http://localhost:8200 (token: root)" -ForegroundColor White
Write-Host ""
Write-Host "To clean up:" -ForegroundColor Yellow
Write-Host "  docker compose down -v" -ForegroundColor White
