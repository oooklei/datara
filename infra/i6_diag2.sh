#!/usr/bin/env bash
# I6 诊断二：失败实例的任务级明细 + 任务日志内容
set -u
API=http://localhost:8000/api/v1
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
IID=20260919091705-19-48b0

echo "=== 实例任务明细 ==="
curl -sf "$API/instances/$IID" -H "token: $TOKEN" | jq -c '.data.taskInstances[] | {nodeId, nodeType, name, state, attempt, logPath, outputs}'

echo "=== 各任务日志 ==="
for LP in $(curl -sf "$API/instances/$IID" -H "token: $TOKEN" | jq -r '.data.taskInstances[].logPath // empty'); do
  echo "--- $LP ---"
  docker exec datara-worker cat "$LP" 2>/dev/null | tail -15
done

echo "=== graph_json 里 sync 节点 ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -B -N -e \
  "SELECT JSON_EXTRACT(graph_json, '$.nodes[1]') FROM t_wf_definition WHERE code=19;" 2>/dev/null | head -c 1500
echo
echo "DIAG2_DONE"
