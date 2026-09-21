#!/bin/bash
# 门1 处置：1) poll 信封修复同步进 api 容器 2) 停遗留 job1 释放 group 分区 3) 复测
set -e
echo "=== 1) 同步 poll 信封修复 → datara-api ==="
docker cp /mnt/lei/datara/datara-backend/api/streamdata.py datara-api:/app/api/streamdata.py
docker restart datara-api >/dev/null
for i in 1 2 3 4 5; do
  sleep 4
  if docker exec datara-api python -c "import socket;socket.create_connection(('127.0.0.1',8000),3).close();print('api port-up')"; then
    break
  fi
done

echo "=== 2) 同步 gate 脚本 ==="
docker cp /tmp/i8_gate.py datara-worker:/tmp/i8_gate.py
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }

echo "=== 3) 停遗留 job1（释放 group i8-flink 分区）==="
G stop 1 || true
sleep 4
G status 1 || true

echo "=== 4) 再投 20 条（job2 从 group 已提交位点续跑）==="
G produce datara-demo-orders 20

sleep 8
echo "=== 5) job2 状态 ==="
G status 2
echo "=== 6) poll（信封修复验证）==="
G poll 2 10
