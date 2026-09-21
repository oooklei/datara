#!/bin/bash
# dep2_g8 替代口径：四角色登录 API 实测（data.user.role = 前端 canEdit 数据源）
for u in admin:Admin@123 dev:Dev@123 analyst:Analyst@123 viewer:Viewer@123; do
  USER=${u%%:*}; PWD=${u##*:}
  R=$(curl -s -X POST http://localhost:8000/api/v1/login -H 'Content-Type: application/json' \
      -d "{\"user_name\":\"$USER\",\"user_pwd\":\"$PWD\"}")
  echo "$USER → $(echo "$R" | python3 -c "
import json,sys
d=json.load(sys.stdin); dd=(d.get('data') or {})
u=dd.get('user') or {}
print('code=',d.get('code'),'role=',u.get('role'),'perms=',u.get('perms'))" 2>&1)"
done
echo "=== t_user 四账号 ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "SELECT user_name,user_role,state FROM datara_meta.t_user ORDER BY id;" 2>/dev/null
