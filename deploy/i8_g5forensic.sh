#!/bin/bash
# 门5 取证-II：裁决日志版重载 → 重启 job5 → 断流 → 捕获探测判定明细
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)
WF=$(MYQ "SELECT doc_id FROM datara_meta.t_stream_job WHERE id=$JOB;")

docker cp /mnt/lei/datara/datara-backend/worker/stream/sources.py datara-worker:/app/worker/stream/sources.py
docker kill datara-worker >/dev/null
docker start datara-worker >/dev/null
sleep 90
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"
G run "$WF"
sleep 25
G status "$JOB"

echo "=== 断流取证：stop kafka 15s ==="
docker stop datara-kafka >/dev/null
sleep 15
docker logs datara-worker --since 40s 2>&1 | grep -E "探测失败|探测判定|不可达|KafkaTimeout" | tail -8 || true

echo "=== 恢复：start kafka 75s ==="
docker start datara-kafka >/dev/null
sleep 75
G status "$JOB"
docker logs datara-worker --since 80s 2>&1 | grep -E "探测判定|不可达|装配完成|管道异常|KafkaTimeout" | tail -10 || true

echo "=== produce 5 条验证 ==="
G produce datara-demo-orders 5
sleep 15
G status "$JOB"
echo "=== 取证-II 完成 ==="
