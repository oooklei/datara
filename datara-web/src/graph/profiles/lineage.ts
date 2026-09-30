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

/* ---------- 详情抽屉关联信息（Task 7 升级：数据面 + 上下游计数 + 明细列表） ---------- */

/** lineageRelated 导出（Task 7，便于单测直测）：先数据面（数据源/临时表/来源/参与工作流/上下游计数），
 * 后上游/下游明细列表；ds/tmp/wfs/sources 仅 graph 聚合路径注入（buildLineageGraphDoc），旧路径不显示。 */
export function lineageRelated(node: GNode, doc: GraphDocument): RelatedItem[] {
  const items: RelatedItem[] = []
  const nameOf = (id: string) => doc.nodes.find((n) => n.id === id)?.data.name ?? id
  const ds = typeof node.data.ds === 'string' ? node.data.ds : ''
  if (ds) items.push({ text: `数据源：${ds}`, color: '#0891b2' })
  if (node.data.tmp === true) items.push({ text: '临时表', color: '#d97706' })
  const sources = Array.isArray(node.data.sources) ? node.data.sources as string[] : []
  if (sources.length) {
    items.push({
      text: `来源：${sources.map((s) => (s === 'design' ? '设计推导' : '运行事实')).join(' + ')}`,
      color: sources.includes('runtime') ? '#1668dc' : '#d97706',
    })
  }
  const wfs = Array.isArray(node.data.wfs) ? node.data.wfs as unknown[] : []
  if (wfs.length) items.push({ text: `参与工作流：${wfs.map((w) => `wf${w}`).join('、')}`, color: '#7c3aed' })
  const ups = doc.edges.filter((e) => e.target === node.id)
  const downs = doc.edges.filter((e) => e.source === node.id)
  items.push({ text: `上游 ${ups.length} 条 · 下游 ${downs.length} 条`, color: '#334155' })
  ups.forEach((e) => items.push({
    text: `上游 ← ${nameOf(e.source)}${e.label ? `（${e.label}）` : ''}`,
    color: '#d97706',
  }))
  downs.forEach((e) => items.push({
    text: `下游 → ${nameOf(e.target)}${e.label ? `（${e.label}）` : ''}`,
    color: '#1668dc',
  }))
  if (!ups.length && !downs.length) items.push({ text: '无上下游血缘（孤岛资产）', color: '#e5484d' })
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
  /* Task 5 来源视觉体系：dep=运行事实（实线）/ dep_design=设计推导（虚线）/
   * 双源=dep 实线 + label「（双源）」徽标（见 lineageUtils.buildLineageGraphDoc）；
   * Task 7：dep_focus=一键影响分析/源头追踪的全链聚焦态（高亮色 + 流动动画），label 沿用原边。 */
  edgeKinds: {
    dep: { kind: 'dep', label: '加工流向（运行事实）', color: '#1668dc' },
    dep_design: { kind: 'dep_design', label: '设计推导（未验证）', color: '#d97706', dashed: true },
    dep_unlinked: { kind: 'dep_unlinked', label: '未入工作流', color: '#94a3b8', dashed: true },
    dep_focus: { kind: 'dep_focus', label: '聚焦全链', color: '#e11d48', animated: true },
    field_dep: { kind: 'field_dep', label: '字段级血缘', color: '#7c3aed', dashed: true },
  },
  palette: [],
  /** Task 7：节点双击/右键「以此为中心」上抛 center-node（宿主 LineageView 重拉） */
  nodeCenter: true,
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
