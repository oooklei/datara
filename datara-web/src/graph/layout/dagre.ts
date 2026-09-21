/**
 * dagre 层次布局封装（DAG 分层：TB 自上而下 / LR 自左向右）
 */
import dagre from '@dagrejs/dagre'
import type { GraphDocument } from '../model'

export interface LayoutOptions {
  dir?: 'TB' | 'LR'
  nodeW?: number
  nodeH?: number
  rankSep?: number
  nodeSep?: number
}

export function dagreLayout(doc: GraphDocument, opts: LayoutOptions = {}): GraphDocument {
  const { dir = 'TB', nodeW = 180, nodeH = 48, rankSep = 70, nodeSep = 40 } = opts
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: dir, ranksep: rankSep, nodesep: nodeSep, marginx: 40, marginy: 40 })
  g.setDefaultEdgeLabel(() => ({}))
  doc.nodes.forEach((n) => g.setNode(n.id, { width: nodeW, height: nodeH }))
  doc.edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)

  const out: GraphDocument = { ...doc, nodes: doc.nodes.map((n) => ({ ...n })) }
  out.nodes.forEach((n) => {
    const pos = g.node(n.id)
    if (pos) {
      n.position = {
        x: (pos.x as number) - nodeW / 2,
        y: (pos.y as number) - nodeH / 2,
      }
    }
  })
  return out
}
