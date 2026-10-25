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

export function listWorkflowRunStats(projectId: number, options: { workflowId?: number; limit?: number } = {}) {
  const query: Record<string, string> = { project_id: String(projectId), limit: String(options.limit ?? 50) }
  if (options.workflowId) query.workflow_id = String(options.workflowId)
  return request<WorkflowRunStatPage>('/rebuild/execution/run-stats', { query })
}

export function getWorkflowRunStat(projectId: number, statId: number) {
  return request<WorkflowRunStatDetail>(`/rebuild/execution/run-stats/${statId}`, {
    query: { project_id: String(projectId), detail_limit: '200' },
  })
}

