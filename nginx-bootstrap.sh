#!/bin/sh
set -eu

BOOTSTRAP_TEMPLATE="/opt/edq/nginx/http-bootstrap.conf.template"
HTTPS_TEMPLATE="/opt/edq/nginx/https.conf.template"
TARGET_CONFIG="/etc/nginx/conf.d/default.conf"

if [ ! -f "$BOOTSTRAP_TEMPLATE" ] || [ ! -f "$HTTPS_TEMPLATE" ]; then
  echo "EDQ frontend bootstrap: missing nginx templates" >&2
  exit 1
fi

DOMAIN="${DOMAIN:-localhost}"
FULLCHAIN="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
PRIVKEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"

if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ]; then
  echo "EDQ frontend bootstrap: enabling HTTPS config for ${DOMAIN}"
  envsubst '${DOMAIN}' < "$HTTPS_TEMPLATE" > "$TARGET_CONFIG"
else
  echo "EDQ frontend bootstrap: certificates not found for ${DOMAIN}; serving HTTP bootstrap config"
  envsubst '${DOMAIN}' < "$BOOTSTRAP_TEMPLATE" > "$TARGET_CONFIG"
fi

chown nginx:nginx "$TARGET_CONFIG" 2>/dev/null || true
