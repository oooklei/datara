#!/bin/bash
# I8 门5 完整终验 v3：断流 → reconnecting 留痕 → 恢复 → 位点续增（fail_event 修复后）
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
JOB=5

OFF_BEFORE=$(G offsets "$JOB" | grep -o 'datara-demo-orders:0": [0-9]*' | grep -o '[0-9]*$' | head -1)
echo "=== ① 基线：running，offset=$OFF_BEFORE ==="
MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;"

echo "=== ② 断流：stop kafka ==="
docker stop datara-kafka >/dev/null
sleep 45
echo "--- 45s 后 ---"
echo "DB: $(MYQ "SELECT status,LEFT(last_error,70) FROM datara_meta.t_stream_job WHERE id=$JOB;")"

echo "=== ③ 恢复：start kafka → 轮询等 running（上限 300s） ==="
docker start datara-kafka >/dev/null
for i in $(seq 1 30); do
  sleep 10
  ST=$(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")
  echo "t=$((i*10))s status=$ST"
  [ "$ST" = "running" ] && break
done

echo "=== ④ 复投 5 条 → 轮询位点续增（上限 150s） ==="
G produce datara-demo-orders 5
OK=""
for i in $(seq 1 10); do
  sleep 15
  OFF_AFTER=$(G offsets "$JOB" | grep -o 'datara-demo-orders:0": [0-9]*' | grep -o '[0-9]*$' | head -1)
  echo "t=$((i*15))s offset=$OFF_AFTER"
  if [ -n "$OFF_AFTER" ] && [ -n "$OFF_BEFORE" ] && [ "$OFF_AFTER" -ge $((OFF_BEFORE + 5)) ]; then OK=yes; break; fi
done
G status "$JOB"

echo "=== ⑤ 日志取证（本轮断流→恢复） ==="
docker exec datara-redis redis-cli LRANGE "datara:flink:logs:$JOB" 0 -1 | head -20

echo "=== 门5 终验 v3 ==="
[ "$OK" = "yes" ] && echo "GATE5_RESULT=PASS" || echo "GATE5_RESULT=FAIL"
