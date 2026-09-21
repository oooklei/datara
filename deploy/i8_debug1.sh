#!/bin/bash
echo "=== 全部流任务状态 ==="
docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py status all 2>/dev/null
echo "=== topic 分区与消息验证 ==="
docker exec datara-kafka kafka-run-class.sh kafka.tools.GetOffsetShell --broker-list localhost:9092 --topic datara-demo-orders --time -1 2>/dev/null | tail -3
echo "=== worker 近期 flink 日志 ==="
docker logs datara-worker --since 6m 2>&1 | grep -E "flink|流任务|Kafka" | tail -15
