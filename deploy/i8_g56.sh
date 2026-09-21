#!/bin/bash
# I8 门6 容错（kill worker → reaper 失联接管 → 位点续跑）+ 门5 复测（断流感知修复后 reconnecting 留痕）
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)

echo "=== 门6-① 宿主崩溃：docker kill datara-worker ==="
G status "$JOB"
docker kill datara-worker >/dev/null
docker start datara-worker >/dev/null
echo "--- 等待 reaper 失联接管（alive TTL 45s + reaper 30s 周期）---"
sleep 90
G status "$JOB"

echo "=== 门6-② 位点续跑：produce 5 条（判据 totalIn 增量=5 无重放）==="
G produce datara-demo-orders 5
sleep 10
G status "$JOB"
G offsets "$JOB"

echo "=== 门5-复测① 断流：stop kafka（判据 reconnecting + 日志留痕）==="
docker stop datara-kafka >/dev/null
sleep 12
G status "$JOB"
echo "--- 重连日志留痕 ---"
docker logs datara-worker --since 3m 2>&1 | grep -E "reconnect|重连|管道异常|broker" | tail -8 || true

echo "=== 门5-复测② 恢复：start kafka（判据自动回 running）==="
docker start datara-kafka >/dev/null
sleep 40
G status "$JOB"

echo "=== 门5-复测③ 位点续跑：produce 5 条（offsets 续增不回退）==="
G produce datara-demo-orders 5
sleep 10
G status "$JOB"
G offsets "$JOB"
echo "=== 门5/门6 完成 ==="
