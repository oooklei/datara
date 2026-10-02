#!/bin/bash
# e2e B 段独立对账（只读；与 /tmp/run_e2e.sh B 段逐字一致，避免 A 段重复触发实例）
set -e
echo "===== B. 数据对账（源库/数仓） ====="
echo "-- B1 源库 ec_retail.ods_order 总行数 / PAID 行数（期望两值相等=ods_order_sync 行数）:"
docker exec datara-mysql-src sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT COUNT(*), SUM(status=\"PAID\") FROM ec_retail.ods_order"' 2>/dev/null

echo "-- B2 数仓 ods_order_sync 行数:"
docker exec datara-mysql-dw sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM datara_dw.ods_order_sync"' 2>/dev/null

echo "-- B3 数仓 ods_order_sync.status 取值分布（期望全部 PAID）:"
docker exec datara-mysql-dw sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT status, COUNT(*) FROM datara_dw.ods_order_sync GROUP BY status"' 2>/dev/null

echo "-- B4 数仓 ods_order_multi 行数与来源 schema 分布（期望 15 行；east/south/main 各 5）:"
docker exec datara-mysql-dw sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM datara_dw.ods_order_multi"' 2>/dev/null
docker exec datara-mysql-dw sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT src_schema, COUNT(*) FROM datara_dw.ods_order_multi GROUP BY src_schema ORDER BY src_schema"' 2>/dev/null

echo "-- B5 数仓 ods_order_file 行数（期望 5000=orders_part.csv 数据行）:"
docker exec datara-mysql-dw sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM datara_dw.ods_order_file"' 2>/dev/null

echo "-- B6 数仓 ods_order_file 表结构（autoCreate 推断 DDL 产物）:"
docker exec datara-mysql-dw sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SHOW CREATE TABLE datara_dw.ods_order_file\G"' 2>/dev/null | head -20

echo "RECONCILE_DONE"
