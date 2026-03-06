# ============================================================
# Secure OpenCode Container Runner (PowerShell)
# Applies defense-in-depth security controls
# ============================================================

param(
    [string]$WorkspaceDir = ".",
    [switch]$EnableNetwork = $false
)

$IMAGE = "opencode-sandbox:1.2.17"
$CONTAINER_NAME = "opencode-secure-$(Get-Date -Format 'yyyyMMddHHmmss')"
$WorkspacePath = (Resolve-Path $WorkspaceDir).Path

Write-Host "Starting hardened OpenCode container..." -ForegroundColor Cyan
Write-Host "   Workspace: $WorkspacePath" -ForegroundColor Gray

$dockerArgs = @(
    "run", "-it", "--rm"
    "--name", $CONTAINER_NAME
    
    # Security: User namespace remapping - run as non-root
    "--user", "1001:1001"
    
    # Security: Prevent privilege escalation
    "--security-opt=no-new-privileges:true"
    
    # Security: Drop all Linux capabilities
    "--cap-drop=ALL"
    
    # Security: Read-only root filesystem
    "--read-only"
    
    # Security: Writable /tmp with security restrictions
    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=100m"
    
    # Security: Writable workspace with security restrictions
    "--tmpfs", "/home/opencodeuser/workspace:rw,noexec,nosuid,nodev,size=500m"
    
    # Security: Resource limits to prevent DoS
    "--memory=2g"
    "--memory-swap=2g"
    "--cpus=2"
    "--pids-limit=100"
)

# Network isolation (disable by default)
if (-not $EnableNetwork) {
    $dockerArgs += "--network=none"
    Write-Host "   Network: Disabled (isolated)" -ForegroundColor Yellow
} else {
    Write-Host "   Network: Enabled" -ForegroundColor Yellow
}

# Mount workspace as volume if needed (commented by default to use tmpfs)
# Uncomment these lines and comment out the tmpfs workspace line above:
# $dockerArgs += "-v"
# $dockerArgs += "${WorkspacePath}:/home/opencodeuser/workspace:rw"

$dockerArgs += $IMAGE

# Add any additional arguments passed to the script
$dockerArgs += $args

Write-Host "   Executing: docker $($dockerArgs -join ' ')" -ForegroundColor Gray
& docker $dockerArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "Container exited cleanly" -ForegroundColor Green
} else {
    Write-Host "Container exited with code: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
