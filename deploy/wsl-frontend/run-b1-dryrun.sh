#!/usr/bin/env bash
# B1 试运行验收：画布右键 dry-run → 实例生成 → datara 实例页日志可见。
set -euo pipefail
BASE=http://192.168.1.9:18091
DIR=/lei/datara/deployments/F-DS-EMBED-20261030/e2e
KEY=$(cat "$DIR/.vk")
RESP=$(curl -sS -X POST "$BASE/api/v1/rebuild/validation-token" \
  -H "X-Backend-Validation-Key: $KEY" \
  -H "X-Backend-Validation-Scope: high-priority-e2e")
TOKEN=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
if [ -z "$TOKEN" ]; then echo 'token failed' >&2; exit 1; fi
export DATARA_DS_VERIFY_TOKEN="$TOKEN"
export NODE_PATH=/tmp/dsverify/node_modules
export TMPDIR="$DIR"
export DATARA_CHROMIUM_PATH="${DATARA_CHROMIUM_PATH:-$HOME/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome}"
cd "$DIR"
node verify-ds-dryrun.cjs "$BASE" 33
