#!/bin/bash
# 门5 取证复测：探测日志版进容器；同步最新 gate.py；重启 job5；断流→恢复全链路取证
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)
WF=$(MYQ "SELECT doc_id FROM datara_meta.t_stream_job WHERE id=$JOB;")

echo "=== 0) 同步探测日志版 sources.py + 最新 gate.py + 重载 ==="
docker cp /mnt/lei/datara/datara-backend/worker/stream/sources.py datara-worker:/app/worker/stream/sources.py
docker cp /tmp/i8_gate.py datara-worker:/tmp/i8_gate.py
docker kill datara-worker >/dev/null
docker start datara-worker >/dev/null
sleep 90
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"
G run "$WF"
sleep 30
G status "$JOB"

echo "=== 门5-B' 断流取证：stop kafka → 探测失败明细 ==="
docker stop datara-kafka >/dev/null
sleep 15
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"
docker logs datara-worker --since 2m 2>&1 | grep -E "探测失败|不可达|管道异常" | tail -6 || true

echo "=== 门5-C' 恢复：start kafka（60s）==="
docker start datara-kafka >/dev/null
sleep 60
G status "$JOB"
docker logs datara-worker --since 90s 2>&1 | grep -E "探测失败|KafkaTimeout|flink job=5" | tail -8 || true

echo "=== 门5-D' produce 5 条验证续跑 ==="
G produce datara-demo-orders 5
sleep 10
G status "$JOB"
G offsets "$JOB"
echo "=== 取证复测完成 ==="
