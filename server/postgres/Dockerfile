FROM postgres:17-alpine
COPY ca-bundle.crt /usr/local/share/ca-certificates/proxy-ca.crt
RUN cat /usr/local/share/ca-certificates/proxy-ca.crt >> /etc/ssl/certs/ca-certificates.crt
RUN apk upgrade --no-cache 2>/dev/null || true
USER postgres
