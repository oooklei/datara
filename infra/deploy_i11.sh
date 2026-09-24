#!/usr/bin/env bash
# I11 增量部署（1.9 远端执行）：
# 1) 解包 datara-backend 源码树 → 宿主（含 common/models.py、api/wf_definition.py、logger/log_api.py）
# 2) web dist 覆盖（备份 dist.bak；nginx 挂载宿主目录立即生效）
# 3) 重建 datara-api + datara-logger（api 启动 init_db create_all 自动建 t_wf_category）
# 4) 健康等待 + 路由/建表自检
set -e
cd /mnt/lei/datara

echo "=== 1. 后端源码解包 ==="
if [ -f /root/datara_i11_backend.tgz ]; then
  tar -xzf /root/datara_i11_backend.tgz -C /mnt/lei/datara
  find datara-backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
  echo "backend files:"
  grep -c "class WfCategory" datara-backend/common/models.py
  grep -c "delete_instance_logs" datara-backend/logger/log_api.py
else
  echo "（backend tgz 不存在，跳过）"
fi

echo "=== 2. 前端 dist 覆盖（备份旧目录）==="
if [ -f /root/datara_i11_web.tgz ]; then
  rm -rf datara-web/dist.bak
  mv datara-web/dist datara-web/dist.bak
  mkdir -p datara-web/dist
  tar -xzf /root/datara_i11_web.tgz -C datara-web/dist
  rm -f /root/datara_i11_web.tgz
  ls datara-web/dist | head -5
else
  echo "（web tgz 不存在，跳过前端覆盖）"
fi

echo "=== 3. 重建 api/logger 容器 ==="
docker compose up -d --build datara-api datara-logger

echo "=== 4. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. 自检：t_wf_category 建表 ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -e "SHOW TABLES LIKE 't_wf_category';"

echo "=== 6. 路由探测（存在=401，不存在=404）==="
probe() { curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/v1$1"; }
p_cat=$(probe /workflow-definitions/categories)
p_tags=$(probe /workflow-definitions/123/tags)
p_logs_del=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "http://localhost:8000/api/v1/logs?instance_id=probe-i11")
echo "route_probe categories=$p_cat tags=$p_tags logs_del=$p_logs_del"

echo "=== 7. 容器状态 ==="
docker compose ps --format '{{.Name}} {{.Status}}'
echo "DEPLOY_DONE"