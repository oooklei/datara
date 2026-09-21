#!/bin/bash
cat > /tmp/probe2.py <<'EOF'
import socket, time
print("--- TCP 探测 x5 ---")
for i in range(5):
    t0 = time.time()
    try:
        s = socket.create_connection(("datara-kafka", 9092), timeout=3)
        print(f"#{i+1} TCP-OK {time.time()-t0:.2f}s")
        s.close()
    except OSError as e:
        print(f"#{i+1} TCP-FAIL {time.time()-t0:.2f}s {e}")
    time.sleep(0.3)
print("--- kafka-python bootstrap 测试 ---")
try:
    from kafka import KafkaConsumer
    t0 = time.time()
    c = KafkaConsumer("datara-demo-orders", bootstrap_servers=["datara-kafka:9092"],
                      group_id="probe-test", consumer_timeout_ms=2000)
    batches = c.poll(timeout_ms=2000, max_records=3)
    n = sum(len(v) for v in batches.values())
    print(f"bootstrap+poll OK {time.time()-t0:.2f}s records={n}")
    c.close()
except Exception as e:
    print(f"bootstrap FAIL: {type(e).__name__}: {e}")
EOF
docker cp /tmp/probe2.py datara-worker:/tmp/probe2.py
docker exec datara-worker python /tmp/probe2.py
echo "--- job5 最新日志 ---"
docker logs datara-worker --since 2m 2>&1 | grep "flink job=5" | tail -6
echo "--- kafka 容器状态与日志 ---"
docker ps --format '{{.Names}} {{.Status}}' | grep kafka
docker logs datara-kafka --since 4m 2>&1 | tail -8
