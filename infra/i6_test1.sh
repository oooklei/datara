#!/usr/bin/env bash
# I6 十四项实测门 #2~#13（1.9 远端执行；门 #1=i6_setup.sh、门 #14=页面观察另行留痕）
# 设计文档 §10；调用模式对齐 i5_test1.sh（登录 token → 建定义 → 保存 doc → run → 轮询 → 对账）
set -u
API=http://localhost:8000/api/v1
FAILS=0

chk() { # chk <描述> <实际> <期望>
  if [ "$2" = "$3" ]; then echo "PASS: $1 = $2"
  else echo "FAIL: $1 期望 [$3] 实得 [$2]"; FAILS=$((FAILS+1)); fi
}

SRCQ() { docker exec datara-mysql-src mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 -B -N -e "$1" 2>/dev/null; }
DWQ()  { docker exec datara-mysql-dw  mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 -B -N -e "$1" 2>/dev/null; }
METAQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 datara_meta -B -N -e "$1" 2>/dev/null; }

TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' \
  -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
[ -n "$TOKEN" ] && [ "$TOKEN" != "null" ] || { echo "登录失败"; exit 1; }
echo "token=${TOKEN:0:8}..."

mkparam() { # mkparam <writerTable> <strategy> <schemasJSON> <autoSchema> <extraJSON>
  # 注意：jq 变量名不可用 as（保留字），故用 au
  jq -n --arg wt "$1" --arg st "$2" --argjson rs "$3" --argjson au "$4" --argjson ex "$5" '
    {readerType:"mysql", readerDs:"内置源库-ec_retail", readerTable:"ods_order_sync_src",
     readerSchemas:$rs, autoSchema:$au, writerType:"mysql", writerDs:"内置数仓-datara_dw",
     writerTable:$wt, autoCreate:true, truncate:false, strategy:$st, flagColumn:"src_schema",
     fieldMap:[], batchSize:1000, errorThreshold:0} + $ex'
}

mkdoc() { # mkdoc <wf_id> <wf_name> <sync_node_name> <sync_data_json>
  jq -n --arg id "$1" --arg nm "$2" --arg sn "$3" --argjson sd "$4" '{
    id: $id, name: $nm, version: 1, meta: {profile: "dag"},
    nodes: [
      {id: "n_start", type: "start", position: {x: 80,  y: 200}, data: {name: "开始"}},
      {id: "n_sync",  type: "sync",  position: {x: 340, y: 200}, data: ($sd + {name: $sn})},
      {id: "n_end",   type: "end",   position: {x: 620, y: 200}, data: {name: "结束"}}
    ],
    edges: [
      {id: "e1", source: "n_start", target: "n_sync"},
      {id: "e2", source: "n_sync",  target: "n_end"}
    ]
  }'
}

CNEW_ID=""; CNEW_CODE=""
create_and_save() { # create_and_save <name> <sync_node_name> <sync_data_json> → 置 CNEW_ID（wf_xxx）/CNEW_CODE（数字）
  local RSP DOC
  RSP=$(curl -sf -X POST $API/workflow-definitions -H "token: $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$1\"}")
  CNEW_ID=$(echo "$RSP" | jq -r .data.id)
  CNEW_CODE=$(echo "$RSP" | jq -r .data.code)
  DOC=$(mkdoc "$CNEW_ID" "$1" "$2" "$3")
  curl -sf -X PUT $API/workflow-definitions/$CNEW_ID/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
    -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I6 实测", tags: ["同步"]}')" >/dev/null
}

IID=""; WSTATE=""
run_wf() { # run_wf <wf_id> [code] → 触发运行并轮询，置 IID/WSTATE（code 缺省用 CNEW_CODE）
  local R i
  local CODE=${2:-$CNEW_CODE}
  curl -sf -X POST $API/workflow-definitions/$1/run -H "token: $TOKEN" \
    -H 'Content-Type: application/json' -d '{}' >/dev/null
  for i in $(seq 1 40); do
    sleep 2
    R=$(curl -sf -G "$API/instances" -H "token: $TOKEN" \
      --data-urlencode "wf_code=$CODE" --data-urlencode "page_size=5" \
      | jq -r '.data.list[0] // "none" | if . == "none" then "none none" else "\(.instanceId) \(.state)" end')
    IID=${R%% *}; WSTATE=${R##* }
    case "$WSTATE" in success|failure|kill) echo "  instance=$IID state=$WSTATE (round $i)"; return;; esac
  done
  echo "  轮询超时 state=$WSTATE"
}

sync_out() { # 输出当前 IID 的 sync 节点 outputs（JSON）
  curl -sf "$API/instances/$IID" -H "token: $TOKEN" \
    | jq -c '[.data.taskInstances[] | select(.nodeType=="sync")][0].outputs'
}
task_log() { # 输出当前 IID 第一个 sync 节点日志全文
  local LP
  LP=$(curl -sf "$API/instances/$IID" -H "token: $TOKEN" \
    | jq -r '[.data.taskInstances[] | select(.nodeType=="sync")][0].logPath')
  docker exec datara-worker cat "$LP" 2>/dev/null
}

echo "================ 门 #2 单 schema 源表基准（MySQL→dw） ================"
P=$(mkparam ods_i6_single union '["ec_retail_east"]' false '{}')
create_and_save "I6-单源基准" "单源同步" "$P"; WF_SINGLE=$CNEW_ID
run_wf "$WF_SINGLE"
chk "门#2 实例终态" "$WSTATE" "success"
chk "门#2 read_rows"   "$(sync_out | jq -r .read_rows)"  "500"
chk "门#2 write_rows"  "$(sync_out | jq -r .write_rows)" "500"
chk "门#2 batch_id=instance_id" "$(sync_out | jq -r .batch_id)" "$IID"
chk "门#2 schemas_included" "$(sync_out | jq -c .schemas_included)" '["ec_retail_east"]'
chk "门#2 dw 行数"   "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_single;")" "500"
chk "门#2 dw 金额和" "$(DWQ "SELECT ROUND(SUM(amount),2) FROM datara_dw.ods_i6_single;")" "187875.00"

echo "================ 门 #3/#5 多 schema UNION ALL + 追加语义 ================"
P=$(mkparam ods_i6_union union '["ec_retail_east","ec_retail_south"]' false '{}')
create_and_save "I6-并集追加" "并集同步" "$P"; WF_UNION=$CNEW_ID
run_wf "$WF_UNION"
chk "门#3 实例终态" "$WSTATE" "success"
chk "门#3 dw 行数=两schema之和" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_union;")" "800"
chk "门#3 dw 金额和" "$(DWQ "SELECT ROUND(SUM(amount),2) FROM datara_dw.ods_i6_union;")" "600750.00"
chk "门#3 union 无标识列" "$(DWQ "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME='ods_i6_union' AND COLUMN_NAME='src_schema';")" "0"
run_wf "$WF_UNION"   # 第二次：truncate=false 追加语义（门 #5）
chk "门#5 实例终态" "$WSTATE" "success"
chk "门#5 追加后行数翻倍" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_union;")" "1600"

echo "================ 门 #4 schema 标识列 src_flag ================"
P=$(mkparam ods_i6_flag src_flag '["ec_retail_east","ec_retail_south"]' false '{}')
create_and_save "I6-标识列" "标识列同步" "$P"; WF_FLAG=$CNEW_ID; WF_FLAG_CODE=$CNEW_CODE
run_wf "$WF_FLAG"   # 第一跑
chk "门#4 实例终态" "$WSTATE" "success"
chk "门#4 dw 总行数" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_flag;")" "800"
chk "门#4 east 逐行来源" "$(DWQ "SELECT CONCAT(COUNT(*),'/',ROUND(SUM(amount),2)) FROM datara_dw.ods_i6_flag WHERE src_schema='ec_retail_east';")" "500/187875.00"
chk "门#4 south 逐行来源" "$(DWQ "SELECT CONCAT(COUNT(*),'/',ROUND(SUM(amount),2)) FROM datara_dw.ods_i6_flag WHERE src_schema='ec_retail_south';")" "300/412875.00"

echo "================ 门 #6 分区隔离 partition ================"
P=$(mkparam ods_i6_part partition '["ec_retail_east","ec_retail_south"]' false '{}')
create_and_save "I6-分区隔离" "分区同步" "$P"; WF_PART=$CNEW_ID
run_wf "$WF_PART"
chk "门#6 实例终态" "$WSTATE" "success"
chk "门#6 east 分表" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_part_east;")" "500"
chk "门#6 south 分表" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_part_south;")" "300"

echo "================ 门 #7 运行时 schema 探测 ================"
bash /mnt/lei/datara/infra/i6_setup.sh north
P=$(mkparam ods_i6_probe src_flag '["ec_retail_east","ec_retail_south"]' false '{}')
create_and_save "I6-探测" "探测同步" "$P"; WF_PROBE=$CNEW_ID
run_wf "$WF_PROBE"
chk "门#7 autoSchema=false 不纳入" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_probe;")" "800"
P=$(mkparam ods_i6_probe src_flag '["ec_retail_east","ec_retail_south"]' true '{"truncate":true}')
DOC=$(mkdoc "$WF_PROBE" "I6-探测" "探测同步" "$P")
curl -sf -X PUT $API/workflow-definitions/$WF_PROBE/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
  -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I6 门7 autoSchema=true"}')" >/dev/null
run_wf "$WF_PROBE"
chk "门#7 autoSchema=true 自动纳入" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_probe;")" "1000"
chk "门#7 schemas_included 含 north" "$(sync_out | jq -r '.schemas_included | index("ec_retail_north") != null')" "true"
chk "门#7 日志探测留痕" "$(task_log | grep -c '探测到新增 schema')" "1"

echo "================ 门 #8 文件读端 CSV→dw ================"
mkdir -p /mnt/lei/datara/files
{ echo "id,order_no,amount,create_time"
  for n in $(seq 1 20); do
    echo "$n,I6F$(printf '%06d' "$n"),$(awk -v n="$n" 'BEGIN{printf "%.2f", n*3.3}'),2026-03-01 00:$n:00"
  done
} > /mnt/lei/datara/files/i6_orders.csv
P=$(jq -n '{readerType:"csv", readerPath:"i6_orders.csv", readerEncoding:"utf-8",
            readerDelimiter:",", readerHeader:true,
            writerType:"mysql", writerDs:"内置数仓-datara_dw", writerTable:"ods_i6_file",
            autoCreate:true, truncate:false, strategy:"union", flagColumn:"src_schema",
            fieldMap:[], batchSize:1000, errorThreshold:0}')
create_and_save "I6-文件读端" "文件同步" "$P"; WF_FILE=$CNEW_ID
run_wf "$WF_FILE"
chk "门#8 实例终态" "$WSTATE" "success"
chk "门#8 dw 行数" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_file;")" "20"
chk "门#8 autoCreate TEXT 列推断" "$(DWQ "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME='ods_i6_file' AND DATA_TYPE='text';")" "4"

echo "================ 门 #9 字段映射（amt ← amount） ================"
P=$(mkparam ods_i6_map union '["ec_retail_east"]' false \
  '{"fieldMap":[{"from":"id","to":"id"},{"from":"order_no","to":"order_no"},{"from":"amount","to":"amt"},{"from":"create_time","to":"create_time"}]}')
create_and_save "I6-字段映射" "映射同步" "$P"; WF_MAP=$CNEW_ID
run_wf "$WF_MAP"
chk "门#9 实例终态" "$WSTATE" "success"
chk "门#9 目标列改名" "$(DWQ "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME='ods_i6_map' AND COLUMN_NAME='amt';")" "1"
chk "门#9 amt 数据对账" "$(DWQ "SELECT ROUND(SUM(amt),2) FROM datara_dw.ods_i6_map;")" "187875"   # amt 为 fieldMap 改名列（TEXT），SUM 无小数位

echo "================ 门 #10 脏数据阈值 ================"
SRCQ "DROP DATABASE IF EXISTS ec_retail_bad;
CREATE DATABASE ec_retail_bad;
CREATE TABLE ec_retail_bad.ods_order_sync_src (id INT, order_no VARCHAR(64), amount DECIMAL(12,2), create_time DATETIME) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO ec_retail_bad.ods_order_sync_src VALUES (1,'B1',1.00,'2026-03-01 00:00:01'),(1,'B1x',1.00,'2026-03-01 00:00:02'),(2,'B2',2.00,'2026-03-01 00:00:03');"
DWQ "DROP TABLE IF EXISTS datara_dw.ods_i6_bad;
CREATE TABLE datara_dw.ods_i6_bad (id INT PRIMARY KEY, order_no VARCHAR(64), amount DECIMAL(12,2), create_time DATETIME) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
P=$(mkparam ods_i6_bad union '["ec_retail_bad"]' false '{"autoCreate":false,"truncate":true,"errorThreshold":0}')
create_and_save "I6-脏数据" "脏数据同步" "$P"; WF_BAD=$CNEW_ID
run_wf "$WF_BAD"
chk "门#10 阈值0坏行→failure" "$WSTATE" "failure"
chk "门#10 日志定位坏行" "$(task_log | grep -c '定位坏行')" "1"
P=$(mkparam ods_i6_bad union '["ec_retail_bad"]' false '{"autoCreate":false,"truncate":true,"errorThreshold":1}')
DOC=$(mkdoc "$WF_BAD" "I6-脏数据" "脏数据同步" "$P")
curl -sf -X PUT $API/workflow-definitions/$WF_BAD/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
  -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I6 门10 阈值=1"}')" >/dev/null
run_wf "$WF_BAD"
chk "门#10 阈值内→success" "$WSTATE" "success"
chk "门#10 bad_rows=1" "$(sync_out | jq -r .bad_rows)" "1"
chk "门#10 坏行剔除后落库" "$(DWQ "SELECT COUNT(*) FROM datara_dw.ods_i6_bad;")" "2"

echo "================ 门 #12 C17 血缘（表级边/字段映射/幂等） ================"
chk "门#12 标识列边(每源schema一条)" "$(METAQ "SELECT COUNT(*) FROM t_lineage_edge WHERE to_table='ods_i6_flag' AND node_name='标识列同步';")" "2"
chk "门#12 from_table 全称" "$(METAQ "SELECT COUNT(*) FROM t_lineage_edge WHERE to_table='ods_i6_flag' AND from_table='ec_retail_east.ods_order_sync_src';")" "1"
chk "门#12 stmt 留 union SQL" "$(METAQ "SELECT COUNT(*) FROM t_lineage_edge WHERE to_table='ods_i6_flag' AND stmt LIKE '%UNION ALL%';")" "2"
run_wf "$WF_FLAG" "$WF_FLAG_CODE"   # 第二次运行：新实例号新边（同实例重放才幂等）
chk "门#12 新实例边新增不重复" "$(METAQ "SELECT COUNT(*) FROM t_lineage_edge WHERE to_table='ods_i6_flag';")" "4"
chk "门#12 字段映射落库" "$(METAQ "SELECT COUNT(*) FROM t_lineage_field f JOIN t_lineage_edge e ON e.id=f.edge_id WHERE e.to_table='ods_i6_map' AND f.from_field='amount' AND f.to_field='amt';")" "1"

echo "================ 门 #13 F34 同步列表 sync-tasks ================"
LST=$(curl -sf "$API/sync-tasks?page_size=50" -H "token: $TOKEN")
chk "门#13 列表含标识列工作流" "$(echo "$LST" | jq -r --argjson c "$WF_FLAG_CODE" '[.data.list[] | select(.wfCode==$c)] | length')" "1"
chk "门#13 聚合实例数" "$(echo "$LST" | jq -r --argjson c "$WF_FLAG_CODE" '[.data.list[] | select(.wfCode==$c)][0].instanceCount')" "2"
chk "门#13 聚合读行数(最近实例口径)" "$(echo "$LST" | jq -r --argjson c "$WF_FLAG_CODE" '[.data.list[] | select(.wfCode==$c)][0].readRows')" "800"
chk "门#13 keyword 过滤" "$(curl -sf "$API/sync-tasks?keyword=%E6%A0%87%E8%AF%86%E5%88%97" -H "token: $TOKEN" | jq -r '.data.total')" "1"
chk "门#13 state 过滤" "$(curl -sf "$API/sync-tasks?state=success&page_size=50" -H "token: $TOKEN" | jq -r '[.data.list[] | select(.lastState!="success")] | length')" "0"
INS=$(curl -sf "$API/sync-tasks/$WF_FLAG_CODE/instances?page_size=10" -H "token: $TOKEN")
chk "门#13 实例明细条数" "$(echo "$INS" | jq -r .data.total)" "2"
chk "门#13 batchId=instanceId" "$(echo "$INS" | jq -r '.data.list[0].batchId == .data.list[0].instanceId')" "true"
# 未打标工作流负例
RSP=$(curl -sf -X POST $API/workflow-definitions -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{"name":"I6-未打标负例"}')
WF_NOTAG=$(echo "$RSP" | jq -r .data.id); NOTAG_CODE=$(echo "$RSP" | jq -r .data.code)
DOC=$(mkdoc "$WF_NOTAG" "I6-未打标负例" "占位" "$(mkparam ods_i6_x union '["ec_retail_east"]' false '{}')")
curl -sf -X PUT $API/workflow-definitions/$WF_NOTAG/save -H "token: $TOKEN" -H 'Content-Type: application/json' \
  -d "$(jq -n --argjson doc "$DOC" '{doc: $doc, remark: "I6 门13 负例（无同步标签）"}')" >/dev/null
chk "门#13 未打标不在列表" "$(echo "$LST" | jq -r --argjson c "$NOTAG_CODE" '[.data.list[] | select(.wfCode==$c)] | length')" "0"
chk "门#13 未打标实例接口报错" "$(curl -s "$API/sync-tasks/$NOTAG_CODE/instances" -H "token: $TOKEN" | jq -r .msg)" "工作流未打同步标签: I6-未打标负例"

echo "================ 汇总 ================"
echo "FAILS=$FAILS"
if [ "$FAILS" -eq 0 ]; then echo "I6_TEST1_ALL_PASS"; else echo "I6_TEST1_HAS_FAILURE"; fi
