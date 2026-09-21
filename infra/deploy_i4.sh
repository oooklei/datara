#!/usr/bin/env bash
# I4 增量部署脚本（1.9 远端执行）：解包覆盖 → 样例入卷 → 重建容器 → meta DDL → sp_i4_demo → 自检
set -e
cd /mnt/lei/datara

echo "=== 1. 解包覆盖 ==="
tar -xzf /mnt/lei/datara/datara_i4.tgz -C /mnt/lei/datara
rm -f /mnt/lei/datara/datara_i4.tgz

echo "=== 2. I2 样例文件入 files 共享卷 ==="
mkdir -p /mnt/lei/datara/files/samples
cp -f /mnt/lei/datara/infra/files/samples/* /mnt/lei/datara/files/samples/
ls -la /mnt/lei/datara/files/samples/

echo "=== 3. 重建并启动容器 ==="
docker compose up -d --build

echo "=== 4. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. meta 库执行 02_meta_i4.sql（幂等）==="
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta < /mnt/lei/datara/infra/mysql/init/02_meta_i4.sql

echo "=== 6. src 库建测试存储过程 sp_i4_demo（幂等 DROP+CREATE）==="
docker exec -i datara-mysql-src mysql -uroot -pdatara_2026 ec_retail <<'EOSQL'
DROP PROCEDURE IF EXISTS sp_i4_demo;
DELIMITER //
CREATE PROCEDURE sp_i4_demo(IN p INT, OUT r INT)
BEGIN
  SET r = p * 2;
END//
DELIMITER ;
EOSQL
docker exec -i datara-mysql-src mysql -uroot -pdatara_2026 ec_retail -e "CALL sp_i4_demo(2, @r); SELECT @r AS out_value;"

echo "=== 7. DDL/挂载自检 ==="
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -e "SHOW TABLES LIKE 't_tmp_data'; SHOW TABLES LIKE 't_ide_history'; SHOW COLUMNS FROM t_data_source LIKE 'params';"
echo "--- worker files 卷挂载 ---"
docker exec datara-worker ls -la /datara/files/samples/
echo "--- api files 卷挂载 ---"
docker exec datara-api ls -la /datara/files/samples/

echo "=== 8. 容器状态 ==="
docker compose ps
echo "DEPLOY_DONE"
