#!/usr/bin/env bash
# 同步本地 rebuild 源码到 1.9 dt-rebuild 容器（§10 线 §10.5 B / §10.9-10.11）。
# 先备份容器内现有 rebuild，再整树覆盖，重启后校验路由与进程。
set -euo pipefail
D=/lei/datara/deployments/F-DS-EMBED-20261030
SRC="$D/src/rebuild"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

docker exec dt-rebuild sh -c "rm -rf /app/rebuild.bak-$STAMP && cp -a /app/rebuild /app/rebuild.bak-$STAMP"
docker exec dt-rebuild sh -c "rm -rf /app/rebuild"
docker cp "$SRC" dt-rebuild:/app/rebuild
docker exec dt-rebuild sh -c "find /app/rebuild -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"
docker restart dt-rebuild >/dev/null
sleep 6
echo "--- health ---"
docker ps --filter name=dt-rebuild --format '{{.Names}}\t{{.Status}}'
echo "--- routes (orchestration) ---"
docker exec dt-rebuild python3 -c "
from rebuild.api.app import create_app
app = create_app()
paths = sorted({r.path for r in app.routes})
inst = [p for p in paths if 'workflow-instances' in p or 'task-instances' in p]
print('instance_routes=', len(inst))
for p in inst: print(' ', p)
" 2>&1 | tail -20
echo "--- api.py md5 in container ---"
docker exec dt-rebuild md5sum /app/rebuild/orchestration/api.py
