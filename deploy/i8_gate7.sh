#!/bin/bash
# I8 门7：全链路时延实测（§11.7）——订单流+CDC→融合→API 消费，端到端秒级可见
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=5

echo "=== ① 基线：任务 running + 记录投递前时刻 ==="
G status "$JOB"
T0=$(date +%s)
echo "T0=$T0 ($(date '+%H:%M:%S'))"

echo "=== ② 持续投递 12 条订单（1s 间隔，含 ts）+ 中途 2 条 CDC DML ==="
docker exec datara-worker sh -c "PYTHONPATH=/app python - <<'EOF'
import json, time
from kafka import KafkaProducer
p = KafkaProducer(bootstrap_servers='datara-kafka:9092', value_serializer=lambda v: json.dumps(v).encode())
base = time.time()
for i in range(12):
    now = time.time()
    msg = {'order_id': f'G7-{i}', 'category': ['food','electronic','clothing'][i % 3],
           'amount': round(10 + i * 1.5, 2), 'ts': round(now, 3)}
    p.send('datara-demo-orders', msg)
    print(f'send#{i} at {now:.3f}')
    time.sleep(1)
p.flush(); p.close()
EOF"
docker exec datara-worker python /tmp/i8_gate.py dml 2 >/dev/null 2>&1 || true
T1=$(date +%s)
echo "投递完成 T1=$T1 ($(date '+%H:%M:%S')，耗时 $((T1-T0))s)"

echo "=== ③ 每 3s poll API 输出，直至可见新数据（上限 60s） ==="
FIRST_SEEN=""
for i in $(seq 1 20); do
  sleep 3
  OUT=$(G poll "$JOB" 5 2>/dev/null)
  N=$(echo "$OUT" | grep -o '"rows": *[0-9]*' | grep -o '[0-9]*$' | head -1)
  echo "t=$((i*3))s poll rows=$N"
  if [ -n "$N" ] && [ "$N" -gt 0 ]; then FIRST_SEEN=$((i*3)); break; fi
done
echo "首见新数据耗时: ${FIRST_SEEN:->60}s（自投递完成起）"

echo "=== ④ 输出行样本（看 win_end/updated_at 与当前时刻差） ==="
G poll "$JOB" 5
date '+now=%H:%M:%S'

echo "=== ⑤ 指标确认 ==="
G status "$JOB"
echo "=== 门7 完成（判据：投递→API 可见秒级；窗口聚合行按窗口粒度如实记录）==="
