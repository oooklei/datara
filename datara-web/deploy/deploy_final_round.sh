#!/bin/bash
# 终审收尾部署：seed ep→map 边 sourceHandle + sync.py 兜底 ds 查询复用（物料仅 seed + sync.py）
set -e
cd /mnt/lei/datara
cp /tmp/seed_sync_orch_usecases.py datara-backend/tools/
cp /tmp/sync.py datara-backend/worker/executors/sync.py
docker cp /tmp/seed_sync_orch_usecases.py datara-master:/app/tools/
docker cp /tmp/sync.py datara-worker:/app/worker/executors/sync.py
docker cp /tmp/sync.py datara-master:/app/worker/executors/sync.py
docker restart datara-master datara-worker
sleep 8
docker ps --format '{{.Names}}|{{.Status}}' | grep -E 'datara-(master|worker)'
docker exec -w /app datara-master python -m tools.seed_sync_orch_usecases
echo DEPLOY_DONE
