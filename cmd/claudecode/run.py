#!/usr/bin/env python3
"""
ClaudeCode Secure Sandbox Launcher - Cross-platform (Windows/macOS/Linux)

Run ClaudeCode CLI in a hardened container with Vault secrets management and Squid proxy.

Usage:
    python claudecode_run.py --workspace ./test-workspace --dev-mode
    python claudecode_run.py --workspace ./test-workspace --dev-mode --prompt "your question"
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Optional
import yaml
from colorama import Fore, Style, init

# Add lib to path so we can import shared modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
from vault_client import VaultClient
from docker_compose_manager import DockerComposeManager


# Initialize colorama for cross-platform colored output
init(autoreset=False)


def print_header(text: str):
    """Print a formatted header."""
    print()
    print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{text}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
    print()


def validate_workspace(workspace_path: str) -> str:
    """Validate and resolve workspace path.
    
    Args:
        workspace_path: Workspace directory path
        
    Returns:
        Absolute path to workspace
        
    Raises:
        ValueError if workspace doesn't exist
    """
    path = Path(workspace_path).resolve()
    
    if not path.exists():
        print(f"{Fore.RED}[ERROR] Workspace path does not exist: {workspace_path}{Style.RESET_ALL}")
        sys.exit(1)
    
    if not path.is_dir():
        print(f"{Fore.RED}[ERROR] Workspace path is not a directory: {workspace_path}{Style.RESET_ALL}")
        sys.exit(1)
    
    return str(path)


def load_secrets_config(config_path: str) -> list:
    """Load secrets configuration from YAML.
    
    Args:
        config_path: Path to YAML config file
        
    Returns:
        List of secret configs with normalized keys ('env' instead of 'env_var')
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
            # Handle nested structure: vault.secrets or just secrets
            secrets = config.get('vault', {}).get('secrets')
            if not secrets:
                secrets = config.get('secrets', [])
            
            # Normalize keys: convert 'env_var' to 'env' if needed
            normalized = []
            for secret in secrets:
                normalized_secret = {}
                normalized_secret['path'] = secret.get('path')
                normalized_secret['key'] = secret.get('key')
                # Handle both 'env' and 'env_var' keys
                normalized_secret['env'] = secret.get('env') or secret.get('env_var')
                normalized.append(normalized_secret)
            
            return normalized
    except Exception as e:
        print(f"{Fore.YELLOW}[WARN] Could not load secrets config: {e}{Style.RESET_ALL}")
        # Return default secrets list
        return [
            {'path': 'secret/opencode/openai', 'key': 'api_key', 'env': 'OPENAI_API_KEY'},
            {'path': 'secret/opencode/anthropic', 'key': 'api_key', 'env': 'ANTHROPIC_API_KEY'},
            {'path': 'secret/opencode/github', 'key': 'token', 'env': 'GITHUB_TOKEN'},
        ]


def fetch_secrets_from_vault(
    vault_addr: str,
    vault_token: str,
    secrets_config: list,
    mode: str = 'dev'
) -> Dict[str, str]:
    """Fetch secrets from Vault on the host machine.
    
    Args:
        vault_addr: Vault server address
        vault_token: Vault authentication token
        secrets_config: List of secret configs
        mode: 'dev' or 'prod' for logging
        
    Returns:
        Dict of environment variable names to values
    """
    print(f"{Fore.CYAN}Fetching secrets on host machine (Vault token never leaves your computer)...{Style.RESET_ALL}")
    print()
    
    vault = VaultClient(vault_addr, vault_token, mode=mode)
    
    if not vault.connect():
        print(f"{Fore.RED}[ERROR] Could not connect to Vault at {vault_addr}{Style.RESET_ALL}")
        sys.exit(1)
    
    print(f"{Fore.CYAN}Fetching secrets from Vault...{Style.RESET_ALL}")
    print(f"Mode: {Fore.CYAN}{mode.upper()}{Style.RESET_ALL}")
    print(f"Vault Address: {vault_addr}")
    if mode == 'dev':
        print(f"Auth Method: token (hardcoded 'root')")
    print()
    
    print(f"{Fore.CYAN}Fetching secrets...{Style.RESET_ALL}")
    secrets_env, _ = vault.fetch_secrets(secrets_config)
    
    print()
    
    return secrets_env


def set_environment_variables(secrets: Dict[str, str]):
    """Set environment variables in current process.
    
    Args:
        secrets: Dict of variable names to values
    """
    print(f"{Fore.CYAN}Setting secrets as environment variables...{Style.RESET_ALL}")
    
    for var_name, var_value in secrets.items():
        os.environ[var_name] = var_value
        print(f"  Set: {var_name}")
    
    print()
    print(f"{Fore.GREEN}Secrets loaded into environment (memory only){Style.RESET_ALL}")
    print(f"These will be passed to Docker and then cleared")
    print()


def clear_environment_variables(var_names: list):
    """Clear environment variables from current process.
    
    Args:
        var_names: List of variable names to clear
    """
    for var_name in var_names:
        if var_name in os.environ:
            del os.environ[var_name]
    
    print(f"{Fore.GREEN}Secrets cleared from memory{Style.RESET_ALL}")


def resolve_apparmor_profile(apparmor_arg: str) -> str:
    """Resolve user-provided AppArmor mode/name to concrete profile value.

    Supported aliases:
    - dev -> agent-dev
    - restricted -> agent-restricted
    - unconfined -> unconfined
    Any other value is passed through as-is.
    """
    profile = (apparmor_arg or 'unconfined').strip().lower()
    if profile == 'dev':
        return 'agent-dev'
    if profile == 'restricted':
        return 'agent-restricted'
    if profile == 'unconfined':
        return 'unconfined'
    return apparmor_arg.strip()


def run_claudecode(
    workspace_path: str,
    docker_manager: DockerComposeManager,
    secrets: Dict[str, str],
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    provider: str = 'claude',
    strict: bool = False,
    isolation_mode: str = 'none',
    apparmor_profile: str = 'unconfined',
    interactive: bool = False,
    view_logs: bool = False
):
    """Run the ClaudeCode container.
    
    Args:
        workspace_path: Path to workspace directory
        docker_manager: Docker Compose manager instance
        secrets: Dict of environment variables to pass
        prompt: Optional one-shot prompt
        interactive: Force interactive mode
        view_logs: Show logs after execution
    """
    # Set environment variables for docker-compose to use
    env = os.environ.copy()
    env.update(secrets)
    env['WORKSPACE_PATH'] = workspace_path
    env['OPENCODE_APPARMOR_PROFILE'] = apparmor_profile
    env['CLAUDECODE_APPARMOR_PROFILE'] = apparmor_profile
    
    if isolation_mode != 'none':
        image_name = 'claudecode-sandbox:1.0.98' if provider == 'claude' else 'opencode-sandbox:1.2.17'
        command = [
            'docker', 'run',
            '--rm',
            '--read-only',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=100m',
            '--tmpfs', '/home/opencodeuser/.local:rw,nosuid,size=64m' if provider == 'openai' else '/home/claudeuser/.local:rw,nosuid,size=64m',
            '--tmpfs', '/home/opencodeuser/.config:rw,nosuid,size=64m' if provider == 'openai' else '/home/claudeuser/.config:rw,nosuid,size=64m',
            '--tmpfs', '/home/opencodeuser/.cache:rw,nosuid,size=64m' if provider == 'openai' else '/home/claudeuser/.cache:rw,nosuid,size=64m',
            '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true',
            '--security-opt', f'apparmor={apparmor_profile}',
            '--pids-limit', '100',
            '--memory', '2g',
            '--cpus', '2',
            '-w', '/home/opencodeuser/workspace' if provider == 'openai' else '/home/claudeuser/workspace'
        ]

        if isolation_mode == 'full':
            command.extend(['--network', 'none'])
        else:
            command.extend(['--network', 'opencode-network'])

        for key, value in secrets.items():
            command.extend(['-e', f'{key}={value}'])

        if isolation_mode == 'fs':
            command.extend(['-e', 'HTTP_PROXY=http://squid-proxy:3128'])
            command.extend(['-e', 'HTTPS_PROXY=http://squid-proxy:3128'])
            command.extend(['-e', 'NO_PROXY=localhost,127.0.0.1'])

        command.append(image_name)
    else:
        # Build the docker-compose run command (matches PowerShell script)
        command = [
            'docker', 'compose',
            '-p', docker_manager.project_name,
            '-f', docker_manager.compose_file,
            'run',
            '--no-deps',
            '--rm'
        ]

        # Add -it for interactive if no prompt (matches PowerShell behavior)
        if not prompt:
            command.extend(['-it', '--service-ports'])

        service_name = 'claudecode' if provider == 'claude' else 'opencode'
        command.append(service_name)

    if model and provider == 'claude':
        command.extend(['--model', model])

    if provider == 'claude' or strict:
        disallowed_tools = ','.join([
            'Bash(curl:*)',
            'Bash(wget:*)',
            'Bash(nc:*)',
            'Bash(base64:*)',
            'Bash(python -c:*)',
            'Bash(node -e:*)',
            'Bash(bash -c:*)',
            'Bash(eval:*)',
            'Bash(sudo:*)'
        ])
        if provider == 'claude':
            command.extend(['--disallowedTools', disallowed_tools])
    
    # Add prompt if provided (one-shot mode)
    if prompt:
        if provider == 'claude':
            command.extend(['-p', prompt])
        else:
            command.extend(['run', prompt])
    
    print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
    if provider == 'claude':
        print(f"{Fore.CYAN}Starting ClaudeCode CLI{Style.RESET_ALL}")
    else:
        print(f"{Fore.CYAN}Starting OpenAI Compatibility Mode (OpenCode backend){Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
    print()
    
    print(f"Your code at: {workspace_path}")
    if isolation_mode == 'full':
        print(f"Network: Fully isolated (--network none)")
    elif isolation_mode == 'fs':
        print(f"Network: Proxied via Squid on isolated filesystem mode")
    else:
        print(f"Network: Proxied through Squid (see squid.conf for allowed domains)")
    print(f"Vault UI: http://localhost:8200 (token: root)")
    print()
    
    if prompt:
        print(f"Running in one-shot mode with prompt")
    else:
        print(f"ClaudeCode CLI Options:" if provider == 'claude' else "OpenAI Compatibility Options:")
        print(f"  Interactive Mode: Opens in container terminal")
        print(f"  One-Shot Mode: Pass prompt as argument")
        print(f"  Example: --prompt 'analyze this code'")
        print()
        print(f"Starting in interactive mode...")
        print(f"Type your prompts or 'exit' to quit")
    
    print()
    
    try:
        result = subprocess.run(command, env=env, check=False)
        return result.returncode
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to run container: {e}{Style.RESET_ALL}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='ClaudeCode Secure Sandbox Launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python claudecode_run.py --workspace ./test-workspace --dev-mode
    python claudecode_run.py --workspace ./test-workspace --dev-mode --prompt "write hello world"
    python claudecode_run.py --workspace ./code --prod-mode
        """
    )
    
    parser.add_argument(
        '--workspace',
        required=True,
        help='Path to workspace directory'
    )
    
    parser.add_argument(
        '--dev-mode',
        action='store_true',
        help='Use development mode (local Vault, no OIDC)'
    )
    
    parser.add_argument(
        '--prod-mode',
        action='store_true',
        help='Use production mode (OIDC, production Vault)'
    )
    
    parser.add_argument(
        '--prompt',
        help='One-shot prompt mode: provide a question for ClaudeCode'
    )

    parser.add_argument(
        '--explicit-path',
        help='Optional explicit host path to use as workspace (overrides --workspace)'
    )

    parser.add_argument(
        '--model',
        help='Claude model alias/name (e.g. sonnet, opus, claude-sonnet-4-20250514)'
    )

    parser.add_argument(
        '--provider',
        choices=['auto', 'claude', 'openai'],
        default='auto',
        help='Provider mode: auto-detect from secrets, force claude, or force openai compatibility mode'
    )

    parser.add_argument(
        '--strict',
        action='store_true',
        help='Enable strict runtime policy output and enforcement (Claude mode uses --disallowedTools; OpenAI mode uses OpenCode backend lockdown)'
    )

    parser.add_argument(
        '--isolated',
        action='store_true',
        help='Run fully isolated container (no host mount, no network)'
    )

    parser.add_argument(
        '--isolated-fs',
        action='store_true',
        help='Run with no host filesystem mount but keep proxied network access for inference'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Force interactive mode'
    )
    
    parser.add_argument(
        '--view-logs',
        action='store_true',
        help='Show container logs after execution'
    )
    
    parser.add_argument(
        '--no-rebuild',
        action='store_true',
        help='Skip rebuilding container images'
    )

    parser.add_argument(
        '--apparmor',
        default='unconfined',
        help='AppArmor profile: unconfined, dev, restricted, or a custom profile name'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.dev_mode and args.prod_mode:
        print(f"{Fore.RED}[ERROR] Cannot specify both --dev-mode and --prod-mode{Style.RESET_ALL}")
        sys.exit(1)
    
    if not args.dev_mode and not args.prod_mode:
        print(f"{Fore.RED}[ERROR] Must specify either --dev-mode or --prod-mode{Style.RESET_ALL}")
        sys.exit(1)

    if args.isolated and args.isolated_fs:
        print(f"{Fore.RED}[ERROR] Cannot use both --isolated and --isolated-fs{Style.RESET_ALL}")
        sys.exit(1)
    
    # Validate workspace
    selected_workspace = args.explicit_path if args.explicit_path else args.workspace
    workspace_path = validate_workspace(selected_workspace)
    
    # Determine mode
    mode = 'dev' if args.dev_mode else 'prod'
    
    print_header(f"ClaudeCode Secure Sandbox Launcher")

    resolved_apparmor_profile = resolve_apparmor_profile(args.apparmor)
    
    print(f"Workspace: {workspace_path}")
    print(f"Mode: {Fore.YELLOW}Development (using local Vault){Style.RESET_ALL}" if args.dev_mode else f"Mode: {Fore.GREEN}Production (using secrets-config.yaml){Style.RESET_ALL}")
    print(f"AppArmor: {resolved_apparmor_profile}")
    if args.isolated:
        print(f"Isolation: {Fore.YELLOW}FULL (no network, no host mount){Style.RESET_ALL}")
    elif args.isolated_fs:
        print(f"Isolation: {Fore.YELLOW}FS-ONLY (no host mount, proxied network){Style.RESET_ALL}")
    print()
    
    # Get project directory (where docker-compose.yml is)
    # Get project root directory (parent of cmd/)
    project_dir = Path(__file__).parent.parent.parent
    docker_manager = DockerComposeManager(str(project_dir))
    
    try:
        # Build images if not skipped
        if not args.no_rebuild:
            build_target = 'claudecode' if args.provider in ['auto', 'claude'] else 'opencode'
            if not docker_manager.build(build_target):
                print(f"{Fore.RED}[ERROR] Failed to build images{Style.RESET_ALL}")
                sys.exit(1)
            print()
        
        # Check/start Vault in dev mode
        if args.dev_mode:
            print(f"{Fore.CYAN}Checking local Vault dev server...{Style.RESET_ALL}")
            
            if docker_manager.is_running('opencode-vault'):
                print(f"{Fore.GREEN}Vault is running and ready{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}ERROR: Vault is not running!{Style.RESET_ALL}")
                print()
                print(f"To start Vault in dev mode, run:")
                print(f"  python start_vault.py")
                print()
                sys.exit(1)
            
            print()
        
        # Check/start Squid proxy
        print(f"{Fore.CYAN}Checking Squid proxy...{Style.RESET_ALL}")
        
        if docker_manager.is_running('opencode-squid'):
            print(f"{Fore.GREEN}Squid is already running{Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}Starting Squid proxy for network policy enforcement...{Style.RESET_ALL}")
            
            if not docker_manager.up('squid-proxy'):
                print(f"{Fore.RED}[ERROR] Failed to start Squid proxy{Style.RESET_ALL}")
                sys.exit(1)
            
            # Give Squid a moment to start
            print(f"{Fore.CYAN}Waiting for proxy to start...{Style.RESET_ALL}")
            import time
            time.sleep(3)
            print(f"{Fore.GREEN}Proxy ready{Style.RESET_ALL}")
        
        print()
        
        # Fetch secrets from Vault on host machine
        print(f"{Fore.CYAN}Fetching secrets on host machine (Vault token never leaves your computer)...{Style.RESET_ALL}")
        print()
        print(f"{Fore.CYAN}Fetching secrets from Vault...{Style.RESET_ALL}")
        print(f"Mode: {Fore.CYAN}{mode.upper()}{Style.RESET_ALL}")
        
        vault_addr = 'http://localhost:8200'
        vault_token = 'root' if args.dev_mode else os.environ.get('VAULT_TOKEN', '')
        
        # Try to find vault CLI
        vault_cli = 'vault'  # Default to PATH
        # Check if user has vault in Downloads (common location)
        vault_download_path = Path.home() / 'Downloads' / 'vault_1.20.0_windows_amd64' / 'vault.exe'
        if vault_download_path.exists():
            vault_cli = str(vault_download_path)
        
        # Point to config subdirectories
        config_subdir = 'dev' if args.dev_mode else 'prod'
        secrets_config_filename = 'secrets-config.claudecode.dev.yaml' if args.dev_mode else 'secrets-config.claudecode.yaml'
        secrets_config_path = project_dir / 'config' / config_subdir / secrets_config_filename
        
        secrets_config = load_secrets_config(str(secrets_config_path))
        
        print(f"[DEBUG] Loaded {len(secrets_config)} secrets from config")
        for secret in secrets_config:
            print(f"[DEBUG]   - {secret.get('env')}: {secret.get('path')}")
        
        vault = VaultClient(vault_addr, vault_token, mode, vault_cli_path=vault_cli)
        
        if not vault.connect():
            print(f"{Fore.RED}[ERROR] Could not connect to Vault at {vault_addr}{Style.RESET_ALL}")
            sys.exit(1)
        
        print(f"{Fore.CYAN}Fetching secrets...{Style.RESET_ALL}")
        secrets, _ = vault.fetch_secrets(secrets_config)
        
        if not secrets:
            print(f"{Fore.YELLOW}[WARN] No secrets fetched from Vault{Style.RESET_ALL}")

        effective_provider = args.provider
        if effective_provider == 'auto':
            if secrets.get('ANTHROPIC_API_KEY'):
                effective_provider = 'claude'
            elif secrets.get('OPENAI_API_KEY'):
                effective_provider = 'openai'
            else:
                print(f"{Fore.RED}[ERROR] No usable API key found (need ANTHROPIC_API_KEY or OPENAI_API_KEY){Style.RESET_ALL}")
                sys.exit(1)

        if args.model and args.model.lower().startswith('openai/') and args.provider == 'auto':
            effective_provider = 'openai'

        if effective_provider == 'claude' and (not secrets.get('ANTHROPIC_API_KEY')):
            print(f"{Fore.RED}[ERROR] ANTHROPIC_API_KEY is required for ClaudeCode mode but was not found in Vault{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Use --provider openai to run OpenAI compatibility mode with OpenCode backend{Style.RESET_ALL}")
            sys.exit(1)

        if effective_provider == 'openai' and (not secrets.get('OPENAI_API_KEY')):
            print(f"{Fore.RED}[ERROR] OPENAI_API_KEY is required for OpenAI compatibility mode but was not found in Vault{Style.RESET_ALL}")
            sys.exit(1)

        print(f"{Fore.CYAN}Provider selected: {effective_provider}{Style.RESET_ALL}")
        if args.strict:
            print(f"{Fore.CYAN}Strict mode: enabled{Style.RESET_ALL}")
            if effective_provider == 'claude':
                print(f"{Fore.CYAN}Runtime policy: applying --disallowedTools denylist{Style.RESET_ALL}")
            else:
                print(f"{Fore.CYAN}Runtime policy: OpenCode backend lockdown policy active (opencode.json + container restrictions){Style.RESET_ALL}")
        
        print()
        
        # Set environment variables
        set_environment_variables(secrets)
        
        isolation_mode = 'none'
        if args.isolated:
            isolation_mode = 'full'
        elif args.isolated_fs:
            isolation_mode = 'fs'

        # Run ClaudeCode
        exit_code = run_claudecode(
            workspace_path,
            docker_manager,
            secrets,
            prompt=args.prompt,
            model=args.model,
            provider=effective_provider,
            strict=args.strict,
            isolation_mode=isolation_mode,
            apparmor_profile=resolved_apparmor_profile,
            interactive=args.interactive,
            view_logs=args.view_logs
        )
        
        # Show logs if requested
        if args.view_logs:
            print()
            print(f"{Fore.CYAN}Proxy access logs:{Style.RESET_ALL}")
            docker_manager.logs('squid-proxy')
        
    finally:
        # Clean up secrets from environment
        print()
        print(f"{Fore.CYAN}Cleaning up secrets from environment...{Style.RESET_ALL}")
        clear_environment_variables(['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GITHUB_TOKEN', 'VAULT_TOKEN'])
        
        # Keep Vault and Squid running in dev mode
        if args.dev_mode:
            print()
            print(f"{Fore.CYAN}Cleaning up containers...{Style.RESET_ALL}")
            print(f"{Fore.GREEN}Vault and Squid will remain running for next test{Style.RESET_ALL}")
            print(f"(Stop them with: docker compose down)")
        else:
            # In production, clean everything
            docker_manager.down()
        
        print()
        print(f"{Fore.GREEN}Done{Style.RESET_ALL}")
    
    sys.exit(exit_code if exit_code == 0 else 1)


if __name__ == '__main__':
    main()
