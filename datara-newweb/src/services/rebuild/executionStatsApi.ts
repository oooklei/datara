import { request } from '../http'

export interface WorkflowRunStat {
  id: number
  workflow_id: number
  workflow_instance_id: number
  instance_type: string
  status: string
  source_count?: number | null
  target_count?: number | null
  success_count: number
  failure_count: number
  skipped_count: number
  total_count: number
  started_at: string
  finished_at?: string | null
  dag_name?: string | null
}

export interface WorkflowRunReconcileDetail {
  id: number
  source_object: string
  target_object: string
  source_count?: number | null
  target_count?: number | null
  success_count: number
  failure_count: number
  skipped_count: number
  difference_count?: number | null
  started_at?: string | null
  finished_at?: string | null
}

export interface WorkflowRunStatDetail extends WorkflowRunStat {
  details: WorkflowRunReconcileDetail[]
  detail_total: number
}

export interface WorkflowRunStatPage { total: number; items: WorkflowRunStat[] }

export type WorkflowInstanceType = 'TRIAL' | 'FORMAL' | 'STREAM'

export interface WorkflowRunStatQuery {
  workflowId?: number
  instanceType?: WorkflowInstanceType
  status?: string
  startedFrom?: string
  startedTo?: string
  offset?: number
  limit?: number
}

export function listWorkflowRunStats(projectId: number, options: WorkflowRunStatQuery = {}) {
  const query: Record<string, string> = { project_id: String(projectId), limit: String(options.limit ?? 50) }
  if (options.workflowId) query.workflow_id = String(options.workflowId)
  if (options.instanceType) query.instance_type = options.instanceType
  if (options.status) query.status = options.status
  if (options.startedFrom) query.started_from = options.startedFrom
  if (options.startedTo) query.started_to = options.startedTo
  if (options.offset !== undefined) query.offset = String(options.offset)
  return request<WorkflowRunStatPage>('/rebuild/execution/run-stats', { query })
}

export function getWorkflowRunStat(projectId: number, statId: number) {
  return request<WorkflowRunStatDetail>(`/rebuild/execution/run-stats/${statId}`, {
    query: { project_id: String(projectId), detail_limit: '200' },
  })
}

/* ---------- T6 运行监控日志通道（审计弹窗 #9 LogPanel 数据源） ----------
 * 后端契约（rebuild/execution/api.py 实测）：
 *  - GET  /runs/{instance_id}            → 实例详情 + logs（后端 LIMIT 200 条）；
 *  - POST /runs/{instance_id}/cancel     → 终态 CANCELLED（带项目归属校验）；
 *  - POST /workflow-instances            → 重跑入口（TRIAL 自动草稿快照 / STREAM version=0；
 *                                          FORMAL 必须给 published version_id，run-stats 行无此
 *                                          字段不可还原 → FORMAL 重跑不提供此入口）。
 * 通道形态：日志走 3s 轮询（RUNNING/PENDING 持续、终态单拉即停）；SSE 待后端端点立项后切换。
 */

/** 运行实例日志行 */
export interface WorkflowRunLogLine {
  task_instance_id: number
  attempt_no: number
  level: string
  message: string
}

/** 运行实例详情 + 日志 */
export interface WorkflowRunInstanceDetail {
  instance_id: number
  workflow_id: number
  instance_type: string
  status: string
  trigger_type?: string | null
  logs: WorkflowRunLogLine[]
}

/** 运行实例详情与日志（RUNNING 轮询 3s / 终态单拉） */
export function getWorkflowRunLogs(projectId: number, instanceId: number) {
  return request<WorkflowRunInstanceDetail>(`/rebuild/execution/runs/${instanceId}`, {
    query: { project_id: String(projectId) },
  })
}

/** 停止运行实例（transition → CANCELLED 并 finalize 统计） */
export function cancelWorkflowRun(projectId: number, instanceId: number) {
  return request<{ instance_id: number; status: string }>(`/rebuild/execution/runs/${instanceId}/cancel`, {
    method: 'POST',
    json: { project_id: projectId },
  })
}

/** 重跑（TRIAL 自动以当前草稿快照发起 / STREAM version=0；FORMAL 不提供此入口） */
export function rerunWorkflowInstance(projectId: number, workflowId: number, instanceType: 'TRIAL' | 'STREAM') {
  return request<{ instance_id: number; status: string }>('/rebuild/execution/workflow-instances', {
    method: 'POST',
    json: { project_id: projectId, workflow_id: workflowId, instance_type: instanceType, trigger_type: 'RERUN' },
  })
}

