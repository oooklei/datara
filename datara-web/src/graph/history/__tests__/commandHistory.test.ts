/**
 * Task 22（2e）undo 命令栈（commandHistory + captureCommand）单元测试。
 * 覆盖：push/undo/redo 对偶与让位（undo→redo 栈、redo→undo 栈）/ push 清空 redo /
 * 容量裁剪（上限 50，与快照栈对齐）/ reset 双栈清空 / 空栈 undo·redo 返回 null /
 * captureCommand 捕获真实前后档且快照深拷贝隔离（改输入与 apply 结果均不污染栈内档）。
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCommandHistory } from '../commandHistory'
import { captureCommand } from '../commands'
import type { GraphDocument } from '../../model'

function docOf(name: string): GraphDocument {
  return {
    id: 'wf_test',
    name: 't',
    version: 1,
    meta: { profile: 'dag' },
    nodes: [{ id: 'n1', type: 'task', position: { x: 0, y: 0 }, data: { name } }],
    edges: [],
  }
}

describe('Task 22 undo 命令栈（commandHistory）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('push/undo/redo 对偶：undo 返回前档、redo 返回后档', () => {
    const h = useCommandHistory()
    const before = docOf('before')
    const after = docOf('after')
    h.push(captureCommand('update-props', before, after))
    expect(h.canUndo).toBe(true)
    expect(h.canRedo).toBe(false)
    expect(h.undo(after)).toEqual(before)
    expect(h.canRedo).toBe(true)
    expect(h.redo(before)).toEqual(after)
    expect(h.canUndo).toBe(true)
    expect(h.canRedo).toBe(false)
  })

  it('push 清空 redo（与快照栈语义一致）', () => {
    const h = useCommandHistory()
    const a = docOf('a')
    h.push(captureCommand('update-props', a, docOf('b')))
    h.undo(a)
    expect(h.canRedo).toBe(true)
    h.push(captureCommand('update-props', a, docOf('c')))
    expect(h.canRedo).toBe(false)
    expect(h.redo(a)).toBeNull()
  })

  it('容量裁剪（cap 50）：最旧命令被挤出，恰好可撤销 50 次', () => {
    const h = useCommandHistory()
    const before = docOf('before')
    for (let i = 0; i < 60; i++) {
      h.push(captureCommand('update-props', before, docOf(`after-${i}`)))
    }
    expect(h.undoStack.length).toBe(50)
    let n = 0
    while (h.undo(before) !== null) n++
    expect(n).toBe(50)
    expect(h.canUndo).toBe(false)
  })

  it('reset 双栈清空（换档点宿主调用后历史失配不串档）', () => {
    const h = useCommandHistory()
    h.push(captureCommand('update-props', docOf('a'), docOf('b')))
    h.reset()
    expect(h.canUndo).toBe(false)
    expect(h.canRedo).toBe(false)
    expect(h.undo(docOf('x'))).toBeNull()
  })

  it('空栈 undo/redo 返回 null', () => {
    const h = useCommandHistory()
    const d = docOf('d')
    expect(h.undo(d)).toBeNull()
    expect(h.redo(d)).toBeNull()
  })

  it('captureCommand 快照深拷贝隔离：改输入与 apply 结果均不污染栈内档', () => {
    const h = useCommandHistory()
    const before = docOf('before')
    const after = docOf('after')
    after.nodes[0]!.position = { x: 9, y: 9 }
    const cmd = captureCommand('move-nodes', before, after)
    // 捕获后改输入 doc：命令内部快照不受影响
    after.nodes[0]!.position = { x: 77, y: 77 }
    const applied = cmd.apply(before)
    expect(applied.nodes[0]!.position).toEqual({ x: 9, y: 9 })
    // apply 结果为深拷贝：改它不影响后续 apply/undo
    applied.nodes[0]!.position = { x: 88, y: 88 }
    expect(cmd.apply(before).nodes[0]!.position).toEqual({ x: 9, y: 9 })
    h.push(cmd)
    expect(h.undo(applied)).toEqual(before)
  })
})
