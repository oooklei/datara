#!/usr/bin/env bash
# F59 门8：1.9 全新空目录一条命令验证（与生产栈 /mnt/lei/datara 完全隔离）
# 隔离手段：独立项目名/容器前缀/镜像 tag/端口段（infra/.env 注入）
set -u
echo "=== 0. 全新空目录 ==="
PKG=/mnt/lei/datara-pkgtest
if [ -e "$PKG" ]; then echo "ABORT: $PKG 已存在（为防误删生产目录，需人工确认后手动清理）"; exit 1; fi
mkdir -p "$PKG"
tar -xzf /root/datara-1.9.0.tar.gz -C "$PKG" --strip-components=1
cd "$PKG"

echo "=== 1. 隔离配置 infra/.env ==="
cat > infra/.env <<'EOF'
COMPOSE_PROJECT_NAME=datara-pkgtest
CTN_PREFIX=dpkg
BACKEND_IMAGE=datara-backend:pkgtest
WEB_PORT=18090
API_PORT=18000
ZK_PORT=12181
REDIS_PORT=16380
META_PORT=13307
SRC_PORT=13310
DW_PORT=13309
EOF
cat infra/.env

echo "=== 2. 一条命令部署（bash bin/install.sh）==="
bash bin/install.sh
echo "INSTALL_RC=$?"
