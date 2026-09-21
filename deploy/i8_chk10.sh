#!/bin/bash
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
echo "--- job5 DB ---"
MYQ "SELECT status, LEFT(last_error, 120) FROM datara_meta.t_stream_job WHERE id=5\G"
echo "--- worker job5 全量日志（第 7~10 次重试明细）---"
docker logs datara-worker --since 10m 2>&1 | grep "flink job=5" | tail -20
