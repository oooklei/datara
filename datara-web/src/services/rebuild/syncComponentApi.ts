/**
 * R4-SYNC client for the accepted rebuild/sync API (§6.4).
 * GREEN 已接线（FE-01 修订 2026-10-19）。
 * FE-09 前置改写（2026-10-19）：真实卡点由「R3 收口+SYNC 契约解禁」更正为
 * 「工作流版本域数据可用性」（SyncPlanInput 需 workflow_id/workflow_version，大盘 #2）；
 * 本契约 5 方法已接线（getCapabilities/explore/autoMap/savePlan/listPlans）。
 * FE-09 正式页落差登记：/sync/detail 正式页仍走旧 syncApi 只读实例明细，
 * 13 字段表单+映射 8 字段承接待工作流版本域可用后落地。
 * 横幅状态词表见 services/rebuild/bannerStatus.ts。
 */

import { getToken } from '../http'

const BASE = '/api/v1/rebuild/sync'
const TIMEOUT_MS = 15000

export interface SyncObjectRef {
  datasource_id: number
  schema: string
  object: string
}

export interface SyncColumn {
  column_name: string
  data_type: string
  column_type?: string
  is_nullable?: boolean
  column_key?: string
  column_comment?: string
}

export interface SyncMapping {
  source_column: string
  target_column: string
  source_type: string
  target_type: string
  transform_expression: string
  nullable: boolean
  default_value: unknown
  mapping_status: 'AUTO' | 'ADJUSTED' | 'UNMATCHED'
}

export interface SyncPlanInput {
  project_id: number
  workflow_id: number
  workflow_version: number
  task_id: string
  source: SyncObjectRef
  target: SyncObjectRef
  mappings: SyncMapping[]
  transform_config: {
    transform_expression?: Record<string, string>
    filter_condition?: string
  }
  target_properties: {
    partition_incremental?: { partition_field?: string; incremental_field?: string }
    primary_key_conflict?: { primary_key?: string[]; conflict_strategy?: 'insert' | 'ignore' | 'update' | 'upsert' }
    batch_concurrency?: { batch_size?: number; concurrency?: number }
  }
}

export interface SyncPlan extends SyncPlanInput {}

export interface SyncCapabilities {
  form_fields: string[]
  mapping_fields: string[]
  mapping_status: string[]
}

export interface SyncExploreResult {
  items: SyncColumn[]
  truncated: boolean
  limit: number
}

export interface SyncContract {
  getCapabilities(): Promise<SyncCapabilities>
  explore(projectId: number, ref: SyncObjectRef, limit?: number): Promise<SyncExploreResult>
  autoMap(projectId: number, source: SyncObjectRef, target: SyncObjectRef): Promise<SyncMapping[]>
  savePlan(plan: SyncPlanInput): Promise<{ saved: true; workflow_version: number; task_id: string }>
  listPlans(projectId: number, workflowId: number, workflowVersion: number): Promise<SyncPlan[]>
}

export class SyncApiError extends Error {
  readonly status: number
  readonly code: number | string
  readonly diagnostics: Array<Record<string, unknown>>

  constructor(status: number, code: number | string, message: string, diagnostics: Array<Record<string, unknown>> = []) {
    super(message)
    this.name = 'SyncApiError'
    this.status = status
    this.code = code
    this.diagnostics = diagnostics
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers.token = token
    const response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) },
      signal: controller.signal,
    })
    const envelope = await response.json().catch(() => null) as {
      code?: number | string
      msg?: string
      data?: T | null
    } | null
    if (!envelope) throw new SyncApiError(response.status, response.status, `无法解析 SYNC 响应（HTTP ${response.status}）`)
    const success = response.ok && (envelope.code === 0 || envelope.code === '0')
    if (!success) {
      const data = envelope.data as { diagnostics?: Array<Record<string, unknown>> } | null | undefined
      throw new SyncApiError(response.status, envelope.code ?? response.status, envelope.msg ?? 'SYNC 请求失败', data?.diagnostics ?? [])
    }
    return envelope.data as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new SyncApiError(0, 'TIMEOUT', `SYNC 请求超时（${TIMEOUT_MS / 1000}s）`)
    }
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

export function createSyncComponentContract(): SyncContract {
  return {
    getCapabilities: () => request<SyncCapabilities>('/capabilities'),
    explore: (projectId, ref, limit = 200) => {
      const query = new URLSearchParams({
        project_id: String(projectId),
        datasource_id: String(ref.datasource_id),
        schema: ref.schema,
        object_name: ref.object,
        limit: String(limit),
      })
      return request<SyncExploreResult>(`/explore?${query}`)
    },
    autoMap: async (projectId, source, target) => {
      const result = await request<{ mappings: SyncMapping[] }>('/mappings/auto', {
        method: 'POST', body: JSON.stringify({ project_id: projectId, source, target }),
      })
      return result.mappings
    },
    savePlan: (plan) => request('/plans', { method: 'POST', body: JSON.stringify(plan) }),
    listPlans: async (projectId, workflowId, workflowVersion) => {
      const query = new URLSearchParams({
        project_id: String(projectId), workflow_id: String(workflowId), workflow_version: String(workflowVersion),
      })
      const result = await request<{ items: SyncPlan[] }>(`/plans?${query}`)
      return result.items
    },
  }
}

/** Local suggestion helper retained for offline editing and unit tests. */
export function suggestInitialMapping(source: SyncColumn[], target: SyncColumn[]): SyncMapping[] {
  const byName = new Map(source.map((column) => [column.column_name.toLocaleLowerCase(), column]))
  return target.map((targetColumn) => {
    const sourceColumn = byName.get(targetColumn.column_name.toLocaleLowerCase())
    return {
      source_column: sourceColumn?.column_name ?? '',
      target_column: targetColumn.column_name,
      source_type: sourceColumn?.data_type ?? '',
      target_type: targetColumn.data_type,
      transform_expression: '',
      nullable: sourceColumn?.is_nullable ?? true,
      default_value: null,
      mapping_status: sourceColumn ? 'AUTO' : 'UNMATCHED',
    }
  })
}
