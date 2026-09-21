#!/usr/bin/env bash
# I5 门#10 复测：tmp_flag 修复热部署（任一侧临时注册名 → 1）+ 重跑 I5-血缘-TMP 工作流
set -e
echo "=== 0. 容器内代码路径探测 ==="
APPDIR=$(docker exec datara-worker sh -c "python -c 'import worker, os; print(os.path.dirname(os.path.dirname(worker.__file__)))'")
echo "APPDIR=$APPDIR"
docker ps --format '{{.Names}}' | grep -E 'api|master|worker'

echo "=== 1. docker cp 热修（worker/api/master 三个容器）==="
for C in $(docker ps --format '{{.Names}}' | grep -E 'datara-(worker|api|master)'); do
  docker cp /tmp/fix/lineage.py $C:$APPDIR/worker/lineage.py
  docker cp /tmp/fix/models.py  $C:$APPDIR/common/models.py
  echo "  cp -> $C"
done

echo "=== 2. 重启 worker（加载新 lineage.py）==="
docker restart datara-worker > /dev/null
sleep 8
docker ps --format '{{.Names}} {{.Status}}' | grep datara-worker

echo "=== 3. 重跑 I5-血缘-TMP 工作流（wf_b30303e0，新实例）==="
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
curl -sf -X POST $API/workflow-definitions/wf_b30303e0/run -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' > /dev/null
CODE=16
IID=""
for i in $(seq 1 30); do
  sleep 2
  IID=$($META "SELECT instance_id FROM t_workflow_instance WHERE wf_code=$CODE AND state IN ('success','failure','kill') ORDER BY id DESC LIMIT 1;" 2>/dev/null)
  if [ -n "$IID" ] && [ "$IID" != "20260919011626-16-f5c3" ]; then break; fi
done
ST=$($META "SELECT state FROM t_workflow_instance WHERE instance_id='$IID';" 2>/dev/null)
echo "new_instance=$IID state=$ST"

echo "=== 4. 断言：from_table=raw_txt_i5 + tmp_flag=1 ==="
$META "SELECT stmt_no, from_table, to_table, tmp_flag FROM t_lineage_edge WHERE instance_id='$IID' ORDER BY id;" 2>/dev/null

echo "=== 5. sql 任务日志 ==="
LP=$($META "SELECT log_path FROM t_task_instance WHERE instance_id='$IID' AND node_id='n_sql_1';" 2>/dev/null)
docker exec datara-worker sh -c "grep -a 'lineage\|终态' '$LP'"

echo "=== 6. 旧实例回归确认（仍为 0，历史行不回改）==="
$META "SELECT instance_id, from_table, tmp_flag FROM t_lineage_edge WHERE wf_code=16 ORDER BY id;" 2>/dev/null
echo "FIX_TMP_DONE"
