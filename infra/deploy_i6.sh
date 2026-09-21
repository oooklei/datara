#!/usr/bin/env bash
# I6 增量部署脚本（1.9 远端执行）：解包覆盖 → 重建容器（api/worker 镜像层拿到 sync 执行器与两 API）
# → 执行器注册自检 → 容器状态。I6 整体零 DDL（设计文档 §2 结论），无 meta SQL 步骤。
set -e
cd /mnt/lei/datara

echo "=== 1. 解包覆盖（幂等：tgz 存在才解）==="
if [ -f /mnt/lei/datara/datara_i6.tgz ]; then
  tar -xzf /mnt/lei/datara/datara_i6.tgz -C /mnt/lei/datara
  rm -f /mnt/lei/datara/datara_i6.tgz
else
  echo "（tgz 不存在，跳过解包——重跑场景）"
fi

echo "=== 2. 重建并启动容器 ==="
docker compose up -d --build

echo "=== 3. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 4. sync 执行器注册自检（worker 容器内 EXECUTORS 探活）==="
docker exec datara-worker python -c "
from worker.executor import EXECUTORS
assert 'sync' in EXECUTORS, 'sync executor missing'
print('EXECUTORS:', sorted(EXECUTORS))
"

echo "=== 5. api/sync.py 路由自检（OpenAPI schema 解析 + HTTP 探活）==="
# 新版 Starlette include_router 懒加载：app.routes 含 _IncludedRouter 包装（无 path 属性），
# 改用 app.openapi()['paths'] 拿解析后的全量真实路径
docker exec datara-api python -c "
from api.main import app
paths = list(app.openapi()['paths'].keys())
assert any('/sync-tasks' in p for p in paths), 'sync-tasks route missing'
print('SYNC ROUTES:', sorted(p for p in paths if 'sync-tasks' in p))
"
sync_http=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/sync-tasks 2>/dev/null || echo 000)
echo "GET /api/v1/sync-tasks -> HTTP $sync_http（200=免token / 401=未带token鉴权形态，均正常）"
case "$sync_http" in
  200|401|403) ;;
  *) echo "sync-tasks HTTP 探活异常"; exit 1 ;;
esac

echo "=== 6. 容器状态 ==="
docker compose ps
echo "DEPLOY_DONE"
