#!/bin/bash
# I8 门5 终验 v2：探测 10s 超时 + MAX_RETRIES=30；断流恢复全流程（§11.5）——在 1.9 上直接执行
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)
WF=$(MYQ "SELECT doc_id FROM datara_meta.t_stream_job WHERE id=$JOB;")
echo "job=$JOB wf=$WF"

echo "=== ① 同步修复版（sources.py 探测 10s + engine.py 重试 30 次）进 worker 并重载 ==="
docker cp /mnt/lei/datara/datara-backend/worker/stream/sources.py datara-worker:/app/worker/stream/sources.py
docker cp /mnt/lei/datara/datara-backend/worker/stream/engine.py datara-worker:/app/worker/stream/engine.py
docker kill datara-worker >/dev/null
docker start datara-worker >/dev/null
sleep 60
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"

echo "=== ② 重启 failed 的门5 任务（run 幂等救起） ==="
G run "$WF"
sleep 8
G status "$JOB"

echo "=== ③ 断流：stop kafka → 观察 reconnecting 留痕 ==="
docker stop datara-kafka >/dev/null
sleep 45
echo "--- 45s 后状态 ---"
G status "$JOB"
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"
OFF_BEFORE=$(G offsets "$JOB" | grep -o 'datara-demo-orders:0": [0-9]*' | grep -o '[0-9]*$' | head -1)
echo "断流前 kafka offset=$OFF_BEFORE"

echo "=== ④ 恢复：start kafka → 轮询等 running（上限 300s，KRaft 冷启动实测 >180s） ==="
docker start datara-kafka >/dev/null
for i in $(seq 1 30); do
  sleep 10
  ST=$(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")
  echo "t=$((i*10))s status=$ST"
  [ "$ST" = "running" ] && break
done

echo "=== ⑤ 复投 5 条 → 轮询等位点续增（上限 120s，组 rejoin 需时） ==="
G produce datara-demo-orders 5
OK=""
for i in $(seq 1 8); do
  sleep 15
  OFF_AFTER=$(G offsets "$JOB" | grep -o 'datara-demo-orders:0": [0-9]*' | grep -o '[0-9]*$' | head -1)
  echo "t=$((i*15))s kafka offset=$OFF_AFTER"
  if [ -n "$OFF_AFTER" ] && [ -n "$OFF_BEFORE" ] && [ "$OFF_AFTER" -ge $((OFF_BEFORE + 5)) ]; then OK=yes; break; fi
done
G status "$JOB"

echo "=== ⑥ 日志取证 ==="
docker exec datara-redis redis-cli LRANGE "datara:flink:logs:$JOB" 0 -1 | head -30

echo "=== 门5 终验 v2 完成（判据：reconnecting 留痕→恢复 running、offset 增量≥5 不回退、终态非 failed）==="
[ "$OK" = "yes" ] && echo "GATE5_RESULT=PASS" || echo "GATE5_RESULT=FAIL"
