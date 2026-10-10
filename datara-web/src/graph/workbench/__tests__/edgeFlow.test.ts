/**
 * Task 18（§5.1）边流动动画（flowingEdgeIds 纯函数）单元测试。
 * 流动条件：两端节点运行态均在 {executing, executed}（数据流向 source→target）；
 * nodeStates 支持 Record<string,string> 与 Record<string,{state}> 两种形态；
 * 缺态 / 他态（idle/cached/error 等）不流动；EDGE_FLOWING_CLASS 类名钉死（theme.css 关键帧契约）。
 */
import { describe, expect, it } from 'vitest'
import { flowingEdgeIds, EDGE_FLOWING_CLASS } from '../syncFromDoc'

const edges = [
  { id: 'e1', source: 'a', target: 'b' },
  { id: 'e2', source: 'b', target: 'c' },
  { id: 'e3', source: 'c', target: 'd' },
]

describe('Task 18 边流动动画（flowingEdgeIds）', () => {
  it('EDGE_FLOWING_CLASS 值钉死（theme.css 动画类名契约）', () => {
    expect(EDGE_FLOWING_CLASS).toBe('edge-flowing')
  })

  it('{state} 形态：两端 executing/executed 才流动', () => {
    const flowing = flowingEdgeIds(edges, {
      a: { state: 'executing' },
      b: { state: 'executed' },
      c: { state: 'idle' },
      d: { state: 'idle' },
    })
    expect(flowing).toEqual(new Set(['e1']))
  })

  it('string 形态：连续运行段整段流动', () => {
    const flowing = flowingEdgeIds(edges, { a: 'executing', b: 'executing', c: 'executing', d: 'executed' })
    expect(flowing).toEqual(new Set(['e1', 'e2', 'e3']))
  })

  it('任一端为非运行态（cached/error）→ 不流动', () => {
    expect(flowingEdgeIds(edges, { a: { state: 'executing' }, b: { state: 'cached' } }).has('e1')).toBe(false)
    expect(flowingEdgeIds(edges, { a: { state: 'executed' }, b: { state: 'error' } }).has('e1')).toBe(false)
  })

  it('端点缺态 → 不流动；空状态表返回空集', () => {
    expect(flowingEdgeIds(edges, { a: { state: 'executing' } }).has('e1')).toBe(false)
    expect(flowingEdgeIds(edges, {}).size).toBe(0)
  })
})
