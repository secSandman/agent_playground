# ============================================================
# Squid Proxy for OpenCode Network Policy Enforcement
# Allows FQDN-based allowlisting with localhost and private network access
# ============================================================

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Squid proxy server
RUN apt-get update && apt-get install -y --no-install-recommends \
    squid \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration
COPY squid.conf /etc/squid/squid.conf

# Create cache directories with proper permissions
RUN mkdir -p /var/spool/squid /var/run/squid && \
    chown -R proxy:proxy /var/spool/squid && \
    chown -R proxy:proxy /var/log/squid && \
    chown -R proxy:proxy /var/run/squid

# Initialize cache
RUN squid -z -N

# Run as non-root
USER proxy

EXPOSE 3128

# Run in foreground mode
CMD ["squid", "-N", "-d", "1"]
