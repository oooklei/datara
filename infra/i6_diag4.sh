#!/usr/bin/env bash
# I6 六疑点集中查证（第三轮 6 FAIL 定性）
API=http://localhost:8000/api/v1
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' \
  -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
DWQ()  { docker exec datara-mysql-dw  mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 -B -N -e "$1" 2>/dev/null; }
SRCQ() { docker exec datara-mysql-src mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 -B -N -e "$1" 2>/dev/null; }
METAQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -B -N -e "$1" 2>/dev/null; }

echo "=== 1. 血缘边全貌（wf 17~24）==="
METAQ "SELECT wf_code, node_name, from_table, to_table, tmp_flag FROM t_lineage_edge WHERE wf_code BETWEEN 17 AND 24 ORDER BY wf_code, id;"
echo "=== 2. src 实例各库同名表行数（1003 之谜）==="
for DB in $(SRCQ "SHOW DATABASES;" | grep -v -E '^(information_schema|mysql|performance_schema|sys)$'); do
  CNT=$(SRCQ "SELECT COUNT(*) FROM \`$DB\`.ods_order_sync_src;" 2>/dev/null)
  [ -n "$CNT" ] && echo "$DB = $CNT"
done
echo "=== 3. 门#7 二跑实例日志（探测条数）==="
curl -sf -G "$API/instances" -H "token: $TOKEN" --data-urlencode "wf_code=21" --data-urlencode "page_size=5" \
  | jq -r '.data.list[] | select(.state=="success") | .instanceId' | tail -1 > /tmp/i6_iid7
IID7=$(cat /tmp/i6_iid7)
LP7=$(curl -sf "$API/instances/$IID7" -H "token: $TOKEN" | jq -r '[.data.taskInstances[] | select(.nodeType=="sync")][0].logPath')
docker exec datara-worker grep -E '探测|schema|清空' "$LP7" 2>/dev/null
echo "=== 4. 门#10 一跑日志 脏数据 上下文 ==="
curl -sf -G "$API/instances" -H "token: $TOKEN" --data-urlencode "wf_code=24" --data-urlencode "page_size=5" \
  | jq -r '.data.list[] | select(.state=="failure") | .instanceId' | tail -1 > /tmp/i6_iid10
IID10=$(cat /tmp/i6_iid10)
LP10=$(curl -sf "$API/instances/$IID10" -H "token: $TOKEN" | jq -r '[.data.taskInstances[] | select(.nodeType=="sync")][0].logPath')
docker exec datara-worker grep -n -B2 -A2 '脏数据' "$LP10" 2>/dev/null
echo "=== 5. 门#9 ods_i6_map 列类型 ==="
DWQ "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME='ods_i6_map' ORDER BY ORDINAL_POSITION;"
echo "=== 6. ods_i6_file 行数与 id 分布（40 之谜）==="
DWQ "SELECT COUNT(*), COUNT(DISTINCT id), MIN(id), MAX(id) FROM datara_dw.ods_i6_file;"
echo "=== 7. 门#12 二跑实例（wf=19 最新实例）血缘条数 ==="
METAQ "SELECT instance_id, COUNT(*) FROM t_lineage_edge WHERE wf_code=19 GROUP BY instance_id;"
echo "I6_DIAG4_DONE"
