#!/usr/bin/env python3
"""
Start Vault dev server in Docker for local testing.

Usage:
    python start_vault.py

This starts a Vault dev server that persists until you manually stop it.
Use this to prepare your secrets out-of-band before running run.py
"""

import subprocess
import os
import sys
import time
from pathlib import Path
from colorama import Fore, Style, init

from docker_compose_manager import DockerComposeManager


# Initialize colorama for cross-platform colored output
init(autoreset=False)


def main():
    """Start Vault dev server."""
    project_dir = Path(__file__).parent
    docker_manager = DockerComposeManager(str(project_dir))
    
    print(f"{Fore.CYAN}Starting Vault dev server...{Style.RESET_ALL}")
    print()
    
    # Start Vault
    if not docker_manager.up('vault-dev'):
        print(f"{Fore.RED}[ERROR] Failed to start Vault{Style.RESET_ALL}")
        sys.exit(1)
    
    print(f"{Fore.CYAN}Waiting for Vault to be ready...{Style.RESET_ALL}")
    time.sleep(2)
    
    # Check if Vault is unsealed
    max_retries = 30
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ['docker', 'exec', 'opencode-vault', 'vault', 'status'],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0 and 'Sealed' in result.stdout:
                if 'Sealed    false' in result.stdout or 'sealed=false' in result.stdout.lower():
                    print()
                    print(f"{Fore.GREEN}✓ Vault is running and unsealed{Style.RESET_ALL}")
                    print()
                    print(f"Vault Address: http://localhost:8200")
                    print(f"Root Token: root")
                    print()
                    print(f"{Fore.YELLOW}Add your secrets with:{Style.RESET_ALL}")
                    print(f"  docker exec opencode-vault vault kv put secret/opencode/openai api_key=sk-proj-...")
                    print(f"  docker exec opencode-vault vault kv put secret/opencode/anthropic api_key=sk-ant-...")
                    print(f"  docker exec opencode-vault vault kv put secret/opencode/github token=ghp_...")
                    print()
                    print(f"{Fore.YELLOW}Then run:{Style.RESET_ALL}")
                    print(f"  python run.py --workspace ./test-workspace --dev-mode --prompt 'your question'")
                    print()
                    print(f"{Fore.GRAY}Stop Vault with: docker compose down{Style.RESET_ALL}")
                    return 0
        except Exception:
            pass
        
        time.sleep(1)
    
    print(f"{Fore.RED}Timeout waiting for Vault to start{Style.RESET_ALL}")
    sys.exit(1)


if __name__ == '__main__':
    main()
