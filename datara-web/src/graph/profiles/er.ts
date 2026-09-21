/**
 * er profile：U5 数仓建模 ER 画布。
 * 实体 = 表实体卡片（自定义 nodeComp，字段列表 PK/FK 徽标）；
 * 边 = 实体关系（1:N / N:1 / 1:1 / M:N，smoothstep 直角连线）。
 * 布局 = 分层列网格（列序 = 数仓分层）。
 */
import { findIsolated } from '../model'
import type { GNode, GraphDocument } from '../model'
import type { RelatedItem, ViewProfile } from './types'
import ErNode from '../workbench/ErNode.vue'

const LAYERS = [
  { key: 'ODS', color: '#0891b2', desc: '源表原样接入' },
  { key: 'DIM', color: '#d97706', desc: '公共维度' },
  { key: 'DWD', color: '#1668dc', desc: '明细事实' },
  { key: 'DWS', color: '#7c3aed', desc: '轻度汇总' },
  { key: 'ADS', color: '#16a34a', desc: '应用宽表' },
]

/* ---------- Inspector 关联信息：实体 → 关系列表 ---------- */

function entityRelated(node: GNode, doc: GraphDocument): RelatedItem[] {
  const CARD: Record<string, string> = { rel_1n: '1:N', rel_n1: 'N:1', rel_11: '1:1', rel_nm: 'M:N' }
  const nameOf = (id: string) => doc.nodes.find((n) => n.id === id)?.data.name ?? id
  return doc.edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => {
      const out = e.source === node.id
      const other = out ? e.target : e.source
      const card = CARD[e.kind ?? 'rel_1n'] ?? '?'
      return out
        ? { text: `${card} → ${nameOf(other)}`, color: '#1668dc' }
        : { text: `${nameOf(other)} → ${card} 本表`, color: '#d97706' }
    })
}

/* ---------- 校验器 ---------- */

const validators = [
  (doc: GraphDocument) =>
    findIsolated(doc).map((id) => ({
      level: 'warn' as const,
      msg: `孤立实体「${doc.nodes.find((n) => n.id === id)?.data.name}」未建立任何关系`,
      nodeId: id,
    })),
  (doc: GraphDocument) =>
    doc.nodes
      .filter((n) => {
        const fs = n.data.fields as { key?: string }[] | undefined
        return Array.isArray(fs) && fs.length > 0 && !fs.some((f) => f.key === 'PK')
      })
      .map((n) => ({
        level: 'warn' as const,
        msg: `实体「${n.data.name}」未定义主键（PK）`,
        nodeId: n.id,
      })),
  (doc: GraphDocument) =>
    doc.edges.filter((e) => e.source === e.target).map((e) => ({
      level: 'warn' as const, msg: '存在自环关系（实体指向自身）', edgeId: e.id,
    })),
]

/* ---------- 实体类型（按分层，5 类共用 ErNode 渲染） ---------- */

const entTypes: Record<string, import('./types').NodeSchema> = Object.fromEntries(
  LAYERS.map((l) => [
    `ent_${l.key.toLowerCase()}`,
    {
      type: `ent_${l.key.toLowerCase()}`,
      label: `${l.key} 表实体`,
      icon: '▤',
      color: l.color,
      desc: `${l.key}：${l.desc}，拖入画布后连接关系线建模`,
      defaults: { layer: l.key, domain: '', comment: '', fields: [] },
      form: [
        { key: 'domain', label: '所属业务域', type: 'text', placeholder: '如：交易域' },
        { key: 'comment', label: '模型说明', type: 'textarea', placeholder: '建模口径、来源说明' },
      ],
      summary: (d) => {
        const fs = Array.isArray(d.fields) ? (d.fields as unknown[]).length : 0
        return `${fs} 字段 · ${d.domain || '未分域'}`
      },
      related: entityRelated,
    } satisfies import('./types').NodeSchema,
  ]),
)

export const erProfile: ViewProfile = {
  id: 'er',
  name: 'ER 画布',
  mode: 'edit',
  layout: 'er',
  defaultEdge: 'rel_1n',
  nodeComp: ErNode,
  nodeTypes: entTypes,
  edgeKinds: {
    rel_1n: { kind: 'rel_1n', label: '一对多 1:N', color: '#1668dc', edgeType: 'smoothstep' },
    rel_n1: { kind: 'rel_n1', label: '多对一 N:1', color: '#0891b2', edgeType: 'smoothstep' },
    rel_11: { kind: 'rel_11', label: '一对一 1:1', color: '#16a34a', edgeType: 'smoothstep' },
    rel_nm: { kind: 'rel_nm', label: '多对多 M:N', color: '#d97706', dashed: true, edgeType: 'smoothstep' },
  },
  palette: [
    { name: '表实体 · 按分层', types: LAYERS.map((l) => `ent_${l.key.toLowerCase()}`) },
  ],
  erGrid: {},
  validators,
}

/** 关系边 kind 的基数标注（seed 与联动共用） */
export function cardLabel(kind?: string): string {
  return ({ rel_1n: '1:N', rel_n1: 'N:1', rel_11: '1:1', rel_nm: 'M:N' })[kind ?? 'rel_1n'] ?? ''
}
