#!/usr/bin/env bash
# Developer helper: run npm scripts for the frontend inside a Node container
# (Node is not needed on the host). node_modules live in a named volume.
#   scripts/dev_web.sh typecheck | build | install
set -euo pipefail
cd "$(dirname "$0")/.."
src="$(pwd -W 2>/dev/null || pwd)/frontend"
cmd="${1:-typecheck}"
run() {
  MSYS_NO_PATHCONV=1 docker run --rm -v "$src:/app" -v vidora_web_node_modules:/app/node_modules -w /app \
    node:22-alpine sh -c "$1"
}
run "[ -d node_modules/react ] || npm ci --no-audit --no-fund --fetch-retries=5"
case "$cmd" in
  install) ;;
  typecheck) run "npx tsc -b" ;;
  build) run "npm run build" ;;
  *) echo "unknown command: $cmd" >&2; exit 2 ;;
esac
