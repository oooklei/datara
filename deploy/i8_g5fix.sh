#!/bin/bash
# 门5 收口第一步：部署 fail_event 修复 → 重启 job5 → 验证消费真正恢复（复投 5 条增量）
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
JOB=5
WF=$(MYQ "SELECT doc_id FROM datara_meta.t_stream_job WHERE id=$JOB;")
echo "=== ① 部署 fail_event 修复 ==="
docker cp /mnt/lei/datara/datara-backend/worker/stream/engine.py datara-worker:/app/worker/stream/engine.py
docker kill datara-worker >/dev/null && docker start datara-worker >/dev/null
sleep 55

echo "=== ② 重启 job5 ==="
G run "$WF"
sleep 20
G status "$JOB"
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"

echo "=== ③ 复投 5 条 → 验证消费恢复 ==="
G produce datara-demo-orders 5
OK=""
for i in $(seq 1 6); do
  sleep 10
  OFF=$(G offsets "$JOB" | grep -o 'datara-demo-orders:0": [0-9]*' | grep -o '[0-9]*$' | head -1)
  echo "t=$((i*10))s offset=$OFF"
  if [ -n "$OFF" ] && [ "$OFF" -ge 165 ]; then OK=yes; break; fi
done
G status "$JOB"
[ "$OK" = "yes" ] && echo "STEP1_RESULT=PASS（消费恢复）" || echo "STEP1_RESULT=FAIL"
