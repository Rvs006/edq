# ---- Builder stage: clone testssl.sh (requires git) ----
FROM ubuntu:22.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin testssl.sh to a stable release tag
RUN git clone --depth 1 --branch v3.2.3 https://github.com/drwetter/testssl.sh.git /opt/testssl && \
    chmod +x /opt/testssl/testssl.sh


# ---- Runtime stage: lean image without git/wget ----
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    python3 \
    python3-pip \
    curl \
    openssh-client \
    hydra \
    nikto \
    iputils-ping \
    iproute2 \
    net-tools \
    bsdmainutils \
    libcap2-bin \
    ca-certificates \
    && setcap cap_net_raw,cap_net_admin+ep /usr/bin/nmap \
    && rm -rf /var/lib/apt/lists/*

# Copy testssl.sh from builder stage (no git needed at runtime)
COPY --from=builder /opt/testssl /opt/testssl
RUN chmod +x /opt/testssl/testssl.sh && \
    ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh

# Pin Python tool versions; add gunicorn for production serving
RUN pip3 install --no-cache-dir "ssh-audit==3.3.0" "flask==3.0.*" "gunicorn==22.0.*"

# Create non-root user for gunicorn process ownership
RUN groupadd -r edqtools && useradd -r -g edqtools -d /app -s /sbin/nologin edqtools

WORKDIR /app
COPY server.py .
COPY wordlists/ /usr/share/wordlists/

RUN chown -R edqtools:edqtools /app

# Run as root because nmap SYN scan (-sS) and OS detection (-O)
# require raw socket access. Docker cap_add grants container-level
# capabilities but non-root users cannot use them.
# Security: the API is authenticated via TOOLS_API_KEY and only
# accessible on the internal Docker network (not exposed to host).
USER root

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=15s \
    CMD curl -sf http://localhost:8001/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8001", "--workers", "4", "--threads", "2", "--timeout", "300", "server:app"]
