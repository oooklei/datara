#!/usr/bin/env bash
# I5 部署固化后回归：重跑 I5-血缘-TMP，断言 tmp_flag=1 在新镜像下成立
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"
TOKEN=$(curl -sf -X POST $API/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | jq -r .data.token)
curl -sf -X POST $API/workflow-definitions/wf_b30303e0/run -H "token: $TOKEN" -H 'Content-Type: application/json' -d '{}' > /dev/null
IID=""
for i in $(seq 1 30); do
  sleep 2
  IID=$($META "SELECT instance_id FROM t_workflow_instance WHERE wf_code=16 AND state IN ('success','failure','kill') ORDER BY id DESC LIMIT 1;" 2>/dev/null)
  if [ -n "$IID" ] && [ "$IID" != "20260919012247-16-83d5" ]; then break; fi
done
ST=$($META "SELECT state FROM t_workflow_instance WHERE instance_id='$IID';" 2>/dev/null)
echo "instance=$IID state=$ST"
echo "--- 血缘边（from=raw_txt_i5 tmp_flag=1 → datara_dw.dwd_i5_tmp_out）---"
$META "SELECT from_table, to_table, tmp_flag FROM t_lineage_edge WHERE instance_id='$IID';" 2>/dev/null
echo "REGRESS_DONE"
