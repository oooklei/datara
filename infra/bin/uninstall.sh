#!/usr/bin/env bash
# ============================================================
# Datara 卸载（I2 设计文档 §8.4；破坏性：删除全部数据卷，不可恢复）
# 行为：docker compose down -v --remove-orphans
#   数据卷一并删除：mysql-meta-data / mysql-src-data / mysql-dw-data /
#                   redis-data / zookeeper-data / datara-logs
# 幂等：栈未运行时重复执行无报错
# ============================================================
set -u
cd "$(dirname "$0")/../.."   # 仓库根/包根（docker-compose.yml 定位见下）

# compose 文件定位（发布包 infra/docker-compose.yml 优先，仓库根兜底）+ 发布包配置加载
if [ -z "${COMPOSE_FILE:-}" ]; then
  if [ -f "$PWD/infra/docker-compose.yml" ]; then export COMPOSE_FILE="$PWD/infra/docker-compose.yml"
  elif [ -f "$PWD/docker-compose.yml" ]; then export COMPOSE_FILE="$PWD/docker-compose.yml"; fi
fi
if [ -f "infra/.env" ]; then set -a; . infra/.env; set +a; fi

log() { echo "[uninstall] $*"; }

log "停止并移除容器、网络与全部数据卷（数据不可恢复）..."
docker compose down -v --remove-orphans \
  || log "compose down 返回非零（栈可能未在运行，视为幂等继续）"

log "主机目录未删除：datara-web/dist、部署 tar 包、宿主日志目录（如需彻底清理请手动处理）"
log "卸载完成（重装：bash infra/bin/install.sh [--with-demo-data]）"
