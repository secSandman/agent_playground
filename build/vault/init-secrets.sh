#!/bin/sh
#
# Initialize Vault with test secrets for local development
# This script runs inside the vault-dev container after Vault is ready
#

set -e

export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='root'

echo "Enabling KV secrets engine v2..."
vault secrets enable -version=2 -path=secret kv 2>/dev/null || echo "KV engine already enabled"

echo "Creating test secrets at secret/opencode/* (if not already present)..."

# Create test OpenAI API key ONLY if it doesn't exist
if ! vault kv get secret/opencode/openai > /dev/null 2>&1; then
    echo "Initializing secret/opencode/openai with test values..."
    vault kv put secret/opencode/openai \
        api_key="sk-test-openai-key-12345" \
        org_id="org-test-12345"
else
    echo "secret/opencode/openai already exists, skipping initialization"
fi

# Create test Anthropic API key ONLY if it doesn't exist
if ! vault kv get secret/opencode/anthropic > /dev/null 2>&1; then
    echo "Initializing secret/opencode/anthropic with test values..."
    vault kv put secret/opencode/anthropic \
        api_key="sk-ant-test-key-67890"
else
    echo "secret/opencode/anthropic already exists, skipping initialization"
fi

# Create test GitHub token ONLY if it doesn't exist
if ! vault kv get secret/opencode/github > /dev/null 2>&1; then
    echo "Initializing secret/opencode/github with test values..."
    vault kv put secret/opencode/github \
        token="ghp_test_token_abcdefghijklmnopqrstuvwxyz"
else
    echo "secret/opencode/github already exists, skipping initialization"
fi

echo "Test secrets initialized successfully!"
echo ""
echo "Available secrets:"
vault kv list secret/opencode 2>/dev/null || echo "(no secrets found)"

echo ""
echo "To read a secret:"
echo "  vault kv get secret/opencode/openai"
