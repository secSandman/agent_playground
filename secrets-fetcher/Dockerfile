# ============================================================
# Secrets Fetcher Container
# Retrieves secrets from various providers before launching OpenCode
# ============================================================

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install HashiCorp Vault CLI
RUN curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list && \
    apt-get update && apt-get install -y vault && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    pyyaml \
    boto3

# Copy secrets fetcher script
COPY fetch-secrets.py /usr/local/bin/fetch-secrets
RUN chmod +x /usr/local/bin/fetch-secrets

# Create non-root user
RUN useradd -m -s /bin/bash -u 1001 secretsuser

# Create directories
RUN mkdir -p /config /tmp && \
    chown -R secretsuser:secretsuser /config /tmp

USER secretsuser
WORKDIR /tmp

ENTRYPOINT ["python3", "/usr/local/bin/fetch-secrets"]
