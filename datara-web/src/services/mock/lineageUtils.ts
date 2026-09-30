/**
 * lineageUtils — M09 血缘分析纯函数工具（todo 10）
 * 表级/字段级血缘图构建 + N 层上下游过滤 + 影响分析推导，均为纯函数。
 * 数据源 = dataStore.tableLineage / fieldLineage（图文档 lineageGraph 不动）。
 */
import { dagreLayout } from '../../graph/layout/dagre'
import type { GEdge, GEdgeKind, GNode, GraphDocument, ImpactSubgraph } from '../../graph/model'
import type { FieldLineage, ImpactExample, MetaTable, TableLineage } from '../types'
import type { LineageGraphEdge, LineageGraphResult } from '../lineageApi'

const LAYER_KEYS = ['ODS', 'DIM', 'DWD', 'DWS', 'ADS'] as const

/** 表名（或 表.字段）→ 数仓分层；未知前缀兜底 ODS（源侧资产） */
export function layerOf(name: string): string {
  const base = name.split('.')[0]
  const prefix = base.split('_')[0].toUpperCase()
  return (LAYER_KEYS as readonly string[]).includes(prefix) ? prefix : 'ODS'
}

/** 中心表命中判定（id 全名 / id 裸表名尾段 / kw 带前缀反查）：
 * graph 文档节点 id 为数据源点分 fq，深链 ?table= 传裸表名时据此归一为命中节点的 fq。 */
export function matchCenter(id: string, kw: string): boolean {
  return id === kw || id.endsWith(`.${kw}`) || kw.endsWith(`.${id}`)
}

/** 表级血缘图：节点 = 边端点去重（元数据富化），边 = 加工流向（未入工作流 → dep_unlinked） */
export function buildTableLineageDoc(rows: TableLineage[], metaTables?: MetaTable[]): GraphDocument {
  const metaByName = new Map((metaTables ?? []).map((t) => [t.name, t]))
  const ids = new Set<string>()
  rows.forEach((r) => { ids.add(r.from); ids.add(r.to) })
  const nodes: GNode[] = [...ids].map((name) => {
    const meta = metaByName.get(name)
    const layer = layerOf(name)
    return {
      id: name,
      type: `ln_${layer.toLowerCase()}`,
      position: { x: 0, y: 0 },
      data: {
        name,
        layer,
        domain: meta?.domain ?? '',
        rows: meta?.rows ?? 0,
        core: meta?.tags?.includes('核心') ?? false,
      },
    }
  })
  const edges: GEdge[] = rows.map((r, i) => ({
    id: `tle${i + 1}`,
    source: r.from,
    target: r.to,
    kind: r.wf === '未入工作流' ? 'dep_unlinked' : 'dep',
    label: r.task,
  }))
  const doc: GraphDocument = {
    id: 'lineage_table',
    name: '全域血缘（表级）',
    version: 1,
    meta: { profile: 'lineage', updatedAt: '2026-09-12 07:35' },
    nodes,
    edges,
  }
  return dagreLayout(doc, { dir: 'LR' })
}

/** 字段级血缘图：节点 = 字段端点，边 kind=field_dep 且标注转换表达式 */
export function buildFieldLineageDoc(fieldLineage: FieldLineage): GraphDocument {
  const ids = new Set<string>()
  Object.entries(fieldLineage).forEach(([target, items]) => {
    ids.add(target)
    items.forEach((it) => ids.add(it.from))
  })
  const nodes: GNode[] = [...ids].map((name) => {
    const layer = layerOf(name)
    return {
      id: name,
      type: `ln_${layer.toLowerCase()}`,
      position: { x: 0, y: 0 },
      data: { name, layer, domain: '', rows: 0, core: false },
    }
  })
  const edges: GEdge[] = []
  Object.entries(fieldLineage).forEach(([target, items]) => {
    items.forEach((it) => {
      edges.push({
        id: `fle${edges.length + 1}`,
        source: it.from,
        target,
        kind: 'field_dep',
        label: it.transform,
      })
    })
  })
  const doc: GraphDocument = {
    id: 'lineage_field',
    name: '字段级血缘',
    version: 1,
    meta: { profile: 'lineage', updatedAt: '2026-09-12 07:35' },
    nodes,
    edges,
  }
  return dagreLayout(doc, { dir: 'LR' })
}

/* ---------- Task 5：GET /lineage/graph 聚合结果 → 图文档（来源视觉体系） ---------- */

/** 聚边 → 边 kind + 基础 label：runtime 参与即实线 dep；仅 design → 虚线 dep_design。
 * label 用 refs 合成（graph 契约无任务名，取 wfCode·nodeId；field 级取转换表达式）。 */
function graphEdgeKindOf(e: LineageGraphEdge): { kind: GEdgeKind; base: string } {
  if (e.level === 'field') {
    return { kind: 'field_dep', base: e.refs.find((r) => r.transform)?.transform ?? '字段映射' }
  }
  const parts = e.refs.slice(0, 2).map((r) => `wf${r.wfCode}·${r.nodeId}`)
  if (e.refs.length > 2) parts.push(`等 ${e.refs.length} 处`)
  const dual = e.sources.includes('design') && e.sources.includes('runtime')
  return { kind: dual || e.sources.includes('runtime') ? 'dep' : 'dep_design', base: parts.join(' / ') }
}

/** graph 聚合结果 → 血缘图文档：
 * 边三态 = 运行事实（dep 实线）/ 设计推导（dep_design 虚线）/ 双源（dep 实线 + label「（双源）」徽标）；
 * 节点 sources 仅 design（无运行佐证）→ data.unverified=true（DataNode「未验」角标）；
 * Task 7 数据面富化：ds（数据源）/ tmp（临时表→DataNode 虚线边框）/ wfs（参与工作流）/ sources
 * → 详情抽屉 lineageRelated 展示。 */
export function buildLineageGraphDoc(res: LineageGraphResult, metaTables?: MetaTable[]): GraphDocument {
  const metaByName = new Map((metaTables ?? []).map((t) => [t.name, t]))
  const nodes: GNode[] = res.nodes.map((n) => {
    const layer = layerOf(n.table || n.fq)
    const meta = metaByName.get(n.table || n.fq)
    return {
      id: n.fq,
      type: `ln_${layer.toLowerCase()}`,
      position: { x: 0, y: 0 },
      data: {
        name: n.fq,
        layer,
        domain: meta?.domain ?? '',
        rows: meta?.rows ?? 0,
        core: meta?.tags?.includes('核心') ?? false,
        unverified: n.sources.length === 1 && n.sources[0] === 'design',
        ds: n.ds || undefined,
        tmp: !!n.tmpFlag,
        wfs: [...n.wfs],
        sources: [...n.sources],
      },
    }
  })
  const edges: GEdge[] = res.edges.map((e, i) => {
    const { kind, base } = graphEdgeKindOf(e)
    const dual = e.sources.includes('design') && e.sources.includes('runtime')
    return {
      id: `gle${i + 1}`,
      source: e.from,
      target: e.to,
      kind,
      // 双源标记优先于空 refs 兜底（双源佐证徽标不可丢），base 空 → 仅「（双源）」
      label: dual ? `${base}（双源）` : (base || '设计推导'),
    }
  })
  const isField = res.edges.some((e) => e.level === 'field')
  const doc: GraphDocument = {
    id: isField ? 'lineage_field' : 'lineage_table',
    name: isField ? '字段级血缘' : '全域血缘（表级）',
    version: 1,
    meta: { profile: 'lineage', updatedAt: '2026-09-12 07:35' },
    nodes,
    edges,
  }
  return dagreLayout(doc, { dir: 'LR' })
}

/** graph 聚边 → TableLineage 行（影响分析 deriveImpact 的 BFS 输入；
 * task/wf 契约无名称字段，以 refs 首个 wfCode·nodeId 合成展示名）。 */
export function graphEdgesToRows(res: LineageGraphResult): TableLineage[] {
  return res.edges.filter((e) => e.level === 'table').map((e) => {
    const ref = e.refs[0]
    return {
      from: e.from,
      to: e.to,
      task: ref ? `wf${ref.wfCode}·${ref.nodeId}` : '设计推导',
      wf: ref ? String(ref.wfCode) : '-',
    }
  })
}

/** Task 7 一键聚焦高亮：dep/dep_design 边 → dep_focus（lineage profile 高亮色 + 流动动画），
 * 其余语义（field_dep / dep_unlinked）保持原样；浅拷贝不改原文档（computed 层消费）。 */
export function focusAllEdges(doc: GraphDocument): GraphDocument {
  return {
    ...doc,
    edges: doc.edges.map((e) => (e.kind === 'dep' || e.kind === 'dep_design'
      ? { ...e, kind: 'dep_focus' as const }
      : e)),
  }
}

/** Task 8 实例追溯边标注：按 (from,to) 命中追溯边行的 stmt_no 次序，label 追加「#1 #2」（升序去重）。
 * 数据源 = /lineage/tables（instance_id 过滤）行自带的 stmtNo；无命中（mock 样例无实例维度）不改边。
 * 浅拷贝不改原文档（computed 层消费，与 focusAllEdges 同模式）。 */
export function annotateStmtNo(
  doc: GraphDocument,
  rows: { from: string; to: string; stmtNo: number }[],
): GraphDocument {
  const nosByEdge = new Map<string, number[]>()
  rows.forEach((r) => {
    const arr = nosByEdge.get(`${r.from}\n${r.to}`)
    if (arr) { if (!arr.includes(r.stmtNo)) arr.push(r.stmtNo) }
    else nosByEdge.set(`${r.from}\n${r.to}`, [r.stmtNo])
  })
  nosByEdge.forEach((arr) => arr.sort((a, b) => a - b))
  return {
    ...doc,
    edges: doc.edges.map((e) => {
      const nos = nosByEdge.get(`${e.source}\n${e.target}`)
      return nos?.length ? { ...e, label: `${e.label} #${nos.join(' #')}` } : e
    }),
  }
}

/** 影响分析：命中 impactExample 精确 shape，否则通用 BFS 推导下游表/任务 */
export function deriveImpact(
  table: string,
  tableLineage: TableLineage[],
  example?: ImpactExample | null,
): ImpactSubgraph {
  if (example && example.table === table) {
    return {
      table,
      downTables: example.downTables,
      downTasks: example.downTasks,
      downIndicators: example.downIndicators,
      reports: example.reports,
    }
  }
  const downTables: { name: string; task: string }[] = []
  const downTasks: { name: string; wf: string; type: string }[] = []
  const seenTables = new Set<string>()
  const seenTasks = new Set<string>()
  const visited = new Set<string>([table])
  const queue = [table]
  while (queue.length) {
    const cur = queue.shift()!
    tableLineage.forEach((r) => {
      if (r.from !== cur || visited.has(r.to)) return
      visited.add(r.to)
      if (!seenTables.has(r.to)) {
        seenTables.add(r.to)
        downTables.push({ name: r.to, task: r.task })
      }
      const taskName = r.task.split(' ')[0]
      if (!seenTasks.has(taskName)) {
        seenTasks.add(taskName)
        downTasks.push({ name: taskName, wf: r.wf, type: 'SQL任务' })
      }
      queue.push(r.to)
    })
  }
  return { table, downTables, downTasks, downIndicators: [], reports: [] }
}

/** 影响范围摘要文案（空态：暂无血缘） */
export function impactSummary(imp: ImpactSubgraph): string {
  const parts: string[] = []
  if (imp.downTables.length) parts.push(`${imp.downTables.length} 张下游表`)
  if (imp.downTasks.length) parts.push(`${imp.downTasks.length} 个任务`)
  if (imp.downIndicators.length) parts.push(`${imp.downIndicators.length} 个指标`)
  if (imp.reports.length) parts.push(`${imp.reports.length} 个报表`)
  return parts.length ? `影响 ${parts.join('、')}` : '暂无血缘（该表无下游影响对象）'
}