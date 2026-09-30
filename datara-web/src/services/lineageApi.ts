/**
 * lineageApi（I5 F25/F27）：血缘查询真实后端实现。
 * 端点对齐 datara-backend/api/lineage.py（§6 契约唯一权威）：
 * - GET /lineage/tables：表级边（TableLineage 四键 {from,to,task,wf} + 追溯附加字段；
 *   多实例按 wf/node/stmt/from/to 去重保最新，表名剥 db 前缀对齐前端契约）
 * - GET /lineage/fields：字段级映射（FieldLineage 契约直出；常量来源项 from="" 由视图层过滤）
 * - GET /lineage/graph：血缘图聚合（Task 4/1.9；design/runtime 双源聚边 + 中心表 BFS 扩散，
 *   表级数据面主通道，Task 5 前端接入）
 * - GET /lineage/stats：统计浮窗（去重呈现口径）
 * - GET /lineage/trace：实例/节点维度追溯（实例快照原貌，含字段明细）
 */
import { http } from './http'
import { isMock } from './apiMode'
import { mockLineageGraph } from './mock/api'

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

/* ---------------- GET /lineage/graph 血缘图聚合（Task 5 前端接入） ---------------- */

/** 血缘来源类型（t_lineage_edge.src_type：design=设计态推导 / runtime=运行实例采集） */
export type LineageSrcType = 'design' | 'runtime'

/** graph 节点（fq 全名 = db.table 原值；file:{path} 整体保留） */
export interface LineageGraphNode {
  fq: string
  ds: string
  table: string
  tmpFlag: number
  sources: LineageSrcType[]
  /** 涉及的工作流编码（去重升序） */
  wfs: number[]
}

/** graph 边明细引用（同 (wf,node,stmt) 多实例保留最新） */
export interface LineageGraphRef {
  wfCode: number
  nodeId: string
  stmtNo: number
  /** 仅 field 级携带：转换表达式 */
  transform?: string
}

/** graph 聚边（同 (from,to) 一条；sources = 全量行 src_type 去重） */
export interface LineageGraphEdge {
  from: string
  to: string
  level: 'table' | 'field'
  sources: LineageSrcType[]
  refs: LineageGraphRef[]
}

/** opaque 节点（解析期不产边的组件，从定义图重算） */
export interface LineageGraphOpaque {
  wfCode: number
  nodeId: string
  type: string
  reason?: string
}

/** GET /lineage/graph 返回 data 形状 */
export interface LineageGraphResult {
  nodes: LineageGraphNode[]
  edges: LineageGraphEdge[]
  opaques: LineageGraphOpaque[]
  truncated: boolean
}

export interface LineageGraphParams {
  level: 'table' | 'field'
  source?: 'all' | 'design' | 'runtime'
  wfCode?: number
  table?: string
  direction?: 'upstream' | 'downstream' | 'both'
  /** 0=全链（后端默认） */
  depth?: number
  limit?: number
}

/** 血缘图聚合（mock 模式返回双源样例，见 mock/api.ts mockLineageGraph） */
export async function fetchLineageGraph(params: LineageGraphParams): Promise<LineageGraphResult> {
  if (isMock) return mockLineageGraph(params)
  const q = new URLSearchParams()
  q.set('level', params.level)
  if (params.source) q.set('source', params.source)
  if (params.wfCode !== undefined) q.set('wfCode', String(params.wfCode))
  if (params.table) q.set('table', params.table)
  if (params.direction) q.set('direction', params.direction)
  if (params.depth !== undefined) q.set('depth', String(params.depth))
  if (params.limit !== undefined) q.set('limit', String(params.limit))
  return http.get<LineageGraphResult>(`/lineage/graph?${q.toString()}`)
}
