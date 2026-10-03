#!/usr/bin/env bash
# 页面设计器 P1 部署后探针（在 192.168.1.9 执行）
set -e
BASE=http://localhost:8000/api/v1

echo "=== 1. 登录 ==="
LOGIN=$(curl -s -X POST "$BASE/login" -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}')
echo "$LOGIN" | head -c 200; echo
TOKEN=$(echo "$LOGIN" | grep -o '"token":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "token_len=${#TOKEN}"
if [ -z "$TOKEN" ]; then echo "LOGIN_FAIL"; exit 1; fi

echo "=== 2. GET /page-designer/resources ==="
CODE=$(curl -s -o /tmp/pd_res.json -w '%{http_code}' -H "token: $TOKEN" "$BASE/page-designer/resources")
echo "http=$CODE bytes=$(wc -c < /tmp/pd_res.json)"
head -c 400 /tmp/pd_res.json; echo

echo "=== 3. 组件表 execution_model 分布 ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -N -e "SHOW TABLES LIKE '%component%';" 2>/dev/null
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -N -e "SELECT execution_model, COUNT(*) FROM t_component GROUP BY execution_model;" 2>/dev/null || \
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta -N -e "SELECT execution_model, COUNT(*) FROM t_component_def GROUP BY execution_model;" 2>/dev/null || echo "（组件表名需人工确认）"

echo "=== 4. 未鉴权探针（应 401/403）==="
echo "no_token_resources=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/page-designer/resources")"

echo "PROBE_DONE"
