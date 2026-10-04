#!/usr/bin/env bash
# I12 增量部署脚本（1.9 远端执行）：组件设计器 fields 模式（组件初始化落地）
# 1) 前端 dist 覆盖（备份 dist.bak，nginx 挂载宿主目录立即生效）
# 2) 后端源码树同步（component_design.py 发布闸门双源扩展：spec.fields / 八段 form.params）
# 3) 重建 datara-api / datara-worker（同一后端镜像 build: ./datara-backend）
# 4) 健康等待 + 自检（双源闸门代码进容器、容器状态）
set -e
cd /lei/datara

echo "=== 1. 前端 dist 覆盖（备份旧目录）==="
if [ -f /root/datara_dep_web.tgz ]; then
  rm -rf datara-web/dist.bak
  mv datara-web/dist datara-web/dist.bak
  mkdir -p datara-web/dist
  tar -xzf /root/datara_dep_web.tgz -C datara-web/dist
  ls datara-web/dist | head -5
else
  echo "（web tgz 不存在，跳过前端覆盖——重跑场景）"
fi

echo "=== 2. 后端源码同步 ==="
if [ -f /root/datara_dep_backend.tgz ]; then
  tar -xzf /root/datara_dep_backend.tgz -C /lei/datara
  find datara-backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi
grep -c "_gate_fields_rows" /lei/datara/datara-backend/api/component_design.py

echo "=== 3. 重建 api/worker 容器（拿到新镜像层）==="
docker compose up -d --build datara-api datara-worker

echo "=== 4. 等待健康（最多 90s）==="
for i in $(seq 1 18); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. 自检：双源闸门代码进容器镜像（容器 WORKDIR=/app）==="
docker exec datara-api grep -c "_gate_fields_rows" /app/api/component_design.py

echo "=== 6. 容器状态 ==="
docker compose ps --format '{{.Name}} {{.Status}}'
echo "DEPLOY_DONE"
