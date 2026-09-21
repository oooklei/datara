/**
 * ER 分层列布局：表实体按数仓分层排成若干纵向列（列序 = 分层顺序），
 * 行距按实体最大字段数自适应（ER 实体卡片高度随字段列表变化）。
 */
import type { GNode, GraphDocument } from '../model'

export interface ErGridLayoutOptions {
  /** 列（分层）顺序 */
  layerOrder?: string[]
  /** 实体 data 中分层字段名 */
  layerKey?: string
  colGap?: number
  rowGap?: number
  /** 实体卡片估算行高基数 */
  cardBase?: number
  /** 每个字段增量 */
  cardPerField?: number
  originX?: number
  originY?: number
  /** 同列最大行数（超过换新列组） */
  maxPerCol?: number
}

export function erGridLayout(doc: GraphDocument, opts: ErGridLayoutOptions = {}): GraphDocument {
  const {
    layerOrder = ['ODS', 'DIM', 'DWD', 'DWS', 'ADS'],
    layerKey = 'layer',
    colGap = 90, rowGap = 46,
    cardBase = 74, cardPerField = 26,
    originX = 60, originY = 60,
    maxPerCol = 4,
  } = opts
  const out: GraphDocument = { ...doc, nodes: doc.nodes.map((n) => ({ ...n })) }

  const groups = new Map<string, GNode[]>()
  out.nodes.forEach((node) => {
    const g = String(node.data[layerKey] ?? 'ODS')
    if (!groups.has(g)) groups.set(g, [])
    groups.get(g)!.push(node)
  })

  let x = originX
  layerOrder.forEach((layer) => {
    const list = groups.get(layer)
    if (!list?.length) return
    // 同列内按字段数降序 → 高卡片在前，视觉稳定
    list.sort((a, b) => {
      const fa = Array.isArray(a.data.fields) ? (a.data.fields as unknown[]).length : 0
      const fb = Array.isArray(b.data.fields) ? (b.data.fields as unknown[]).length : 0
      return fb - fa
    })
    // 纵向分块（每块 maxPerCol 个实体），块间横向排
    for (let start = 0; start < list.length; start += maxPerCol) {
      const chunk = list.slice(start, start + maxPerCol)
      let y = originY
      const colW = Math.max(...chunk.map((node) => cardW(node))) + colGap
      chunk.forEach((node) => {
        node.position = { x, y }
        y += cardH(node) + rowGap
      })
      x += colW
    }
  })
  return out

  function cardH(node: GNode): number {
    const f = Array.isArray(node.data.fields) ? (node.data.fields as unknown[]).length : 0
    return cardBase + f * cardPerField
  }
  function cardW(_node: GNode): number {
    return 230
  }
}
