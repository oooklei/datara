/**
 * 力导向布局（确定性）：资产地图等关系总览图。
 * 圆环初始位 → 迭代「点对斥力 + 边引力 + 向心力」，无随机源，结果可复现。
 * 规模小（<100 节点）O(n²) 迭代无性能压力。
 */
import type { GraphDocument } from '../model'

export interface ForceLayoutOptions {
  iterations?: number
  /** 点对斥力强度 */
  repulsion?: number
  /** 边理想长度 */
  idealLen?: number
  /** 向心力强度 */
  gravity?: number
  originX?: number
  originY?: number
  /** 初始圆环半径 */
  radius?: number
}

export function forceLayout(doc: GraphDocument, opts: ForceLayoutOptions = {}): GraphDocument {
  const {
    iterations = 300, repulsion = 26000, idealLen = 170, gravity = 0.035,
    originX = 420, originY = 380, radius = 260,
  } = opts
  const out: GraphDocument = { ...doc, nodes: doc.nodes.map((n) => ({ ...n })) }
  const ns = out.nodes
  const n = ns.length
  if (!n) return out

  // 确定性初始位：按索引均匀圆环
  ns.forEach((node, i) => {
    const a = (2 * Math.PI * i) / n - Math.PI / 2
    node.position = { x: originX + radius * Math.cos(a), y: originY + radius * Math.sin(a) }
  })

  const index = new Map(ns.map((node, i) => [node.id, i]))
  const edges = out.edges
    .map((e) => [index.get(e.source), index.get(e.target)] as const)
    .filter((p): p is readonly [number, number] => p[0] !== undefined && p[1] !== undefined)
  // 度数高的节点引力更强（枢纽资产聚中）
  const deg = new Array<number>(n).fill(0)
  edges.forEach(([a, b]) => { deg[a] += 1; deg[b] += 1 })

  for (let it = 0; it < iterations; it++) {
    const fx = new Array<number>(n).fill(0)
    const fy = new Array<number>(n).fill(0)
    // 斥力
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = ns[i].position.x - ns[j].position.x
        const dy = ns[i].position.y - ns[j].position.y
        const d2 = Math.max(dx * dx + dy * dy, 120)
        const f = repulsion / d2
        const d = Math.sqrt(d2)
        const ux = (dx / d) * f
        const uy = (dy / d) * f
        fx[i] += ux; fy[i] += uy
        fx[j] -= ux; fy[j] -= uy
      }
    }
    // 引力（沿边）
    for (const [a, b] of edges) {
      const dx = ns[b].position.x - ns[a].position.x
      const dy = ns[b].position.y - ns[a].position.y
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const f = (d - idealLen) * 0.012 * (1 + 0.12 * Math.min(deg[a], deg[b]))
      const ux = (dx / d) * f
      const uy = (dy / d) * f
      fx[a] += ux; fy[a] += uy
      fx[b] -= ux; fy[b] -= uy
    }
    // 向心力 + 位移
    for (let i = 0; i < n; i++) {
      const node = ns[i]
      fx[i] += (originX - node.position.x) * gravity * (1 + 0.25 * deg[i])
      fy[i] += (originY - node.position.y) * gravity * (1 + 0.25 * deg[i])
      // 迭代后期阻尼收敛
      const damp = 1 - it / iterations
      node.position = {
        x: node.position.x + Math.max(-24, Math.min(24, fx[i] * damp)),
        y: node.position.y + Math.max(-24, Math.min(24, fy[i] * damp)),
      }
    }
  }
  return out
}
