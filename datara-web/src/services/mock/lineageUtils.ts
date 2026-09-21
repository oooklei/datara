/**
 * lineageUtils — M09 血缘分析纯函数工具（todo 10）
 * 表级/字段级血缘图构建 + N 层上下游过滤 + 影响分析推导，均为纯函数。
 * 数据源 = dataStore.tableLineage / fieldLineage（图文档 lineageGraph 不动）。
 */
import { dagreLayout } from '../../graph/layout/dagre'
import type { GEdge, GNode, GraphDocument, ImpactSubgraph } from '../../graph/model'
import type { FieldLineage, ImpactExample, MetaTable, TableLineage } from '../types'

const LAYER_KEYS = ['ODS', 'DIM', 'DWD', 'DWS', 'ADS'] as const

/** 表名（或 表.字段）→ 数仓分层；未知前缀兜底 ODS（源侧资产） */
export function layerOf(name: string): string {
  const base = name.split('.')[0]
  const prefix = base.split('_')[0].toUpperCase()
  return (LAYER_KEYS as readonly string[]).includes(prefix) ? prefix : 'ODS'
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

/** N 层上下游过滤：BFS 保留 center 及 depth 跳内可达节点与其间边 */
export function filterByDepth(
  doc: GraphDocument,
  center: string,
  dir: 'up' | 'down',
  depth: number,
): GraphDocument {
  const reach = new Set<string>([center])
  let frontier = new Set<string>([center])
  for (let hop = 0; hop < depth; hop++) {
    const next = new Set<string>()
    doc.edges.forEach((e) => {
      if (dir === 'down' && frontier.has(e.source) && !reach.has(e.target)) {
        reach.add(e.target); next.add(e.target)
      } else if (dir === 'up' && frontier.has(e.target) && !reach.has(e.source)) {
        reach.add(e.source); next.add(e.source)
      }
    })
    frontier = next
    if (frontier.size === 0) break
  }
  return {
    ...doc,
    nodes: doc.nodes.filter((n) => reach.has(n.id)),
    edges: doc.edges.filter((e) => reach.has(e.source) && reach.has(e.target)),
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