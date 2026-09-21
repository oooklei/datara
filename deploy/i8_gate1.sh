#!/bin/bash
# I8 实测门 1：Kafka 订单流接入（§11.1）——C18 消费 → 速率/位点实时可见
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }

echo "=== 门1-① 建画布并启动流任务 ==="
WF=$(G mkwf "G1-$(date +%H%M%S)" g1 | grep -o 'wf_[0-9a-f][0-9a-f]*' | tail -1)
echo "wf=$WF"
G run "$WF"
sleep 5
JOB=$(docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e \
  "SELECT id FROM datara_meta.t_stream_job WHERE doc_id='$WF';" 2>/dev/null)
echo "jobId=$JOB"

echo "=== 门1-② 模拟订单生产者 20 条 ==="
G produce datara-demo-orders 20
sleep 8

echo "=== 门1-③ 速率/累计/位点实时指标 ==="
G status "$JOB"
echo "--- 日志尾 ---"
TOKEN=$(docker exec datara-worker python -c "
import requests
d = requests.post('http://datara-api:8000/api/v1/login', json={'user_name':'admin','user_pwd':'Admin@123'}, timeout=10).json()['data']
print(d['token'])")
curl -s -H "token: $TOKEN" "http://localhost:8000/api/v1/stream-jobs/$JOB/logs?lines=8" | python3 -c "import json,sys; [print(l) for l in json.load(sys.stdin)['data'][:8]]" || true

echo "=== 门1-④ API 轮询输出 ==="
G poll "$JOB" 10
echo "=== 门1-⑤ 位点落库 ==="
G offsets "$JOB"
echo "=== 门1 完成（PASS 判据：running/totalIn≥20/totalOut≥20/offsets 非空）==="
echo "G1_JOB=$JOB" > /tmp/i8_g1.env
