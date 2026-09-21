/**
 * F56b N14 撤销/重做历史栈（stores/graph）单元测试。
 * 覆盖：markDirty 快照推进 / 幂等不入栈 / replace 入栈 / undo·redo 换档 /
 * 容量裁剪（上限 50）/ 栈底返回 false 与 dirty 置位。
 * 不触网：文档经 setDoc 注入（save/load 由 graphService.test.ts 覆盖）。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGraphStore } from '../graph'
import type { GraphDocument } from '../../graph/model'

function docOf(name: string, nodes: number): GraphDocument {
  return {
    id: 'wf_test',
    name,
    version: 1,
    meta: { profile: 'dag' },
    nodes: Array.from({ length: nodes }, (_, i) => ({
      id: `n${i}`,
      type: 'task',
      position: { x: i * 100, y: 0 },
      data: { name: `节点${i}` },
    })),
    edges: [],
  }
}

describe('F56b N14 图文档历史栈（撤销/重做）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('markDirty 推进基线：连续两次变更可撤销回上一步', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    expect(s.canUndo).toBe(false)
    s.doc!.nodes[0]!.data.name = '改名'
    s.markDirty()
    expect(s.canUndo).toBe(true)
    s.doc!.nodes.push({ id: 'n1', type: 'task', position: { x: 0, y: 50 }, data: { name: '新节点' } })
    s.markDirty()
    expect(s.undo()).toBe(true)
    expect(s.doc!.nodes).toHaveLength(1) // 回到「改名」态
    expect(s.doc!.nodes[0]!.data.name).toBe('改名')
    expect(s.canRedo).toBe(true)
    expect(s.redo()).toBe(true)
    expect(s.doc!.nodes).toHaveLength(2)
  })

  it('幂等 markDirty（内容未变）不入栈', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    s.markDirty()
    expect(s.undoStack.length).toBe(0)
  })

  it('replace（自动布局）入栈一次，可撤销回替换前', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 2))
    const laid = docOf('v0', 2)
    laid.nodes.forEach((n, i) => { n.position = { x: 0, y: i * 120 } })
    s.replace(laid)
    expect(s.undo()).toBe(true)
    expect(s.doc!.nodes[0]!.position).toEqual({ x: 0, y: 0 })
  })

  it('历史栈容量裁剪（上限 50）：最早快照被丢弃', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    for (let i = 0; i < 60; i++) {
      s.doc!.nodes[0]!.data.count = i
      s.markDirty()
    }
    expect(s.undoStack.length).toBeLessThanOrEqual(50)
    let n = 0
    while (s.undo()) n++
    expect(n).toBe(50)
    expect(s.canUndo).toBe(false)
  })

  it('undo 到栈底返回 false；撤销后 dirty 置位', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    expect(s.undo()).toBe(false)
    s.doc!.nodes[0]!.data.name = 'x'
    s.markDirty()
    expect(s.undo()).toBe(true)
    expect(s.dirty).toBe(true)
    expect(s.undo()).toBe(false)
  })
})
