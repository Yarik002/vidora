#!/usr/bin/env bash
# Developer helper: format + lint the backend in the dev image (no Python tooling needed on the host).
#   scripts/dev_lint.sh          check only
#   scripts/dev_lint.sh --fix    apply ruff format and safe fixes
set -euo pipefail
cd "$(dirname "$0")/.."
src="$(pwd -W 2>/dev/null || pwd)/backend"
if [[ "${1:-}" == "--fix" ]]; then
  cmd="ruff format app tests && ruff check --fix app tests"
else
  cmd="ruff format --check app tests && ruff check app tests"
fi
MSYS_NO_PATHCONV=1 docker run --rm --network none -e RUFF_CACHE_DIR=/tmp/ruff -v "$src:/app" -w /app \
  vidora-backend-dev:latest sh -c "$cmd"
