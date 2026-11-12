#!/usr/bin/env bash
# Creates or completes .env with random secrets. Idempotent: existing values are never changed,
# only missing keys are appended. Secret values are never printed.
#
#   scripts/gen_env.sh [--domain video.example.com --email you@example.com]
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env"

DOMAIN_ARG=""
EMAIL_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN_ARG="$2"; shift 2 ;;
    --email) EMAIL_ARG="$2"; shift 2 ;;
    *) echo "gen_env: unknown argument $1" >&2; exit 2 ;;
  esac
done
if [[ -n "$DOMAIN_ARG" && -z "$EMAIL_ARG" ]]; then
  echo "gen_env: --domain needs --email (Let's Encrypt account)" >&2; exit 2
fi

rand() { # $1 = length, alphanumeric only (safe for URLs, shells and YAML)
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1" || true
}
rand_password() { # letters + guaranteed digits, so it always passes the app's password policy
  printf '%s%s%s' "$(rand_from 'A-Za-z' "$1")" "$(rand_from '0-9' 3)" "$(rand_from 'a-z' 2)"
}
rand_from() { LC_ALL=C tr -dc "$1" </dev/urandom | head -c "$2" || true; }

touch "$ENV_FILE"
chmod 600 "$ENV_FILE" 2>/dev/null || true

has_key() { grep -qE "^$1=" "$ENV_FILE"; }
set_default() { # key value: append only if missing
  if ! has_key "$1"; then printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"; fi
}
set_value() { # key value: replace or append (used for non-secret deploy settings)
  if has_key "$1"; then
    local tmp; tmp="$(mktemp)"
    grep -vE "^$1=" "$ENV_FILE" >"$tmp" || true
    printf '%s=%s\n' "$1" "$2" >>"$tmp"
    cat "$tmp" >"$ENV_FILE" && rm -f "$tmp"
  else
    printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"
  fi
}

set_default ENVIRONMENT production
set_default POSTGRES_DB vidora
set_default POSTGRES_USER vidora
set_default POSTGRES_PASSWORD "$(rand 32)"
set_default REDIS_PASSWORD "$(rand 32)"
set_default MINIO_ROOT_USER "vidora-root"
set_default MINIO_ROOT_PASSWORD "$(rand 40)"
set_default S3_ACCESS_KEY "vidora-app"
set_default S3_SECRET_KEY "$(rand 40)"
set_default BUCKET_RAW vidora-raw
set_default BUCKET_MEDIA vidora-media
set_default JWT_SECRET "$(rand 64)"
set_default ADMIN_USERNAME admin
set_default ADMIN_EMAIL "admin@vidora.example.com"
set_default ADMIN_PASSWORD "$(rand_password 14)"
set_default DEMO_PASSWORD "$(rand_password 10)"
set_default MAX_UPLOAD_MB 1024

# TLS: with a domain -> Let's Encrypt (needs an email), without -> internal CA on demand.
if [[ -n "$DOMAIN_ARG" ]]; then
  set_value SITE_ADDRESS "https://$DOMAIN_ARG"
  set_value TLS_KIND acme
  set_value ACME_EMAIL "$EMAIL_ARG"
  set_value HSTS_MODE on
else
  set_default SITE_ADDRESS "https://"
  set_default TLS_KIND internal
  set_default ACME_EMAIL ""
  set_default HSTS_MODE off
fi

echo "gen_env: $ENV_FILE is ready ($(grep -cE '^[A-Z0-9_]+=' "$ENV_FILE") keys, values not shown)"
