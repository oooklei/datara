#!/usr/bin/env bash
# I6 实测诊断：实例真态 + 定义保存情况 + master/worker 日志尾部
set -u
API=http://localhost:8000/api/v1
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)

echo "=== 1. I6 定义保存情况 ==="
curl -sf -G "$API/workflow-definitions" -H "token: $TOKEN" --data-urlencode "search=I6-" --data-urlencode "page_size=50" \
  | jq -c '.data.list[] | {id, code, name, nodeCount, updatedAt}'

echo "=== 2. 最近 8 条实例原始态 ==="
curl -sf -G "$API/instances" -H "token: $TOKEN" --data-urlencode "page_size=8" \
  | jq -c '.data.list[] | {instanceId, wfCode, state, runMode, startTime}'

echo "=== 3. master 日志尾部 ==="
docker logs datara-master --tail 30 2>&1 | tail -30

echo "=== 4. worker 日志尾部 ==="
docker logs datara-worker --tail 30 2>&1 | tail -30

echo "=== 5. 手动重跑 I6-单源基准（原始响应） ==="
WF_ID=$(curl -sf -G "$API/workflow-definitions" -H "token: $TOKEN" --data-urlencode "search=I6-单源基准" | jq -r '.data.list[0].id')
echo "wf_id=$WF_ID"
curl -s -X POST $API/workflow-definitions/$WF_ID/run -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' | head -c 600
echo
sleep 6
CODE=$(curl -sf -G "$API/workflow-definitions" -H "token: $TOKEN" --data-urlencode "search=I6-单源基准" | jq -r '.data.list[0].code')
echo "code=$CODE"
curl -s -G "$API/instances" -H "token: $TOKEN" --data-urlencode "wf_code=$CODE" --data-urlencode "page_size=3" \
  | jq -c '.data.list[]? | {instanceId, state}'
echo "DIAG_DONE"
