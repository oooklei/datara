#!/bin/bash
# I8 正式部署：后端解包重建镜像 + 前端 dist 重建（设计文档 §12）
set -e
cd /mnt/lei/datara

echo "=== 1. 后端源码解包 ==="
tar -xzf /tmp/datara-backend-i8.tar.gz -C /mnt/lei/datara
find /mnt/lei/datara/datara-backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
ls datara-backend/worker/stream/ && echo "流模块文件就位"

echo "=== 2. 后端镜像重建（含 kafka-python / mysql-replication 安装）==="
docker compose up -d --build datara-master datara-api datara-worker datara-logger datara-alert 2>&1 | tail -20

echo "=== 3. 前端 dist 重建 ==="
rm -rf datara-web/dist
mkdir -p datara-web/dist
tar -xzf /tmp/datara-web-dist-i8.tar.gz -C datara-web/dist
docker restart datara-web
ls datara-web/dist | head -5

echo "=== I8 部署完成 ==="
