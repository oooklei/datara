#!/usr/bin/env bash
# ============================================================
# Datara 日志定期清理（F50，I3 设计文档 §11.2）
# 用法：bash infra/bin/clean_logs.sh [--retain-days N] [--dry-run]
#   --retain-days N   保留天数（默认 30；.env LOG_RETAIN_DAYS 可覆盖，命令行优先）
#   --dry-run         只打印将清理的内容与统计，不实际删除
# 动作（幂等，可重复执行）：
#   ① 共享卷日志目录 /datara/logs/{instance_id}：mtime 超过保留天数 → 删除
#   ② meta 库索引行：t_task_log 过期实例行删除；t_alert_record 过期行删除
#   ③ {instance_id}_ 前缀临时数据清扫：
#      /datara/tmp 临时文件 + 各库临时表（INFORMATION_SCHEMA 枚举 DROP，为 I4 C22 预置）
#   ④ t_tmp_data 过期行清扫（I4）：expire_at 到期 active 行 → 按目标库 DROP 临时表 /
#      删共享卷文件（/datara/files）→ 删 meta 行
#   ⑤ 输出清理统计
# 部署：脚本幂等；建议 crontab 每日 02:00（install.sh 不自动注册，仅打印提示）：
#   0 2 * * * cd /mnt/lei/datara && bash infra/bin/clean_logs.sh >> /var/log/datara_clean.log 2>&1
# ============================================================
set -u
cd "$(dirname "$0")/../.."   # 仓库根/包根（docker-compose.yml 定位见下）

# compose 文件定位（发布包 infra/docker-compose.yml 优先，仓库根兜底）+ 发布包配置加载
if [ -z "${COMPOSE_FILE:-}" ]; then
  if [ -f "$PWD/infra/docker-compose.yml" ]; then export COMPOSE_FILE="$PWD/infra/docker-compose.yml"
  elif [ -f "$PWD/docker-compose.yml" ]; then export COMPOSE_FILE="$PWD/docker-compose.yml"; fi
fi
if [ -f "infra/.env" ]; then set -a; . infra/.env; set +a; fi

RETAIN_DAYS="${LOG_RETAIN_DAYS:-30}"
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --retain-days) RETAIN_DAYS="$2"; shift 2 ;;
    --dry-run)     DRY_RUN=1; shift ;;
    *) echo "[clean] 未知参数: $1" >&2; exit 1 ;;
  esac
done
case "$RETAIN_DAYS" in
  ''|*[!0-9]*) echo "[clean] --retain-days 非法: $RETAIN_DAYS" >&2; exit 1 ;;
esac

log()  { echo "[clean] $*"; }
run_sql() {  # run_sql "SQL" [db] → stdout（utf8mb4：容器 client 缺省 latin1，防中文双重编码）
  docker compose exec -T mysql-meta mysql -uroot -p"$MYSQL_PWD" --default-character-set=utf8mb4 -N -B ${2:+"$2"} -e "$1" 2>/dev/null
}

# ---------- 读取 meta 库口令 ----------
MYSQL_PWD="$(grep -E '^MYSQL_ROOT_PASSWORD=' .env 2>/dev/null | cut -d= -f2- | tr -d '\r')"
MYSQL_PWD="${MYSQL_PWD:-datara_2026}"

# ---------- ① 过期日志目录（容器内 /datara/logs，按目录 mtime） ----------
mapfile -t EXPIRED < <(docker compose exec -T datara-worker bash -c \
  "find /datara/logs -mindepth 1 -maxdepth 1 -type d -mtime +${RETAIN_DAYS} -printf '%f\n' 2>/dev/null" \
  | tr -d '\r')
DIR_COUNT=${#EXPIRED[@]}

# ---------- ③a 过期 {instance_id}_ 临时文件统计 ----------
TMP_FILE_COUNT=0
if [ "$DIR_COUNT" -gt 0 ]; then
  for iid in "${EXPIRED[@]}"; do
    n=$(docker compose exec -T datara-worker bash -c \
      "find /datara/tmp -maxdepth 1 -name '${iid}_*' 2>/dev/null | wc -l" 2>/dev/null | tr -d '\r')
    TMP_FILE_COUNT=$((TMP_FILE_COUNT + ${n:-0}))
  done
fi

# ---------- ② 索引行统计 + ③b 临时表统计 ----------
TASKLOG_COUNT=0
ALERT_COUNT=0
TMPTABLE_COUNT=0
DROPS=""
CUTOFF="$(date -d "-${RETAIN_DAYS} days" '+%Y-%m-%d %H:%M:%S')"
for iid in "${EXPIRED[@]}"; do
  n=$(run_sql "SELECT COUNT(*) FROM t_task_log WHERE instance_id='${iid}'" datara_meta)
  TASKLOG_COUNT=$((TASKLOG_COUNT + ${n:-0}))
  TMPTABLE_COUNT=$((TMPTABLE_COUNT + $(run_sql \
    "SELECT COUNT(*) FROM information_schema.tables WHERE TABLE_NAME LIKE '${iid}\\_%'")))
done
ALERT_COUNT=$(run_sql "SELECT COUNT(*) FROM t_alert_record WHERE create_time < '${CUTOFF}'" datara_meta)

# ---------- ④ t_tmp_data 过期行（I4，retain-days 之外独立口径：expire_at 到期即清） ----------
TMPDATA_COUNT=0
SRC_DROPS=""
DW_DROPS=""
FILE_RM=""
mapfile -t TMPDATA_ROWS < <(run_sql \
  "SELECT IFNULL(s.host,''), IFNULL(s.db_name,''), t.kind, IFNULL(t.ref,'') FROM t_tmp_data t LEFT JOIN t_data_source s ON s.id = t.target_ds_id WHERE t.status='active' AND t.expire_at IS NOT NULL AND t.expire_at < NOW()" \
  datara_meta)
TMPDATA_COUNT=${#TMPDATA_ROWS[@]}
for row in "${TMPDATA_ROWS[@]}"; do
  IFS=$'\t' read -r host db kind ref <<< "$row"
  [ -z "$kind" ] && continue
  if [ "$kind" = "table" ]; then
    if [ -z "$host" ] || [ -z "$db" ] || [ -z "$ref" ]; then continue; fi
    case "$host" in
      datara-mysql-src) SRC_DROPS="${SRC_DROPS}DROP TABLE IF EXISTS \`$db\`.\`$ref\`;" ;;
      datara-mysql-dw)  DW_DROPS="${DW_DROPS}DROP TABLE IF EXISTS \`$db\`.\`$ref\`;" ;;
      *) log "警告: 未知目标库容器 ${host}，跳过临时表 ${db}.${ref}" ;;
    esac
  elif [ "$kind" = "file" ]; then
    case "$ref" in /datara/files/*) FILE_RM="${FILE_RM} ${ref}" ;; esac
  fi
done

# ---------- 输出计划 / 执行 ----------
log "保留天数=${RETAIN_DAYS}（截止 ${CUTOFF}）模式=$([ "$DRY_RUN" = 1 ] && echo dry-run || echo 实际清理)"
log "将清理：日志目录 ${DIR_COUNT} 个 / t_task_log 索引行 ${TASKLOG_COUNT} 行 / t_alert_record ${ALERT_COUNT} 行 / 临时文件 ${TMP_FILE_COUNT} 个 / 临时表 ${TMPTABLE_COUNT} 张 / t_tmp_data 过期 ${TMPDATA_COUNT} 行"
for iid in "${EXPIRED[@]}"; do
  log "  过期实例目录: ${iid}"
done

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run 结束（未删除任何内容）"
  exit 0
fi

if [ "$DIR_COUNT" -gt 0 ]; then
  # ① 日志目录 + ③a 临时文件（容器内）
  for iid in "${EXPIRED[@]}"; do
    docker compose exec -T datara-worker bash -c \
      "rm -rf '/datara/logs/${iid}'; find /datara/tmp -maxdepth 1 -name '${iid}_*' -exec rm -rf {} + 2>/dev/null" \
      >/dev/null 2>&1
  done
  # ② t_task_log 过期行
  SQL=""
  for iid in "${EXPIRED[@]}"; do
    SQL="${SQL}DELETE FROM t_task_log WHERE instance_id='${iid}';"
  done
  [ -n "$SQL" ] && run_sql "$SQL" datara_meta
fi
# ② t_alert_record 过期行
run_sql "DELETE FROM t_alert_record WHERE create_time < '${CUTOFF}'" datara_meta

# ③b 临时表 DROP（跨库枚举生成后执行）
if [ "$TMPTABLE_COUNT" -gt 0 ]; then
  for iid in "${EXPIRED[@]}"; do
    while IFS= read -r line; do
      [ -n "$line" ] && DROPS="${DROPS}${line}"
    done < <(run_sql "SELECT CONCAT('DROP TABLE IF EXISTS \`', TABLE_SCHEMA, '\`.\`', TABLE_NAME, '\`;') \
      FROM information_schema.tables WHERE TABLE_NAME LIKE '${iid}\\_%'")
  done
  [ -n "$DROPS" ] && run_sql "$DROPS"
fi

# ---------- ④ t_tmp_data 过期行执行（DROP 按目标库容器；文件删 worker 容器内共享卷） ----------
if [ "$TMPDATA_COUNT" -gt 0 ]; then
  [ -n "$SRC_DROPS" ] && docker compose exec -T datara-mysql-src mysql -uroot -p"$MYSQL_PWD" -e "$SRC_DROPS" >/dev/null 2>&1
  [ -n "$DW_DROPS" ] && docker compose exec -T datara-mysql-dw mysql -uroot -p"$MYSQL_PWD" -e "$DW_DROPS" >/dev/null 2>&1
  [ -n "$FILE_RM" ] && docker compose exec -T datara-worker rm -f $FILE_RM >/dev/null 2>&1
  run_sql "DELETE FROM t_tmp_data WHERE status='active' AND expire_at IS NOT NULL AND expire_at < NOW()" datara_meta
fi

log "清理完成：目录 ${DIR_COUNT} / task_log ${TASKLOG_COUNT} 行 / alert ${ALERT_COUNT} 行 / 临时文件 ${TMP_FILE_COUNT} / 临时表 ${TMPTABLE_COUNT} / t_tmp_data ${TMPDATA_COUNT} 行"
