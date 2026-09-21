#!/usr/bin/env bash
# I6 诊断：最新失败实例的任务明细 + sync 任务日志（1.9 远端执行）
API=http://localhost:8000/api/v1
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' \
  -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)

IID=$(curl -sf -G "$API/instances" -H "token: $TOKEN" \
  --data-urlencode "state=failure" --data-urlencode "page_size=1" \
  | jq -r '.data.list[0].instanceId')
echo "=== 最新失败实例: $IID ==="
curl -sf "$API/instances/$IID" -H "token: $TOKEN" | jq -c '.data.taskInstances[] | {nodeId, nodeType, name, state, attempt, outputs, logPath}'
LP=$(curl -sf "$API/instances/$IID" -H "token: $TOKEN" \
  | jq -r '[.data.taskInstances[] | select(.nodeType=="sync")][0].logPath')
echo "=== sync 日志 $LP ==="
docker exec datara-worker cat "$LP" 2>/dev/null | tail -40
echo "=== worker 最近日志 ==="
docker logs datara-worker --tail 20 2>&1 | tail -20
echo "=== master 最近日志 ==="
docker logs datara-master --tail 15 2>&1 | tail -15
