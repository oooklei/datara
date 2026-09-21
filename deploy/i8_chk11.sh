#!/bin/bash
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "SELECT id,status,LEFT(last_error,80),host FROM datara_meta.t_stream_job WHERE id=5;" 2>/dev/null
echo ---
docker logs datara-worker --since 10m 2>&1 | grep -E "流任务|管道|Kafka|kafka|探测|reaper|自愈" | tail -45
echo === redis 日志 ===
docker exec datara-redis redis-cli LRANGE "datara:flink:logs:5" 0 -1 | head -25
