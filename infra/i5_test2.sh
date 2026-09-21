#!/usr/bin/env bash
# I5 实测阶段二（门 #7 幂等 / #11 #12 API 契约 / #14 trace 接口）
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
IID=$($META "SELECT instance_id FROM t_workflow_instance WHERE wf_code=10 ORDER BY id DESC LIMIT 1;" 2>/dev/null)
echo "base_instance=$IID"

echo "=== 门#7: 整体重跑（新实例 → 新血缘行=追溯设计；API 呈现去重不翻倍）==="
E0=$($META "SELECT COUNT(*) FROM t_lineage_edge;" 2>/dev/null)
curl -sf -X POST $API/instances/$IID/rerun -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' | jq -c .data
NEW=""
for i in $(seq 1 30); do
  sleep 2
  NEW=$($META "SELECT instance_id FROM t_workflow_instance WHERE wf_code=10 AND instance_id!='$IID' AND state='success' ORDER BY id DESC LIMIT 1;" 2>/dev/null)
  if [ -n "$NEW" ]; then echo "rerun_instance=$NEW (round $i)"; break; fi
done
E1=$($META "SELECT COUNT(*) FROM t_lineage_edge;" 2>/dev/null)
F1=$($META "SELECT COUNT(*) FROM t_lineage_field;" 2>/dev/null)
echo "db_edges_before=$E0 db_edges_after=$E1 (新实例新边，追溯需要) db_fields=$F1"

echo "=== 门#11: GET /lineage/tables 契约 ==="
curl -sf "$API/lineage/tables" -H "token: $TOKEN" > /tmp/ln_tables.json
echo "API 呈现条数（去重后，应=2 不翻倍）: $(jq '.data | length' /tmp/ln_tables.json)"
jq -c '.data[0]' /tmp/ln_tables.json
jq -e '.data[0] | has("from") and has("to") and has("task") and has("wf") and has("instanceId") and has("nodeId") and has("dsName") and has("tmpFlag") and has("stmt") and has("stmtNo") and has("wfCode") and has("createTime")' /tmp/ln_tables.json > /dev/null && echo "契约形状 OK"

echo "=== 门#12a: GET /lineage/fields 契约 ==="
curl -sf "$API/lineage/fields?table=dwd_i5_order_wide" -H "token: $TOKEN" | jq -c '.data["dwd_i5_order_wide.net_amount"]'

echo "=== 门#12b: GET /lineage/stats ==="
curl -sf "$API/lineage/stats" -H "token: $TOKEN" | jq -c .data

echo "=== 门#14: GET /lineage/trace（实例快照+字段明细）==="
curl -sf "$API/lineage/trace?instance_id=$IID" -H "token: $TOKEN" > /tmp/ln_trace.json
echo "trace 边数: $(jq '.data | length' /tmp/ln_trace.json)"
jq -c '.data[0] | {from, to, stmtNo, fields}' /tmp/ln_trace.json
echo "STAGE2_DONE rerun_instance=$NEW"
