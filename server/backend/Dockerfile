# ---------- Stage 1: unpack vendored testssl.sh ----------
FROM python:3.13-slim AS tools-builder

ARG TESTSSL_SOURCE_SHA256=1c4bb10185a67592164eb870c717b8bdd03f290c8d68f9a8c658335ff5ac8b91

COPY third_party/testssl-v3.2.3.tar.gz /tmp/testssl.tar.gz
RUN mkdir -p /opt/testssl \
    && echo "${TESTSSL_SOURCE_SHA256}  /tmp/testssl.tar.gz" | sha256sum -c - \
    && tar xzf /tmp/testssl.tar.gz --strip-components=1 -C /opt/testssl \
    && rm /tmp/testssl.tar.gz \
    && chmod +x /opt/testssl/testssl.sh

# ---------- Stage 2: build Hydra without Firebird support ----------
FROM python:3.13-slim AS hydra-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG HYDRA_SOURCE_SHA256=9dd193b011fdb3c52a17b0da61a38a4148ffcad731557696819d4721d1bee76b

WORKDIR /build
COPY third_party/hydra-v9.5.tar.gz .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    libpcre2-dev \
    libssh-dev \
    libssl-dev \
    zlib1g-dev \
    && mkdir hydra \
    && echo "${HYDRA_SOURCE_SHA256}  hydra-v9.5.tar.gz" | sha256sum -c - \
    && tar xzf hydra-v9.5.tar.gz --strip-components=1 -C hydra \
    && rm hydra-v9.5.tar.gz \
    && cd hydra \
    && ./configure \
    && make -j"$(nproc)" \
    && install -m 0755 hydra /usr/local/bin/hydra \
    && ! ldd /usr/local/bin/hydra | grep -E "libfbclient|libnghttp2|libopenjp2" \
    && rm -rf /var/lib/apt/lists/* /build/hydra

# ---------- Stage 3: build Python dependencies ----------
FROM python:3.13-slim AS builder

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade "pip>=26.0.1"

# Build context is repo root; requirements is in server/backend/
COPY server/backend/requirements.txt .
COPY tools/requirements.txt tools-requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
# Also install tools sidecar deps
RUN pip install --no-cache-dir --prefix=/install -r tools-requirements.txt

# ---------- Stage 4: runtime (backend + tools combined) ----------
FROM python:3.13-slim
ENV HOME=/home/edq
ENV XDG_CACHE_HOME=/app/.cache
ENV XDG_CONFIG_HOME=/app/.config

# Set INSTALL_LIBREOFFICE=true to include LibreOffice for DOCX/XLSX to PDF conversion.
# fpdf2 is used by default; set EDQ_USE_LIBREOFFICE=true at runtime to preserve
# workbook-backed template layout in PDF output.
ARG INSTALL_LIBREOFFICE=false

ARG DEBIAN_FRONTEND=noninteractive
ARG NIKTO_SOURCE_SHA256=656554f9aeba8c462689582b59d141369dbcadac11141cd02752887f363430ec

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    wget \
    nmap \
    openssh-client \
    iputils-ping \
    iproute2 \
    net-tools \
    bsdmainutils \
    libcap2-bin \
    ca-certificates \
    perl \
    libnet-ssleay-perl \
    libjson-perl \
    libxml-writer-perl \
    snmp \
    procps \
    busybox \
    libpcre2-8-0 \
    libssh-4 \
    && ln -s /bin/busybox /usr/local/bin/nslookup \
    && setcap cap_net_raw,cap_net_admin+ep /usr/bin/nmap \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade "pip>=26.0.1"

RUN if [ "$INSTALL_LIBREOFFICE" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends libreoffice-calc libreoffice-writer \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Install nikto from the vendored release archive. Keeping the archive in the
# repo avoids Docker build failures on networks that block GitHub/codeload.
COPY third_party/nikto-2.6.0.tar.gz /tmp/nikto.tar.gz
RUN mkdir -p /opt/nikto \
    && echo "${NIKTO_SOURCE_SHA256}  /tmp/nikto.tar.gz" | sha256sum -c - \
    && tar xzf /tmp/nikto.tar.gz --strip-components=1 -C /opt/nikto \
    && rm /tmp/nikto.tar.gz \
    && ln -s /opt/nikto/program/nikto.pl /usr/local/bin/nikto \
    && chmod +x /opt/nikto/program/nikto.pl

# Copy testssl.sh from builder
COPY --from=tools-builder /opt/testssl /opt/testssl
RUN chmod +x /opt/testssl/testssl.sh && \
    ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh

# Copy source-built Hydra from builder. The binary keeps EDQ's HTTP/HTTPS/SSH
# credential checks without linking Firebird, nghttp2, or OpenJPEG libraries.
COPY --from=hydra-builder /usr/local/bin/hydra /usr/local/bin/hydra
RUN hydra -h 2>&1 | grep -q "Hydra v" && \
    ! ldd /usr/local/bin/hydra | grep -E "libfbclient|libnghttp2|libopenjp2"

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

RUN mkdir -p /app/assets

# Copy backend code (build context is repo root)
COPY server/backend/ .
COPY templates/ /app/templates/
COPY frontend/public/electracom-logo.png /app/assets/electracom-logo.png

# Copy tools sidecar
COPY tools/server.py /app/tools/server.py
COPY tools/wordlists/ /usr/share/wordlists/

RUN mkdir -p data uploads reports /app/.cache/dconf /app/.config /app/tools /home/edq && \
    chmod +x /app/entrypoint.sh

# Run as non-root user. nmap has setcap for raw socket access.
# The tools API is only accessible on localhost (same container).
RUN groupadd -r edq && useradd -r -g edq -d /home/edq -s /sbin/nologin edq \
    && chown -R edq:edq /app data uploads reports /home/edq
USER edq

EXPOSE 8000 8001

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
    CMD wget -qO /dev/null http://localhost:8000/api/v1/health && case "$(printf '%s' "${EDQ_START_INTERNAL_TOOLS:-true}" | tr '[:upper:]' '[:lower:]')" in false|0|no|off) exit 0 ;; *) wget -qO /dev/null http://localhost:8001/health ;; esac

ENTRYPOINT ["/app/entrypoint.sh"]
