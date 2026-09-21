#!/usr/bin/env bash
# ============================================================
# Datara 一键部署（幂等，重跑无副作用）
# 行为序列（I1 §3.2 + I2 设计文档 §8.1）：
#   1) 前置检查：docker / docker compose / 端口 / 磁盘余量
#   2) docker compose up -d --build 拉起全栈（11 容器）
#   3) 健康等待 180s（失败打印不健康容器日志尾 30 行）
#   4) 执行 init SQL（幂等建表）：meta(01_meta + 02_meta_i3) + src(ec_retail) + dw(datara_dw)
#   5) 写入四初始账号（python -m common.init_accounts）
#   6) 打印访问地址与账号清单
#   7) --with-demo-data：灌测试数据基座（src 14+3 表 + dw 种子 + 自动对账，
#      1.9 NAS 预算 ≤10 分钟；缺省不灌数，仅提示）
# 用法：bash infra/bin/install.sh [--with-demo-data]
# 兼容两种布局：仓库根（docker-compose.yml 在根）与发布包（infra/docker-compose.yml）
# 同机多套隔离：COMPOSE_PROJECT_NAME / CTN_PREFIX / *_PORT 经 infra/.env 或环境变量注入
# ============================================================
set -u
cd "$(dirname "$0")/../.."   # 切到仓库根/包根

# compose 文件定位：发布包（infra/docker-compose.yml）优先，仓库根兜底；用户已设置则尊重
if [ -z "${COMPOSE_FILE:-}" ]; then
  if [ -f "$PWD/infra/docker-compose.yml" ]; then
    export COMPOSE_FILE="$PWD/infra/docker-compose.yml"
  elif [ -f "$PWD/docker-compose.yml" ]; then
    export COMPOSE_FILE="$PWD/docker-compose.yml"
  fi
fi
# 发布包配置（端口/前缀/凭据）；仓库布局无此文件自动跳过
if [ -f "infra/.env" ]; then set -a; . infra/.env; set +a; fi

CTN="${CTN_PREFIX:-datara}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-datara_2026}"
HEALTH_TIMEOUT=180
HEALTHY_CONTAINERS="${CTN}-mysql-meta ${CTN}-mysql-src ${CTN}-mysql-dw ${CTN}-redis ${CTN}-zookeeper ${CTN}-api ${CTN}-master ${CTN}-worker ${CTN}-alert ${CTN}-logger"
DEMO_DATA=0

log()  { echo "[install] $*"; }
fail_exit() { echo "[install][错误] $*" >&2; exit 1; }

# ---------- 0. 参数 ----------
for arg in "$@"; do
  if [ "$arg" = "--with-demo-data" ]; then
    DEMO_DATA=1
  fi
done

# ---------- 1. 前置检查 ----------
command -v docker >/dev/null 2>&1 || fail_exit "未检测到 docker，请先安装"
docker compose version >/dev/null 2>&1 || fail_exit "未检测到 docker compose 插件（需 v2）"

check_port_free() {
  local port="$1" service="$2"
  # 已被本栈容器占用 → 视为幂等重跑，放行
  local cid
  cid=$(docker compose ps -q "$service" 2>/dev/null)
  if [ -n "$cid" ]; then
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | grep -q ":${port} "; then
      fail_exit "端口 ${port} 已被其他进程占用（且非本栈 ${service} 容器）"
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -ltn 2>/dev/null | grep -q ":${port} "; then
      fail_exit "端口 ${port} 已被其他进程占用（且非本栈 ${service} 容器）"
    fi
  fi
  return 0
}

check_port_free "${WEB_PORT:-8090}" datara-web
check_port_free "${API_PORT:-8000}" datara-api
check_port_free "${ZK_PORT:-2181}" zookeeper
check_port_free "${REDIS_PORT:-6380}" redis
check_port_free "${META_PORT:-3307}" mysql-meta
check_port_free "${SRC_PORT:-3310}" datara-mysql-src
check_port_free "${DW_PORT:-3309}" datara-mysql-dw

# 磁盘余量 > 2G（KB 口径）
avail_kb=$(df -Pk . 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "$avail_kb" ] && [ "$avail_kb" -lt 2097152 ]; then
  fail_exit "磁盘余量不足 2G（当前 ${avail_kb}KB），请清理后重试"
fi
log "前置检查通过（docker / compose / 端口 ${WEB_PORT:-8090} ${API_PORT:-8000} ${ZK_PORT:-2181} ${REDIS_PORT:-6380} ${META_PORT:-3307} ${SRC_PORT:-3310} ${DW_PORT:-3309} / 磁盘）"

# ---------- 2. 拉起全栈 ----------
log "docker compose up -d --build（首次构建拉取镜像可能较慢）"
docker compose up -d --build || fail_exit "compose 拉起失败"

# 部署教训（09-18 实测）：后端容器重建后，已运行 nginx（datara-web）的 upstream DNS 失效 → 502。
# 强制重建 web 使其重新解析 upstream（全新部署无感；重跑/升级场景自愈）。
docker compose up -d --force-recreate datara-web >/dev/null 2>&1 || true

# ---------- 3. 健康等待 120s ----------
log "等待容器 healthy（最长 ${HEALTH_TIMEOUT}s）..."
elapsed=0
while [ "$elapsed" -lt "$HEALTH_TIMEOUT" ]; do
  all_healthy=1
  for c in $HEALTHY_CONTAINERS; do
    status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$c" 2>/dev/null || echo "missing")
    if [ "$status" != "healthy" ] && [ "$status" != "no-healthcheck" ]; then
      all_healthy=0
      break
    fi
  done
  [ "$all_healthy" = "1" ] && break
  sleep 5
  elapsed=$((elapsed + 5))
done

if [ "$all_healthy" != "1" ]; then
  echo "[install][错误] 超时仍有容器未健康，日志尾部如下：" >&2
  for c in $HEALTHY_CONTAINERS; do
    status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$c" 2>/dev/null || echo "missing")
    if [ "$status" != "healthy" ] && [ "$status" != "no-healthcheck" ]; then
      echo "===== $c（$status）=====" >&2
      docker logs --tail 30 "$c" 2>&1 || true
    fi
  done
  exit 1
fi
log "全部容器 healthy"

# ---------- 4. schema 初始化（幂等：CREATE TABLE IF NOT EXISTS） ----------
# --default-character-set=utf8mb4：容器内 mysql client 缺省 latin1，中文 seed 会双重编码（09-18 实测教训）
log "执行 01_meta.sql（幂等建表）"
docker compose exec -T mysql-meta mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 datara_meta < infra/mysql/init/01_meta.sql || fail_exit "meta 建表执行失败"
log "执行 02_meta_i3.sql（I3：t_wf_schedule + 加列 + 内置数据源/节点 seed，幂等）"
docker compose exec -T mysql-meta mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 datara_meta < infra/mysql/init/02_meta_i3.sql || fail_exit "I3 增量建表执行失败"
log "执行 src/dw init SQL（ec_retail 14+3 表 / datara_dw 派生表，幂等）"
docker compose exec -T datara-mysql-src mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 ec_retail < infra/mysql/src/init/01_schema.sql || fail_exit "src 建表执行失败"
docker compose exec -T datara-mysql-dw mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 datara_dw < infra/mysql/dw/init/01_schema.sql || fail_exit "dw 建表执行失败"

# ---------- 5. 初始账号写入（bcrypt 幂等） ----------
log "写入初始账号（python -m common.init_accounts）"
docker compose exec -T datara-api python -m common.init_accounts || fail_exit "初始账号写入失败"

# ---------- 5b. MySQL TCP 就绪探测（规避官方镜像"临时 server→正式 server"窗口） ----------
# 全新卷初始化时 entrypoint 先起 --skip-networking 临时 server（healthcheck 可能已绿，
# 但 TCP 3306 不可连）；init SQL 走 socket 仍成功，而 gen/应用走 TCP 会撞 refused。
# 探测从 datara-api 容器发起（mysql 镜像无 python）；TCP 通 = 正式 server 就绪。
wait_mysql_tcp() {
  local host="$1"
  for i in $(seq 1 30); do
    if docker compose exec -T datara-api python -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('$host',3306))==0 else 1)" 2>/dev/null; then
      log "${host} TCP 3306 就绪"
      return 0
    fi
    sleep 2
  done
  fail_exit "${host} TCP 3306 60s 内未就绪（可能仍处临时 server 窗口）；请重跑本脚本"
}
wait_mysql_tcp datara-mysql-src
wait_mysql_tcp datara-mysql-dw

# ---------- 5c. 日志清理脚本提示（F50：不自动注册 crontab，仅提示） ----------
log "提示：日志清理脚本未自动注册定时，建议 crontab 每日 02:00 执行：" \
    "0 2 * * * cd $(pwd) && bash infra/bin/clean_logs.sh --retain-days ${LOG_RETAIN_DAYS:-30}"

# ---------- 6. 演示数据（--with-demo-data 显式开启；缺省不灌数） ----------
if [ "$DEMO_DATA" = "1" ]; then
  log "灌测试数据基座（src 14+3 表 + dw 种子 + 自动对账；1.9 NAS 预算 ≤10 分钟）..."
  docker compose exec -T datara-api python -m tools.datagen.run gen || fail_exit "演示数据灌数失败"
else
  log "未灌演示数据（需要时追加 --with-demo-data；或重跑 install.sh --with-demo-data）"
fi

# ---------- 7. 输出访问地址与账号 ----------
server_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "${server_ip:-}" ] && server_ip="127.0.0.1"
cat <<EOF

==================== Datara 部署完成 ====================
访问地址：http://${server_ip}:${WEB_PORT:-8090}
初始账号（密码可用 DATARA_*_PWD 环境变量覆盖）：
  admin    / Admin@123     （管理员）
  dev      / Dev@123       （开发者）
  analyst  / Analyst@123   （分析师）
  viewer   / Viewer@123    （观察者）
常用命令：
  docker compose ps              # 容器状态
  docker compose logs -f datara-api
  bash infra/bin/reset.sh --refill          # 数据重置 + 重灌演示数据
  bash infra/bin/import.sh --type csv-dir --path <目录>   # 导入客户数据
=========================================================
EOF
