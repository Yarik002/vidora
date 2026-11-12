#!/usr/bin/env bash
# Rotate generated secrets in .env without printing them.
#   scripts/rotate_secret.sh ADMIN_PASSWORD DEMO_PASSWORD
# Removes the keys and lets gen_env.sh generate fresh values.
# Safe to rotate (then ./deploy.sh): JWT_SECRET (logs everyone out), APP_DB_PASSWORD (migrate re-applies it),
# DEMO_PASSWORD (before seeding). ADMIN_PASSWORD only applies to an admin that is not created yet.
# NOT safe without extra steps: POSTGRES_PASSWORD, REDIS_PASSWORD, MINIO_ROOT_PASSWORD, S3_SECRET_KEY
# (the running services keep the old value; see docs/security.md, "Secret rotation").
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo "rotate_secret: .env not found" >&2; exit 1; }
[[ $# -gt 0 ]] || { echo "usage: $0 KEY [KEY...]" >&2; exit 2; }
for key in "$@"; do
  [[ "$key" =~ ^[A-Z0-9_]+$ ]] || { echo "rotate_secret: bad key name: $key" >&2; exit 2; }
  tmp="$(mktemp)"
  grep -vE "^${key}=" .env >"$tmp" || true
  cat "$tmp" >.env && rm -f "$tmp"
  echo "rotate_secret: $key removed"
done
bash scripts/gen_env.sh
