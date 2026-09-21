#!/bin/bash
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
sleep 20
echo "--- job5 实时 ---"
G status 5
echo "--- 近 4 分钟 job5 全量日志 ---"
docker logs datara-worker --since 4m 2>&1 | grep "flink job=5" | tail -15
