#!/usr/bin/env bash
# I4 修复补丁部署：解包两文件 → 重建镜像（代码层缓存失效，依赖层走缓存）→ 健康检查
set -e
cd /mnt/lei/datara
tar -xzf /mnt/lei/datara/datara_fix1.tgz -C /mnt/lei/datara
rm -f /mnt/lei/datara/datara_fix1.tgz
docker compose up -d --build
for i in $(seq 1 24); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  master_ok=$(curl -sf http://localhost:18001/health >/dev/null 2>&1 && echo OK || echo NG)
  worker_ok=$(curl -sf http://localhost:18002/health >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok master=$master_ok worker=$worker_ok"
  if [ "$api_ok" = "OK" ] && [ "$master_ok" = "OK" ] && [ "$worker_ok" = "OK" ]; then break; fi
done
docker compose ps --format '{{.Name}} {{.Status}}' | head -12
echo "PATCH_DONE"
