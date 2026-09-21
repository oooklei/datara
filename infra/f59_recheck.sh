#!/usr/bin/env bash
# F59 门8 补验：生产栈零影响 + pkgtest 栈健康 + 前端产物核对
set -u
echo "=== 1. 生产栈（/mnt/lei/datara，8090）健康 ==="
docker ps --filter name=datara- --format '{{.Names}}\t{{.Status}}' | sort
echo "prod web: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8090/)"
echo "prod api: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/health)"

echo "=== 2. pkgtest 栈（dpkg-*，18090）健康 ==="
docker ps --filter name=dpkg- --format '{{.Names}}\t{{.Status}}' | sort
echo "pkg web: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:18090/)"
echo "pkg api health: $(curl -s http://localhost:18000/api/v1/health)"

echo "=== 3. pkg 前端产物指纹（发布包 dist 生效核对）==="
curl -s http://localhost:18090/ | grep -o 'index-[A-Za-z0-9_-]*\.js' | head -1
curl -s http://localhost:8090/ | grep -o 'index-[A-Za-z0-9_-]*\.js' | head -1

echo "=== 4. pkg 冒烟链路复核（独立项目名/网络生效）==="
docker exec dpkg-worker sh -c 'cd /app && PYTHONPATH=/app ADMIN_PWD=Admin@123 python - < /dev/stdin' < /mnt/lei/datara-pkgtest/infra/smoke/smoke.py | tail -2

echo "=== 5. 卷隔离核对（pkgtest 卷独立前缀）==="
docker volume ls --format '{{.Name}}' | grep -E 'datara-pkgtest|^(datara_)' | sort
echo "RECHECK_DONE"
