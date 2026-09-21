/**
 * lineageApi（I5 F25/F27）：血缘查询真实后端实现。
 * 端点对齐 datara-backend/api/lineage.py（§6 契约唯一权威）：
 * - GET /lineage/tables：表级边（TableLineage 四键 {from,to,task,wf} + 追溯附加字段；
 *   多实例按 wf/node/stmt/from/to 去重保最新，表名剥 db 前缀对齐前端契约）
 * - GET /lineage/fields：字段级映射（FieldLineage 契约直出；常量来源项 from="" 由视图层过滤）
 * - GET /lineage/stats：统计浮窗（去重呈现口径）
 * - GET /lineage/trace：实例/节点维度追溯（实例快照原貌，含字段明细）
 */
import { http } from './http'

/** 后端边行（/lineage/tables 与 /lineage/trace 共用形状） */
export interface LineageEdgeRow {
  from: string
  to: string
  task: string
  wf: string
  instanceId: string
  nodeId: string
  dsName: string
  tmpFlag: number
  stmt: string
  stmtNo: number
  wfCode: number
  createTime: string | null
}

export interface LineageStats {
  edgeCount: number
  fieldCount: number
  tableCount: number
  wfCount: number
  lastTime: string | null
}

export interface TraceFieldRow {
  toField: string
  from: string
  fromTable: string
  fromField: string
  transform: string
}

export interface TraceEdgeRow extends LineageEdgeRow {
  fields: TraceFieldRow[]
}

export async function listTableLineage(params?: {
  keyword?: string
  wf_code?: number
  instance_id?: string
  table?: string
}): Promise<LineageEdgeRow[]> {
  const q = new URLSearchParams()
  if (params?.keyword) q.set('keyword', params.keyword)
  if (params?.wf_code !== undefined) q.set('wf_code', String(params.wf_code))
  if (params?.instance_id) q.set('instance_id', params.instance_id)
  if (params?.table) q.set('table', params.table)
  const qs = q.toString()
  return http.get<LineageEdgeRow[]>(`/lineage/tables${qs ? `?${qs}` : ''}`)
}

export async function listFieldLineage(params?: {
  table?: string
  wf_code?: number
}): Promise<Record<string, { from: string; transform: string }[]>> {
  const q = new URLSearchParams()
  if (params?.table) q.set('table', params.table)
  if (params?.wf_code !== undefined) q.set('wf_code', String(params.wf_code))
  const qs = q.toString()
  return http.get<Record<string, { from: string; transform: string }[]>>(
    `/lineage/fields${qs ? `?${qs}` : ''}`,
  )
}

export async function lineageStats(): Promise<LineageStats> {
  return http.get<LineageStats>('/lineage/stats')
}

export async function lineageTrace(
  instanceId: string,
  nodeId?: string,
): Promise<TraceEdgeRow[]> {
  const q = new URLSearchParams()
  q.set('instance_id', instanceId)
  if (nodeId) q.set('node_id', nodeId)
  return http.get<TraceEdgeRow[]>(`/lineage/trace?${q.toString()}`)
}
