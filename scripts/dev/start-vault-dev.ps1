#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start Vault dev server in Docker for local testing.
    
.DESCRIPTION
    Starts a Vault dev server that persists until you manually stop it.
    Use this to prepare your secrets out-of-band before running start-opencode.ps1
    
.EXAMPLE
    .\start-vault-dev.ps1
    
.NOTES
    Once running, add your API keys with:
    
    docker exec opencode-vault vault kv put secret/opencode/openai api_key="sk-proj-..."
    docker exec opencode-vault vault kv put secret/opencode/anthropic api_key="sk-ant-..."
    docker exec opencode-vault vault kv put secret/opencode/github token="ghp_..."
    
    Stop with:
    docker compose down
#>

$ErrorActionPreference = "Stop"

Write-Host "Starting Vault dev server..." -ForegroundColor Cyan

docker compose up -d vault-dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start Vault" -ForegroundColor Red
    exit 1
}

Write-Host "Waiting for Vault to be ready..." -ForegroundColor Gray
Start-Sleep -Seconds 2

$maxRetries = 30
$retries = 0
while ($retries -lt $maxRetries) {
    $health = docker exec opencode-vault vault status 2>$null | Select-String "Sealed"
    if ($health -match "false") {
        Write-Host ""
        Write-Host "Vault is running and unsealed" -ForegroundColor Green
        Write-Host ""
        Write-Host "Vault Address: http://localhost:8200" -ForegroundColor Gray
        Write-Host "Root Token: root" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Add your secrets with:" -ForegroundColor Yellow
        Write-Host "  docker exec opencode-vault vault kv put secret/opencode/openai api_key=sk-proj-..." -ForegroundColor Gray
        Write-Host "  docker exec opencode-vault vault kv put secret/opencode/anthropic api_key=sk-ant-..." -ForegroundColor Gray
        Write-Host "  docker exec opencode-vault vault kv put secret/opencode/github token=ghp_..." -ForegroundColor Gray
        Write-Host ""
        Write-Host "Then run:" -ForegroundColor Yellow
        Write-Host "  .\start-opencode.ps1 -DevMode -WorkspacePath .\test-workspace -Prompt 'your question'" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Stop Vault with: docker compose down" -ForegroundColor Gray
        exit 0
    }
    
    Start-Sleep -Seconds 1
    $retries++
}

Write-Host "Timeout waiting for Vault to start" -ForegroundColor Red
exit 1
