#!/bin/bash
# engine.py tgt_base readerTable 修复部署（仅 engine.py 单文件；dist/sync.py/seed/dag.py 本轮未变不重拷）
set -e
cd /mnt/lei/datara
cp /tmp/engine.py datara-backend/master/engine.py
docker cp /tmp/engine.py datara-master:/app/master/engine.py
docker restart datara-master
sleep 8
docker ps --format '{{.Names}}|{{.Status}}' | grep datara-master
docker logs datara-master --tail 20 2>&1 | tail -20
echo DEPLOY_DONE
