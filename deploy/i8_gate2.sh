#!/bin/bash
# I8 实测门 2：MySQL CDC binlog 行事件接入（§11.2）——C18 CDC 源 → ApiSink → 位点 log_file/log_pos 落库
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }

echo "=== 前置：遗留任务状态确认 ==="
G status all

echo "=== 门2-① 建 CDC 画布并启动流任务 ==="
WF=$(G mkwf "G2-$(date +%H%M%S)" g2 | grep -o 'wf_[0-9a-f][0-9a-f]*' | tail -1)
echo "wf=$WF"
G run "$WF"
sleep 5
JOB=$(docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e \
  "SELECT id FROM datara_meta.t_stream_job WHERE doc_id='$WF';" 2>/dev/null)
echo "jobId=$JOB"
G wait "$JOB" running 20

echo "=== 门2-② DML 触发 binlog 行事件（INSERT 5 + UPDATE 1）==="
G dml 5
sleep 10

echo "=== 门2-③ 指标（判据 totalIn=6 totalOut=6）==="
G status "$JOB"

echo "=== 门2-④ API 轮询（行事件 op/schema/table）==="
G poll "$JOB" 10

echo "=== 门2-⑤ 位点落库（判据 log_file/log_pos 非空）==="
G offsets "$JOB"
echo "G2_JOB=$JOB" > /tmp/i8_g2.env
