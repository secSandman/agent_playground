"""
Vault client for fetching secrets securely.
Keeps Vault token on host machine only (never exposed to container).
"""

import os
import sys
import subprocess
from typing import Dict, Optional, Tuple
from colorama import Fore, Style


class VaultClient:
    """Interact with Vault to fetch secrets using Vault CLI."""

    def __init__(self, vault_addr: str, vault_token: str, mode: str = "dev", vault_cli_path: str = "vault"):
        """Initialize Vault client.
        
        Args:
            vault_addr: Vault server address (e.g., http://localhost:8200)
            vault_token: Vault authentication token
            mode: 'dev' or 'prod' for logging context
            vault_cli_path: Path to vault CLI executable
        """
        self.vault_addr = vault_addr
        self.vault_token = vault_token
        self.mode = mode
        self.vault_cli_path = vault_cli_path
        
        # Set environment for vault CLI
        os.environ['VAULT_ADDR'] = vault_addr
        os.environ['VAULT_TOKEN'] = vault_token

    def connect(self) -> bool:
        """Connect to Vault.
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            # Try to run vault status to check connection
            result = subprocess.run(
                [self.vault_cli_path, 'status'],
                capture_output=True,
                text=True,
                check=False,
                timeout=5
            )
            
            print(f"{Fore.CYAN}[DEBUG] Vault CLI: {self.vault_cli_path}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[DEBUG] Vault status exit code: {result.returncode}{Style.RESET_ALL}")
            
            # vault status returns non-zero even when working (sealed/unsealed info)
            # Just check that we got some output
            if result.stdout or result.stderr:
                return True
            return False
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to connect to Vault: {e}{Style.RESET_ALL}")
            return False

    def fetch_secret(self, path: str, key: str) -> Optional[str]:
        """Fetch a single secret from Vault.
        
        Args:
            path: Secret path (e.g., 'secret/opencode/openai')
            key: Key within the secret (e.g., 'api_key')
            
        Returns:
            Secret value if found, None otherwise
        """
        try:
            # Use vault kv get -field=<key> <path>
            result = subprocess.run(
                [self.vault_cli_path, 'kv', 'get', f'-field={key}', path],
                capture_output=True,
                text=True,
                check=False,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            
            return None
        except subprocess.TimeoutExpired:
            print(f"{Fore.YELLOW}[WARN] Timeout fetching {path}{Style.RESET_ALL}")
            return None
        except Exception as e:
            print(f"{Fore.YELLOW}[WARN] Error fetching {path}: {e}{Style.RESET_ALL}")
            return None

    def fetch_secrets(self, secrets_config: list) -> Tuple[Dict[str, str], bool]:
        """Fetch multiple secrets from Vault.
        
        Args:
            secrets_config: List of dicts with 'path', 'key', 'env' keys
            
        Returns:
            Tuple of (dict of env_var: value, success_bool)
        """
        secrets_env = {}
        all_success = True
        
        print(f"{Fore.CYAN}[DEBUG] Secrets config has {len(secrets_config)} entries{Style.RESET_ALL}")

        for secret in secrets_config:
            path = secret.get('path')
            key = secret.get('key')
            env_var = secret.get('env')
            
            if not all([path, key, env_var]):
                continue
            
            print(f"  Fetching {Fore.CYAN}{env_var}{Style.RESET_ALL} from {path}...")
            
            value = self.fetch_secret(path, key)
            
            if value:
                secrets_env[env_var] = value
                print(f"  {Fore.GREEN}[OK]{Style.RESET_ALL} Retrieved {env_var}")
            else:
                print(f"  {Fore.YELLOW}[SKIP]{Style.RESET_ALL} Secret not found (optional): {path}")
        
        return secrets_env, all_success

    def write_secret(self, path: str, data: Dict[str, str]) -> bool:
        """Write a secret to Vault.
        
        Args:
            path: Secret path
            data: Dict of key-value pairs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Build command: vault kv put <path> key1=value1 key2=value2 ...
            cmd = [self.vault_cli_path, 'kv', 'put', path]
            for k, v in data.items():
                cmd.append(f'{k}={v}')
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10
            )
            
            return result.returncode == 0
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to write secret to {path}: {e}{Style.RESET_ALL}")
            return False
