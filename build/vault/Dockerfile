# ============================================================
# Vault Dev Server for Local Testing
# DO NOT USE IN PRODUCTION - This is for development only!
# ============================================================

FROM hashicorp/vault:1.18

# Copy scripts
COPY init-secrets.sh /vault/scripts/init-secrets.sh
COPY entrypoint.sh /vault/scripts/entrypoint.sh
RUN chmod +x /vault/scripts/init-secrets.sh /vault/scripts/entrypoint.sh

# Expose Vault port
EXPOSE 8200

# Run with entrypoint that starts Vault and initializes secrets
ENTRYPOINT ["/vault/scripts/entrypoint.sh"]
