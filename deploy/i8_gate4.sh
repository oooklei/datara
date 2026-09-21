#!/bin/bash
# I8 实测门 4：C20 输出三通道（§11.4）——轮询 / SSE / WS（复用门3 常驻任务）
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
JOB=$(cut -d= -f2 /tmp/i8_g3.env)
echo "=== 门4：C20 输出三通道（job=$JOB）==="

echo "--- ① 轮询通道 ---"
G poll "$JOB" 5

echo "--- ② SSE 通道（5 帧）---"
G sse "$JOB" 5

echo "--- ③ WS 通道（3 帧）---"
docker exec datara-worker pip show websocket-client >/dev/null 2>&1 || docker exec datara-worker pip install -q websocket-client
docker cp /tmp/i8_ws_test.py datara-worker:/tmp/i8_ws_test.py
docker exec datara-worker python /tmp/i8_ws_test.py "$JOB"

echo "=== 门4 完成（判据：三通道均返回 rows>0 快照）==="
