#!/usr/bin/env bash
# I9 部署后自检（1.9）：seek 修复入镜像 + 执行器注册 + 容器状态 + 前端产物
set -e
cd /mnt/lei/datara

echo "--- seek fix in image (expect 4) ---"
docker exec datara-worker grep -c "_seeked" /app/worker/stream/sources.py

echo "--- EXECUTORS ---"
docker exec datara-worker python -c "from worker.executor import EXECUTORS; print(sorted(EXECUTORS))"

echo "--- stream source import smoke ---"
docker exec datara-worker python -c "from worker.stream.sources import KafkaSource; print('KafkaSource OK')"

echo "--- compose ps ---"
docker compose ps

echo "--- web dist ---"
ls datara-web/dist | head -3
curl -sf http://localhost:8090/ >/dev/null && echo WEB_OK

echo "DEPLOY_DONE"
