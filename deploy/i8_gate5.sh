#!/bin/bash
# I8 实测门 5：断流恢复（§11.5）——stop kafka → reconnecting 留痕 → 重启自动重连 → 位点续跑不丢
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)

echo "=== 门5-① 基线（job=$JOB）==="
G status "$JOB"

echo "=== 门5-② 断流：docker stop datara-kafka ==="
docker stop datara-kafka >/dev/null
sleep 12
G status "$JOB"
echo "--- 重连日志留痕 ---"
docker logs datara-worker --since 2m 2>&1 | grep -E "reconnect|重连" | tail -6 || true

echo "=== 门5-③ 恢复：docker start datara-kafka ==="
docker start datara-kafka >/dev/null
sleep 40
G status "$JOB"

echo "=== 门5-④ 位点续跑：投递 10 条新订单（判据 offsets 从断点续增、不回退重消费）==="
G produce datara-demo-orders 10
sleep 10
G status "$JOB"
G offsets "$JOB"

echo "=== 门5 完成 ==="
