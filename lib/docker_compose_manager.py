"""
Docker Compose helper for running containers.
"""

import subprocess
import os
import sys
import time
from typing import Optional, List
from colorama import Fore, Style


class DockerComposeManager:
    """Manage Docker Compose operations."""

    def __init__(self, project_dir: str):
        """Initialize Docker Compose manager.
        
        Args:
            project_dir: Path to directory containing docker-compose.yml
        """
        self.project_dir = project_dir
        self.compose_file = os.path.join(project_dir, '.docker-compose', 'docker-compose.base.yml')
        self.project_name = 'opencode'

    def run_command(self, command: List[str], check: bool = True) -> int:
        """Run a docker-compose command.
        
        Args:
            command: Command list (e.g., ['build', 'opencode'])
            check: If True, raise on non-zero exit code
            
        Returns:
            Exit code
        """
        full_command = ['docker', 'compose', '-p', self.project_name, '-f', self.compose_file] + command
        
        try:
            result = subprocess.run(
                full_command,
                cwd=self.project_dir,
                check=False
            )
            
            if check and result.returncode != 0:
                print(f"{Fore.RED}[ERROR] Command failed: {' '.join(full_command)}{Style.RESET_ALL}")
                return result.returncode
            
            return result.returncode
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to run command: {e}{Style.RESET_ALL}")
            return 1

    def build(self, service: str = None, no_cache: bool = False) -> bool:
        """Build a service or all services.
        
        Args:
            service: Service name, or None for all
            no_cache: Skip Docker cache
            
        Returns:
            True if successful
        """
        command = ['build']
        
        if no_cache:
            command.append('--no-cache')
        
        if service:
            command.append(service)
        
        print(f"{Fore.CYAN}Building container images...{Style.RESET_ALL}")
        return self.run_command(command) == 0

    def up(self, service: str = None, detach: bool = True) -> bool:
        """Start services.
        
        Args:
            service: Service name, or None for all
            detach: Run in background
            
        Returns:
            True if successful
        """
        command = ['up']
        
        if detach:
            command.append('-d')
        
        if service:
            command.append(service)
        
        return self.run_command(command) == 0

    def down(self) -> bool:
        """Stop and remove all containers.
        
        Returns:
            True if successful
        """
        print(f"{Fore.CYAN}Stopping containers...{Style.RESET_ALL}")
        return self.run_command(['down']) == 0

    def is_running(self, container_name: str) -> bool:
        """Check if a container is running.
        
        Args:
            container_name: Name of the container
            
        Returns:
            True if running
        """
        try:
            result = subprocess.run(
                ['docker', 'ps', '--filter', f'name={container_name}', '--filter', 'status=running', '-q'],
                capture_output=True,
                text=True,
                check=False
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def wait_for_container(self, container_name: str, max_retries: int = 30, interval: int = 1) -> bool:
        """Wait for a container to be healthy.
        
        Args:
            container_name: Name of the container
            max_retries: Max number of health checks
            interval: Seconds between checks
            
        Returns:
            True if container became healthy
        """
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ['docker', 'inspect', '--format={{.State.Health.Status}}', container_name],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5  # Add timeout to prevent hanging
                )
                
                status = result.stdout.strip()
                
                if status == 'healthy':
                    return True
                
                # If no healthcheck is defined, check if container is running
                if not status or 'no value' in status.lower():
                    result = subprocess.run(
                        ['docker', 'ps', '--filter', f'name={container_name}', '--filter', 'status=running', '-q'],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=5
                    )
                    if result.stdout.strip():
                        return True
                
                if attempt < max_retries - 1:
                    time.sleep(interval)
            except subprocess.TimeoutExpired:
                print(f"{Fore.YELLOW}[WARN] Health check timeout for {container_name}{Style.RESET_ALL}")
                return False
            except Exception:
                pass
        
        return False

    def exec(self, container_name: str, command: List[str]) -> int:
        """Execute a command in a running container.
        
        Args:
            container_name: Name of the container
            command: Command to execute
            
        Returns:
            Exit code
        """
        full_command = ['docker', 'exec', container_name] + command
        
        try:
            result = subprocess.run(full_command, check=False)
            return result.returncode
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to exec: {e}{Style.RESET_ALL}")
            return 1

    def logs(self, service: str = None) -> int:
        """Show container logs.
        
        Args:
            service: Service name, or None for all
            
        Returns:
            Exit code
        """
        command = ['logs']
        
        if service:
            command.append(service)
        
        return self.run_command(command, check=False)
