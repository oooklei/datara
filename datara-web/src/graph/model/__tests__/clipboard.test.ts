import { describe, it, expect } from 'vitest'
import { pasteSelection, type ClipboardNode, type ClipboardEdge } from '../clipboard'

/** 源快照：两节点 A→B 内部边 + 一条跨组件边（C 不在快照内，粘贴时必须丢弃） */
function snap() {
  const nodes: ClipboardNode<{ name: string; cfg: { deep: number } }>[] = [
    { id: 'A', type: 'ds', position: { x: 10, y: 20 }, data: { name: 'A', cfg: { deep: 1 } } },
    { id: 'B', type: 'sql', position: { x: 110, y: 20 }, data: { name: 'B', cfg: { deep: 1 } } },
  ]
  const edges: ClipboardEdge[] = [
    { source: 'A', target: 'B', kind: 'flow', label: 'ab', sourceHandle: 'out_1', targetHandle: 'in_0' },
    { source: 'B', target: 'C', kind: 'flow' },
  ]
  return { nodes, edges }
}

describe('pasteSelection（方案 §3.5：多选复制粘贴，纯函数）', () => {
  it('新 id 来自注入的 nextId 生成器（按节点类型调用，顺序一致）', () => {
    const calls: string[] = []
    const r = pasteSelection(snap(), (type) => {
      calls.push(type)
      return `nd_${calls.length}`
    })
    expect(calls).toEqual(['ds', 'sql'])
    expect(r.nodes.map((n) => n.id)).toEqual(['nd_1', 'nd_2'])
  })

  it('offset 默认 24：位置整体偏移', () => {
    const r = pasteSelection(snap(), () => 'x')
    expect(r.nodes.map((n) => n.position)).toEqual([{ x: 34, y: 44 }, { x: 134, y: 44 }])
  })

  it('offset 注入生效：0 = 原位复制、100 = 大偏移', () => {
    const r0 = pasteSelection(snap(), () => 'x', 0)
    expect(r0.nodes.map((n) => n.position)).toEqual([{ x: 10, y: 20 }, { x: 110, y: 20 }])
    const r100 = pasteSelection(snap(), () => 'x', 100)
    expect(r100.nodes[0]!.position).toEqual({ x: 110, y: 120 })
  })

  it('data structuredClone 深拷贝：改 pasted.data 不影响源快照（含嵌套对象）', () => {
    const s = snap()
    const r = pasteSelection(s, () => 'x')
    r.nodes[0]!.data.name = 'A2'
    r.nodes[0]!.data.cfg.deep = 99
    expect(s.nodes[0]!.data.name).toBe('A')
    expect(s.nodes[0]!.data.cfg.deep).toBe(1)
  })

  it('跨组件连线被丢弃，仅保留两端都在快照节点集内的内部边', () => {
    const r = pasteSelection(snap(), () => 'x')
    expect(r.edges).toHaveLength(1)
  })

  it('内部边端点按新节点 id 重映射，kind/label/handle 保留，id 由模块级序号生成', () => {
    const r = pasteSelection(snap(), (type) => `nd_${type}`)
    expect(r.edges[0]).toMatchObject({
      id: expect.stringMatching(/^e_paste_/),
      source: 'nd_ds',
      target: 'nd_sql',
      kind: 'flow',
      label: 'ab',
      sourceHandle: 'out_1',
      targetHandle: 'in_0',
    })
  })

  it('多次调用边 id 唯一（模块级序号递增，Date.now 同毫秒也不撞）', () => {
    const r1 = pasteSelection(snap(), () => 'x')
    const r2 = pasteSelection(snap(), () => 'x')
    const ids = [...r1.edges, ...r2.edges].map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
    ids.forEach((id) => expect(id).toMatch(/^e_paste_/))
  })

  it('纯度：粘贴不改源快照 position', () => {
    const s = snap()
    pasteSelection(s, () => 'x')
    expect(s.nodes[0]!.position).toEqual({ x: 10, y: 20 })
  })
})
