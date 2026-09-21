/**
 * 泳道布局：按 node.lane 分层（对应 profile.lanes 顺序），层内水平排列。
 * 用于部署拓扑五层泳道等视角。
 */
import type { GraphDocument } from '../model'
import type { LaneDef } from '../profiles/types'

export interface LaneLayoutOptions {
  lanes: LaneDef[]
  nodeW?: number
  nodeH?: number
  colGap?: number
  rowGap?: number
  originX?: number
  originY?: number
}

export function laneLayout(doc: GraphDocument, opts: LaneLayoutOptions): GraphDocument {
  const { lanes, nodeW = 168, nodeH = 48, colGap = 60, rowGap = 56, originX = 60, originY = 90 } = opts
  const out: GraphDocument = { ...doc, nodes: doc.nodes.map((n) => ({ ...n })) }
  const laneIndex = new Map(lanes.map((l, i) => [l.key, i]))

  out.nodes.forEach((n) => {
    const row = laneIndex.get(n.lane ?? '') ?? 0
    n.position = { x: n.position.x, y: originY + row * (nodeH + rowGap) }
  })

  // 层内按现有 x 排序后重新均匀分布
  lanes.forEach((lane) => {
    const group = out.nodes
      .filter((n) => (n.lane ?? '') === lane.key)
      .sort((a, b) => a.position.x - b.position.x)
    group.forEach((n, i) => {
      n.position.x = originX + i * (nodeW + colGap)
    })
  })
  return out
}
