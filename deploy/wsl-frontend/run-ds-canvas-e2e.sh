#!/usr/bin/env bash
# §10.7 海豚集成验收（A1 画布可设计 / A2 脚本挂接）：在 1.9 隔离目录取短时 token 并执行浏览器验证。
# token/key 仅进程环境传递，不落盘、不入 URL、不入静态产物。
set -euo pipefail
DIR=/lei/datara/deployments/F-DS-EMBED-20261030/e2e
BASE=http://192.168.1.9:18091
PROJECT_ID="${1:-33}"
NEW_NODE_NAME="${2:-}"

KEY=$(cat "$DIR/.vk")
RESP=$(curl -sS -X POST "$BASE/api/v1/rebuild/validation-token" \
  -H "X-Backend-Validation-Key: $KEY" \
  -H "X-Backend-Validation-Scope: high-priority-e2e")
TOKEN=$(printf '%s' "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
if [ -z "$TOKEN" ]; then echo 'token exchange failed' >&2; exit 1; fi

export DATARA_DS_VERIFY_TOKEN="$TOKEN"
export NODE_PATH=/tmp/dsverify/node_modules
export TMPDIR="$DIR"
# 1.9 缓存的 chromium 与 playwright-core 版本号不一致，显式指定二进制（仅本机路径，不入仓库）。
export DATARA_CHROMIUM_PATH="${DATARA_CHROMIUM_PATH:-$HOME/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome}"
cd "$DIR"
if [ -n "$NEW_NODE_NAME" ]; then
  node verify-ds-canvas-design.cjs "$BASE" "$PROJECT_ID" "$NEW_NODE_NAME"
else
  node verify-ds-canvas-design.cjs "$BASE" "$PROJECT_ID"
fi
