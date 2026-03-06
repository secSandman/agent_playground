.PHONY: help setup clean test dev-start dev-stop vault-start vault-stop proxy-logs opencode claudecode

help:
	@echo "OpenCode Secure Sandbox - Development Commands"
	@echo ""
	@echo "Getting Started:"
	@echo "  make setup              Install Python dependencies"
	@echo "  make dev-start          Start Vault in development mode"
	@echo ""
	@echo "Running OpenCode:"
	@echo "  make opencode           Run OpenCode with Python CLI"
	@echo "  make claudecode         Run ClaudeCode with Python CLI"
	@echo ""
	@echo "Vault Commands:"
	@echo "  make vault-start        Start Vault dev server"
	@echo "  make vault-stop         Stop Vault dev server"
	@echo ""
	@echo "Docker/Container Management:"
	@echo "  make down               Stop all containers"
	@echo "  make proxy-logs         View Squid proxy logs"
	@echo "  make clean              Clean up test workspace and artifacts"
	@echo ""

setup:
	pip install --only-binary :all: -r requirements.txt

# Development mode startup
dev-start: vault-start
	@echo "Development environment started"
	@echo "  Vault UI: http://localhost:8200"
	@echo "  Vault Token: root"
	@echo ""
	@echo "Run 'make opencode' to start OpenCode"

# Vault management
vault-start:
	python start_vault.py

vault-stop:
	docker compose -f .docker-compose/docker-compose.base.yml down opencode-vault

# Run OpenCode
opencode:
	python opencode_run.py --workspace ./test-workspace --dev-mode --no-rebuild

claudecode:
	python claudecode_run.py --workspace ./test-workspace --dev-mode --no-rebuild

# Container management
down:
	docker compose -f .docker-compose/docker-compose.base.yml down

proxy-logs:
	docker compose -f .docker-compose/docker-compose.base.yml logs -f opencode-squid

# Cleanup
clean:
	rm -rf test-workspace/*
	rm -f opencode-secrets.env
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Testing
test:
	pytest testing/ -v

test-unit:
	pytest testing/unit/ -v

test-integration:
	pytest testing/integration/ -v

test-e2e:
	pytest testing/e2e/ -v
