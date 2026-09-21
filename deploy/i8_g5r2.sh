#!/bin/bash
# 门5 终版复测：TCP 探测修复进容器；任务 failed 则经 run wf 幂等重启；断流 reconnecting 留痕 → 恢复 → 位点续增
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }

echo "=== 0) TCP 探测修复进容器 + kill/start 重载 ==="
docker cp /mnt/lei/datara/datara-backend/worker/stream/sources.py datara-worker:/app/worker/stream/sources.py
docker kill datara-worker >/dev/null
docker start datara-worker >/dev/null
sleep 90
ST=$(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")
echo "重载后 DB 状态: $ST"
case "$ST" in
  starting|running|reconnecting) echo "任务已恢复活跃"; ;;
  *)
    WF=$(MYQ "SELECT doc_id FROM datara_meta.t_stream_job WHERE id=$JOB;")
    echo "任务 $ST → run wf 幂等重启 wf=$WF"
    G run "$WF"
    ;;
esac
sleep 8
G status "$JOB"

echo "=== 门5-① 断流：stop kafka（判据 reconnecting + last_error 留痕）==="
docker stop datara-kafka >/dev/null
sleep 15
echo "DB: $(MYQ "SELECT status FROM datara_meta.t_stream_job WHERE id=$JOB;")"
MYQ "SELECT LEFT(last_error, 80) FROM datara_meta.t_stream_job WHERE id=$JOB;"
docker logs datara-worker --since 2m 2>&1 | grep -E "管道异常|不可达" | tail -4 || true

echo "=== 门5-② 恢复：start kafka（判据回 running 且消费推进）==="
docker start datara-kafka >/dev/null
sleep 45
G status "$JOB"

echo "=== 门5-③ 位点续跑：produce 5 条（offsets 续增不回退）==="
G produce datara-demo-orders 5
sleep 10
G status "$JOB"
G offsets "$JOB"
echo "=== 门5 终版复测完成 ==="
