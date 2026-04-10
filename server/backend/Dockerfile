# ---------- Stage 1: clone testssl.sh ----------
FROM ubuntu:22.04 AS tools-builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v3.2.3 https://github.com/drwetter/testssl.sh.git /opt/testssl && \
    chmod +x /opt/testssl/testssl.sh

# ---------- Stage 2: build Python dependencies ----------
FROM python:3.12-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Build context is repo root; requirements is in server/backend/
COPY server/backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
# Also install tools sidecar deps
RUN pip install --no-cache-dir --prefix=/install "ssh-audit==3.3.0" "flask==3.0.*" "gunicorn==22.0.*"

# ---------- Stage 3: runtime (backend + tools combined) ----------
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    libreoffice-writer \
    nmap \
    hydra \
    openssh-client \
    iputils-ping \
    iproute2 \
    net-tools \
    bsdmainutils \
    libcap2-bin \
    ca-certificates \
    perl \
    libnet-ssleay-perl \
    && setcap cap_net_raw,cap_net_admin+ep /usr/bin/nmap \
    && rm -rf /var/lib/apt/lists/*

# Install nikto from source (not in Debian repos)
RUN cd /opt && wget -q https://github.com/sullo/nikto/archive/refs/tags/2.5.0.tar.gz \
    && tar xzf 2.5.0.tar.gz && rm 2.5.0.tar.gz \
    && ln -s /opt/nikto-2.5.0/program/nikto.pl /usr/local/bin/nikto \
    && chmod +x /opt/nikto-2.5.0/program/nikto.pl

# Copy testssl.sh from builder
COPY --from=tools-builder /opt/testssl /opt/testssl
RUN chmod +x /opt/testssl/testssl.sh && \
    ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy backend code (build context is repo root)
COPY server/backend/ .
COPY templates/ /app/templates/

# Copy tools sidecar
COPY tools/server.py /app/tools/server.py
COPY tools/wordlists/ /usr/share/wordlists/

RUN mkdir -p data uploads reports /app/.cache/dconf /app/.config/libreoffice /app/tools && \
    chmod +x /app/entrypoint.sh

# Run as root — nmap SYN scan and OS detection require raw socket access.
# Security: the tools API is only accessible on localhost (same container).
USER root

EXPOSE 8000 8001

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
    CMD curl -sf http://localhost:8000/api/v1/health >/dev/null && curl -sf http://localhost:8001/health >/dev/null || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
