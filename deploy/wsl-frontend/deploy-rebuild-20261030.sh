#!/usr/bin/env bash
# 同步本地 rebuild 源码到 1.9 datara-rebuild-api 容器（§10 线 §10.5 B / §10.9-10.11）。
# 先备份容器内现有 rebuild，再整树覆盖，重启后校验路由与进程。
set -euo pipefail
D=/lei/datara/deployments/F-DS-EMBED-20261030
SRC="$D/src/rebuild"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

docker exec datara-rebuild-api sh -c "rm -rf /app/rebuild.bak-$STAMP && cp -a /app/rebuild /app/rebuild.bak-$STAMP"
docker exec datara-rebuild-api sh -c "rm -rf /app/rebuild"
docker cp "$SRC" datara-rebuild-api:/app/rebuild
docker exec datara-rebuild-api sh -c "find /app/rebuild -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"
docker restart datara-rebuild-api >/dev/null
sleep 6
echo "--- health ---"
docker ps --filter name=datara-rebuild-api --format '{{.Names}}\t{{.Status}}'
echo "--- routes (orchestration) ---"
docker exec datara-rebuild-api python3 -c "
from rebuild.api.app import create_app
app = create_app()
paths = sorted({r.path for r in app.routes})
inst = [p for p in paths if 'workflow-instances' in p or 'task-instances' in p]
print('instance_routes=', len(inst))
for p in inst: print(' ', p)
" 2>&1 | tail -20
echo "--- api.py md5 in container ---"
docker exec datara-rebuild-api md5sum /app/rebuild/orchestration/api.py
