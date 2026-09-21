#!/bin/bash
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
echo "--- 等 60s 观察 job5 自愈 ---"
sleep 60
G status 5
echo "--- 再投 5 条验证消费 ---"
G produce datara-demo-orders 5
sleep 15
G status 5
G offsets 5
echo "--- kafka 服务端 i8-flink 组活动 ---"
docker logs datara-kafka --since 5m 2>&1 | grep "i8-flink" | tail -6
