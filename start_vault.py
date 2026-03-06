#!/usr/bin/env python3
"""
Vault Dev Server Starter - Root wrapper

This script delegates to cmd/vault/start_vault.py
"""

import sys
from pathlib import Path

# Add cmd/vault to path
cmd_vault_path = Path(__file__).parent / "cmd" / "vault"
sys.path.insert(0, str(cmd_vault_path))

# Import and run
from start_vault import main

if __name__ == "__main__":
    main()
