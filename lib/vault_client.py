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

    def __init__(self, vault_addr: str, vault_token: str, mode: str = "dev", vault_cli_path: str = "vault",
                 vault_namespace: str = "", oidc_role: str = "", oidc_mount: str = "oidc",
                 oidc_auth_namespace: str = ""):
        self.vault_addr = vault_addr
        self.vault_token = vault_token
        self.mode = mode
        self.vault_cli_path = vault_cli_path
        self.vault_namespace = vault_namespace
        self.oidc_role = oidc_role
        self.oidc_mount = oidc_mount
        self.oidc_auth_namespace = oidc_auth_namespace  # root namespace for OIDC login

        os.environ['VAULT_ADDR'] = vault_addr
        if vault_namespace:
            os.environ['VAULT_NAMESPACE'] = vault_namespace
        if vault_token:
            os.environ['VAULT_TOKEN'] = vault_token
        # Set an empty VAULT_TOKEN so vault CLI doesn't fall back to reading
        # ~/.vault-token (which fails on Windows with "Incorrect function")
        elif 'VAULT_TOKEN' not in os.environ:
            os.environ['VAULT_TOKEN'] = ''
        # Disable the file-based token helper — avoids Windows pipe/file errors
        # with ~/.vault-token on certain filesystem configurations
        os.environ['VAULT_TOKEN_HELPER'] = ''

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

    def login_oidc(self) -> bool:
        """Trigger OIDC browser login and capture the resulting token."""
        import json, shutil
        from pathlib import Path

        print(f"{Fore.CYAN}Authenticating to Vault via OIDC (role={self.oidc_role})...{Style.RESET_ALL}")

        # Build a clean env for the vault subprocess so the token helper
        # never tries to read a stale/corrupt ~/.vault-token before login.
        vault_env = os.environ.copy()
        vault_env['VAULT_ADDR'] = self.vault_addr
        vault_env['VAULT_TOKEN'] = ''          # clear so helper is not consulted
        # Keep namespace out of env for login; pass it explicitly as CLI arg.
        vault_env.pop('VAULT_NAMESPACE', None)

        # Only pass -path if the mount name differs from the method name.
        # `-method=oidc` already routes to /auth/oidc/; adding `-path=oidc`
        # would double it to /auth/oidc/oidc/ and cause a 403.
        cmd = [self.vault_cli_path, 'login', '-method=oidc', '-format=json']
        if self.oidc_auth_namespace:
            cmd.append(f'-namespace={self.oidc_auth_namespace}')
        if self.oidc_mount and self.oidc_mount != 'oidc':
            cmd.append(f'-path={self.oidc_mount}')
        cmd.append(f'role={self.oidc_role}')

        try:
            # Run interactively (no capture) so the browser callback URL is visible
            result = subprocess.run(cmd, env=vault_env, check=False, timeout=120,
                                    capture_output=True, text=True)

            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    token = data.get('auth', {}).get('client_token', '').strip()
                    if token:
                        self.vault_token = token
                        os.environ['VAULT_TOKEN'] = token
                        print(f"{Fore.GREEN}[OK] OIDC login successful{Style.RESET_ALL}")
                        return True
                except json.JSONDecodeError:
                    pass

            # Fallback: vault wrote token to ~/.vault-token (non -no-store path)
            token_file = Path.home() / '.vault-token'
            if token_file.is_file():
                token = token_file.read_text().strip()
                if token:
                    self.vault_token = token
                    os.environ['VAULT_TOKEN'] = token
                    print(f"{Fore.GREEN}[OK] OIDC login successful (token from file){Style.RESET_ALL}")
                    return True

            print(f"{Fore.RED}[ERROR] OIDC login failed: {result.stderr.strip()}{Style.RESET_ALL}")
            return False

        except subprocess.TimeoutExpired:
            print(f"{Fore.RED}[ERROR] OIDC login timed out (120s){Style.RESET_ALL}")
            return False
        except Exception as e:
            print(f"{Fore.RED}[ERROR] OIDC login error: {e}{Style.RESET_ALL}")
            return False

    def fetch_secret(self, path: str, key: str) -> Optional[str]:
        """Fetch a single secret from Vault.

        Path may be a full KV v2 mount-prefix path like 'Secrets/kv/opencode/openai'.
        Splits on first two segments to derive -mount and sub-path automatically.
        """
        try:
            # Path format from config: '<mount>/<sub-path>', e.g. 'kv/opencode/openai'
            # vault kv get requires: -mount=<mount> -namespace=<ns> <sub-path>
            parts = path.split('/', 1)
            if len(parts) == 2:
                mount, sub_path = parts
                cmd = [self.vault_cli_path, 'kv', 'get',
                       f'-mount={mount}',
                       f'-field={key}',
                       sub_path]
            else:
                cmd = [self.vault_cli_path, 'kv', 'get', f'-field={key}', path]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)

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
