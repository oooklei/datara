#!/usr/bin/env bash
# I9 实测门驱动（F57 门6）：1.9 上执行冒烟 + seek 修复验证（datara-worker 容器内）
# 用法：scp infra/i9_run.sh deploy/i9_smoke.py deploy/i9_seek.py root@192.168.1.9:/tmp/ && ssh root@192.168.1.9 bash /tmp/i9_run.sh
set -u
sed -i 's/\r$//' /tmp/i9_smoke.py /tmp/i9_seek.py 2>/dev/null
docker cp /tmp/i9_smoke.py datara-worker:/tmp/i9_smoke.py
docker cp /tmp/i9_seek.py datara-worker:/tmp/i9_seek.py

RC=0
echo '===== I9 SMOKE ====='
docker exec -e PYTHONPATH=/app datara-worker python /tmp/i9_smoke.py || RC=1
echo '===== I9 SEEK GATE ====='
docker exec -e PYTHONPATH=/app datara-worker python /tmp/i9_seek.py || RC=1
echo "I9_GATE_RC=$RC"
exit $RC
