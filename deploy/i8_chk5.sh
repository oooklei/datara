#!/bin/bash
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
echo "--- job5 当前 ---"
G status 5
G offsets 5
echo "--- worker 近 3 分钟关键日志 ---"
docker logs datara-worker --since 3m 2>&1 | grep -E "flink job=5" | tail -10
