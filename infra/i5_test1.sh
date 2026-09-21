#!/usr/bin/env bash
# I5 实测阶段一（门 #5/#6/#7 首轮）：基准工作流创建+运行 → t_lineage 落库 → 对账数据打印
set -e
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta"

echo "=== 0. src 基准数据 ==="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 ec_retail -B -e "SHOW TABLES; SELECT COUNT(*) AS ods_order_rows FROM ods_order; SELECT COUNT(*) AS dim_user_rows FROM dim_user;" 2>/dev/null

echo "=== 1. 建目标表 dwd_i5_order_wide（幂等）==="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 ec_retail -e "DROP TABLE IF EXISTS dwd_i5_order_wide; CREATE TABLE dwd_i5_order_wide (id BIGINT, order_no VARCHAR(64), username VARCHAR(128), net_amount DECIMAL(18,2), create_time DATETIME);" 2>/dev/null
echo TABLE_OK

echo "=== 2. 数据源清单（确认名称）==="
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
echo "token=${TOKEN:0:8}..."
curl -sf "$API/datasources" -H "token: $TOKEN" | jq -r '.data[] | "\(.id) \(.name) \(.type) \(.db)"'

echo "=== 3. 新建工作流 I5-血缘-实测 ==="
WF_ID=$(curl -sf -X POST $API/workflow-definitions -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{"name":"I5-血缘-实测"}' | jq -r '.data.id')
echo "wf=$WF_ID"

echo "=== 4. 保存画布（start → sql → end）==="
cat > /tmp/i5_base.sql <<'EOSQL'
INSERT INTO dwd_i5_order_wide
SELECT o.id, o.order_no, u.username, o.amount * 0.9 AS net_amount, o.create_time
FROM ods_order o JOIN dim_user u ON u.id = o.user_id
WHERE o.status = 'DONE'
EOSQL
DOC=$(jq -n --arg id "$WF_ID" --rawfile sql /tmp/i5_base.sql '{
  id: $id, name: "I5-血缘-实测", version: 1, meta: {profile: "dag"},
  nodes: [
    {id: "n_start", type: "start", position: {x: 80, y: 200}, data: {name: "开始"}},
    {id: "n_sql_1", type: "sql", position: {x: 340, y: 200}, data: {name: "加工宽表", datasource: "内置源库-ec_retail", sql: $sql, pre: "", post: ""}},
    {id: "n_end", type: "end", position: {x: 620, y: 200}, data: {name: "结束"}}
  ],
  edges: [
    {id: "e1", source: "n_start", target: "n_sql_1"},
    {id: "e2", source: "n_sql_1", target: "n_end"}
  ]
}')
curl -sf -X PUT $API/workflow-definitions/$WF_ID/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
  -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I5 实测基准"}')" | jq -c .data
echo "wf_saved=$WF_ID"

echo "=== 5. 触发运行 ==="
curl -sf -X POST $API/workflow-definitions/$WF_ID/run -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' | jq -c .
WF_CODE=$(curl -sf "$API/workflow-definitions?search=%E8%A1%80%E5%AE%9E" -H "token: $TOKEN" | jq -r '.data.list[0].code')
echo "wf_code=$WF_CODE"

echo "=== 6. 轮询实例状态（最多 60s）==="
for i in $(seq 1 30); do
  sleep 2
  STATE=$(curl -sf "$API/instances?pageSize=5" -H "token: $TOKEN" | jq -r "[.data.list[] | select(.wfCode == $WF_CODE)][0].state")
  IID=$(curl -sf "$API/instances?pageSize=5" -H "token: $TOKEN" | jq -r "[.data.list[] | select(.wfCode == $WF_CODE)][0].instanceId")
  echo "round $i: instance=$IID state=$STATE"
  if [ "$STATE" = "success" ] || [ "$STATE" = "failure" ] || [ "$STATE" = "kill" ]; then break; fi
done
echo "INSTANCE=$IID"

echo "=== 7. 任务状态 + 血缘落库 ==="
curl -sf "$API/instances/$IID" -H "token: $TOKEN" | jq -c '.data.taskInstances[] | {nodeId, name, state}'
$META -e "SELECT COUNT(*) AS edge_rows FROM t_lineage_edge;" 2>/dev/null
$META -e "SELECT wf_code, wf_name, instance_id, node_id, stmt_no, from_table, to_table, tmp_flag FROM t_lineage_edge\\G" 2>/dev/null
$META -e "SELECT e.to_table, f.to_field, f.from_table, f.from_field, f.transform FROM t_lineage_field f JOIN t_lineage_edge e ON e.id = f.edge_id ORDER BY f.id;" 2>/dev/null

echo "=== 8. 目标表数据 ==="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 ec_retail -B -e "SELECT COUNT(*) AS wide_rows FROM dwd_i5_order_wide;" 2>/dev/null
echo "STAGE1_DONE instance=$IID wf=$WF_ID code=$WF_CODE"
