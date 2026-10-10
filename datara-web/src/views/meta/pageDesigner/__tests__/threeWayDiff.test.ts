/**
 * Task 23（§2.4/§8.2）保存 409 三方逐项 diff 纯函数（threeWayDiff）单元测试。
 * 覆盖：展开粒度（顶层键 / 数组逐下标 / 对象逐子键）/ mine=remote 项跳过 /
 * 单侧独有键展开与默认采纳 / 默认 adopt（单侧改动取改动侧、双侧改动取远端）/
 * mergeThreeWay 按 decisions 合并、深拷贝隔离、decisions 覆盖默认 / getDiffValue 三种 path 形态。
 */
import { describe, expect, it } from 'vitest'
import { threeWayDiffItems, mergeThreeWay, getDiffValue, type DiffSide } from '../threeWayDiff'

describe('threeWayDiffItems 展开', () => {
  it('顶层标量：仅差异项出现，默认采纳单侧改动侧', () => {
    const base = { a: 1, b: 'x' }
    const mine = { a: 2, b: 'x' } // 本地改 a
    const remote = { a: 1, b: 'y' } // 远端改 b
    const items = threeWayDiffItems(mine, remote, base)
    expect(items.map((i) => i.path).sort()).toEqual(['a', 'b'])
    expect(items.find((i) => i.path === 'a')).toMatchObject({
      mine: 2, remote: 1, base: 1, mineChanged: true, remoteChanged: false, adopt: 'mine',
    })
    expect(items.find((i) => i.path === 'b')).toMatchObject({
      mine: 'x', remote: 'y', base: 'x', mineChanged: false, remoteChanged: true, adopt: 'remote',
    })
  })

  it('mine=remote 项跳过；单侧独有键也展开（默认采纳持有侧）', () => {
    const items = threeWayDiffItems({ a: 1, extra: 'm' }, { a: 1 }, { a: 1 })
    expect(items.map((i) => i.path)).toEqual(['extra'])
    expect(items[0]).toMatchObject({ mine: 'm', remote: undefined, base: undefined, mineChanged: true, remoteChanged: false, adopt: 'mine' })
  })

  it('顶层数组 → 逐下标（fields 模式逐行）；对象子键 → 逐子键', () => {
    const base = { fields: [{ id: 'f1' }, { id: 'f2' }], form: { p1: 'a', p2: 'b' } }
    const mine = { fields: [{ id: 'f1' }, { id: 'f2x' }], form: { p1: 'a2', p2: 'b' } }
    const remote = { fields: [{ id: 'f1' }, { id: 'f2' }, { id: 'f3' }], form: { p1: 'a', p2: 'b2' } }
    const items = threeWayDiffItems(mine, remote, base)
    const byPath = new Map(items.map((i) => [i.path, i]))
    expect([...byPath.keys()].sort()).toEqual(['fields.1', 'fields.2', 'form.p1', 'form.p2'])
    // fields.1：本地改、远端未改 → 采纳本地；fields.2：远端新增下标 → 采纳远端
    expect(byPath.get('fields.1')).toMatchObject({ mine: { id: 'f2x' }, remote: { id: 'f2' }, adopt: 'mine' })
    expect(byPath.get('fields.2')).toMatchObject({ mine: undefined, remote: { id: 'f3' }, base: undefined, adopt: 'remote' })
    expect(byPath.get('form.p1')!.adopt).toBe('mine')
    expect(byPath.get('form.p2')!.adopt).toBe('remote')
  })

  it('嵌套一层的对象子键不再递归展开（仅一层，条目数可控）：整值单项呈现', () => {
    const base = { page: { widgets: [{ id: 'w1' }] } }
    const mine = { page: { widgets: [{ id: 'w1' }] } }
    const remote = { page: { widgets: [{ id: 'w1' }, { id: 'w2' }] } }
    const items = threeWayDiffItems(mine, remote, base)
    expect(items.map((i) => i.path)).toEqual(['page.widgets'])
    expect(items[0]).toMatchObject({ mine: [{ id: 'w1' }], remote: [{ id: 'w1' }, { id: 'w2' }], base: [{ id: 'w1' }], mineChanged: false, remoteChanged: true, adopt: 'remote' })
    expect(mergeThreeWay(mine, items, {})).toEqual(remote)
  })

  it('默认采纳：双侧均改 → 远端（服务器最新，可改选）', () => {
    const items = threeWayDiffItems({ k: 'm' }, { k: 'r' }, { k: 'b' })
    expect(items[0]).toMatchObject({ mineChanged: true, remoteChanged: true, adopt: 'remote' })
  })
})

describe('mergeThreeWay 合并', () => {
  it('按逐项默认决策合并：mine 为骨架，采纳项写入远端值', () => {
    const mine = { a: 1, form: { p1: 'a2', p2: 'b' } }
    const remote = { a: 9, form: { p1: 'a', p2: 'b2' } }
    const base = { a: 1, form: { p1: 'a', p2: 'b' } }
    const items = threeWayDiffItems(mine, remote, base)
    const decisions: Record<string, DiffSide> = {}
    for (const it of items) decisions[it.path] = it.adopt
    const merged = mergeThreeWay(mine, items, decisions)
    // a：本地未改远端改 → 采纳远端；form.p1：本地改 → 保持本地；form.p2：远端改 → 采纳远端
    expect(merged).toEqual({ a: 9, form: { p1: 'a2', p2: 'b2' } })
  })

  it('采纳远端值为深拷贝：改合并结果不影响 item.remote', () => {
    const mine = { cfg: { deep: [] as number[] } }
    const remote = { cfg: { deep: [1, 2] } }
    const items = threeWayDiffItems(mine, remote, { cfg: { deep: [] } })
    const merged = mergeThreeWay(mine, items, {})
    expect(merged.cfg).toEqual({ deep: [1, 2] })
    ;(merged.cfg as { deep: number[] }).deep.push(3)
    expect(items[0]!.remote).toEqual([1, 2])
  })

  it('decisions 可覆盖默认采纳方向', () => {
    const mine = { k: 'm' }
    const remote = { k: 'r' }
    const items = threeWayDiffItems(mine, remote, { k: 'b' })
    expect(mergeThreeWay(mine, items, { k: 'mine' }).k).toBe('m')
    expect(mergeThreeWay(mine, items, { k: 'remote' }).k).toBe('r')
  })

  it('mine 为 null（无本地档）时以空对象为骨架合并', () => {
    const items = threeWayDiffItems(null, { k: 'r' }, null)
    expect(items[0]!.adopt).toBe('remote')
    expect(mergeThreeWay(null, items, {})).toEqual({ k: 'r' })
  })
})

describe('getDiffValue', () => {
  it('读取 k / k.i / k.sub 三种形态；越界/缺失/null 档返回 undefined', () => {
    const spec = { a: 1, arr: ['x', 'y'], obj: { s: 3 } }
    expect(getDiffValue(spec, 'a')).toBe(1)
    expect(getDiffValue(spec, 'arr.1')).toBe('y')
    expect(getDiffValue(spec, 'obj.s')).toBe(3)
    expect(getDiffValue(spec, 'arr.9')).toBeUndefined()
    expect(getDiffValue(spec, 'nope')).toBeUndefined()
    expect(getDiffValue(null, 'a')).toBeUndefined()
  })
})
