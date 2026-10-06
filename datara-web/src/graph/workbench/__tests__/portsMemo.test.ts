/**
 * Task 12（方案§3.6）ports memo 单元测试。
 * memoPorts：按 schemaId + data JSON 摘要作键缓存端口工厂结果，
 * 避免 Inspector 编辑等 data 引用换新但深相等场景重复构建端口数组（拖拽帧不经过此路径）。
 */
import { describe, it, expect, vi } from 'vitest'
import { memoPorts } from '../portsMemo'

describe('memoPorts（方案§3.6 惰性求值）', () => {
  it('相同 schemaId+data 摘要不重算，data 变化才重算', () => {
    const factory = vi.fn(() => [{ id: 'out', label: 'O' }])
    const m = memoPorts(factory)
    const data = { name: 'a' }
    m('s1', data)
    m('s1', data) // 同一对象引用 → 命中
    expect(factory).toHaveBeenCalledTimes(1)
    m('s1', { name: 'b' }) // data 变化 → 重算
    expect(factory).toHaveBeenCalledTimes(2)
  })

  it('深相等但不同引用的 data 命中缓存（键为 JSON 摘要而非引用）', () => {
    const factory = vi.fn(() => [{ id: 'out', label: 'O' }])
    const m = memoPorts(factory)
    m('s1', { name: 'a', cfg: { k: 1 } })
    m('s1', { name: 'a', cfg: { k: 1 } }) // 新对象、内容深相等
    expect(factory).toHaveBeenCalledTimes(1)
  })

  it('不同 schemaId 即使 data 相同也重算（键含 schemaId，避免串桶）', () => {
    const factory = vi.fn(() => [{ id: 'out', label: 'O' }])
    const m = memoPorts(factory)
    const data = { name: 'a' }
    m('s1', data)
    m('s2', data)
    expect(factory).toHaveBeenCalledTimes(2)
  })

  it('工厂返回 undefined 也命中缓存（has 判据：不因 get 结果为 undefined 误判未命中）', () => {
    const factory = vi.fn(() => undefined)
    const m = memoPorts(factory)
    const data = { name: 'a' }
    expect(m('s1', data)).toBeUndefined()
    m('s1', data) // 缓存值本身就是 undefined，也应命中而非重算
    expect(factory).toHaveBeenCalledTimes(1)
  })

  it('缓存有界：达到容量上限（64）后清空重建，不无限增长', () => {
    const factory = vi.fn((_: string, data: Record<string, unknown>) => [{ id: String(data.i), label: 'O' }])
    const m = memoPorts(factory)
    for (let i = 0; i < 64; i++) m('s1', { i })
    expect(factory).toHaveBeenCalledTimes(64)
    m('s1', { i: 64 }) // 第 65 个新键触发清空
    m('s1', { i: 0 }) // 旧键已随清空丢弃 → 重算
    expect(factory).toHaveBeenCalledTimes(66)
  })
})
