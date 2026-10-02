#!/bin/bash
# 同步编排重构部署脚本（在 192.168.1.9 执行）
# 前端：rm -rf dist/* 保 inode 后解包新 dist；后端：重启 master/worker 加载 engine.py/sync.py 改动
set -e
cd /mnt/lei/datara

echo "=== 1. 后端文件落位检查 ==="
for f in datara-backend/master/engine.py datara-backend/worker/executors/sync.py datara-backend/tools/seed_sync_orch_usecases.py; do
  if [ ! -f "$f" ]; then echo "MISSING: $f"; exit 1; fi
done
echo "backend files OK"

echo "=== 2. 前端 dist 更新（保 inode；nginx 容器挂载的是 dist-new，勿解包到 dist） ==="
for d in datara-web/dist-new datara-web/dist; do
  if [ ! -d "$d" ]; then echo "MISSING: $d"; exit 1; fi
  rm -rf "$d"/*
  tar -xzf /mnt/lei/datara/datara-deploy.tar.gz -C "$d"
  ls "$d/index.html" >/dev/null
  echo "$d updated: $(find "$d" -type f | wc -l) files"
done

echo "=== 3. 重启 master/worker ==="
docker restart datara-master datara-worker
sleep 8

echo "=== 4. 容器状态 ==="
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'datara-(master|worker|api|web)'

echo "=== 5. master 启动日志尾部（确认无 import 错误） ==="
docker logs datara-master --tail 8 2>&1

echo "DEPLOY_DONE"
