#!/bin/bash
# 门5 复测：断流感知代码 docker cp 进 worker 容器（kill/start 走门6 恢复路径加载新代码）
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)

echo "=== 0) 部署断流感知修复 + kill/start 重载 ==="
docker cp /mnt/lei/datara/datara-backend/worker/stream/sources.py datara-worker:/app/worker/stream/sources.py
G status "$JOB"
docker kill datara-worker >/dev/null
docker start datara-worker >/dev/null
sleep 90
G status "$JOB"

echo "=== 门5-① 断流：stop kafka（判据 reconnecting + 日志留痕）==="
docker stop datara-kafka >/dev/null
sleep 12
G status "$JOB"
docker logs datara-worker --since 2m 2>&1 | grep -E "管道异常|重连|不可达" | tail -8 || true

echo "=== 门5-② 恢复：start kafka（判据自动回 running）==="
docker start datara-kafka >/dev/null
sleep 40
G status "$JOB"

echo "=== 门5-③ 位点续跑：produce 5 条（offsets 续增不回退）==="
G produce datara-demo-orders 5
sleep 10
G status "$JOB"
G offsets "$JOB"
echo "=== 门5 复测完成 ==="
