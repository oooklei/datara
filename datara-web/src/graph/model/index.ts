/**
 * 图模型层：GraphDocument / GNode / GEdge 统一数据结构 + 校验工具
 * 所有视角（DAG/拓扑/ER/血缘…）共享同一模型，差异由 ViewProfile 定义。
 */

export interface GNodeData {
  name: string
  [k: string]: unknown
}

export interface GNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: GNodeData
  /** 泳道归属（topo 等视角使用），值对应 profile.lanes[].key */
  lane?: string
}

/**
 * 边语义闭合联合（各 profile.edgeKinds 全集 + 后续 wave 追加类型）。
 * 来源映射：
 * - dag/topo/etl/stream: flow / branch（条件分支）/ branch_true / branch_false / dep / lag
 * - lineage: dep / dep_unlinked / field_dep（M09 字段级血缘，对齐 data.js fieldLineage）
 * - relation: produce / refer / call / tag
 * - er: rel_1n / rel_n1 / rel_11 / rel_nm
 * - quality: bind_pass / bind_fail / bind_disabled
 */
export type GEdgeKind =
  | 'flow'
  | 'branch'
  | 'branch_true'
  | 'branch_false'
  | 'dep'
  | 'lag'
  | 'dep_unlinked'
  | 'field_dep'
  | 'produce'
  | 'refer'
  | 'call'
  | 'tag'
  | 'rel_1n'
  | 'rel_n1'
  | 'rel_11'
  | 'rel_nm'
  | 'bind_pass'
  | 'bind_fail'
  | 'bind_disabled'

export interface GEdge {
  id: string
  source: string
  target: string
  /** 边语义，对应 profile.edgeKinds（闭合联合，未知 kind 编译期拒绝） */
  kind?: GEdgeKind
  label?: string
  /** 源端点（条件分支等动态端口 = BranchDef.id；普通节点缺省） */
  sourceHandle?: string
  /** 目标端点（预留） */
  targetHandle?: string
  /** 部分依赖配置（DAG 工作台·依赖页）：依赖上游产出的部分结果数据；缺省 = 全量依赖 */
  partial?: EdgePartialDep
}

/** 部分依赖三级粒度：结果表 → 字段子集 → 行过滤表达式，附同周期/同批次依赖条件（可选内核扩展，向后兼容） */
export interface EdgePartialDep {
  /** 依赖的上游结果表 */
  table: string
  /** 字段子集（空 = 全字段） */
  fields: string[]
  /** 行过滤表达式（空 = 全部行） */
  filter: string
  /** 依赖条件：cycle=同周期 / batch=同批次 / cycle_batch=同周期同批次 */
  scope: 'cycle' | 'batch' | 'cycle_batch'
}

/** 任务流业务类型（可选内核扩展，向后兼容）：任务中心按类型分视角打开对应画布 */
export type DocType = 'batch' | 'sync' | 'etl' | 'stream'

/** F56b N6：节点成组（纯元数据，不占画布实体；折叠时隐藏成员并以合成徽标代显） */
export interface DocGroup {
  id: string
  name: string
  nodeIds: string[]
}

export interface GraphDocument {
  id: string
  name: string
  version: number
  meta: { profile: string; updatedAt?: string; type?: DocType }
  nodes: GNode[]
  edges: GEdge[]
  /** F56b N6：节点组（后端 save 以 dict 整体透传落库，额外字段安全；缺省兼容老文档） */
  groups?: DocGroup[]
}

/**
 * 影响分析子图（M09 血缘 · 影响分析面板）。
 * 形状对齐 prototype/assets/data.js impactExample（L420-426）：
 * 选中表 → 下游表 / 下游任务 / 受影响指标 / 关联报表。
 */
export interface ImpactSubgraph {
  /** 选中表名 */
  table: string
  /** 下游受影响表（含加工任务） */
  downTables: { name: string; task: string }[]
  /** 下游受影响任务（含所属工作流与类型） */
  downTasks: { name: string; wf: string; type: string }[]
  /** 受影响指标 */
  downIndicators: { name: string; code: string }[]
  /** 关联报表 */
  reports: string[]
}

export type IssueLevel = 'error' | 'warn'

export interface Issue {
  level: IssueLevel
  msg: string
  nodeId?: string
  edgeId?: string
}

/** 校验器：profile 注入，输入图文档，输出问题列表 */
export type Validator = (doc: GraphDocument) => Issue[]

let seq = 0
export function uid(prefix = 'n'): string {
  seq += 1
  return `${prefix}_${Date.now().toString(36)}${seq.toString(36)}`
}

/** 邻接表 */
export function adjacency(doc: GraphDocument): Map<string, string[]> {
  const m = new Map<string, string[]>()
  doc.nodes.forEach((n) => m.set(n.id, []))
  doc.edges.forEach((e) => {
    if (m.has(e.source)) m.get(e.source)!.push(e.target)
  })
  return m
}

/**
 * 拓扑排序（Kahn）。含环时返回已排序部分与剩余节点。
 * 试运行按此顺序逐节点点亮。
 */
export function topoSort(doc: GraphDocument): { order: string[]; cyclic: string[] } {
  const indeg = new Map<string, number>()
  doc.nodes.forEach((n) => indeg.set(n.id, 0))
  doc.edges.forEach((e) => {
    if (indeg.has(e.target)) indeg.set(e.target, indeg.get(e.target)! + 1)
  })
  const adj = adjacency(doc)
  const q: string[] = []
  indeg.forEach((d, id) => { if (d === 0) q.push(id) })
  const order: string[] = []
  while (q.length) {
    const id = q.shift()!
    order.push(id)
    ;(adj.get(id) ?? []).forEach((t) => {
      const d = indeg.get(t)! - 1
      indeg.set(t, d)
      if (d === 0) q.push(t)
    })
  }
  const cyclic = doc.nodes.map((n) => n.id).filter((id) => !order.includes(id))
  return { order, cyclic }
}

/** 环检测：返回处于环上的节点 id（其余校验器复用 topoSort） */
export function detectCycle(doc: GraphDocument): string[] {
  return topoSort(doc).cyclic
}

/** 孤立节点：无任何入边与出边 */
export function findIsolated(doc: GraphDocument): string[] {
  const linked = new Set<string>()
  doc.edges.forEach((e) => { linked.add(e.source); linked.add(e.target) })
  return doc.nodes.filter((n) => !linked.has(n.id)).map((n) => n.id)
}

/** 断链引用：边的端点不存在 */
export function findBrokenEdges(doc: GraphDocument): string[] {
  const ids = new Set(doc.nodes.map((n) => n.id))
  return doc.edges.filter((e) => !ids.has(e.source) || !ids.has(e.target)).map((e) => e.id)
}

/** 重复边检测（同 source→target→sourceHandle；不同分支端点到同一目标不视为重复） */
export function findDuplicateEdges(doc: GraphDocument): string[] {
  const seen = new Set<string>()
  const dup: string[] = []
  doc.edges.forEach((e) => {
    const k = `${e.source}->${e.target}:${e.sourceHandle ?? ''}`
    if (seen.has(k)) dup.push(e.id)
    seen.add(k)
  })
  return dup
}

/** 深拷贝（结构化，doc 均为可序列化 JSON） */
export function cloneDoc(doc: GraphDocument): GraphDocument {
  return JSON.parse(JSON.stringify(doc)) as GraphDocument
}
