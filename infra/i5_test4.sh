#!/usr/bin/env bash
# I5 实测阶段四：门#8 重测（合法首语句 + 失败次语句 → 仅成功语句落库）
# 上轮 0 边根因：首语句本身不合法（username ∈ dim_user 非 ods_order；目标列为 net_amount），
# executed=[] 属正确行为。本轮照抄 test1 合法 JOIN 语句作首语句，语法错作次语句。
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

echo "=== 门#8 重测: 语句1 合法 INSERT(JOIN) + 语句2 语法错 ==="
cat > /tmp/i5_fail2.sql <<'EOSQL'
INSERT INTO dwd_i5_order_wide SELECT o.id, o.order_no, u.username, o.amount * 0.9 AS net_amount, o.create_time FROM ods_order o JOIN dim_user u ON u.id = o.user_id WHERE o.status = 'DONE' LIMIT 3;
INSERT INT0 this_is_syntax_error
EOSQL
read CODE8 IID8 <<< "$(make_run "I5-血缘-失败" /tmp/i5_fail2.sql "内置源库-ec_retail")"
ST8=$($META "SELECT state FROM t_workflow_instance WHERE instance_id='$IID8';" 2>/dev/null)
echo "wf=$CODE8 instance=$IID8 state=$ST8（应为 failure）"

echo "--- 任务日志关键行（影响行数 3 = 语句1已提交）---"
LP=$($META "SELECT log_path FROM t_task_instance WHERE instance_id='$IID8' AND node_id='n_sql_1';" 2>/dev/null)
docker exec datara-worker sh -c "grep -a '非查询\|执行失败\|lineage\|终态' '$LP'"

echo "--- 血缘边（应仅 stmt_no=1 两条：ods_order/dim_user → dwd_i5_order_wide）---"
$META "SELECT node_id, stmt_no, from_table, to_table, tmp_flag FROM t_lineage_edge WHERE instance_id='$IID8' ORDER BY id;" 2>/dev/null

echo "--- 字段映射（应 5 条，transform 含 o.amount * 0.9）---"
$META "SELECT e.stmt_no, f.to_field, f.from_table, f.from_field, f.transform FROM t_lineage_field f JOIN t_lineage_edge e ON e.id=f.edge_id WHERE e.instance_id='$IID8' ORDER BY f.id;" 2>/dev/null

echo "STAGE4_DONE"
