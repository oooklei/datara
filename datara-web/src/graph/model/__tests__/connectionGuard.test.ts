/**
 * 连线四道闸测试（工作台优化 Task 8，方案 §3.1）
 * 覆盖：四道闸各 1 例 + 放行 null + portTypes 缺省跳过类型道 + sourceHandle 参与重复判定
 * + checkCycle 开关 + 闸序守卫（自连优先于后续道）。
 * GraphDocument 构造对齐 topo.test.ts 惯例。
 */
import { describe, it, expect } from 'vitest'
import type { GraphDocument, GEdge } from '../index'
import { connectionRejectReason } from '../connectionGuard'

function docOf(edges: Partial<GEdge>[]): GraphDocument {
  return {
    id: 't',
    name: 'test',
    version: 1,
    meta: { profile: 'dag' },
    nodes: ['a', 'b', 'c'].map((id) => ({ id, type: 'task', position: { x: 0, y: 0 }, data: { name: id } })),
    edges: edges.map((e, i) => ({ id: `e${i}`, ...e })) as GEdge[],
  }
}

const conn = (over: { source: string; target: string; sourceHandle?: string }) => over

describe('connectionRejectReason（方案 §3.1 连线四道闸）', () => {
  it('① 自连拒绝', () => {
    expect(connectionRejectReason(docOf([]), conn({ source: 'a', target: 'a' }))).toBe('不允许自连')
  })

  it('② 重复边拒绝（同 source+target+sourceHandle）', () => {
    const g = docOf([{ source: 'a', target: 'b' }])
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }))).toBe('依赖边已存在')
  })

  it('③ 成环拒绝（detectCycle 预检：a→b 已存在，b→a 将闭环）', () => {
    const g = docOf([{ source: 'a', target: 'b' }])
    expect(connectionRejectReason(g, conn({ source: 'b', target: 'a' }))).toBe('该连接将形成环（DAG 不允许成环）')
  })

  it('④ 类型交集拒绝：portTypes 提供且 portTypesMatch 失败', () => {
    const g = docOf([])
    expect(
      connectionRejectReason(g, conn({ source: 'a', target: 'b' }), { src: 'table', dst: 'stream' }),
    ).toBe('类型不匹配：源 table → 目标 stream')
  })

  it('放行：全新连线四道闸全过返回 null', () => {
    const g = docOf([{ source: 'a', target: 'b' }])
    expect(connectionRejectReason(g, conn({ source: 'b', target: 'c' }))).toBeNull()
  })

  it('portTypes 缺省时跳过类型道（不判类型直接放行）', () => {
    const g = docOf([])
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }))).toBeNull()
    /* 显式缺省类型（undefined = any）同样放行——handle 匹配不到/未声明类型不误拦 */
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }), {})).toBeNull()
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }), { src: 'table' })).toBeNull()
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }), { dst: 'stream' })).toBeNull()
    /* 类型匹配放行 */
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }), { src: 'table', dst: 'dataset' })).toBeNull()
  })

  it('sourceHandle 参与重复判定：同对节点不同 handle 不算重复', () => {
    const g = docOf([{ source: 'a', target: 'b', sourceHandle: 'br1' }])
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b', sourceHandle: 'br2' }))).toBeNull()
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b', sourceHandle: 'br1' }))).toBe('依赖边已存在')
    /* 缺省 handle 与显式空等价；与具名 handle 互不算重复 */
    expect(connectionRejectReason(g, conn({ source: 'a', target: 'b' }))).toBeNull()
    const g2 = docOf([{ source: 'a', target: 'b' }])
    expect(connectionRejectReason(g2, conn({ source: 'a', target: 'b' }))).toBe('依赖边已存在')
  })

  it('checkCycle=false 跳过成环道（非 DAG 布局视角旧行为）', () => {
    const g = docOf([{ source: 'a', target: 'b' }])
    expect(connectionRejectReason(g, conn({ source: 'b', target: 'a' }), undefined, { checkCycle: false })).toBeNull()
  })

  it('闸序守卫：自连优先于重复边/成环/类型道', () => {
    const g = docOf([{ source: 'a', target: 'b' }])
    expect(
      connectionRejectReason(g, conn({ source: 'a', target: 'a' }), { src: 'table', dst: 'stream' }),
    ).toBe('不允许自连')
  })
})
