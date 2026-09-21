#!/usr/bin/env bash
# ============================================================
# Datara 业务数据导入（I2 设计文档 §8.3）
# 用法：import.sh --type csv-dir|sql-dump --path <路径> [--schema ec_retail] [--truncate]
#   csv-dir ：目录内 <table>.csv（首行列名映射表字段，列失配拒绝导入）
#             → docker compose cp 至 datara-api 容器 → tools.datagen.import_csv
#             （复用容器网络环境，规避 mysql local_infile 配置）
#   sql-dump：dump 文件（宿主机本地路径）经 mysql 直放
# 导入后：csv-dir 通道自动对账并更新 reconcile.json（mode=import）；
#         输出派生失效警告（目标库=派生态）
# 安全边界：仅允许业务 schema（ec_retail / datara_dw），meta 库拒绝导入
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
TYPE="" PATH_ARG="" SCHEMA="ec_retail" TRUNCATE=0
IMPORT_DIR_IN_CONTAINER="/tmp/datara-import"

log()  { echo "[import] $*"; }
fail_exit() { echo "[import][错误] $*" >&2; exit 1; }

usage() {
  echo "用法：import.sh --type csv-dir|sql-dump --path <路径> [--schema ec_retail] [--truncate]" >&2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --type)     TYPE="$2"; shift 2 ;;
    --path)     PATH_ARG="$2"; shift 2 ;;
    --schema)   SCHEMA="$2"; shift 2 ;;
    --truncate) TRUNCATE=1; shift ;;
    *) usage; fail_exit "未知参数：$1" ;;
  esac
done
[ -n "$TYPE" ]     || { usage; fail_exit "缺 --type"; }
[ -n "$PATH_ARG" ] || { usage; fail_exit "缺 --path"; }

# schema → 容器/库 映射（安全边界：仅业务库，meta 拒绝）
case "$SCHEMA" in
  ec_retail)  SERVICE="datara-mysql-src"; DB="ec_retail" ;;
  datara_dw)  SERVICE="datara-mysql-dw";  DB="datara_dw" ;;
  *)          fail_exit "拒绝导入：schema 须为 ec_retail / datara_dw（meta 库不允许导入）" ;;
esac

command -v docker >/dev/null 2>&1 || fail_exit "未检测到 docker"

stale_warning() {
  cat <<'EOF'
[import][派生失效警告] 目标库=派生态：源库数据已变更，dw 物化表随之失配。
  受影响表：datara_dw.dwd_order_detail（订单明细宽表，派生自 src.ods_order_item 等）
  风险提示：平台内基于 dw 的血缘/同步/SQL 查询将基于旧数据（I3 后本提示充实）
  处理指引：docker compose exec datara-api python -m tools.datagen.run gen
           或 bash infra/bin/reset.sh --scope all --refill
EOF
}

# ---------- csv-dir 通道 ----------
if [ "$TYPE" = "csv-dir" ]; then
  [ -d "$PATH_ARG" ] || fail_exit "目录不存在：$PATH_ARG"
  log "清理容器暂存目录并上传 ${PATH_ARG} → datara-api:${IMPORT_DIR_IN_CONTAINER}"
  docker compose exec -T datara-api sh -c "rm -rf ${IMPORT_DIR_IN_CONTAINER} && mkdir -p ${IMPORT_DIR_IN_CONTAINER}" \
    || fail_exit "容器暂存目录准备失败"
  docker compose cp "$PATH_ARG/." "datara-api:${IMPORT_DIR_IN_CONTAINER}/" \
    || fail_exit "CSV 目录上传失败"
  TRUNCATE_FLAG=""
  [ "$TRUNCATE" = "1" ] && TRUNCATE_FLAG="--truncate"
  log "容器内执行导入（schema=${SCHEMA}${TRUNCATE:+，truncate}）..."
  docker compose exec -T datara-api python -m tools.datagen.import_csv \
    --dir "$IMPORT_DIR_IN_CONTAINER" --schema "$SCHEMA" $TRUNCATE_FLAG
  rc=$?
  docker compose exec -T datara-api sh -c "rm -rf ${IMPORT_DIR_IN_CONTAINER}" || true
  [ "$rc" -eq 0 ] || fail_exit "导入失败（退出码 ${rc}，明细见上方输出与 reconcile.json）"
  [ "$SCHEMA" = "ec_retail" ] && stale_warning
  exit 0
fi

# ---------- sql-dump 通道 ----------
if [ "$TYPE" = "sql-dump" ]; then
  [ -f "$PATH_ARG" ] || fail_exit "dump 文件不存在：$PATH_ARG"
  log "直放 dump：$PATH_ARG → ${SERVICE}/${DB}（结构以 dump 内 DDL 为准）"
  docker compose exec -T "$SERVICE" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$DB" < "$PATH_ARG" \
    || fail_exit "dump 执行失败"
  log "导入后行数概览："
  for t in $(docker compose exec -T "$SERVICE" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e \
      "SELECT table_name FROM information_schema.tables WHERE table_schema='${DB}'" 2>/dev/null); do
    cnt=$(docker compose exec -T "$SERVICE" mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e \
      "SELECT COUNT(*) FROM \`${t}\`" 2>/dev/null)
    echo "  ${t}: ${cnt}"
  done
  # 说明：sql-dump 结构未知，不做 fixture 对账；reconcile.json 仅 csv-dir 通道更新
  [ "$SCHEMA" = "ec_retail" ] && stale_warning
  exit 0
fi

usage
fail_exit "--type 须为 csv-dir 或 sql-dump"
