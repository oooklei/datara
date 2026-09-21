#!/usr/bin/env bash
# I5 实测阶段三（门 #9 纯 SELECT 零血缘 / #8 失败语句不产血缘）
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)

make_run() { # $1=名称 $2=sql文件 $3=数据源 → 输出 instance_id
  local WF_ID DOC CODE
  WF_ID=$(curl -sf -X POST $API/workflow-definitions -H "token: $TOKEN" -H 'Content-Type: application/json' -d "{\"name\":\"$1\"}" | jq -r '.data.id')
  DOC=$(jq -n --arg id "$WF_ID" --arg name "$1" --rawfile sql "$2" --arg ds "$3" '{
    id: $id, name: $name, version: 1, meta: {profile: "dag"},
    nodes: [
      {id: "n_start", type: "start", position: {x: 80, y: 200}, data: {name: "开始"}},
      {id: "n_sql_1", type: "sql", position: {x: 340, y: 200}, data: {name: "节点1", datasource: $ds, sql: $sql, pre: "", post: ""}},
      {id: "n_end", type: "end", position: {x: 620, y: 200}, data: {name: "结束"}}
    ],
    edges: [{id: "e1", source: "n_start", target: "n_sql_1"}, {id: "e2", source: "n_sql_1", target: "n_end"}]
  }')
  curl -sf -X PUT $API/workflow-definitions/$WF_ID/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
    -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I5 实测"}')" > /dev/null
  curl -sf -X POST $API/workflow-definitions/$WF_ID/run -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' > /dev/null
  CODE=$($META "SELECT code FROM t_wf_definition WHERE id='$WF_ID';" 2>/dev/null)
  local IID=""
  for i in $(seq 1 30); do
    sleep 2
    IID=$($META "SELECT instance_id FROM t_workflow_instance WHERE wf_code=$CODE AND state IN ('success','failure','kill') ORDER BY id DESC LIMIT 1;" 2>/dev/null)
    if [ -n "$IID" ]; then break; fi
  done
  echo "$CODE $IID"
}

echo "=== 门#9: 纯 SELECT 工作流 ==="
cat > /tmp/i5_sel.sql <<'EOSQL'
SELECT COUNT(*) AS c FROM ods_order
EOSQL
read CODE9 IID9 <<< "$(make_run "I5-血缘-SELECT" /tmp/i5_sel.sql "内置源库-ec_retail")"
ST9=$($META "SELECT state FROM t_workflow_instance WHERE instance_id='$IID9';" 2>/dev/null)
ED9=$($META "SELECT COUNT(*) FROM t_lineage_edge WHERE instance_id='$IID9';" 2>/dev/null)
echo "wf=$CODE9 instance=$IID9 state=$ST9 lineage_edges=$ED9（应为 success/0）"

echo "=== 门#8: 失败语句工作流（语句1 语法错 + 语句2 合法 INSERT）==="
cat > /tmp/i5_fail.sql <<'EOSQL'
INSERT INTO dwd_i5_order_wide SELECT id, order_no, username, amount, create_time FROM ods_order WHERE status = 'PAID' LIMIT 3;
INSERT INT0 this_is_syntax_error
EOSQL
read CODE8 IID8 <<< "$(make_run "I5-血缘-失败" /tmp/i5_fail.sql "内置源库-ec_retail")"
ST8=$($META "SELECT state FROM t_workflow_instance WHERE instance_id='$IID8';" 2>/dev/null)
echo "wf=$CODE8 instance=$IID8 state=$ST8（应为 failure）"
$META "SELECT node_id, stmt_no, from_table, to_table FROM t_lineage_edge WHERE instance_id='$IID8' ORDER BY id;" 2>/dev/null
echo "（应只有 stmt_no=2 的边，语法错误语句零血缘）"
$META "SELECT f.to_field, f.from_table, f.from_field FROM t_lineage_field f JOIN t_lineage_edge e ON e.id=f.edge_id WHERE e.instance_id='$IID8';" 2>/dev/null

echo "=== 门#6 对账：血缘表名 ∈ ec_retail 真实表 ==="
$META "SELECT DISTINCT to_table FROM t_lineage_edge WHERE tmp_flag=0;" 2>/dev/null | while read -r t; do
  tbl="${t#*.}"
  HIT=$(docker exec datara-mysql-src mysql -uroot -pdatara_2026 ec_retail -N -B -e "SHOW TABLES LIKE '$tbl';" 2>/dev/null)
  if [ "$HIT" = "$tbl" ]; then echo "  ok  $t ∈ ec_retail"; else echo "  MISS $t"; fi
done
echo "STAGE3_DONE"
