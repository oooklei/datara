#!/bin/bash
echo "=== 1) 全容器搜索错误字符串 ==="
docker exec datara-worker grep -rn "TCP 探测全部失败" /app --include="*.py" | grep -v __pycache__
echo "=== 2) 谁在抛：engine _pipeline_once 源异常包装段 ==="
docker exec datara-worker grep -n "源 {0}" /app/worker/stream/engine.py 2>/dev/null | head
docker exec datara-worker grep -n "源 " /app/worker/stream/engine.py | head -10
echo "=== 3) 复刻实验：独立进程 KafkaSource 空转探测 ==="
docker exec datara-worker sh -c "PYTHONPATH=/app timeout 60 python - <<'EOF'
import logging, time
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(name)s %(message)s')
logging.getLogger('kafka').setLevel(logging.WARNING)
from worker.stream.sources import KafkaSource
src = KafkaSource('probe', {'srcType':'kafka','brokers':'datara-kafka:9092','topic':'datara-demo-orders','group':'probe5-'+str(int(time.time())),'startFrom':'earliest','format':'json'})
src.open(None)
print('open OK, brokers=', src.brokers)
t0=time.time()
for i in range(60):
    rows = src.poll(100)
    if rows:
        print(f'poll#{i} got {len(rows)} rows'); break
    if i in (20, 30, 40, 50):
        print(f'poll#{i} empty, idle={src._idle}, elapsed={time.time()-t0:.1f}s')
time.sleep(0.5)
print('manual probe _brokers_alive ->', src._brokers_alive())
src.close()
EOF"
echo "=== 4) job5 spec_json 的 brokers/group ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "SELECT spec_json FROM datara_meta.t_stream_job WHERE id=5;" 2>/dev/null | head -c 600
