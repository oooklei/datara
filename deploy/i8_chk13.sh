#!/bin/bash
echo "=== 1) 容器内 sources.py 探测代码版本 ==="
docker exec datara-worker grep -n "timeout=" /app/worker/stream/sources.py | head -5
docker exec datara-worker grep -n "MAX_RETRIES" /app/worker/stream/engine.py | head -2
echo "=== 2) worker→kafka DNS 解析 ==="
docker exec datara-worker getent hosts datara-kafka || echo "DNS-FAIL"
echo "=== 3) worker→kafka TCP 探测（python 直测） ==="
docker exec datara-worker python -c "
import socket
for h in ['datara-kafka']:
    try:
        ip = socket.gethostbyname(h); print('DNS OK', h, '->', ip)
        s = socket.create_connection((ip, 9092), timeout=5); print('TCP OK'); s.close()
    except OSError as e:
        print('FAIL', h, type(e).__name__, e)
"
echo "=== 4) docker logs 全量未过滤 tail -25 ==="
docker logs datara-worker --since 4m 2>&1 | tail -25
echo "=== 5) 其他流任务状态（谁在用 i8-flink 组） ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "SELECT id,status,doc_id FROM datara_meta.t_stream_job ORDER BY id;" 2>/dev/null
echo "=== 6) i8-flink 组详情 ==="
docker exec datara-kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group i8-flink 2>&1 | head -8
