#!/usr/bin/env bash
# F59 发布包：语法门 + 资源/端口预检（1.9 远端执行）
set -u
echo "=== 1. 解包与语法门 ==="
rm -rf /tmp/datara-pkg-syntax
mkdir -p /tmp/datara-pkg-syntax
tar -xzf /root/datara-1.9.0.tar.gz -C /tmp/datara-pkg-syntax || { echo "TAR_FAIL"; exit 1; }
cd /tmp/datara-pkg-syntax/datara-1.9.0
for s in bin/install.sh infra/bin/*.sh; do
  if bash -n "$s"; then echo "SYNTAX_OK $s"; else echo "SYNTAX_FAIL $s"; fi
done

echo "=== 2. 脚本关键点抽查（compose 定位/参数化/502 自愈）==="
grep -c "infra/docker-compose.yml" infra/bin/install.sh
grep -c "force-recreate datara-web" infra/bin/install.sh
grep -c 'CTN_PREFIX:-datara' infra/bin/install.sh
grep -c "COMPOSE_PROJECT_NAME" infra/docker-compose.yml
grep -c "CTN_PREFIX:-datara" infra/docker-compose.yml

echo "=== 3. 资源 ==="
free -m | head -2
df -h /mnt/lei | tail -1

echo "=== 4. 端口占用（8090/8000/2181/6380/3307/3310/3309 为生产栈）==="
ss -ltn | grep -E ':(8090|8000|2181|6380|3307|3310|3309) ' | awk '{print $4}' | sort

echo "=== 5. compose 版本与运行中容器 ==="
docker compose version
docker ps --format '{{.Names}}' | sort | head -20
echo "PREFLIGHT_DONE"
