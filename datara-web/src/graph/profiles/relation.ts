/**
 * relation profile：U7 元数据管理 · 数据资产地图（力导向关系总览）。
 * 资产类型：表 / 指标 / 报表 / API / 标签；边语义：产出 / 引用 / 调用 / 打标。
 * 力导向布局（确定性模拟），点击节点查看关联资产。
 */
import { findIsolated } from '../model'
import type { GNode, GraphDocument } from '../model'
import type { RelatedItem, ViewProfile } from './types'

const ASSETS = [
  { t: 'as_table', name: '数据表', icon: '▤', color: '#1668dc', desc: '库表资产（血缘与其他资产的主体）' },
  { t: 'as_metric', name: '指标', icon: 'Σ', color: '#7c3aed', desc: '原子/派生指标资产' },
  { t: 'as_report', name: '报表', icon: '▦', color: '#16a34a', desc: '看板与报表资产' },
  { t: 'as_api', name: 'API', icon: '⇄', color: '#d97706', desc: '数据服务 API 资产' },
  { t: 'as_tag', name: '标签', icon: '#', color: '#c2410c', desc: '资产标签（核心/敏感/PII）' },
]

function assetRelated(node: GNode, doc: GraphDocument): RelatedItem[] {
  const nameOf = (id: string) => doc.nodes.find((n) => n.id === id)?.data.name ?? id
  const kindText: Record<string, string> = { produce: '产出', refer: '引用', call: '调用', tag: '打标' }
  return doc.edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => {
      const out = e.source === node.id
      const other = out ? e.target : e.source
      const k = kindText[e.kind ?? 'refer'] ?? '关联'
      return out
        ? { text: `${k} → ${nameOf(other)}`, color: '#1668dc' }
        : { text: `被${k} ← ${nameOf(other)}`, color: '#d97706' }
    })
}

const asTypes: Record<string, import('./types').NodeSchema> = Object.fromEntries(
  ASSETS.map((a) => [
    a.t,
    {
      type: a.t,
      label: a.name,
      icon: a.icon,
      color: a.color,
      desc: a.desc,
      defaults: a.t === 'as_table' ? { domain: '', rows: 0 } : { owner: '', desc2: '' },
      form: a.t === 'as_table'
        ? [{ key: 'domain', label: '业务域', type: 'text' }, { key: 'rows', label: '行数', type: 'number' }]
        : [{ key: 'owner', label: '负责人', type: 'text' }, { key: 'desc2', label: '说明', type: 'textarea' }],
      summary: (d) => String(d.owner || d.domain || ''),
      related: assetRelated,
    } satisfies import('./types').NodeSchema,
  ]),
)

export const relationProfile: ViewProfile = {
  id: 'relation',
  name: '资产地图',
  mode: 'view',
  layout: 'force',
  defaultEdge: 'refer',
  nodeTypes: asTypes,
  edgeKinds: {
    produce: { kind: 'produce', label: '产出/加工', color: '#1668dc' },
    refer: { kind: 'refer', label: '引用', color: '#7c3aed' },
    call: { kind: 'call', label: '调用', color: '#d97706' },
    tag: { kind: 'tag', label: '打标', color: '#c2410c', dashed: true },
  },
  palette: [],
  floats: [],
  force: { iterations: 320, idealLen: 190 },
  validators: [
    (doc) => findIsolated(doc).map((id) => ({
      level: 'warn' as const,
      msg: `孤立资产「${doc.nodes.find((n) => n.id === id)?.data.name}」未与任何资产建立关联`,
      nodeId: id,
    })),
  ],
}
