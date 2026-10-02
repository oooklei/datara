#!/bin/bash
# 端点合一修复部署（192.168.1.9）：dist 重构建产物双写 + sync.py readerType 兜底（worker+master）+ seed inputs 引用；seed 重跑
# （原脚本留档：/tmp/deploy_endpoint_unify.sh.bak）
set -e
cd /mnt/lei/datara
for d in datara-web/dist-new datara-web/dist; do
  rm -rf "$d"/*; tar -xzf /tmp/datara-dist.tgz -C "$d"
  echo "$d: $(find "$d" -type f | wc -l) files"
done
cp /tmp/engine.py /tmp/dag.py datara-backend/master/
docker cp /tmp/engine.py datara-master:/app/master/engine.py
docker cp /tmp/dag.py datara-master:/app/master/dag.py
cp /tmp/sync.py datara-backend/worker/executors/sync.py
docker cp /tmp/sync.py datara-worker:/app/worker/executors/sync.py
docker cp /tmp/sync.py datara-master:/app/worker/executors/sync.py
cp /tmp/seed_sync_orch_usecases.py datara-backend/tools/
docker cp /tmp/seed_sync_orch_usecases.py datara-master:/app/tools/
docker restart datara-master datara-worker; sleep 8
docker exec -w /app datara-master python -m tools.seed_sync_orch_usecases
docker logs datara-master --tail 20 2>&1 | tail -20
echo DEPLOY_DONE
