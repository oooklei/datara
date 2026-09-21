/**
 * topoSort 冒烟测试（Wave 0 todo 1）
 * 覆盖：全图拓扑序 / 含环安全 / fromNode 剪枝语义（对齐 execService.reachable L20-34）
 */
import { describe, it, expect } from 'vitest'
import type { GraphDocument } from '../index'
import { topoSort } from '../index'

function doc(nodes: string[], edges: [string, string][]): GraphDocument {
  return {
    id: 't',
    name: 'test',
    version: 1,
    meta: { profile: 'topo' },
    nodes: nodes.map((id) => ({ id, type: 'task', position: { x: 0, y: 0 }, data: { name: id } })),
    edges: edges.map(([source, target], i) => ({ id: `e${i}`, source, target })),
  }
}

/** 校验 order 是否为合法拓扑序：每条边 source 必须排在 target 之前 */
function assertTopoOrder(order: string[], edges: [string, string][]) {
  const pos = new Map(order.map((id, i) => [id, i]))
  for (const [s, t] of edges) {
    if (pos.has(s) && pos.has(t)) {
      expect(pos.get(s)!).toBeLessThan(pos.get(t)!)
    }
  }
}

/** 复刻 execService.reachable（L20-34）语义：BFS 可达集 */
function reachable(g: GraphDocument, from?: string): Set<string> {
  if (!from) return new Set(g.nodes.map((n) => n.id))
  const adj = new Map<string, string[]>()
  g.nodes.forEach((n) => adj.set(n.id, []))
  g.edges.forEach((e) => adj.get(e.source)?.push(e.target))
  const seen = new Set<string>([from])
  const q = [from]
  while (q.length) {
    const cur = q.shift()!
    ;(adj.get(cur) ?? []).forEach((t) => {
      if (!seen.has(t)) {
        seen.add(t)
        q.push(t)
      }
    })
  }
  return seen
}

describe('topoSort', () => {
  it('全图序：DAG 返回包含全部节点的合法拓扑序', () => {
    const g = doc(
      ['a', 'b', 'c', 'd'],
      [
        ['a', 'b'],
        ['a', 'c'],
        ['b', 'd'],
        ['c', 'd'],
      ],
    )
    const { order, cyclic } = topoSort(g)
    expect(order).toHaveLength(4)
    expect(new Set(order)).toEqual(new Set(['a', 'b', 'c', 'd']))
    expect(cyclic).toHaveLength(0)
    assertTopoOrder(order, [
      ['a', 'b'],
      ['a', 'c'],
      ['b', 'd'],
      ['c', 'd'],
    ])
  })

  it('含环安全：环上节点进入 cyclic，非环节点仍有序返回，不挂起', () => {
    const g = doc(
      ['a', 'b', 'c', 'd'],
      [
        ['a', 'b'],
        ['b', 'c'],
        ['c', 'a'], // 环 a→b→c→a
        ['d', 'a'], // d 为环的前驱（入度 0），可正常放置
      ],
    )
    const { order, cyclic } = topoSort(g)
    // d 无入边，必然在 order 中
    expect(order).toContain('d')
    // 环上节点 a/b/c 全部进入 cyclic
    expect(new Set(cyclic)).toEqual(new Set(['a', 'b', 'c']))
    // order 与 cyclic 无交集且并集为全节点
    expect(order.filter((id) => cyclic.includes(id))).toHaveLength(0)
    expect(order.length + cyclic.length).toBe(4)
  })

  it('fromNode 剪枝：仅返回 from 可达节点，且保持拓扑序（对齐 execService.reachable）', () => {
    const g = doc(
      ['a', 'b', 'c', 'd', 'e'],
      [
        ['a', 'b'],
        ['b', 'c'],
        ['d', 'e'], // d/e 与 a 无关
      ],
    )
    const from = 'a'
    const scope = reachable(g, from)
    const { order } = topoSort(g)
    const pruned = order.filter((id) => scope.has(id))
    // 剪枝后只含 a/b/c
    expect(new Set(pruned)).toEqual(new Set(['a', 'b', 'c']))
    // 剪枝后仍为合法拓扑序（a 在 b 前，b 在 c 前）
    assertTopoOrder(pruned, [
      ['a', 'b'],
      ['b', 'c'],
    ])
  })

  it('fromNode 剪枝：from 未命中任何节点时返回空序（execService 语义：scope 为空 → queue 为空）', () => {
    const g = doc(
      ['a', 'b'],
      [['a', 'b']],
    )
    const scope = reachable(g, 'ghost')
    const { order } = topoSort(g)
    const pruned = order.filter((id) => scope.has(id))
    expect(pruned).toHaveLength(0)
  })
})