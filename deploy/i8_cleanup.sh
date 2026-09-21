#!/bin/bash
# I8 收尾清理：停遗留 job3；诊断脚本清档（保留 gate.py 与门脚本备复验）
set -e
G() { docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_gate.py "$@"; }
MYQ() { docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "$1" 2>/dev/null; }

echo "=== 停遗留 job3（wf_644e6518，门4 画布遗留 running） ==="
G stop 3 || true
sleep 5
MYQ "SELECT id,status FROM datara_meta.t_stream_job ORDER BY id;"

echo "=== /tmp 清档 ==="
docker exec datara-worker sh -c "ls /tmp/i8_* 2>/dev/null" || true
docker exec datara-worker sh -c "rm -f /tmp/i8_chk*.sh /tmp/i8_diag*.sh /tmp/i8_dnsmon.sh /tmp/i8_g5r.sh /tmp/i8_g5r2.sh /tmp/i8_g56.sh /tmp/i8_g5probe.py 2>/dev/null; ls /tmp/i8_* 2>/dev/null" || true
echo "=== job5 终态确认（保留作为门7 演示常驻） ==="
G status 5
