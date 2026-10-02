#!/usr/bin/env bash
# I12 T14 前置取证：数据源清单/运行节点/src·dw 库表现状/i12files 目录
set -u
echo "===== A. API 登录 ====="
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/login -H 'Content-Type: application/json' \
  -d '{"user_name":"admin","user_pwd":"Admin@123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")
echo "token_len=${#TOKEN}"

echo "===== B. 数据源清单 ====="
curl -s "http://localhost:8000/api/v1/datasources" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = d.get('data') or []
if isinstance(rows, dict): rows = rows.get('list') or rows.get('items') or []
for r in rows:
    print(r.get('id'), '|', r.get('name'), '|', r.get('type'), '|', r.get('database') or r.get('db') or '', '|', r.get('status') or '')
"

echo "===== C. 运行节点清单 ====="
curl -s "http://localhost:8000/api/v1/runtime-nodes" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = d.get('data') or []
if isinstance(rows, dict): rows = rows.get('list') or rows.get('items') or []
for r in rows:
    print(r.get('id'), '|', r.get('name'), '|', r.get('host'), '|', r.get('status') or '')
"

echo "===== D. src 库 schema 清单 ====="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 -N -e "SHOW DATABASES;" 2>/dev/null

echo "===== E. ec_retail 同步域相关表 ====="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 -N -e \
  "SELECT table_schema, table_name, table_rows FROM information_schema.tables WHERE table_schema LIKE 'ec_retail%' AND table_name IN ('ods_order','ods_payment','ods_cart','ods_favorite','ods_address','dim_user_address','ods_refund','ods_coupon') ORDER BY table_schema, table_name;" 2>/dev/null

echo "===== F. dw 库清单 ====="
docker exec datara-mysql-dw mysql -uroot -pdatara_2026 -N -e "SHOW DATABASES;" 2>/dev/null

echo "===== G. datara_dw 现有表（含 i12_ 残留） ====="
docker exec datara-mysql-dw mysql -uroot -pdatara_2026 -N -e \
  "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY table_schema, table_name;" 2>/dev/null

echo "===== H. i12files 目录 ====="
ls -la /mnt/lei/datara/i12files/ 2>&1 || echo "(i12files 不存在)"

echo "===== I. /datara/files 共享卷（容器内） ====="
docker exec datara-worker sh -c "ls -la /datara/files/ 2>&1 | head -20" || true
