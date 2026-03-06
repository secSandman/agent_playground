# ============================================================
# OpenCode Sandbox Test Suite
# Verify all components are working correctly
# ============================================================

param(
    [string]$TestWorkspace = "$PSScriptRoot\test-workspace"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OpenCode Sandbox Test Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$tests = @{
    Passed = 0
    Failed = 0
    Total = 0
}

function Test-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    
    $tests.Total++
    Write-Host "[$($tests.Total)] Testing: $Name..." -ForegroundColor Yellow -NoNewline
    
    try {
        & $Action
        Write-Host " PASS" -ForegroundColor Green
        $tests.Passed++
        return $true
    } catch {
        Write-Host " FAIL" -ForegroundColor Red
        Write-Host "   Error: $_" -ForegroundColor Red
        $tests.Failed++
        return $false
    }
}

# Test 1: Docker is running
Test-Step "Docker daemon is running" {
    $null = docker ps
    if ($LASTEXITCODE -ne 0) { throw "Docker is not running" }
}

# Test 2: Dockerfile exists
Test-Step "Dockerfile exists" {
    if (-not (Test-Path "$PSScriptRoot\Dockerfile")) {
        throw "Dockerfile not found"
    }
}

# Test 3: Squid proxy Dockerfile exists
Test-Step "Squid proxy Dockerfile exists" {
    if (-not (Test-Path "$PSScriptRoot\squid-proxy\Dockerfile")) {
        throw "Squid proxy Dockerfile not found"
    }
}

# Test 4: Squid config exists
Test-Step "Squid configuration exists" {
    if (-not (Test-Path "$PSScriptRoot\squid-proxy\squid.conf")) {
        throw "Squid config not found"
    }
}

# Test 5: docker-compose.yml exists
Test-Step "docker-compose.yml exists" {
    if (-not (Test-Path "$PSScriptRoot\docker-compose.yml")) {
        throw "docker-compose.yml not found"
    }
}

# Test 6: Build OpenCode image
Test-Step "Build OpenCode image" {
    Push-Location $PSScriptRoot
    try {
        docker build -t opencode-sandbox:1.2.17-test . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    } finally {
        Pop-Location
    }
}

# Test 7: Build Squid image
Test-Step "Build Squid proxy image" {
    Push-Location $PSScriptRoot
    try {
        docker compose build squid-proxy 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    } finally {
        Pop-Location
    }
}

# Test 8: Start Squid proxy
Test-Step "Start Squid proxy" {
    Push-Location $PSScriptRoot
    try {
        docker compose up -d squid-proxy 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to start proxy" }
        
        # Wait for health check
        Start-Sleep -Seconds 5
        $health = docker inspect --format='{{.State.Health.Status}}' opencode-squid
        if ($health -ne "healthy") {
            throw "Proxy not healthy: $health"
        }
    } finally {
        Pop-Location
    }
}

# Test 9: Test workspace mount
Test-Step "Create test workspace" {
    if (Test-Path $TestWorkspace) {
        Remove-Item -Recurse -Force $TestWorkspace
    }
    New-Item -ItemType Directory -Path $TestWorkspace | Out-Null
    "console.log('Hello from test');" | Out-File "$TestWorkspace\test.js"
}

# Test 10: Run container with workspace
Test-Step "Run OpenCode container with workspace mount" {
    Push-Location $PSScriptRoot
    try {
        $env:WORKSPACE_PATH = $TestWorkspace
        $output = docker compose run --rm -T opencode --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Container failed to run: $output"
        }
    } finally {
        Pop-Location
    }
}

# Test 11: Verify proxy logs traffic
Test-Step "Verify proxy logs network traffic" {
    $logs = docker compose logs squid-proxy 2>&1
    if (-not $logs) {
        throw "No proxy logs found"
    }
}

# Test 12: Verify security settings
Test-Step "Verify non-root user in container" {
    Push-Location $PSScriptRoot
    try {
        $env:WORKSPACE_PATH = $TestWorkspace
        $user = docker compose run --rm -T opencode whoami 2>&1
        if ($user -notmatch "opencodeuser") {
            throw "Container not running as opencodeuser: $user"
        }
    } finally {
        Pop-Location
    }
}

# Cleanup
Write-Host ""
Write-Host "Cleaning up..." -ForegroundColor Gray
Push-Location $PSScriptRoot
try {
    docker compose down 2>&1 | Out-Null
    if (Test-Path $TestWorkspace) {
        Remove-Item -Recurse -Force $TestWorkspace
    }
    docker rmi opencode-sandbox:1.2.17-test -f 2>&1 | Out-Null
} finally {
    Pop-Location
}

# Results
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Results" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total:  $($tests.Total)" -ForegroundColor Gray
Write-Host "Passed: $($tests.Passed)" -ForegroundColor Green
Write-Host "Failed: $($tests.Failed)" -ForegroundColor $(if ($tests.Failed -gt 0) { "Red" } else { "Green" })
Write-Host ""

if ($tests.Failed -gt 0) {
    Write-Host "TESTS FAILED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now run:" -ForegroundColor Cyan
    Write-Host "  .\start-opencode.ps1 -WorkspacePath <your-project-path>" -ForegroundColor Gray
    exit 0
}
