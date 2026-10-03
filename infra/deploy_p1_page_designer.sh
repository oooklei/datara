#!/usr/bin/env bash
# 页面设计器 P1 部署（在 192.168.1.9 执行）
# 1) 后端源码解包落位  2) dist+dist-new 双覆盖(保 inode)  3) 重建 datara-api  4) 健康等待
set -e
cd /lei/datara

echo "=== 1. 后端源码解包 ==="
if [ -f /lei/datara/datara_dep_backend.tgz ]; then
  tar -xzf /lei/datara/datara_dep_backend.tgz -C /lei/datara
  find datara-backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
  echo "page_designer.py: $(ls -l datara-backend/api/page_designer.py | awk '{print $5, $9}')"
  echo "component_design.py: $(ls -l datara-backend/api/component_design.py | awk '{print $5, $9}')"
  echo "dag_catalog execution_model refs: $(grep -c execution_model datara-backend/common/dag_catalog.json)"
else
  echo "MISSING backend tgz"; exit 1
fi

echo "=== 2. 前端 dist 更新（dist + dist-new 双覆盖，保 inode）==="
for d in datara-web/dist-new datara-web/dist; do
  if [ ! -d "$d" ]; then echo "MISSING: $d"; exit 1; fi
  rm -rf "$d"/*
  tar -xzf /lei/datara/datara_dep_web.tgz -C "$d"
  ls "$d/index.html" >/dev/null
  echo "$d updated: $(find "$d" -type f | wc -l) files"
done

echo "=== 3. 重建 datara-api（master/worker 无改动不动）==="
docker compose up -d --build datara-api

echo "=== 4. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. 容器状态 + api 日志尾部 ==="
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'datara-(api|web|master|worker)'
docker logs datara-api --tail 8 2>&1 || true

echo "=== 6. 清理部署包 ==="
rm -f /lei/datara/datara_dep_backend.tgz /lei/datara/datara_dep_web.tgz

echo "DEPLOY_DONE"
