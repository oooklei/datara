#!/bin/bash
echo "--- kafka 容器状态 ---"
docker ps -a --format '{{.Names}} {{.Status}}' | grep -E 'kafka'
echo "--- worker 容器内 TCP 探测 ---"
cat > /tmp/tcpprobe.py <<'EOF'
import socket
try:
    s = socket.create_connection(("datara-kafka", 9092), timeout=2)
    print("TCP-OK")
    s.close()
except OSError as e:
    print("TCP-FAIL:", e)
EOF
docker cp /tmp/tcpprobe.py datara-worker:/tmp/tcpprobe.py
docker exec datara-worker python /tmp/tcpprobe.py
echo "--- kafka 容器近 5 分钟日志 ---"
docker logs datara-kafka --since 5m 2>&1 | tail -6
