/**
 * lineage profile：U6 元数据管理 · 血缘分析（全域表级血缘，dagre LR）。
 * 节点 = 分层表资产；边 = 加工流向（标注加工任务）；Inspector 展示上游/下游。
 */
import { detectCycle, findIsolated } from '../model'
import type { GNode, GraphDocument } from '../model'
import type { RelatedItem, ViewProfile } from './types'
import LineageStatsPanel from '../workbench/panels/LineageStatsPanel.vue'

const LAYERS = [
  { key: 'ODS', color: '#0891b2' },
  { key: 'DIM', color: '#d97706' },
  { key: 'DWD', color: '#1668dc' },
  { key: 'DWS', color: '#7c3aed' },
  { key: 'ADS', color: '#16a34a' },
]

/* ---------- 上下游关联信息 ---------- */

function lineageRelated(node: GNode, doc: GraphDocument): RelatedItem[] {
  const items: RelatedItem[] = []
  const nameOf = (id: string) => doc.nodes.find((n) => n.id === id)?.data.name ?? id
  doc.edges
    .filter((e) => e.target === node.id)
    .forEach((e) => items.push({
      text: `上游 ← ${nameOf(e.source)}${e.label ? `（${e.label}）` : ''}`,
      color: '#d97706',
    }))
  doc.edges
    .filter((e) => e.source === node.id)
    .forEach((e) => items.push({
      text: `下游 → ${nameOf(e.target)}${e.label ? `（${e.label}）` : ''}`,
      color: '#1668dc',
    }))
  if (!items.length) items.push({ text: '无上下游血缘（孤岛资产）', color: '#e5484d' })
  return items
}

const lnTypes: Record<string, import('./types').NodeSchema> = Object.fromEntries(
  LAYERS.map((l) => [
    `ln_${l.key.toLowerCase()}`,
    {
      type: `ln_${l.key.toLowerCase()}`,
      label: `${l.key} 资产`,
      icon: '▤',
      color: l.color,
      desc: `${l.key} 层数据资产节点`,
      defaults: { layer: l.key, domain: '', rows: 0, core: false },
      form: [
        { key: 'domain', label: '业务域', type: 'text' },
        { key: 'rows', label: '行数', type: 'number' },
      ],
      summary: (d) => [d.domain || l.key, d.rows ? `${Number(d.rows) >= 10000 ? `${(Number(d.rows) / 10000).toFixed(0)} 万行` : `${d.rows} 行`}` : ''].filter(Boolean).join(' · '),
      related: lineageRelated,
    } satisfies import('./types').NodeSchema,
  ]),
)

export const lineageProfile: ViewProfile = {
  id: 'lineage',
  name: '血缘分析',
  mode: 'view',
  layout: 'dagre',
  layoutDir: 'LR',
  defaultEdge: 'dep',
  nodeTypes: lnTypes,
  edgeKinds: {
    dep: { kind: 'dep', label: '加工流向', color: '#1668dc' },
    dep_unlinked: { kind: 'dep_unlinked', label: '未入工作流', color: '#94a3b8', dashed: true },
    field_dep: { kind: 'field_dep', label: '字段级血缘', color: '#7c3aed', dashed: true },
  },
  palette: [],
  floats: [
    { id: 'lineage-stats', label: '血缘统计', comp: LineageStatsPanel, w: 420, h: 340, mode: 'view' },
  ],
  validators: [
    (doc) => detectCycle(doc).length
      ? [{ level: 'error', msg: '血缘存在环（分层加工链路不应回环）' }]
      : [],
    (doc) => findIsolated(doc).map((id) => ({
      level: 'warn' as const,
      msg: `孤岛资产「${doc.nodes.find((n) => n.id === id)?.data.name}」无任何血缘关系`,
      nodeId: id,
    })),
  ],
}
