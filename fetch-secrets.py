#!/usr/bin/env python3
"""
Secrets Fetcher for OpenCode Container
Retrieves API credentials from various secrets management platforms
Supports: Static env vars, HashiCorp Vault, AWS Secrets Manager
"""

import os
import sys
import json
import yaml
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class SecretsManager:
    """Base class for secrets management"""
    
    def __init__(self, config: dict):
        self.config = config
        self.security = config.get('security', {})
        self.audit_log = self.security.get('audit_log', False)
        self.audit_log_path = self.security.get('audit_log_path', '/var/log/opencode/secrets-audit.log')
    
    def audit(self, message: str):
        """Log audit message"""
        if self.audit_log:
            try:
                os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
                with open(self.audit_log_path, 'a') as f:
                    f.write(f"{message}\n")
            except Exception as e:
                logger.warning(f"Failed to write audit log: {e}")
    
    def fetch_secrets(self) -> Dict[str, str]:
        """Fetch secrets and return as dict of env_var: value"""
        raise NotImplementedError


class StaticSecretsManager(SecretsManager):
    """Static environment variable based secrets"""
    
    def fetch_secrets(self) -> Dict[str, str]:
        logger.info("Using static API keys from environment variables")
        static_config = self.config.get('static', {})
        secrets = {}
        
        for key, value in static_config.items():
            # Expand environment variables
            expanded = os.path.expandvars(value)
            if expanded and not expanded.startswith('${'):
                env_var = key.upper()
                secrets[env_var] = expanded
                self.audit(f"Loaded static secret: {env_var}")
                logger.info(f"Loaded: {env_var}")
            else:
                logger.warning(f"Missing environment variable for: {key}")
        
        return secrets


class VaultSecretsManager(SecretsManager):
    """HashiCorp Vault secrets manager"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.vault_config = config.get('vault', {})
        self.vault_addr = self.vault_config.get('addr')
        self.auth_method = self.vault_config.get('auth_method', 'token')
        self.namespace = self.vault_config.get('namespace', '')
        
        if not self.vault_addr:
            raise ValueError("vault.addr is required when using vault provider")
        
        os.environ['VAULT_ADDR'] = self.vault_addr
        if self.namespace:
            os.environ['VAULT_NAMESPACE'] = self.namespace
            logger.info(f"Vault namespace: {self.namespace}")
    
    def authenticate(self) -> str:
        """Authenticate to Vault and return token"""
        logger.info(f"Authenticating to Vault using {self.auth_method}")
        
        if self.auth_method == 'token':
            return self._auth_token()
        elif self.auth_method == 'oidc':
            return self._auth_oidc()
        elif self.auth_method == 'kubernetes':
            return self._auth_kubernetes()
        elif self.auth_method == 'approle':
            return self._auth_approle()
        else:
            raise ValueError(f"Unsupported auth method: {self.auth_method}")
    
    def _auth_token(self) -> str:
        """Use existing token"""
        token = self.vault_config.get('token', {}).get('token')
        if not token:
            token = os.environ.get('VAULT_TOKEN')
        if not token:
            # Try reading from ~/.vault-token
            token_file = Path.home() / '.vault-token'
            if token_file.exists():
                token = token_file.read_text().strip()
        
        if not token:
            raise ValueError("No vault token found")
        
        self.audit(f"Using Vault token authentication")
        return token
    
    def _auth_oidc(self) -> str:
        """Authenticate using OIDC (e.g. Entra ID via HCP Vault)"""
        role = self.vault_config.get('oidc', {}).get('role', '').strip()
        mount_path = self.vault_config.get('oidc', {}).get('mount_path', 'oidc')

        logger.info(f"Starting OIDC authentication — mount={mount_path}, role={role or '(default)'}")
        logger.info("This will open your browser for authentication...")

        cmd = ['vault', 'login', f'-method=oidc', f'-path={mount_path}', '-no-store', '-format=json']
        if role:
            cmd.append(f'role={role}')
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            login_data = json.loads(result.stdout)
            token = login_data.get('auth', {}).get('client_token', '').strip()
            if token:
                role_msg = f"role: {role}" if role else "default role"
                self.audit(f"OIDC authentication successful for {role_msg}")
                return token

            raise ValueError("OIDC login succeeded but no token in auth.client_token")
        except subprocess.CalledProcessError as e:
            logger.error(f"OIDC authentication failed: {e.stderr}")
            raise
    
    def _auth_kubernetes(self) -> str:
        """Authenticate using Kubernetes service account"""
        k8s_config = self.vault_config.get('kubernetes', {})
        role = k8s_config.get('role')
        mount_path = k8s_config.get('mount_path', 'kubernetes')
        jwt_path = k8s_config.get('service_account_token_path', 
                                   '/var/run/secrets/kubernetes.io/serviceaccount/token')
        
        if not os.path.exists(jwt_path):
            raise ValueError(f"Kubernetes service account token not found at: {jwt_path}")
        
        jwt = Path(jwt_path).read_text().strip()
        
        cmd = [
            'vault', 'write', '-field=token',
            f'auth/{mount_path}/login',
            f'role={role}',
            f'jwt={jwt}'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            token = result.stdout.strip()
            self.audit(f"Kubernetes authentication successful for role: {role}")
            return token
        except subprocess.CalledProcessError as e:
            logger.error(f"Kubernetes authentication failed: {e.stderr}")
            raise
    
    def _auth_approle(self) -> str:
        """Authenticate using AppRole"""
        approle_config = self.vault_config.get('approle', {})
        role_id = os.path.expandvars(approle_config.get('role_id', ''))
        secret_id = os.path.expandvars(approle_config.get('secret_id', ''))
        mount_path = approle_config.get('mount_path', 'approle')
        
        if not role_id or not secret_id:
            raise ValueError("AppRole requires both role_id and secret_id")
        
        cmd = [
            'vault', 'write', '-field=token',
            f'auth/{mount_path}/login',
            f'role_id={role_id}',
            f'secret_id={secret_id}'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            token = result.stdout.strip()
            self.audit(f"AppRole authentication successful")
            return token
        except subprocess.CalledProcessError as e:
            logger.error(f"AppRole authentication failed: {e.stderr}")
            raise
    
    def fetch_secrets(self) -> Dict[str, str]:
        """Fetch secrets from Vault"""
        # Authenticate
        token = self.authenticate()
        os.environ['VAULT_TOKEN'] = token
        
        secrets = {}
        secret_paths = self.vault_config.get('secrets', [])
        
        for secret_config in secret_paths:
            path = secret_config.get('path')
            key = secret_config.get('key')
            env_var = secret_config.get('env_var')
            
            if not all([path, key, env_var]):
                logger.warning(f"Incomplete secret config: {secret_config}")
                continue
            
            try:
                # Read secret from Vault
                cmd = ['vault', 'kv', 'get', '-field', key, path]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                value = result.stdout.strip()
                
                if value:
                    secrets[env_var] = value
                    self.audit(f"Retrieved secret from Vault: {path} -> {env_var}")
                    logger.info(f"Retrieved: {env_var} from {path}")
                else:
                    logger.warning(f"Empty value for {env_var} at {path}")
                    
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to read {path}: {e.stderr}")
                if self.security.get('strict_mode', True):
                    raise
        
        return secrets


class AWSSecretsManager(SecretsManager):
    """AWS Secrets Manager"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.aws_config = config.get('aws_secrets_manager', {})
        self.region = self.aws_config.get('region', 'us-east-1')
        
        try:
            import boto3
            self.client = boto3.client('secretsmanager', region_name=self.region)
        except ImportError:
            raise ImportError("boto3 is required for AWS Secrets Manager. Install: pip install boto3")
    
    def fetch_secrets(self) -> Dict[str, str]:
        """Fetch secrets from AWS Secrets Manager"""
        logger.info("Fetching secrets from AWS Secrets Manager")
        
        secrets = {}
        secret_configs = self.aws_config.get('secrets', [])
        
        for config in secret_configs:
            secret_id = config.get('secret_id')
            key = config.get('key')
            env_var = config.get('env_var')
            
            if not all([secret_id, env_var]):
                logger.warning(f"Incomplete AWS secret config: {config}")
                continue
            
            try:
                response = self.client.get_secret_value(SecretId=secret_id)
                secret_data = json.loads(response['SecretString'])
                
                if key:
                    value = secret_data.get(key)
                else:
                    value = secret_data
                
                if value:
                    secrets[env_var] = str(value)
                    self.audit(f"Retrieved secret from AWS: {secret_id} -> {env_var}")
                    logger.info(f"Retrieved: {env_var} from {secret_id}")
                else:
                    logger.warning(f"Key {key} not found in {secret_id}")
                    
            except Exception as e:
                logger.error(f"Failed to read AWS secret {secret_id}: {e}")
                if self.security.get('strict_mode', True):
                    raise
        
        return secrets


def load_config(config_path: str = '/config/secrets-config.yaml') -> dict:
    """Load secrets configuration from YAML file"""
    # Try multiple locations
    search_paths = [
        config_path,
        './secrets-config.yaml',
        '/etc/opencode/secrets-config.yaml',
        os.path.expanduser('~/.opencode/secrets-config.yaml')
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            logger.info(f"Loading config from: {path}")
            with open(path, 'r') as f:
                return yaml.safe_load(f)
    
    raise FileNotFoundError(f"secrets-config.yaml not found in: {search_paths}")


def get_secrets_manager(config: dict) -> SecretsManager:
    """Factory function to get appropriate secrets manager"""
    provider = config.get('provider', 'static')
    
    if provider == 'static':
        return StaticSecretsManager(config)
    elif provider == 'vault':
        return VaultSecretsManager(config)
    elif provider == 'aws-secrets-manager':
        return AWSSecretsManager(config)
    else:
        raise ValueError(f"Unknown secrets provider: {provider}")


def export_to_env_file(secrets: Dict[str, str], output_path: str = '/tmp/opencode-secrets.env'):
    """Export secrets to environment file for docker"""
    with open(output_path, 'w') as f:
        for key, value in secrets.items():
            # Escape special characters for shell
            escaped_value = value.replace('"', '\\"')
            f.write(f'{key}="{escaped_value}"\n')
    
    # Secure the file
    os.chmod(output_path, 0o600)
    logger.info(f"Secrets written to: {output_path}")


def main():
    """Main entry point"""
    try:
        # Load configuration
        config_path = os.environ.get('SECRETS_CONFIG', '/config/secrets-config.yaml')
        config = load_config(config_path)
        
        # Get secrets manager
        manager = get_secrets_manager(config)
        
        # Fetch secrets
        secrets = manager.fetch_secrets()
        
        if not secrets:
            logger.warning("No secrets retrieved!")
            return 1
        
        logger.info(f"Successfully retrieved {len(secrets)} secret(s)")
        
        # Export to environment file
        output_path = os.environ.get('SECRETS_OUTPUT', '/tmp/opencode-secrets.env')
        export_to_env_file(secrets, output_path)
        
        # Also export to current process env (for local use)
        for key, value in secrets.items():
            os.environ[key] = value
        
        logger.info("Secrets loaded successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
