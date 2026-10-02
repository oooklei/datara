#!/bin/bash
# autoSchema 语义修正部署（在 192.168.1.9 执行）
# 仅前端 dist 更新 + seed 脚本重跑（幂等删建 3 用例）；engine.py/sync.py 上轮已热修进容器
set -e
cd /mnt/lei/datara

echo "=== 1. 前端 dist 更新（保 inode） ==="
if [ ! -d datara-web/dist ]; then echo "MISSING: datara-web/dist"; exit 1; fi
rm -rf datara-web/dist/*
tar -xzf /tmp/datara-dist.tgz -C datara-web/dist
ls datara-web/dist/index.html >/dev/null
echo "dist updated: $(find datara-web/dist -type f | wc -l) files"

echo "=== 2. seed 脚本落位（宿主 + 容器） ==="
cp /tmp/seed_sync_orch_usecases.py datara-backend/tools/seed_sync_orch_usecases.py
docker cp /tmp/seed_sync_orch_usecases.py datara-master:/app/tools/seed_sync_orch_usecases.py
docker exec datara-master grep -n 'autoSchema' /app/tools/seed_sync_orch_usecases.py

echo "=== 3. 重跑 seed（幂等删建 3 用例） ==="
docker exec -w /app datara-master python -m tools.seed_sync_orch_usecases

echo "DEPLOY_DONE"
