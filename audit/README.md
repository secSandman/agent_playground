# Security Audit Tools

This folder contains a rough local scanner for security best-practice checks.

## Script

- `security_audit.py`: Checks Docker/container hardening posture and scans for likely secrets in local directories.

## What It Checks

- Dockerfile best practices (`USER`, digest pinning hint, package install hygiene)
- Compose runtime hardening (`user`, `no-new-privileges`, `cap_drop`, syscall policy hints)
- OpenCode/Claude settings hardening signals in image builds
- Local user privilege context (admin/root vs standard user)
- Rough secret scan (API key/token/private key patterns + sensitive filenames)

## Usage

From repo root:

```bash
python audit/security_audit.py
```

Target specific directories:

```bash
python audit/security_audit.py --paths ./test-workspace ./config
```

Output JSON report:

```bash
python audit/security_audit.py --format json --output ./audit/report.json
```

Limit scan depth/size:

```bash
python audit/security_audit.py --max-files 1500 --max-file-size-kb 512
```

## Notes

- This is a rough static scan, not a formal security assessment.
- Expect false positives; manually validate findings before remediation.
- Avoid scanning very large/untrusted trees without adjusting limits.
