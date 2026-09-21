#!/usr/bin/env bash
# I5 增量部署脚本（1.9 远端执行）：解包覆盖 → 重建容器（requirements 变更触发依赖层拉取 sqlglot）
# → meta DDL(03_meta_i5.sql) → 依赖/DDL 自检
set -e
cd /mnt/lei/datara

echo "=== 1. 解包覆盖 ==="
tar -xzf /mnt/lei/datara/datara_i5.tgz -C /mnt/lei/datara
rm -f /mnt/lei/datara/datara_i5.tgz

echo "=== 2. 重建并启动容器 ==="
docker compose up -d --build

echo "=== 3. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 4. meta 库执行 03_meta_i5.sql（幂等）==="
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta < /mnt/lei/datara/infra/mysql/init/03_meta_i5.sql

echo "=== 5. 依赖/DDL 自检 ==="
docker exec datara-api python -c "import sqlglot; print('sqlglot', sqlglot.__version__)"
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -e "SHOW TABLES LIKE 't_lineage%';"

echo "=== 6. 容器状态 ==="
docker compose ps
echo "DEPLOY_DONE"
