#!/usr/bin/env bash
# I6 实测重跑前清理：I6-% 定义/实例/血缘 + 场景库 ec_retail_bad + dw 目标表（跨轮次污染根治）
set -e
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 2>/dev/null <<'SQL'
CREATE TEMPORARY TABLE tmp_i6 AS SELECT code FROM t_wf_definition WHERE name LIKE 'I6-%';
SELECT COUNT(*) AS defs_to_delete FROM tmp_i6;
DELETE FROM t_task_instance WHERE instance_id IN (SELECT instance_id FROM t_workflow_instance WHERE wf_code IN (SELECT code FROM tmp_i6));
DELETE FROM t_workflow_instance WHERE wf_code IN (SELECT code FROM tmp_i6);
DELETE FROM t_lineage_edge WHERE wf_code IN (SELECT code FROM tmp_i6);
DELETE FROM t_lineage_field WHERE edge_id NOT IN (SELECT id FROM t_lineage_edge);
DELETE FROM t_wf_definition WHERE code IN (SELECT code FROM tmp_i6);
SELECT COUNT(*) AS i6_defs_left FROM t_wf_definition WHERE name LIKE 'I6-%';
SQL
# 场景重置：坏数据源库（门 #7 探测会被上一轮遗留的 bad 同名表污染）+ dw 目标表（追加语义会跨轮翻倍）
docker exec datara-mysql-src mysql -uroot -pdatara_2026 -B -N \
  -e "DROP DATABASE IF EXISTS ec_retail_bad;" 2>/dev/null
DW_TABLES=$(docker exec datara-mysql-dw mysql -uroot -pdatara_2026 -B -N \
  -e "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME LIKE 'ods_i6%';" 2>/dev/null)
for T in $DW_TABLES; do
  docker exec datara-mysql-dw mysql -uroot -pdatara_2026 -B -N \
    -e "DROP TABLE IF EXISTS datara_dw.\`$T\`;" 2>/dev/null
done
echo "dw_dropped: $DW_TABLES"
echo "I6_CLEAN_DONE"
