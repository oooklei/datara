#!/bin/bash
# I8 门7 时延精测 v2：修正 rows 解析
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=5
T0=$(date +%s)
echo "T0=$T0 ($(date '+%H:%M:%S')) 投 3 条 + 1 DML"
docker exec datara-worker sh -c "PYTHONPATH=/app python - <<'EOF'
import json, time
from kafka import KafkaProducer
p = KafkaProducer(bootstrap_servers='datara-kafka:9092', value_serializer=lambda v: json.dumps(v).encode())
t = time.time()
for i in range(3):
    now = time.time()
    p.send('datara-demo-orders', {'order_id': f'G7B-{i}', 'category': 'food', 'amount': 50.0+i, 'ts': round(now,3)})
    print(f'send#{i} {now:.3f}')
p.flush(); p.close()
print(f'done {time.time():.3f}')
EOF"
docker exec datara-worker python /tmp/i8_gate.py dml 1 >/dev/null 2>&1 || true
T1=$(date +%s)
echo "投递完成 T1=$T1 ($(date '+%H:%M:%S'))"

echo "=== 每 2s poll 至首见新数据（上限 60s） ==="
for i in $(seq 1 30); do
  sleep 2
  OUT=$(G poll "$JOB" 3 2>/dev/null | head -6)
  N=$(echo "$OUT" | grep -oE 'rows=[0-9]+' | head -1 | cut -d= -f2)
  NEW=$(echo "$OUT" | grep -c "G7B\|cdc-17898167")
  echo "t=$(( (i*2) ))s rows=$N 新行命中=$NEW"
  if [ "$NEW" -gt 0 ]; then
    NOW=$(date +%s)
    echo "首见新数据: 投递开始+=$((NOW-T0))s，投递完成+=$((NOW-T1))s"
    break
  fi
done
echo "--- 首见输出样本 ---"
G poll "$JOB" 3
date '+now=%H:%M:%S'
echo "--- 指标 ---"
G status "$JOB"
