import { request } from '../http'

export interface WorkflowRunStat {
  id: number
  workflow_id: number
  workflow_instance_id: number
  instance_type: string
  status: string
  success_count: number
  failure_count: number
  skipped_count: number
  total_count: number
  started_at: string
  finished_at?: string | null
  dag_name?: string | null
}

export interface WorkflowRunStatPage { total: number; items: WorkflowRunStat[] }

export function listWorkflowRunStats(projectId: number, options: { workflowId?: number; limit?: number } = {}) {
  const query: Record<string, string> = { project_id: String(projectId), limit: String(options.limit ?? 50) }
  if (options.workflowId) query.workflow_id = String(options.workflowId)
  return request<WorkflowRunStatPage>('/api/v1/rebuild/execution/run-stats', { query })
}

