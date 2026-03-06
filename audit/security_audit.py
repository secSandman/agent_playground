#!/usr/bin/env python3
import argparse
import json
import os
import platform
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Finding:
    severity: str
    category: str
    check: str
    path: Optional[str]
    details: str


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
}


SECRET_PATTERNS: List[Tuple[str, str, re.Pattern]] = [
    ("high", "OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("high", "Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    ("high", "AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("high", "GitHub token (classic)", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("high", "GitHub token (fine-grained)", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("high", "Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("high", "Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("medium", "JWT-like token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("high", "Private key block", re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----")),
]


SENSITIVE_FILENAME_PATTERNS = [
    re.compile(r"(^|/)id_rsa(\.pub)?$"),
    re.compile(r"(^|/)id_ed25519(\.pub)?$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.p12$"),
    re.compile(r"\.pfx$"),
    re.compile(r"\.key$"),
    re.compile(r"(^|/)\.env(\..*)?$"),
]


def rel_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(path)


def add_find(findings: List[Finding], severity: str, category: str, check: str, path: Optional[Path], details: str, repo_root: Path) -> None:
    findings.append(
        Finding(
            severity=severity,
            category=category,
            check=check,
            path=rel_path(path, repo_root) if path else None,
            details=details,
        )
    )


def read_text_safe(path: Path, max_bytes: int) -> Optional[str]:
    try:
        if path.stat().st_size > max_bytes:
            return None
        data = path.read_bytes()
        if b"\x00" in data:
            return None
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def check_dockerfile(path: Path, findings: List[Finding], repo_root: Path) -> None:
    content = read_text_safe(path, max_bytes=2 * 1024 * 1024)
    if content is None:
        add_find(findings, "medium", "dockerfile", "dockerfile-readable", path, "Could not parse Dockerfile (binary or too large).", repo_root)
        return

    lowered = content.lower()

    # Check USER directive
    user_match = re.search(r"^\s*USER\s+(\S+)\s*$", content, flags=re.MULTILINE | re.IGNORECASE)
    if " user " not in f" {lowered} " and "\nuser " not in lowered:
        add_find(findings, "high", "dockerfile", "non-root-user", path, "No USER directive found; container may run as root.", repo_root)
    elif re.search(r"^\s*USER\s+root\s*$", content, flags=re.MULTILINE):
        add_find(findings, "high", "dockerfile", "non-root-user", path, "USER root found; prefer non-root runtime user.", repo_root)
    else:
        user_value = user_match.group(1) if user_match else "unknown"
        # Try to find useradd line to get full user details
        useradd_match = re.search(r"useradd.*?-u\s+(\d+).*?(\w+)", content)
        if useradd_match:
            uid = useradd_match.group(1)
            username = useradd_match.group(2)
            add_find(findings, "info", "dockerfile", "non-root-user", path, 
                    f"✓ Non-root USER: {username} (UID {uid})", repo_root)
        else:
            add_find(findings, "info", "dockerfile", "non-root-user", path, 
                    f"✓ Non-root USER directive: {user_value}", repo_root)

    # Check for hardening hints
    hardening_hints = []
    if "cap_drop" in lowered or "--cap-drop" in lowered:
        hardening_hints.append("cap_drop")
    if "no-new-privileges" in lowered:
        hardening_hints.append("no-new-privileges")
    if "read-only" in lowered or "--read-only" in lowered:
        hardening_hints.append("read-only")
    if "security_opt" in lowered or "security-opt" in lowered:
        hardening_hints.append("security_opt")
    
    if hardening_hints:
        add_find(findings, "info", "dockerfile", "runtime-hardening-hints", path, f"✓ Runtime hardening hints found: {', '.join(hardening_hints)}", repo_root)
    else:
        add_find(findings, "medium", "dockerfile", "runtime-hardening-hints", path, "No runtime hardening hints found in Dockerfile comments/instructions.", repo_root)

    if "@sha256:" in content:
        add_find(findings, "info", "dockerfile", "pinned-base-digest", path, "✓ Base image uses digest pinning (@sha256)", repo_root)
    else:
        add_find(findings, "low", "dockerfile", "pinned-base-digest", path, "Base image digest pin (@sha256) not detected.", repo_root)

    if re.search(r"^\s*ADD\s+", content, flags=re.MULTILINE):
        add_find(findings, "low", "dockerfile", "add-instruction", path, "ADD detected; prefer COPY unless archive/URL behavior is required.", repo_root)

    if "apt-get install" in lowered:
        if "--no-install-recommends" in lowered:
            add_find(findings, "info", "dockerfile", "apt-minimal", path, "✓ apt-get uses --no-install-recommends", repo_root)
        else:
            add_find(findings, "medium", "dockerfile", "apt-minimal", path, "apt-get install used without --no-install-recommends.", repo_root)

    if "chmod 400" in lowered or "chmod 600" in lowered:
        add_find(findings, "info", "dockerfile", "file-permissions", path, "✓ Restrictive chmod (400/600) found for security-sensitive files", repo_root)


def _extract_service_block(compose_text: str, service_name: str) -> Optional[str]:
    lines = compose_text.splitlines()
    start_idx = None
    for index, line in enumerate(lines):
        if re.match(rf"^\s{{2}}{re.escape(service_name)}:\s*$", line):
            start_idx = index
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    for index in range(start_idx + 1, len(lines)):
        if re.match(r"^\s{2}[A-Za-z0-9_-]+:\s*$", lines[index]):
            end_idx = index
            break
    return "\n".join(lines[start_idx:end_idx])


def check_compose_runtime(compose_file: Path, findings: List[Finding], repo_root: Path) -> None:
    content = read_text_safe(compose_file, max_bytes=2 * 1024 * 1024)
    if content is None:
        add_find(findings, "high", "compose", "compose-readable", compose_file, "Could not read compose file.", repo_root)
        return

    for service in ("opencode", "claudecode"):
        block = _extract_service_block(content, service)
        if not block:
            add_find(findings, "medium", "compose", "service-exists", compose_file, f"Service '{service}' not found.", repo_root)
            continue

        # Collect all security settings for this service
        security_settings = []
        
        if user_match := re.search(r"\buser:\s*\"?(\d+:\d+)\"?", block):
            uid_gid = user_match.group(1)
            security_settings.append(f"user: {uid_gid}")
        elif re.search(r"\buser:\s*\"?0:?0?\"?", block) or re.search(r"\buser:\s*root\b", block):
            add_find(findings, "high", "compose", "non-root-user", compose_file, f"Service '{service}' appears to run as root.", repo_root)
        else:
            add_find(findings, "medium", "compose", "non-root-user", compose_file, f"Service '{service}' missing explicit user setting.", repo_root)

        if "no-new-privileges:true" in block:
            security_settings.append("security_opt: no-new-privileges:true")
        else:
            add_find(findings, "medium", "compose", "no-new-privileges", compose_file, f"Service '{service}' missing no-new-privileges.", repo_root)

        if re.search(r"cap_drop:\s*\n\s*-\s*ALL", block):
            security_settings.append("cap_drop: ALL")
        else:
            add_find(findings, "high", "compose", "cap-drop-all", compose_file, f"Service '{service}' does not clearly drop ALL capabilities.", repo_root)

        # Extract resource limits
        if mem_match := re.search(r"mem_limit:\s*(\S+)", block):
            security_settings.append(f"mem_limit: {mem_match.group(1)}")
        if cpu_match := re.search(r"cpus:\s*(\S+)", block):
            security_settings.append(f"cpus: {cpu_match.group(1)}")
        if pid_match := re.search(r"pids_limit:\s*(\d+)", block):
            security_settings.append(f"pids_limit: {pid_match.group(1)}")
        
        if security_settings:
            settings_str = "\n    ".join(security_settings)
            add_find(findings, "info", "compose", f"{service}-security-config", compose_file, 
                    f"✓ Service '{service}' security settings:\n    {settings_str}", repo_root)

        if "seccomp" in block or "apparmor" in block:
            add_find(findings, "info", "compose", "syscall-restrictions", compose_file, f"Service '{service}' has seccomp/apparmor style settings.", repo_root)
        else:
            add_find(findings, "medium", "compose", "syscall-restrictions", compose_file, f"Service '{service}' missing explicit seccomp/apparmor policy.", repo_root)

        if "read_only: true" not in block:
            add_find(findings, "low", "compose", "read-only-rootfs", compose_file, f"Service '{service}' does not set read_only: true (may be intentional).", repo_root)


def check_tool_hardening(repo_root: Path, findings: List[Finding]) -> None:
    opencode_df = repo_root / "build" / "opencode" / "Dockerfile"
    claudecode_df = repo_root / "build" / "claudecode" / "Dockerfile"

    opencode_content = read_text_safe(opencode_df, max_bytes=2 * 1024 * 1024)
    if opencode_content:
        if "opencode.json" in opencode_content:
            # Extract the full opencode.json block
            match = re.search(r'cat\s*>\s*/home/opencodeuser/\.config/opencode/opencode\.json\s*<<\s*[\'"]?EOF[\'"]?\s*(.*?)\s*^EOF', 
                            opencode_content, re.MULTILINE | re.DOTALL)
            if match:
                config_json = match.group(1).strip()
                add_find(findings, "info", "settings", "opencode-config", opencode_df, 
                        f"✓ OpenCode hardened config:\n{config_json}", repo_root)
            elif '"deny"' in opencode_content:
                add_find(findings, "info", "settings", "opencode-hardening", opencode_df, 
                        "✓ OpenCode deny-based permission settings detected", repo_root)
        else:
            add_find(findings, "medium", "settings", "opencode-hardening", opencode_df, 
                    "OpenCode hardened settings were not clearly detected.", repo_root)

    claudecode_content = read_text_safe(claudecode_df, max_bytes=2 * 1024 * 1024)
    if claudecode_content:
        if "settings.json" in claudecode_content:
            # Extract the printf/echo settings.json block
            match = re.search(r'printf\s+[\'"](.+?)[\'"].*?settings\.json', 
                            claudecode_content, re.DOTALL)
            if match:
                settings_json = match.group(1).replace('\\n', '\n').replace('\\"', '"')
                chmod_match = re.search(r'chmod\s+(\d+)\s+.*/\.claude/settings\.json', claudecode_content)
                chmod_val = chmod_match.group(1) if chmod_match else "unknown"
                add_find(findings, "info", "settings", "claudecode-config", claudecode_df, 
                        f"✓ Claude hardened config (chmod {chmod_val}):\n{settings_json}", repo_root)
            elif '"deny"' in claudecode_content:
                has_chmod_400 = "chmod 400" in claudecode_content
                chmod_note = " + chmod 400 lockdown" if has_chmod_400 else ""
                add_find(findings, "info", "settings", "claudecode-hardening", claudecode_df, 
                        f"✓ Claude settings deny-list{chmod_note} detected", repo_root)
        else:
            add_find(findings, "medium", "settings", "claudecode-hardening", claudecode_df, 
                    "Claude hardened settings were not clearly detected.", repo_root)


def check_local_account(findings: List[Finding], repo_root: Path) -> None:
    system = platform.system().lower()
    if system == "windows":
        try:
            import ctypes
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            username = os.getenv("USERNAME", "unknown")
            if is_admin:
                add_find(findings, "medium", "host-account", "current-user-privilege", None, f"Current process ({username}) appears elevated (Administrator). Prefer standard user for routine work.", repo_root)
            else:
                add_find(findings, "info", "host-account", "current-user-privilege", None, f"✓ Running as non-admin user: {username}", repo_root)
        except Exception as exc:
            add_find(findings, "low", "host-account", "current-user-privilege", None, f"Could not determine admin status: {exc}", repo_root)
    else:
        try:
            uid = os.getuid()
            username = os.getenv("USER", str(uid))
            if uid == 0:
                add_find(findings, "high", "host-account", "current-user-privilege", None, "Script is running as root. Prefer non-root user.", repo_root)
            else:
                add_find(findings, "info", "host-account", "current-user-privilege", None, f"✓ Running as non-root user: {username} (UID {uid})", repo_root)
        except Exception as exc:
            add_find(findings, "low", "host-account", "current-user-privilege", None, f"Could not determine UID: {exc}", repo_root)


def scan_for_secrets(
    repo_root: Path,
    scan_paths: List[Path],
    max_files: int,
    max_bytes: int,
    findings: List[Finding],
) -> Dict[str, int]:
    scanned = 0
    skipped = 0

    for base in scan_paths:
        if not base.exists():
            add_find(findings, "low", "secrets", "scan-path-exists", base, "Scan path does not exist.", repo_root)
            continue

        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDED_DIRS]
            root_path = Path(root)

            for filename in files:
                if scanned >= max_files:
                    add_find(findings, "low", "secrets", "scan-file-limit", None, f"Reached max files limit ({max_files}).", repo_root)
                    return {"scanned_files": scanned, "skipped_files": skipped}

                file_path = root_path / filename
                rel = rel_path(file_path, repo_root).replace("\\", "/")

                if any(pattern.search(rel) for pattern in SENSITIVE_FILENAME_PATTERNS):
                    add_find(findings, "medium", "secrets", "sensitive-filename", file_path, "Sensitive filename pattern detected; confirm this file is expected and protected.", repo_root)

                try:
                    if file_path.stat().st_size > max_bytes:
                        skipped += 1
                        continue
                except Exception:
                    skipped += 1
                    continue

                text = read_text_safe(file_path, max_bytes=max_bytes)
                if text is None:
                    skipped += 1
                    continue

                scanned += 1

                for severity, label, regex in SECRET_PATTERNS:
                    if regex.search(text):
                        add_find(findings, severity, "secrets", "secret-pattern", file_path, f"Potential {label} detected.", repo_root)

                if platform.system().lower() != "windows":
                    try:
                        mode = stat.S_IMODE(file_path.stat().st_mode)
                        if any(pattern.search(rel) for pattern in SENSITIVE_FILENAME_PATTERNS) and (mode & 0o077):
                            add_find(findings, "medium", "permissions", "sensitive-file-mode", file_path, f"Sensitive file is group/world accessible (mode {oct(mode)}).", repo_root)
                    except Exception:
                        pass

    return {"scanned_files": scanned, "skipped_files": skipped}


def summarize(findings: List[Finding]) -> Dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def render_text_report(results: Dict) -> str:
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("Security Audit Report")
    lines.append("=" * 60)
    lines.append(f"Repo root: {results['repo_root']}")
    lines.append(f"Scanned files: {results['scan_stats']['scanned_files']} (skipped: {results['scan_stats']['skipped_files']})")
    s = results["summary"]
    lines.append(f"Summary: high={s.get('high', 0)} medium={s.get('medium', 0)} low={s.get('low', 0)} info={s.get('info', 0)}")
    lines.append("")

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    sorted_findings = sorted(
        results["findings"],
        key=lambda f: (severity_order.get(f["severity"], 99), f["category"], f["check"], f.get("path") or ""),
    )

    for f in sorted_findings:
        where = f" [{f['path']}]" if f.get("path") else ""
        lines.append(f"- {f['severity'].upper():6} {f['category']:15} {f['check']:25} {where}")
        lines.append(f"  {f['details']}")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append("Note: This is a rough static scanner; validate findings manually before remediation.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rough security best-practices audit for OpenCode/ClaudeCode sandbox.")
    parser.add_argument("--repo-root", default=os.getcwd(), help="Repository root to audit (default: current directory)")
    parser.add_argument("--paths", nargs="*", default=None, help="Directories/files to scan for secrets (default: repo root)")
    parser.add_argument("--max-files", type=int, default=3000, help="Maximum files to scan for secret patterns")
    parser.add_argument("--max-file-size-kb", type=int, default=1024, help="Max file size (KB) for content scanning")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--output", default=None, help="Write report to file")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    findings: List[Finding] = []

    dockerfiles = [
        repo_root / "build" / "opencode" / "Dockerfile",
        repo_root / "build" / "claudecode" / "Dockerfile",
    ]
    for dockerfile in dockerfiles:
        if dockerfile.exists():
            check_dockerfile(dockerfile, findings, repo_root)
        else:
            add_find(findings, "medium", "dockerfile", "dockerfile-exists", dockerfile, "Expected Dockerfile not found.", repo_root)

    compose_file = repo_root / ".docker-compose" / "docker-compose.base.yml"
    if compose_file.exists():
        check_compose_runtime(compose_file, findings, repo_root)
    else:
        add_find(findings, "high", "compose", "compose-file", compose_file, "Compose file not found.", repo_root)

    check_tool_hardening(repo_root, findings)
    check_local_account(findings, repo_root)

    scan_targets = [repo_root] if not args.paths else [Path(p).resolve() for p in args.paths]
    scan_stats = scan_for_secrets(
        repo_root=repo_root,
        scan_paths=scan_targets,
        max_files=max(1, args.max_files),
        max_bytes=max(1, args.max_file_size_kb) * 1024,
        findings=findings,
    )

    results = {
        "repo_root": str(repo_root),
        "scan_paths": [str(p) for p in scan_targets],
        "scan_stats": scan_stats,
        "summary": summarize(findings),
        "findings": [asdict(f) for f in findings],
    }

    output = json.dumps(results, indent=2) if args.format == "json" else render_text_report(results)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"Report written to: {output_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
