#!/usr/bin/env bash
# I9 增量部署脚本（1.9 远端执行）：
# 1) 前端 dist 覆盖（nginx 挂载宿主目录，立即生效；旧 dist 备份为 dist.bak 便于回滚）
# 2) worker/stream/sources.py 已由 scp 同步宿主源码树（I8 seek 时机 bug 修复）
# 3) 仅重建 datara-api / datara-worker（同一后端镜像 build: ./datara-backend；不動 mysql/kafka 等）
# 4) 健康等待 + 自检（seek 修复代码入镜像、执行器注册、容器状态）
set -e
cd /mnt/lei/datara

echo "=== 1. 前端 dist 覆盖（备份旧目录）==="
if [ -f /root/datara_i9_web.tgz ]; then
  rm -rf datara-web/dist.bak
  mv datara-web/dist datara-web/dist.bak
  mkdir -p datara-web/dist
  tar -xzf /root/datara_i9_web.tgz -C datara-web/dist
  ls datara-web/dist | head -5
else
  echo "（tgz 不存在，跳过前端覆盖——重跑场景）"
fi

echo "=== 2. 后端源码一致性自检（宿主树含 seek 修复）==="
grep -c "_seeked" /mnt/lei/datara/datara-backend/worker/stream/sources.py

echo "=== 3. 重建 api/worker 容器（拿到新镜像层）==="
docker compose up -d --build datara-api datara-worker

echo "=== 4. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. 自检：seek 修复代码进容器镜像（容器 WORKDIR=/app）==="
docker exec datara-worker grep -c "_seeked" /app/worker/stream/sources.py

echo "=== 6. 自检：worker 执行器注册 ==="
docker exec datara-worker python -c "
from worker.executor import EXECUTORS
print('EXECUTORS:', sorted(EXECUTORS))
"

echo "=== 7. 容器状态 ==="
docker compose ps
echo "DEPLOY_DONE"
