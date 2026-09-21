#!/usr/bin/env bash
# I5 复核一B：实例状态（meta 库直查）+ worker 血缘日志（容器内文件）
API=http://localhost:8000/api/v1
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"

echo "=== 1. I5 工作流 code（meta 直查）==="
CODE=$($META "SELECT code FROM t_wf_definition WHERE name='I5-血缘-实测' LIMIT 1;" 2>/dev/null)
echo "code=$CODE"

echo "=== 2. 最新实例（meta 直查）==="
$META "SELECT instance_id, state, run_mode, start_time, end_time FROM t_workflow_instance WHERE wf_code=$CODE ORDER BY id DESC LIMIT 2;" 2>/dev/null

echo "=== 3. 任务行状态 ==="
$META "SELECT node_id, name, state, attempt FROM t_task_instance WHERE instance_id=(SELECT instance_id FROM t_workflow_instance WHERE wf_code=$CODE ORDER BY id DESC LIMIT 1);" 2>/dev/null

echo "=== 4. worker 容器内血缘日志 ==="
docker exec datara-worker sh -c "grep -ah 'lineage' /datara/logs/*.log 2>/dev/null | tail -4"
docker logs datara-worker 2>&1 | grep -a 'lineage' | tail -4
echo "CHECK1B_DONE"
