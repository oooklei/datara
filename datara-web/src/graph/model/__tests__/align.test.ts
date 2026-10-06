import { describe, it, expect } from 'vitest'
import { alignNodes, distributeNodes, type AlignNode } from '../align'

/** 构造水平坐标序列 → 最小 AlignNode[]（y 固定 0） */
function mkX(xs: number[]): AlignNode[] {
  return xs.map((x, i) => ({ id: `n${i}`, position: { x, y: 0 } }))
}

/** 构造垂直坐标序列 → 最小 AlignNode[]（x 固定 0） */
function mkY(ys: number[]): AlignNode[] {
  return ys.map((y, i) => ({ id: `n${i}`, position: { x: 0, y } }))
}

describe('alignNodes（方案 §3.5：以选集包围盒为基准的标准编辑器对齐，纯函数）', () => {
  it('left：x 归到选集最小 x（宽度回调缺省不影响 left）', () => {
    const r = alignNodes(mkX([100, 50, 75]), 'left')
    expect(r.map((n) => n.position.x)).toEqual([50, 50, 50])
  })

  it('right：右边界对齐 max(x+w)，注入宽度回调 ()=>40 → max 右边界 140，x=140-40=100', () => {
    const r = alignNodes(mkX([100, 50]), 'right', () => 40)
    expect(r.map((n) => n.position.x)).toEqual([100, 100])
  })

  it('right 无宽度回调：尺寸按 0，退化为 x = max(x)', () => {
    const r = alignNodes(mkX([100, 50]), 'right')
    expect(r.map((n) => n.position.x)).toEqual([100, 100])
  })

  it('hcenter：注入宽度 ()=>40，包围盒 [min 50, max 右边界 140] 中心 95 → x = 95-20 = 75', () => {
    // 注：授权草稿 "(100+140)/2=120 → [100,100]" 误用 max x 作包围盒左界，与其自身公式
    // (min(x_i)+max(x_i+w_i))/2 - w/2 矛盾；按公式与同块 vcenter 用例 (50+140)/2 口径修正为 75
    const r = alignNodes(mkX([100, 50]), 'hcenter', () => 40)
    expect(r.map((n) => n.position.x)).toEqual([75, 75])
  })

  it('hcenter 区分度用例：注入宽度 ()=>40，mkX([100,200]) → 包围盒 [100,240] 中心 170 → x = 150', () => {
    const r = alignNodes(mkX([100, 200]), 'hcenter', () => 40)
    expect(r.map((n) => n.position.x)).toEqual([150, 150])
  })

  it('hcenter 无宽度回调：中心 = (100+50)/2 = 75', () => {
    const r = alignNodes(mkX([100, 50]), 'hcenter')
    expect(r.map((n) => n.position.x)).toEqual([75, 75])
  })

  it('top：y 归到选集最小 y', () => {
    const r = alignNodes(mkY([100, 50, 75]), 'top')
    expect(r.map((n) => n.position.y)).toEqual([50, 50, 50])
  })

  it('bottom：下边界对齐 max(y+h)，注入高度回调 ()=>40 → max 下边界 140，y=140-40=100', () => {
    const r = alignNodes(mkY([100, 50, 75]), 'bottom', undefined, () => 40)
    expect(r.map((n) => n.position.y)).toEqual([100, 100, 100])
  })

  it('vcenter：包围盒垂直中心 (50+140)/2=95 → y = 95-20 = 75', () => {
    const r = alignNodes(mkY([100, 50]), 'vcenter', undefined, () => 40)
    expect(r.map((n) => n.position.y)).toEqual([75, 75])
  })

  it('纯度：不改传入数组，返回同序新数组与新节点对象，泛型额外字段保留', () => {
    const src = [{ id: 'a', position: { x: 30, y: 40 }, type: 'ds', lane: 'L1' }]
    const r = alignNodes(src, 'left')
    expect(src[0]!.position).toEqual({ x: 30, y: 40 }) // 原对象 position 未动
    expect(r).not.toBe(src)
    expect(r[0]).not.toBe(src[0])
    expect(r.map((n) => n.id)).toEqual(['a'])
    expect(r[0]!.type).toBe('ds')
    expect(r[0]!.lane).toBe('L1')
  })

  it('空数组安全返回空数组', () => {
    expect(alignNodes([], 'left')).toEqual([])
  })
})

describe('distributeNodes（方案 §3.5：排序后相邻等间隙 gap=(last-first-Σsize)/(n-1)，纯函数）', () => {
  it('h + 宽度回调 ()=>10：[0,10,60] → [0,25,50]（gap=(60-0-30)/2=15）', () => {
    const r = distributeNodes(mkX([0, 10, 60]), 'h', () => 10)
    expect(r.map((n) => n.position.x)).toEqual([0, 25, 50])
  })

  it('h 无宽度回调：尺寸按 0 → 等距 [0,30,60]', () => {
    const r = distributeNodes(mkX([0, 10, 60]), 'h')
    expect(r.map((n) => n.position.x)).toEqual([0, 30, 60])
  })

  it('v + 高度回调 ()=>10：y [0,10,60] → [0,25,50]', () => {
    const r = distributeNodes(mkY([0, 10, 60]), 'v', undefined, () => 10)
    expect(r.map((n) => n.position.y)).toEqual([0, 25, 50])
  })

  it('少于 3 个：原样返回传入数组引用（2/1/0 个）', () => {
    const a2 = mkX([0, 10])
    const a1 = mkX([5])
    const a0: AlignNode[] = []
    expect(distributeNodes(a2, 'h', () => 10)).toBe(a2)
    expect(distributeNodes(a1, 'h', () => 10)).toBe(a1)
    expect(distributeNodes(a0, 'h', () => 10)).toBe(a0)
  })

  it('纯度：调用后原数组 position 不变', () => {
    const src = mkX([0, 10, 60])
    distributeNodes(src, 'h', () => 10)
    expect(src.map((n) => n.position.x)).toEqual([0, 10, 60])
  })

  it('返回数组与入参同序（乱序入参按原顺序回填，位置按排序秩计算）', () => {
    const src = mkX([60, 0, 10]) // 原顺序 n0=60, n1=0, n2=10；排序秩 n1→0, n2→25, n0→50
    const r = distributeNodes(src, 'h', () => 10)
    expect(r.map((n) => n.id)).toEqual(['n0', 'n1', 'n2'])
    expect(r.map((n) => n.position.x)).toEqual([50, 0, 25])
  })
})
