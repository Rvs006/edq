FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    python3 \
    python3-pip \
    curl \
    wget \
    git \
    openssh-client \
    hydra \
    nikto \
    iputils-ping \
    net-tools \
    bsdmainutils \
    && rm -rf /var/lib/apt/lists/*

# Pin testssl.sh to a stable release tag
RUN git clone --depth 1 --branch v3.2.3 https://github.com/drwetter/testssl.sh.git /opt/testssl && \
    chmod +x /opt/testssl/testssl.sh && \
    ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh

# Pin Python tool versions
RUN pip3 install --no-cache-dir "ssh-audit==3.1.0" "flask==3.0.*"

# Create non-root user (tools still need NET_RAW/NET_ADMIN via cap_add)
RUN groupadd -r edqtools && useradd -r -g edqtools -d /app -s /sbin/nologin edqtools

WORKDIR /app
COPY server.py .

RUN chown -R edqtools:edqtools /app

USER edqtools

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=15s \
    CMD curl -sf http://localhost:8001/health || exit 1

CMD ["python3", "server.py"]
