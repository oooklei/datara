#!/usr/bin/env bash
# I5 实测阶段五：门#10 ${tmp.*} 临时表 → 下游 INSERT 血缘显示注册名 raw_txt_i5（tmp_flag=1）
# 链路：file 节点物化物理表（t_tmp_data.ref）→ sql 节点 ${tmp.raw_txt_i5} 同实例替换 → 解析按 ref 尾段映射注册名
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"
DW="docker exec datara-mysql-dw mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 -N -e"
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)

echo "=== 0. dw 库核对 + 目标表（幂等建）==="
$DW "SHOW DATABASES LIKE 'datara_dw';" 2>/dev/null
$DW "CREATE TABLE IF NOT EXISTS datara_dw.dwd_i5_tmp_out (id TEXT, order_no TEXT, user_id TEXT, status TEXT, amount TEXT, receiver_name TEXT, receiver_phone TEXT, remark TEXT, create_time TEXT, order_date TEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;" 2>/dev/null
echo TABLE_OK

echo "=== 1. 建工作流 I5-血缘-TMP（start → file → sql → end）==="
WF_ID=$(curl -sf -X POST $API/workflow-definitions -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{"name":"I5-血缘-TMP"}' | jq -r '.data.id')
echo "wf=$WF_ID"
cat > /tmp/i5_tmp.sql <<'EOSQL'
INSERT INTO dwd_i5_tmp_out SELECT * FROM ${tmp.raw_txt_i5}
EOSQL
DOC=$(jq -n --arg id "$WF_ID" --rawfile sql /tmp/i5_tmp.sql '{
  id: $id, name: "I5-血缘-TMP", version: 1, meta: {profile: "dag"},
  nodes: [
    {id: "n_start", type: "start", position: {x: 80, y: 200}, data: {name: "开始"}},
    {id: "n_file_1", type: "file", position: {x: 320, y: 200}, data: {name: "raw_txt_i5", datasource: "i4_file_csv", kind: "table", retention: "keep", register: true, targetDs: "内置数仓-datara_dw"}},
    {id: "n_sql_1", type: "sql", position: {x: 560, y: 200}, data: {name: "加工临时表", datasource: "内置数仓-datara_dw", sql: $sql, pre: "", post: ""}},
    {id: "n_end", type: "end", position: {x: 800, y: 200}, data: {name: "结束"}}
  ],
  edges: [
    {id: "e1", source: "n_start", target: "n_file_1"},
    {id: "e2", source: "n_file_1", target: "n_sql_1"},
    {id: "e3", source: "n_sql_1", target: "n_end"}
  ]
}')
curl -sf -X PUT $API/workflow-definitions/$WF_ID/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
  -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I5 tmp 实测"}')" > /dev/null
echo "wf_saved"
curl -sf -X POST $API/workflow-definitions/$WF_ID/run -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' > /dev/null
CODE=$($META "SELECT code FROM t_wf_definition WHERE id='$WF_ID';" 2>/dev/null)
echo "wf_code=$CODE"

echo "=== 2. 轮询实例（最多 60s）==="
IID=""
for i in $(seq 1 30); do
  sleep 2
  IID=$($META "SELECT instance_id FROM t_workflow_instance WHERE wf_code=$CODE AND state IN ('success','failure','kill') ORDER BY id DESC LIMIT 1;" 2>/dev/null)
  if [ -n "$IID" ]; then break; fi
done
ST=$($META "SELECT state FROM t_workflow_instance WHERE instance_id='$IID';" 2>/dev/null)
echo "instance=$IID state=$ST（应为 success）"
$META "SELECT node_id, name, state FROM t_task_instance WHERE instance_id='$IID';" 2>/dev/null

echo "=== 3. t_tmp_data 注册核对（ref=物理表名）==="
$META "SELECT name, kind, ref, retention, rows_count FROM t_tmp_data WHERE instance_id='$IID';" 2>/dev/null

echo "=== 4. 血缘边（断言：from_table=raw_txt_i5 注册名 + tmp_flag=1 → datara_dw.dwd_i5_tmp_out）==="
$META "SELECT stmt_no, from_table, to_table, tmp_flag FROM t_lineage_edge WHERE instance_id='$IID' ORDER BY id;" 2>/dev/null

echo "--- stmt 原文（应为替换后物理表名）---"
$META "SELECT stmt FROM t_lineage_edge WHERE instance_id='$IID' LIMIT 1;" 2>/dev/null

echo "--- 字段映射（SELECT * 预期 0）---"
$META "SELECT COUNT(*) FROM t_lineage_field f JOIN t_lineage_edge e ON e.id=f.edge_id WHERE e.instance_id='$IID';" 2>/dev/null

echo "=== 5. sql 任务日志（[lineage] 行应显示 临时表映射 1）==="
LP=$($META "SELECT log_path FROM t_task_instance WHERE instance_id='$IID' AND node_id='n_sql_1';" 2>/dev/null)
docker exec datara-worker sh -c "grep -a 'sql\|lineage\|终态' '$LP'"

echo "=== 6. 目标表数据 ==="
$DW "SELECT COUNT(*) FROM datara_dw.dwd_i5_tmp_out;" 2>/dev/null
echo "STAGE5_DONE"
