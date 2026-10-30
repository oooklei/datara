#!/usr/bin/env bash
# Generic runner: exchange short-lived validation token, then run a node script.
# Usage: bash run-ds-node.sh <script.cjs> [args...]
# Token/key stay in process env only; never written to disk or URL.
set -uo pipefail
DIR=/lei/datara/deployments/F-DS-EMBED-20261030/e2e
BASE=http://192.168.1.9:18091
SCRIPT="${1:?script name required}"
shift || true

KEY=$(cat "$DIR/.vk")
RESP=$(curl -sS -X POST "$BASE/api/v1/rebuild/validation-token" \
  -H "X-Backend-Validation-Key: $KEY" \
  -H "X-Backend-Validation-Scope: high-priority-e2e")
TOKEN=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])' 2>/dev/null)
if [ -z "${TOKEN:-}" ]; then echo "token exchange failed: $RESP" >&2; exit 1; fi

export DATARA_DS_VERIFY_TOKEN="$TOKEN"
export NODE_PATH=/tmp/dsverify/node_modules
export TMPDIR="$DIR"
export DATARA_CHROMIUM_PATH="${DATARA_CHROMIUM_PATH:-$HOME/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome}"

cd "$DIR"
node "$SCRIPT" "$@"
