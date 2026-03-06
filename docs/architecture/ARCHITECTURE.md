# OpenCode Container Architecture & Usage

## ⚠️ Current-State Notes

This architecture document is aligned to the current Python launcher workflow.

Use these entry points:

```
python opencode_run.py --workspace "C:\path\to\project" --dev-mode
python claudecode_run.py --workspace "C:\path\to\project" --dev-mode --provider openai
```

Compose source-of-truth: `.docker-compose/docker-compose.base.yml`.

## Mode-Based Architecture Overview

The runtime has three operational modes. Choose mode based on required host filesystem access vs isolation.

### Mode A: Local Path (default)

Use when you want live edit/sync with your host workspace.

```
Host Workspace (read/write)
  │ bind mount
  ▼
OpenCode/Claude Container ───► Squid Proxy ───► Allowed APIs
  ▲
   Python launcher
```

- Host path is mounted into `/home/opencodeuser/workspace`
- Network egress goes through proxy policy
- Best for normal coding workflows in local IDE

### Mode B: `--isolated-fs`

Use when you want no host mount, but still allow model inference/network through proxy.

```
Host Workspace (not mounted)
  ✖

OpenCode/Claude Container (ephemeral fs) ───► Squid Proxy ───► Allowed APIs
     ▲
      Python launcher
```

- No host workspace bind mount
- Filesystem is ephemeral/read-only with minimal writable tmpfs paths
- Network remains enabled through proxy allowlist

### Mode C: `--isolated`

Use for maximum isolation: no host mount and no network.

```
Host Workspace (not mounted)    Network (disabled)
  ✖                               ✖

   OpenCode/Claude Container (fully isolated runtime)
        ▲
         Python launcher
```

- No host workspace bind mount
- No outbound network path
- Useful for strict offline/local-only tasks

## Detailed Reference Architecture

```
┌─────────────────────────────────────────────────────────┐
│ HOST MACHINE (Windows/Linux/Mac)                        │
│                                                          │
│  ┌──────────────┐         ┌─────────────────────────┐  │
│  │  VS Code /   │◄───────►│  Your Project Files     │  │
│  │  Your Editor │  edits  │  /path/to/workspace     │  │
│  └──────────────┘         └───────────┬─────────────┘  │
│                                        │                 │
│                                        │ volume mount    │
│  ┌─────────────────────────────────────┼──────────────┐ │
│  │ Docker Network (opencode-network)   │              │ │
│  │                                     ▼              │ │
│  │  ┌────────────────────────────────────────────┐   │ │
│  │  │ OpenCode Container                         │   │ │
│  │  │ - Runs OpenCode CLI                        │   │ │
│  │  │ - Reads/writes files via mount             │   │ │
│  │  │ - Makes API calls through proxy            │   │ │
│  │  │ - Workspace: /home/opencodeuser/workspace  │   │ │
│  │  └────────────┬───────────────────────────────┘   │ │
│  │               │ HTTP/HTTPS                         │ │
│  │               ▼                                     │ │
│  │  ┌────────────────────────────┐                    │ │
│  │  │ Squid Proxy Container      │                    │ │
│  │  │ - Filters by FQDN          │                    │ │
│  │  │ - Allows OpenAI/Anthropic  │────────┐          │ │
│  │  │ - Allows 10.x networks     │        │          │ │
│  │  │ - Logs all traffic         │        │          │ │
│  │  └────────────────────────────┘        │          │ │
│  └─────────────────────────────────────────┼──────────┘ │
│                                            │            │
└────────────────────────────────────────────┼────────────┘
                                             │
                                             ▼
                              ┌──────────────────────────┐
                              │ Internet / APIs          │
                              │ - api.openai.com         │
                              │ - api.anthropic.com      │
                              │ - 10.x.x.x (internal)    │
                              └──────────────────────────┘
```

## How Modes Behave

### 1. **Filesystem Behavior**
- **Local Path**: host workspace mounted read/write for live development
- **`--isolated-fs`**: no host mount; ephemeral container filesystem
- **`--isolated`**: no host mount; strongest filesystem isolation

### 2. **Network Behavior**
- **Local Path**: network via Squid proxy policy
- **`--isolated-fs`**: network via Squid proxy policy
- **`--isolated`**: network disabled

### 3. **Editor Integration**
- In **Local Path**, host editor sees agent file changes immediately
- In isolated modes, changes remain in ephemeral container runtime
- VS Code Remote Containers can still be used for advanced workflows

### 4. **Security Baseline**
- Non-root runtime user
- Dropped Linux capabilities
- Resource constraints (memory/CPU/PID)
- Proxy-based egress control where network is enabled

## Usage (Python Launchers)

```bash
# Local Path mode (default)
python opencode_run.py --workspace "C:/Users/YourName/Projects/myproject" --dev-mode

# Isolated filesystem + network through proxy
python opencode_run.py --workspace "C:/Users/YourName/Projects/myproject" --dev-mode --isolated-fs

# Fully isolated (no host mount + no network)
python opencode_run.py --workspace "C:/Users/YourName/Projects/myproject" --dev-mode --isolated

# Claude launcher using OpenAI compatibility mode
python claudecode_run.py --workspace "C:/Users/YourName/Projects/myproject" --dev-mode --provider openai --strict
```

## Workflow Example

```bash
# 1. Start OpenCode container pointing to your project
python opencode_run.py --workspace "C:\code\myproject" --dev-mode

# 2. Inside container, OpenCode can:
#    - Read files from /home/opencodeuser/workspace (your C:\code\myproject)
#    - Make changes to files
#    - Call OpenAI/Anthropic APIs
#    - Access localhost and 10.x networks

# 3. On your host:
#    - Open VS Code: code C:\code\myproject
#    - Edit files normally
#    - See OpenCode's changes in real-time
#    - Commit to git from host

# 4. Exit OpenCode when done (Ctrl+C or 'exit')
#    - Container stops and removes itself
#    - Proxy stops
#    - Files remain on host
```

## OpenCode UI Clarification

**OpenCode CLI has NO GUI** - it runs in terminal only:
```
$ opencode
> What would you like to do?
> [You type requests in terminal]
> [OpenCode responds and edits files]
```

If you want a GUI, you have two options:
1. **Don't use container** - Install OpenCode Desktop app on host
2. **Use VS Code Extension** - Install OpenCode extension in VS Code on host

**This container setup is for CLI-only usage.**

## Adding More Allowed Domains

Edit `squid-proxy/squid.conf`:

```conf
# Add new allowed domains
acl allowed_domains dstdomain .example.com
acl allowed_domains dstdomain api.myservice.io

# Or allow entire TLD (risky)
acl allowed_domains dstdomain .com
```

Then rebuild:
```bash
docker compose build squid-proxy
docker compose restart squid-proxy
```

## Viewing Network Traffic

```bash
# See what OpenCode is accessing
docker compose logs -f squid-proxy

# Or view detailed access log
docker exec opencode-squid tail -f /var/log/squid/access.log
```

## Troubleshooting

### "Cannot access API"
- Check `squid-proxy` is running: `docker compose ps`
- Verify API key is set: `echo $OPENAI_API_KEY`
- Check proxy logs: `docker compose logs squid-proxy`
- Ensure domain is in squid.conf allowlist

### "Permission denied" on files
- Ensure workspace path is correct and accessible
- Check file permissions on host
- OpenCode runs as UID 1001 - ensure files are readable/writable

### "Network unreachable"
- Verify proxy health: `docker inspect opencode-squid`
- Check network: `docker network ls | grep opencode`
- Ensure `HTTP_PROXY` is set in container

## VS Code Remote Container (Advanced)

To use VS Code **inside** the container:

1. Install "Remote - Containers" extension in VS Code
2. Create `.devcontainer/devcontainer.json` in workspace:
```json
{
  "name": "OpenCode Sandbox",
  "dockerComposeFile": "../.docker-compose/docker-compose.base.yml",
  "service": "opencode",
  "workspaceFolder": "/home/opencodeuser/workspace",
  "extensions": [
    "github.copilot"
  ]
}
```
3. Open workspace in VS Code
4. Command Palette → "Remote-Containers: Reopen in Container"

## Security Checklist

- ✓ Non-root user (UID 1001)
- ✓ Dropped all capabilities
- ✓ Resource limits (2GB RAM, 2 CPUs)
- ✓ Network proxied and logged
- ✓ FQDN-based allowlist
- ✓ No privileged mode
- ✓ Workspace isolated from host system
- ✓ API keys passed as env vars (not in image)

## References

- OpenCode CLI docs: https://docs.opencode.dev/cli
- Docker networking: https://docs.docker.com/network/
- Squid proxy: http://www.squid-cache.org/Doc/
