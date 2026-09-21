#!/bin/bash
cat > /tmp/dnsmon.py <<'EOF'
import socket, time
fails = 0
for i in range(30):
    try:
        ip = socket.gethostbyname("datara-kafka")
        print(f"t+{i:02d}s OK {ip}")
    except OSError as e:
        fails += 1
        print(f"t+{i:02d}s FAIL {e}")
    time.sleep(1)
print(f"--- 30s 内失败 {fails} 次 ---")
EOF
docker cp /tmp/dnsmon.py datara-worker:/tmp/dnsmon.py
docker exec datara-worker python /tmp/dnsmon.py
echo "--- job5 实时 ---"
docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py status 5
