#!/usr/bin/env bash
# I5 门#8 排查：失败实例的任务日志全文 + 血缘落库核查
# 日志路径规则（worker/executor.py _open_live_log）：{log_dir}/{instance_id}/{task_id}.log
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"

echo "=== 1. I5-血缘-失败 工作流的全部实例（两轮）==="
$META "SELECT wi.instance_id, wi.state, wi.wf_code FROM t_workflow_instance wi JOIN t_wf_definition wd ON wd.code=wi.wf_code WHERE wd.name='I5-血缘-失败' ORDER BY wi.id;" 2>/dev/null

IID=$($META "SELECT wi.instance_id FROM t_workflow_instance wi JOIN t_wf_definition wd ON wd.code=wi.wf_code WHERE wd.name='I5-血缘-失败' AND wi.state='failure' ORDER BY wi.id DESC LIMIT 1;" 2>/dev/null)
echo "排查对象 instance_id=$IID"

echo "=== 2. 任务行（含日志路径）==="
$META "SELECT id, node_id, node_name, state, attempt, log_path FROM t_task_instance WHERE instance_id='$IID';" 2>/dev/null

LP=$($META "SELECT log_path FROM t_task_instance WHERE instance_id='$IID' AND node_id='n_sql_1';" 2>/dev/null)
echo "=== 3. SQL 节点任务日志全文（log_path=$LP）==="
docker exec datara-worker sh -c "cat '$LP'" 2>&1

echo "=== 4. 该实例血缘落库 ==="
$META "SELECT COUNT(*) FROM t_lineage_edge WHERE instance_id='$IID';" 2>/dev/null
$META "SELECT node_id, stmt_no, from_table, to_table, tmp_flag FROM t_lineage_edge WHERE instance_id='$IID' ORDER BY id;" 2>/dev/null

echo "=== 5. worker 日志目录结构核对 ==="
docker exec datara-worker sh -c "ls -d /datara/logs/$IID 2>/dev/null && ls /datara/logs/$IID/" 2>&1

echo "CHECK8_DONE"
