#!/usr/bin/env bash
# I17 增量部署脚本（1.9 远端执行）：统一工作流内核批次 + 流画布混编口径 + 基线化八段 spec 适配
# 1) 前端 dist 原地内容覆盖（I15 教训：不删目录不换 inode，bind mount 保持有效）
# 2) 后端源码树同步（streamjob.py 混编白名单 + component_spec.py 双格式适配）
# 3) 重建 datara-api / datara-worker（同一后端镜像 build: ./datara-backend）
# 4) 健康等待 + 自检（新代码进容器断言、spec 视觉抽样、探针四连）
set -e
cd /lei/datara

echo "=== 1. 前端 dist 原地覆盖（保 inode）==="
if [ -f /root/datara_dep_web.tgz ]; then
  tar -xzf /root/datara_dep_web.tgz --strip-components=1 -C datara-web/dist
  ls datara-web/dist | head -5
else
  echo "（web tgz 不存在，跳过前端覆盖——重跑场景）"
fi

echo "=== 2. 后端源码同步 ==="
if [ -f /root/datara_dep_backend.tgz ]; then
  tar -xzf /root/datara_dep_backend.tgz -C /lei/datara
  find datara-backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi
echo "streamjob NON_PIPELINE_TYPES: $(grep -c 'NON_PIPELINE_TYPES' datara-backend/api/streamjob.py)"
echo "component_spec octagon adapter: $(grep -c 'render.get' datara-backend/api/component_spec.py)"

echo "=== 3. 重建 api/worker 容器（拿到新镜像层）==="
docker compose up -d --build datara-api datara-worker

echo "=== 4. 等待健康（最多 120s）==="
for i in $(seq 1 24); do
  sleep 5
  api_ok=$(curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo OK || echo NG)
  web_ok=$(curl -sf http://localhost:8090/ >/dev/null 2>&1 && echo OK || echo NG)
  echo "round $i: api=$api_ok web=$web_ok"
  if [ "$api_ok" = "OK" ] && [ "$web_ok" = "OK" ]; then break; fi
done

echo "=== 5. 自检：新代码进容器 + spec 视觉抽样 + 探针 ==="
echo "in-container NON_PIPELINE_TYPES: $(docker exec datara-api grep -c 'NON_PIPELINE_TYPES' /app/api/streamjob.py)"
docker exec datara-api python - <<'PY'
import json, urllib.request
body = json.load(urllib.request.urlopen("http://localhost:8000/api/v1/components/spec"))
items = body["items"]
empty = [i["type"] for i in items if not (i.get("visual") or {}).get("icon")]
n_fields = sum(1 for i in items if i.get("inputs"))
print("spec_items=%d empty_icon=%d with_fields=%d" % (len(items), len(empty), n_fields))
print("empty_icon_sample=", empty[:6])
PY
echo "echo_probe=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/echo)"
echo "tpl_unauth=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/workflow-templates)"
echo "web_probe=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8090/)"

echo "=== 6. 容器状态 ==="
docker compose ps --format '{{.Name}} {{.Status}}'
echo "DEPLOY_DONE"
