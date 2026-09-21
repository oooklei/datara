#!/usr/bin/env bash
# diag5：门#12 node_name 断言实证（带 charset 直跑断言 SQL + HEX）
echo "=== 带 utf8mb4 直跑断言1 ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 datara_meta -B -N -e \
  "SELECT COUNT(*) FROM t_lineage_edge WHERE to_table='ods_i6_flag' AND node_name='标识列同步';" 2>/dev/null
echo "=== node_name HEX（wf19 首条）==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 datara_meta -B -N -e \
  "SELECT HEX(node_name), node_name FROM t_lineage_edge WHERE wf_code=19 LIMIT 1;" 2>/dev/null
echo "=== t_task_instance.name HEX（wf19 实例）==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 datara_meta -B -N -e \
  "SELECT HEX(name), name FROM t_task_instance WHERE instance_id LIKE '%-19-%' LIMIT 1;" 2>/dev/null
echo "I6_DIAG5_DONE"
