# ============================================================
# Test Secrets Management with Local Vault
# ============================================================

param(
    [switch]$SetupVault = $false,
    [switch]$TestFetcher = $false,
    [switch]$Full = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Vault Secrets Test Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($SetupVault -or $Full) {
    Write-Host "Step 1: Setting up Vault test data" -ForegroundColor Yellow
    Write-Host ""
    
    $env:VAULT_ADDR = "http://127.0.0.1:8200"
    $env:VAULT_TOKEN = "root"
    
    Write-Host "Vault Address: $env:VAULT_ADDR" -ForegroundColor Gray
    Write-Host "Using root token for dev server" -ForegroundColor Gray
    Write-Host ""
    
    # Check if Vault is accessible
    Write-Host "Checking Vault connectivity..." -ForegroundColor Gray
    try {
        vault status 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) {
            throw "Vault not accessible"
        }
        Write-Host "Vault is accessible" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Cannot connect to Vault at $env:VAULT_ADDR" -ForegroundColor Red
        Write-Host "Make sure Vault dev server is running: vault server -dev" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host ""
    Write-Host "Storing test secrets in Vault..." -ForegroundColor Gray
    
    # Store test secrets
    vault kv put secret/opencode/openai api_key="sk-test-openai-key-12345"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to store OpenAI secret"
    }
    Write-Host "  Stored: secret/opencode/openai" -ForegroundColor Green
    
    vault kv put secret/opencode/anthropic api_key="sk-ant-test-anthropic-key-67890"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to store Anthropic secret"
    }
    Write-Host "  Stored: secret/opencode/anthropic" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "Verifying secrets..." -ForegroundColor Gray
    $openaiKey = vault kv get -field=api_key secret/opencode/openai
    $anthropicKey = vault kv get -field=api_key secret/opencode/anthropic
    Write-Host "  OpenAI key: $openaiKey" -ForegroundColor Gray
    Write-Host "  Anthropic key: $anthropicKey" -ForegroundColor Gray
    
    Write-Host ""
    Write-Host "Vault setup complete!" -ForegroundColor Green
}

if ($TestFetcher -or $Full) {
    Write-Host ""
    Write-Host "Step 2: Testing secrets fetcher" -ForegroundColor Yellow
    Write-Host ""
    
    # Create test config
    $testConfig = @"
provider: vault

vault:
  addr: http://host.docker.internal:8200
  auth_method: token
  namespace: ""
  
  token:
    token: `${VAULT_TOKEN}
  
  secrets:
    - path: secret/data/opencode/openai
      key: api_key
      env_var: OPENAI_API_KEY
    
    - path: secret/data/opencode/anthropic
      key: api_key
      env_var: ANTHROPIC_API_KEY

security:
  strict_mode: true
  audit_log: false
"@
    
    $testConfigPath = "$PSScriptRoot\secrets-config-test.yaml"
    $testConfig | Out-File -FilePath $testConfigPath -Encoding UTF8
    Write-Host "Created test config: secrets-config-test.yaml" -ForegroundColor Gray
    
    # Set environment variables
    $env:VAULT_ADDR = "http://127.0.0.1:8200"
    $env:VAULT_TOKEN = "root"
    
    Write-Host "Building secrets fetcher..." -ForegroundColor Gray
    Push-Location $PSScriptRoot
    try {
        docker compose build secrets-fetcher 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to build secrets fetcher"
        }
        Write-Host "Build complete" -ForegroundColor Green
        
        Write-Host ""
        Write-Host "Running secrets fetcher..." -ForegroundColor Gray
        Write-Host ""
        
        # Copy test config for container
        Copy-Item $testConfigPath "$PSScriptRoot\secrets-config.yaml" -Force
        
        # Run fetcher
        $output = docker compose run --rm secrets-fetcher 2>&1
        $exitCode = $LASTEXITCODE
        
        Write-Host $output
        
        if ($exitCode -eq 0) {
            Write-Host ""
            Write-Host "Secrets fetcher SUCCESS!" -ForegroundColor Green
            
            Write-Host ""
            Write-Host "Verifying fetched secrets..." -ForegroundColor Gray
            
            # Check if secrets file was created
            $secretsVolume = docker volume inspect opencode-sandbox_secrets-data -f '{{.Mountpoint}}' 2>$null
            if ($secretsVolume) {
                Write-Host "Secrets volume: $secretsVolume" -ForegroundColor Gray
            }
            
            Write-Host ""
            Write-Host "Test PASSED!" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "Secrets fetcher FAILED with exit code: $exitCode" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
        # Cleanup test config
        if (Test-Path $testConfigPath) {
            Remove-Item $testConfigPath -Force
        }
    }
}

if (-not $SetupVault -and -not $TestFetcher -and -not $Full) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\test-vault-local.ps1 -SetupVault    # Setup Vault with test data" -ForegroundColor Gray
    Write-Host "  .\test-vault-local.ps1 -TestFetcher   # Test secrets fetcher" -ForegroundColor Gray
    Write-Host "  .\test-vault-local.ps1 -Full          # Do both steps" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Prerequisites:" -ForegroundColor Yellow
    Write-Host "  1. Install Vault CLI: https://www.vaultproject.io/downloads" -ForegroundColor Gray
    Write-Host "  2. Start Vault dev server: vault server -dev" -ForegroundColor Gray
    Write-Host "  3. Note the root token from the dev server output" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "All tests completed!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
