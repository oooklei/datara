#!/bin/bash
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
JOB=5
echo "=== DB ==="
MYQ "SELECT id,status,LEFT(last_error,60),host,generation FROM datara_meta.t_stream_job WHERE id=$JOB;"
echo "=== metrics ==="
docker exec datara-redis redis-cli HGETALL "datara:flink:metrics:$JOB"
echo "=== kafka 容器/端口 ==="
docker ps -a --filter name=datara-kafka --format "{{.Status}}"
docker exec datara-worker sh -c "timeout 3 sh -c 'echo > /dev/tcp/datara-kafka/9092' && echo TCP-OK || echo TCP-FAIL"
echo "=== consumer group ==="
docker exec datara-kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null | head -8
echo "=== offsets ==="
G offsets $JOB
echo "=== 最新 12 条日志 ==="
docker exec datara-redis redis-cli LRANGE "datara:flink:logs:$JOB" 0 11
echo "=== worker 容器日志最近 3 分钟（流相关） ==="
docker logs datara-worker --since 3m 2>&1 | grep -E "flink|流任务|管道|Kafka" | tail -15
