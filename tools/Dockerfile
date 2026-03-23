FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
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
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/drwetter/testssl.sh.git /opt/testssl && \
    chmod +x /opt/testssl/testssl.sh && \
    ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh

RUN pip3 install ssh-audit flask

WORKDIR /app
COPY server.py .

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=15s \
    CMD curl -sf http://localhost:8001/health || exit 1

CMD ["python3", "server.py"]
