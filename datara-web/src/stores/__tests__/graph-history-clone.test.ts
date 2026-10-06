/**
 * Task 12（方案§3.6）undo 栈克隆化（双轨设计）单元测试。
 * 双轨：JSON.stringify 快照串仅作幂等对比基线（lastSnap），栈内改存深拷贝对象，
 * undo/redo 不再 JSON.parse。不变量：lastDoc ≡ lastSnap 时刻的深拷贝。
 * 旧实现栈存快照字符串（string[]），「栈条目为对象」用例在旧实现下失败（区分新旧）。
 * save 用 vi.mock 桩掉（不触网；load/save 全链路由 graphService.test.ts 覆盖）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGraphStore } from '../graph'
import type { GraphDocument } from '../../graph/model'

vi.mock('../../services', () => ({
  graphService: {
    get: vi.fn(async () => null),
    save: vi.fn(async () => ({ version: 2 })),
  },
}))

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

describe('Task 12（§3.6）undo 栈克隆化（双轨设计）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('栈条目为深拷贝对象而非快照字符串（旧实现存 string，此断言区分新旧实现）', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    s.doc!.nodes[0]!.data.name = '改名'
    s.markDirty()
    expect(s.undoStack.length).toBe(1)
    expect(s.undoStack[0]).toBeTypeOf('object')
    expect(s.undoStack[0]).not.toBeNull()
  })

  it('undo 返回的 doc 为独立深拷贝（就地修改不影响 redo 链）', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    s.doc!.nodes[0]!.data.name = '改名'
    s.markDirty()
    expect(s.undo()).toBe(true)
    expect(s.doc!.nodes[0]!.data.name).toBe('节点0')
    /* 撤销态上继续就地编辑，不应污染 redo 链 */
    s.doc!.nodes[0]!.data.name = '撤销后又改'
    expect(s.canRedo).toBe(true)
    expect(s.redo()).toBe(true)
    expect(s.doc!.nodes[0]!.data.name).toBe('改名')
  })

  it('undo 后就地编辑再 markDirty，二次 undo 回到上一历史态（防 doc 与基线克隆别名）', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    s.doc!.nodes[0]!.data.name = '改名1'
    s.markDirty()
    s.doc!.nodes[0]!.data.name = '改名2'
    s.markDirty()
    expect(s.undo()).toBe(true) // 回到「改名1」
    expect(s.doc!.nodes[0]!.data.name).toBe('改名1')
    s.doc!.nodes[0]!.data.name = '改名1又改' // 撤销态上继续就地编辑
    s.markDirty()
    expect(s.undo()).toBe(true) // 应回到「改名1」，而非停留在当前态
    expect(s.doc!.nodes[0]!.data.name).toBe('改名1')
  })

  it('markDirty 幂等（内容未变）不入栈、不清 redo', () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    s.doc!.nodes[0]!.data.name = '改名'
    s.markDirty()
    expect(s.undo()).toBe(true)
    expect(s.canRedo).toBe(true)
    s.markDirty() // 内容相对当前基线未变 → 幂等，不清 redo
    expect(s.canRedo).toBe(true)
    expect(s.redo()).toBe(true)
    expect(s.doc!.nodes[0]!.data.name).toBe('改名')
  })

  it('save 刷新基线后 markDirty 不把保存前状态重复入栈', async () => {
    const s = useGraphStore()
    s.setDoc(docOf('v0', 1))
    s.doc!.nodes[0]!.data.name = '改名'
    s.markDirty()
    expect(s.undoStack.length).toBe(1)
    await s.save()
    expect(s.dirty).toBe(false)
    s.markDirty() // 内容相对保存基线未变 → 幂等不入栈
    expect(s.undoStack.length).toBe(1)
  })
})
