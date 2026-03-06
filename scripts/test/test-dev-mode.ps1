#!/usr/bin/env pwsh
#
# Quick test of the full OpenCode startup flow with dev Vault
#

$ErrorActionPreference = "Stop"

# Set HOME for docker-compose
if (-not $env:HOME) {
    $env:HOME = $env:USERPROFILE
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing OpenCode Dev Mode Startup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Clean slate
Write-Host "Cleaning up any existing containers..." -ForegroundColor Yellow
docker compose down -v 2>&1 | Out-Null
Start-Sleep -Seconds 2

# Create a test workspace
$testWorkspace = Join-Path $PSScriptRoot "test-workspace"
if (-not (Test-Path $testWorkspace)) {
    New-Item -ItemType Directory -Path $testWorkspace | Out-Null
}

# Create a simple test file
@"
# Test Workspace
This is a test file to verify OpenCode can access the workspace.
"@ | Out-File -FilePath (Join-Path $testWorkspace "README.md") -Encoding utf8

Write-Host "Created test workspace at: $testWorkspace`n" -ForegroundColor Green

Write-Host "Starting OpenCode in dev mode (this will exit immediately after setup)..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C after verifying the setup completes successfully`n" -ForegroundColor Gray

# Start in dev mode
# This should:
# 1. Build images
# 2. Start vault-dev
# 3. Initialize test secrets
# 4. Start squid-proxy
# 5. Fetch secrets from vault-dev
# 6. Start opencode (we'll Ctrl+C here)

.\start-opencode.ps1 -WorkspacePath $testWorkspace -DevMode

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Test Complete" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
