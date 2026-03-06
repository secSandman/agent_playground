# OpenCode Container Security Hardening Guide

## Security Features Implemented

### 1. **Base Image Security**
- Using Ubuntu 24.04 LTS with security updates
- Minimal package installation (only curl, git, ca-certificates)
- **Recommendation**: Pin base image digest for reproducibility

### 2. **Non-Root User**
- Runs as `opencodeuser` (UID 1001) - never as root
- Account locked (no password login possible)
- No sudo privileges granted

### 3. **Privilege Escalation Prevention**
- Removed all setuid/setgid binaries during build
- Runtime flag: `--security-opt=no-new-privileges:true`
- Runtime flag: `--cap-drop=ALL` (drops all Linux capabilities)

### 4. **Filesystem Security**
- Read-only root filesystem (`--read-only`)
- Writable /tmp with `noexec,nosuid,nodev` (prevents binary execution)
- Writable workspace with `noexec,nosuid,nodev`
- Binary verification via SHA256 checksum

### 5. **Network Isolation**
- No ports exposed by default
- `--network=none` flag available (disable all network)
- Remove `--network=none` only if external access needed

### 6. **Resource Limits** (DoS Prevention)
- Memory limit: 2GB (`--memory=2g`)
- CPU limit: 2 cores (`--cpus=2`)
- Process limit: 100 PIDs (`--pids-limit=100`)
- Tmp size: 100MB (`/tmp`)
- Workspace size: 500MB

### 7. **Container Breakout Mitigations**
- Non-root user namespace
- Dropped capabilities
- Read-only root filesystem
- No privileged mode
- seccomp profile (Docker default)
- **Optional**: Custom AppArmor/SELinux profiles

## Usage

### Basic Secure Execution (Windows)
```powershell
.\run-secure.ps1
```

### With Network Access
```powershell
.\run-secure.ps1 -EnableNetwork
```

### Basic Secure Execution (Linux/Mac)
```bash
chmod +x run-secure.sh
./run-secure.sh
```

### Manual Docker Run (Maximum Security)
```bash
docker run -it --rm \
  --user 1001:1001 \
  --security-opt=no-new-privileges:true \
  --cap-drop=ALL \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=100m \
  --tmpfs /home/opencodeuser/workspace:rw,noexec,nosuid,nodev,size=500m \
  --network=none \
  --memory=2g \
  --memory-swap=2g \
  --cpus=2 \
  --pids-limit=100 \
  opencode-sandbox:1.2.17
```

## Additional Hardening Options

### 1. **User Namespace Remapping** (Host-Level)
Add to Docker daemon config (`/etc/docker/daemon.json`):
```json
{
  "userns-remap": "default"
}
```
Restart Docker: `sudo systemctl restart docker`

### 2. **Custom Seccomp Profile**
Create `seccomp-opencode.json` to restrict syscalls:
```bash
docker run --security-opt seccomp=./seccomp-opencode.json ...
```

### 3. **AppArmor Profile** (Linux)
```bash
docker run --security-opt apparmor=docker-default ...
```

### 4. **SELinux Context** (RHEL/CentOS)
```bash
docker run --security-opt label=type:container_runtime_t ...
```

### 5. **Audit Logging**
Enable Docker audit logging to track container actions:
```bash
docker run --log-driver=json-file --log-opt max-size=10m ...
```

### 6. **Image Scanning**
Scan for vulnerabilities before running:
```bash
docker scout cves opencode-sandbox:1.2.17
# or
trivy image opencode-sandbox:1.2.17
```

## Attack Surface Analysis

### **Mitigated Risks**
1. **Privilege Escalation**: No sudo, dropped capabilities, no setuid binaries
2. **Host Filesystem Access**: Read-only root, isolated workspace
3. **Resource Exhaustion**: Memory, CPU, PID, and disk limits enforced
4. **Network Attacks**: Network disabled by default
5. **Container Breakout**: Non-root user, dropped capabilities, seccomp

### **Residual Risks** (Inherent to Containers)
1. **Kernel Vulnerabilities**: Containers share host kernel
   - *Mitigation*: Keep host kernel updated, use gVisor/Kata Containers
2. **Volume Mount Escapes**: If workspace mounted with host paths
   - *Mitigation*: Use tmpfs instead of bind mounts when possible
3. **Side-Channel Attacks**: CPU/memory side channels
   - *Mitigation*: Use VM-based isolation (Firecracker, Kata)

## Verification Commands

### Check Running Container Security
```bash
# View dropped capabilities
docker inspect opencode-secure-* | jq '.[].HostConfig.CapDrop'

# Check user
docker exec opencode-secure-* whoami
# Should output: opencodeuser

# Verify read-only filesystem
docker exec opencode-secure-* touch /test
# Should fail with: Read-only file system

# Check resource limits
docker stats opencode-secure-*
```

### Test Privilege Escalation Prevention
```bash
# Try to become root (should fail)
docker exec opencode-secure-* su -
docker exec opencode-secure-* sudo ls
```

## Threat Model Summary

| Threat | Mitigation | Effectiveness |
|--------|-----------|---------------|
| Malicious code execution | Non-root user, dropped capabilities | High |
| Filesystem tampering | Read-only root, restricted tmp/workspace | High |
| Container breakout | Dropped caps, seccomp, no-new-privs | Medium-High |
| Resource exhaustion | Memory/CPU/PID limits | High |
| Network exfiltration | Network disabled (optional) | High |
| Kernel exploits | Shared kernel (inherent risk) | Low (Use VMs) |

## References
- [Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [NIST Application Container Security Guide](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-190.pdf)
