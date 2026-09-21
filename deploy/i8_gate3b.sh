#!/bin/bash
# 门3 复测：binlog_row_metadata=FULL（CDC 列名）+ 停遗留任务（group 竞争）+ 独立 group 画布
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }

echo "=== 修复1：binlog_row_metadata → FULL ==="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 -N -e "SET PERSIST binlog_row_metadata='FULL'; SELECT @@binlog_row_metadata;" 2>/dev/null

echo "=== 修复2：停遗留 job2/job4 ==="
G stop 2 || true
G stop 4 || true
sleep 4
G status all

echo "=== 门3 复测：独立 group 融合画布 ==="
WF=$(G mkwf "G3B-$(date +%H%M%S)" g3 | grep -o 'wf_[0-9a-f][0-9a-f]*' | tail -1)
echo "wf=$WF"
G run "$WF"
sleep 5
JOB=$(docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e \
  "SELECT id FROM datara_meta.t_stream_job WHERE doc_id='$WF';" 2>/dev/null)
echo "jobId=$JOB"
G wait "$JOB" running 20

echo "=== 门3-② 双源投递：Kafka 订单 20 条 + CDC DML 2 条 ==="
G produce datara-demo-orders 20
G dml 2
echo "--- 等待窗口触发（tumbling 10s + watermark 2s）---"
sleep 16

echo "=== 门3-③ 指标（判据 totalIn≥23 / windowEmits>0）==="
G status "$JOB"

echo "=== 门3-④ API 轮询（聚合行 + cdc 列名行）==="
G poll "$JOB" 12

echo "=== 门3-⑤ 窗口触发计数 ==="
G windowemits "$JOB"
echo "=== 门3-⑥ 位点 ==="
G offsets "$JOB"
echo "G3_JOB=$JOB" > /tmp/i8_g3.env
