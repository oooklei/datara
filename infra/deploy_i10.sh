#!/usr/bin/env bash
# I10 增量部署脚本（1.9 远端执行）：
# 1) 解包覆盖 datara-backend 源码树 + infra（含 04_meta_i10.sql 与本脚本）
# 2) 前端 dist 覆盖（旧 dist 备份 dist.bak 便于回滚）
# 3) 重建后端五模块（共享镜像：ide.py/vars_render.py/variables.py 变更涉 api/master/worker）
# 4) 健康等待 → 5) meta 库执行 04_meta_i10.sql（幂等）→ 6) DDL 自检
# 7) 容器内代码自检 → 8) nginx 载入 SSE location → 9) 容器状态
set -e
cd /mnt/lei/datara

echo "=== 1. 解包覆盖（后端源码 + infra）==="
tar -xzf /mnt/lei/datara/datara_i10.tgz -C /mnt/lei/datara
rm -f /mnt/lei/datara/datara_i10.tgz

echo "=== 2. 前端 dist 覆盖（备份旧目录）==="
if [ -f /mnt/lei/datara/datara_i10_web.tgz ]; then
  rm -rf datara-web/dist.bak
  mv datara-web/dist datara-web/dist.bak
  mkdir -p datara-web/dist
  tar -xzf /mnt/lei/datara/datara_i10_web.tgz -C datara-web/dist
  rm -f /mnt/lei/datara/datara_i10_web.tgz
  ls datara-web/dist | head -5
else
  echo "（web tgz 不存在，跳过前端覆盖——重跑场景）"
fi

echo "=== 3. 重建后端五模块（共享镜像保持一致）==="
docker compose up -d --build datara-api datara-master datara-worker datara-alert datara-logger

echo "=== 4. 等待健康（最多 120s）==="
for i in $(seq 1 24); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. meta 库执行 04_meta_i10.sql（幂等）==="
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta < /mnt/lei/datara/infra/mysql/init/04_meta_i10.sql

echo "=== 6. DDL 自检 ==="
docker exec -i datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -e "SHOW TABLES LIKE 't_ide_script'; SHOW COLUMNS FROM t_ide_history LIKE 'log_text'; SHOW COLUMNS FROM t_ide_history LIKE 'affected_total'; SHOW COLUMNS FROM t_global_param LIKE 'env';"

echo "=== 7. 容器内代码自检 ==="
docker exec datara-api grep -c "vars_render" /app/api/ide.py
docker exec datara-api grep -c "@router" /app/api/ide.py
docker exec datara-api python -c "import multipart; print('python-multipart', multipart.__version__)"
# 路由存在性用 HTTP 探测（新版 FastAPI app.routes 为 _IncludedRouter 聚合结构，不平铺 path）：
# 存在的路由未带 token → 401；不存在的路径 → 404
probe() { curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/v1$1"; }
p_hist=$(probe /ide/history)
p_params=$(probe /params/global)
p_meta=$(probe /datasources/1/meta)
echo "route_probe hist=$p_hist params=$p_params meta=$p_meta"
if [ "$p_hist" = "401" ] && [ "$p_params" = "401" ] && [ "$p_meta" = "401" ]; then
  echo "ROUTE_CHECK_OK"
else
  echo "ROUTE_CHECK_FAIL" && exit 1
fi

echo "=== 8. nginx 载入 SSE location ==="
docker exec datara-web nginx -s reload
sleep 1
# 未带 token → 代理到 api 返回 401（证明 SSE location 命中且反代通畅；nginx 自身 404 说明未命中）
curl -s -o /dev/null -w "sse_location_http=%{http_code}\n" "http://localhost:8090/api/v1/ide/stream/nonexistent" || true

echo "=== 9. 容器状态 ==="
docker compose ps
echo "DEPLOY_DONE"
