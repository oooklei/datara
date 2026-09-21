/**
 * W0-4 图模型类型扩展测试：
 * - happy: field_dep 边 kind 可被 GEdge 接纳（M09 字段级血缘）
 * - failure: 未知 kind 字符串构造 GEdge 应被 tsc 拒绝（闭合联合）
 * - ImpactSubgraph 形状对齐 data.js impactExample
 */
import { describe, expect, it } from 'vitest'
import type { GEdge, GEdgeKind, ImpactSubgraph } from '../index'

describe('GEdgeKind 闭合联合', () => {
  it('field_dep 边 kind 可被 GEdge 接纳（M09 字段级血缘）', () => {
    const edge: GEdge = { id: 'e1', source: 'ods_gdb_biz_trade_order.amount', target: 'dwd_order_pay_detail.pay_amount', kind: 'field_dep' }
    expect(edge.kind).toBe('field_dep')
  })

  it('未知 kind 字符串应被 tsc 拒绝（闭合联合）', () => {
    // @ts-expect-error - 'bogus_kind' 不在 GEdgeKind 闭合联合中
    const bad: GEdge = { id: 'e2', source: 'a', target: 'b', kind: 'bogus_kind' }
    expect(bad).toBeDefined()
  })

  it('GEdgeKind 联合包含 field_dep 与既有全集成员', () => {
    const kinds: GEdgeKind[] = ['flow', 'branch_true', 'dep', 'lag', 'dep_unlinked', 'field_dep', 'produce', 'refer', 'rel_1n', 'bind_pass', 'bind_fail']
    expect(kinds).toContain('field_dep')
    expect(kinds).toContain('bind_fail')
  })
})

describe('ImpactSubgraph 影响分析子图（M09）', () => {
  it('形状对齐 data.js impactExample（L420-426）', () => {
    const sub: ImpactSubgraph = {
      table: 'dwd_order_pay_detail',
      downTables: [{ name: 'dws_pay_summary_daily', task: 'ETL002' }],
      downTasks: [{ name: 'etl_dws_pay_summary', wf: 'WF-订单主题日增', type: 'SQL任务' }],
      downIndicators: [{ name: '近7天支付金额', code: 'METRIC_002' }],
      reports: ['经营日报'],
    }
    expect(sub.table).toBe('dwd_order_pay_detail')
    expect(sub.downTables[0].task).toBe('ETL002')
    expect(sub.downIndicators[0].code).toBe('METRIC_002')
  })
})