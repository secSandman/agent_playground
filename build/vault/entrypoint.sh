#!/bin/sh

# Start Vault in simple dev mode (in-memory, clean for testing)
vault server -dev \
  -dev-listen-address=0.0.0.0:8200 \
  -dev-root-token-id=root
