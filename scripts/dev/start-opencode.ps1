# ============================================================
# OpenCode Sandbox with Squid Proxy and Secrets Management
# Run OpenCode CLI in a container with controlled network access
# ============================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$WorkspacePath,
    
    [switch]$DevMode = $false,
    [switch]$ViewLogs = $false,
    
    # OpenCode CLI arguments
    [string]$Prompt = $null,  # One-shot prompt mode: --prompt "your prompt here"
    [switch]$Interactive = $false,  # Force interactive mode
    
    # Legacy direct API key parameters (bypasses secrets management)
    [string]$OpenAIKey = $null,
    [string]$AnthropicKey = $null
)

$ErrorActionPreference = "Stop"

# Set HOME for docker-compose
if (-not $env:HOME) {
    $env:HOME = $env:USERPROFILE
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OpenCode Secure Sandbox Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Validate workspace path
if (-not (Test-Path $WorkspacePath)) {
    Write-Host "ERROR: Workspace path does not exist: $WorkspacePath" -ForegroundColor Red
    exit 1
}

$WorkspacePath = (Resolve-Path $WorkspacePath).Path
Write-Host "Workspace: $WorkspacePath" -ForegroundColor Gray

# Determine secrets mode
if ($DevMode) {
    Write-Host "Mode: Development (using local Vault)" -ForegroundColor Yellow
    $secretsConfig = "secrets-config.dev.yaml"
    $vaultToken = "root"
} else {
    Write-Host "Mode: Production (using secrets-config.yaml)" -ForegroundColor Green
    $secretsConfig = "secrets-config.yaml"
    $vaultToken = $env:VAULT_TOKEN
}

# Check if using legacy direct API keys
$useLegacyKeys = $false
if ($OpenAIKey -or $AnthropicKey) {
    Write-Host "WARNING: Using legacy direct API keys. Consider migrating to secrets management." -ForegroundColor Yellow
    $useLegacyKeys = $true
}

Write-Host ""
Write-Host ""
Write-Host "Building container images..." -ForegroundColor Cyan

Push-Location -Path $PSScriptRoot
try {
    # Build all images via docker-compose
    Write-Host "Building images..." -ForegroundColor Gray
    
    if ($DevMode) {
        # In dev mode, also build vault-dev
        docker compose build vault-dev secrets-fetcher squid-proxy
    } else {
        docker compose build secrets-fetcher squid-proxy
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build images"
    }

    # Build OpenCode image if not exists
    $opencodeImage = docker images -q opencode-sandbox:1.2.17
    if (-not $opencodeImage) {
        Write-Host "Building opencode-sandbox:1.2.17..." -ForegroundColor Gray
        docker build -t opencode-sandbox:1.2.17 .
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to build OpenCode image"
        }
    }

    Write-Host "Images ready" -ForegroundColor Green
    Write-Host ""

    # Start vault-dev in dev mode (only if not already running)
    if ($DevMode) {
        Write-Host "Checking local Vault dev server..." -ForegroundColor Cyan
        $vaultStatus = docker ps --filter "name=opencode-vault" --filter "status=running" -q
        if (-not $vaultStatus) {
            Write-Host "ERROR: Vault is not running!" -ForegroundColor Red
            Write-Host ""
            Write-Host "To start Vault in dev mode, run:" -ForegroundColor Yellow
            Write-Host "  docker compose up -d vault-dev" -ForegroundColor Gray
            Write-Host ""
            Write-Host "Then add your API key(s) out of band:" -ForegroundColor Yellow
            Write-Host "  docker exec opencode-vault vault kv put secret/opencode/openai api_key=`"sk-proj-...`"" -ForegroundColor Gray
            Write-Host "  docker exec opencode-vault vault kv put secret/opencode/anthropic api_key=`"sk-ant-...`"" -ForegroundColor Gray
            Write-Host ""
            exit 1
        } else {
            Write-Host "Vault is running and ready" -ForegroundColor Green
        }
        Write-Host ""
    }

    # Start squid proxy (only if not already running)
    Write-Host "Checking Squid proxy..." -ForegroundColor Cyan
    $squidStatus = docker ps --filter "name=opencode-squid" --filter "status=running" -q
    if (-not $squidStatus) {
        Write-Host "Starting Squid proxy for network policy enforcement..." -ForegroundColor Gray
        docker compose up -d squid-proxy
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start Squid proxy"
        }
    } else {
        Write-Host "Squid is already running" -ForegroundColor Green
    }

    # Wait for proxy to be healthy
    Write-Host "Waiting for proxy to be ready..." -ForegroundColor Gray
    $retries = 30
    while ($retries -gt 0) {
        $health = docker inspect --format='{{.State.Health.Status}}' opencode-squid 2>$null
        if ($health -eq "healthy") {
            Write-Host "Proxy ready" -ForegroundColor Green
            break
        }
        Start-Sleep -Seconds 1
        $retries--
    }

    if ($retries -eq 0) {
        throw "Proxy failed to become healthy"
    }

    Write-Host ""
    
    # Fetch secrets unless using legacy direct keys
    if (-not $useLegacyKeys) {
        Write-Host "Fetching secrets on host machine (Vault token never leaves your computer)..." -ForegroundColor Cyan
        
        # Set environment for host-based fetcher
        if ($DevMode) {
            $env:VAULT_ADDR = "http://localhost:8200"
            $env:VAULT_TOKEN = "root"
        }
        
        # Run host-based secrets fetcher (keeps Vault token secure on host)
        # This sets environment variables in the current session
        & .\fetch-secrets-host.ps1 -DevMode:$DevMode
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to fetch secrets"
        }
        
        # Verify secrets were loaded into environment
        if (-not $env:OPENAI_API_KEY) {
            throw "Secrets not loaded into environment"
        }
        
        Write-Host "Secrets loaded into environment (will be cleaned up on exit)" -ForegroundColor Green
        Write-Host ""
    }

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Starting OpenCode CLI" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Your code at: $WorkspacePath" -ForegroundColor Gray
    Write-Host "Network: Proxied through Squid (see squid.conf for allowed domains)" -ForegroundColor Gray
    if ($DevMode) {
        Write-Host "Vault UI: http://localhost:8200 (token: root)" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "OpenCode CLI Options:" -ForegroundColor Yellow
    Write-Host "  Interactive Mode: Opens in container terminal" -ForegroundColor Gray
    Write-Host "  One-Shot Mode: Pass prompt as argument" -ForegroundColor Gray
    Write-Host "  Example: --prompt 'analyze this code'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Starting in interactive mode..." -ForegroundColor Cyan
    Write-Host "Type your prompts or 'exit' to quit" -ForegroundColor Gray
    Write-Host ""

    # Set environment variables for the run
    $env:WORKSPACE_PATH = $WorkspacePath

    # Run OpenCode interactively
    $dockerArgs = @(
        "compose", "run"
        "-it"  # Interactive terminal
        "--rm"
        "--service-ports"
    )

    # Add legacy API keys if provided
    if ($useLegacyKeys) {
        if ($OpenAIKey) {
            $dockerArgs += "-e"
            $dockerArgs += "OPENAI_API_KEY=$OpenAIKey"
        }
        if ($AnthropicKey) {
            $dockerArgs += "-e"
            $dockerArgs += "ANTHROPIC_API_KEY=$AnthropicKey"
        }
    }

    $dockerArgs += "opencode"
    
    # Add OpenCode CLI arguments based on mode
    if ($Prompt) {
        # One-shot mode: execute prompt and exit
        Write-Host "Running in one-shot mode with prompt" -ForegroundColor Gray
        $dockerArgs += "run"
        $dockerArgs += $Prompt
    } else {
        # Interactive TUI mode (default)
        Write-Host "Entering interactive TUI mode..." -ForegroundColor Cyan
        Write-Host "Type your prompts below:" -ForegroundColor Yellow
        Write-Host ""
        # No additional args needed - just runs opencode TUI
    }

    & docker $dockerArgs

    Write-Host ""
    Write-Host "OpenCode session ended" -ForegroundColor Green

} catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
    
    # Clean up secrets from environment
    Write-Host ""
    Write-Host "Cleaning up secrets from environment..." -ForegroundColor Gray
    Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\GITHUB_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:\VAULT_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:\VAULT_ADDR -ErrorAction SilentlyContinue
    Write-Host "Secrets cleared from memory" -ForegroundColor Green
    
    if ($ViewLogs) {
        Write-Host ""
        Write-Host "Proxy access logs:" -ForegroundColor Cyan
        docker compose logs squid-proxy
    }
    
    Write-Host ""
    Write-Host "Cleaning up containers..." -ForegroundColor Gray
    if ($DevMode) {
        # In dev mode, keep Vault and Squid running for next test run
        # Only stop the OpenCode container (already cleaned up by --rm)
        Write-Host "Vault and Squid will remain running for next test" -ForegroundColor Green
        Write-Host "(Stop them with: docker compose down)" -ForegroundColor Gray
    } else {
        # In production, clean everything
        docker compose down
    }
    Write-Host "Done" -ForegroundColor Green
}
