#!/usr/bin/env bash
# ============================================================
# Datara 数据重置（I2 设计文档 §8.2）
# 用法：reset.sh [--scope src|dw|all] [--refill]，默认 --scope all
# 行为：DROP DATABASE → CREATE → 重放 init SQL（结构彻底重置，分区一并清）
# 联动（裁定）：--scope src 自动联动清 dw —— 目标库=派生态，源库清空必牵连
# --refill：清空后立即重灌演示数据（等价 install.sh --with-demo-data 数据段）
# ============================================================
set -u
cd "$(dirname "$0")/../.."   # 仓库根/包根（docker-compose.yml 定位见下）

# compose 文件定位（发布包 infra/docker-compose.yml 优先，仓库根兜底）+ 发布包配置加载
if [ -z "${COMPOSE_FILE:-}" ]; then
  if [ -f "$PWD/infra/docker-compose.yml" ]; then export COMPOSE_FILE="$PWD/infra/docker-compose.yml"
  elif [ -f "$PWD/docker-compose.yml" ]; then export COMPOSE_FILE="$PWD/docker-compose.yml"; fi
fi
if [ -f "infra/.env" ]; then set -a; . infra/.env; set +a; fi

MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-datara_2026}"
SCOPE="all"
REFILL=0

log()  { echo "[reset] $*"; }
fail_exit() { echo "[reset][错误] $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)  SCOPE="${2:-}"; shift 2 ;;
    --refill) REFILL=1; shift ;;
    *) fail_exit "未知参数：$1（用法：reset.sh [--scope src|dw|all] [--refill]）" ;;
  esac
done
case "$SCOPE" in src|dw|all) ;; *) fail_exit "--scope 须为 src|dw|all" ;; esac

command -v docker >/dev/null 2>&1 || fail_exit "未检测到 docker"

# reset_db <服务> <库名> <init_sql>
reset_db() {
  local service="$1" db="$2" init_sql="$3"
  log "重置 ${service} / ${db}（DROP → CREATE → 重放 $(basename "$init_sql")）"
  docker compose exec -T "$service" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e \
    "DROP DATABASE IF EXISTS ${db}; CREATE DATABASE ${db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" \
    || fail_exit "重置库 ${db} 失败"
  docker compose exec -T "$service" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$db" < "$init_sql" \
    || fail_exit "重放 ${init_sql} 失败"
}

stale_warning() {
  cat <<'EOF'
[reset][派生失效警告] 目标库=派生态：源库已重置，dw 物化表随之清空/失配。
  受影响表：datara_dw.dwd_order_detail（订单明细宽表，派生自 src.ods_order_item 等）
  处理指引：bash infra/bin/reset.sh --refill
           或 docker compose exec datara-api python -m tools.datagen.run gen
EOF
}

# ---------- 按范围重置 ----------
if [ "$SCOPE" = "src" ] || [ "$SCOPE" = "all" ]; then
  reset_db datara-mysql-src ec_retail infra/mysql/src/init/01_schema.sql
  log "联动清空 dw（--scope src 触发：源库清空必牵连目标库）"
  reset_db datara-mysql-dw datara_dw infra/mysql/dw/init/01_schema.sql
  stale_warning
elif [ "$SCOPE" = "dw" ]; then
  reset_db datara-mysql-dw datara_dw infra/mysql/dw/init/01_schema.sql
  log "dw 已重置（src 未动；dw 重灌可经 gen 的 seed_dw 步骤）"
fi

# ---------- --refill 重灌 ----------
if [ "$REFILL" = "1" ]; then
  [ "$SCOPE" = "dw" ] && log "提示：--refill 为全量重灌（src 17 表 + dw 种子 + 对账），并非仅 dw"
  log "重灌演示数据（src 14+3 表 + dw 种子 + 自动对账；预算 ≤10 分钟）..."
  docker compose exec -T datara-api python -m tools.datagen.run gen || fail_exit "重灌失败"
else
  log "重置完成（未灌数据；需要演示数据追加 --refill）"
fi
