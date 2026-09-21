/**
 * lineageUtils 纯函数单测（todo 10）
 * 覆盖：分层推导、表级/字段级图构建（dep_unlinked 与元数据富化）、N 层上下游过滤、影响分析（精确/通用/叶子空态）。
 */
import { describe, it, expect } from 'vitest'
import {
  buildFieldLineageDoc,
  buildTableLineageDoc,
  deriveImpact,
  filterByDepth,
  impactSummary,
  layerOf,
} from '../mock/lineageUtils'
import type { FieldLineage, ImpactExample, MetaTable, TableLineage } from '../types'

const tableLineage: TableLineage[] = [
  { from: 'ods_gdb_biz_trade_order', to: 'dwd_order_pay_detail', task: 'etl_dwd_order_pay_clean (ETL001)', wf: 'WF-订单主题日增' },
  { from: 'dwd_order_pay_detail', to: 'dws_pay_summary_daily', task: 'etl_dws_pay_summary (ETL002)', wf: 'WF-订单主题日增' },
  { from: 'dws_pay_summary_daily', to: 'ads_kpi_report', task: 'etl_ads_kpi (ETL003)', wf: 'WF-经营KPI' },
  { from: 'ods_oracle_gl_voucher', to: 'dwd_gl_voucher_detail', task: 'etl_dwd_gl_voucher (ETL004)', wf: '未入工作流' },
]

const metaTables: MetaTable[] = [
  {
    id: 'T1', name: 'ods_gdb_biz_trade_order', layer: 'ODS', domain: '交易域', rows: 4100000,
    size: '1.2GB', owner: '王工', tags: ['核心'], yesterdayOk: true, desc: '', sample: [],
  },
  {
    id: 'T2', name: 'dwd_order_pay_detail', layer: 'DWD', domain: '交易域', rows: 3980000,
    size: '860MB', owner: '李工', tags: ['核心'], yesterdayOk: true, desc: '', sample: [],
  },
]

const fieldLineage: FieldLineage = {
  'dwd_order_pay_detail.pay_amount': [
    { from: 'ods_gdb_biz_trade_order.amount', transform: 'amount - discount' },
  ],
  'dws_pay_summary_daily.pay_amount_sum': [
    { from: 'dwd_order_pay_detail.pay_amount', transform: 'SUM(pay_amount)' },
  ],
}

const example: ImpactExample = {
  table: 'dwd_order_pay_detail',
  downTables: [{ name: 'dws_pay_summary_daily', task: 'ETL002' }],
  downTasks: [{ name: 'etl_dws_pay_summary', wf: 'WF-订单主题日增', type: 'SQL任务' }],
  downIndicators: [{ name: '近7天支付金额', code: 'METRIC_002' }],
  reports: ['经营日报'],
}

describe('layerOf', () => {
  it('按表名前缀推导分层', () => {
    expect(layerOf('ods_gdb_biz_user_info')).toBe('ODS')
    expect(layerOf('dim_user')).toBe('DIM')
    expect(layerOf('dwd_order_pay_detail')).toBe('DWD')
    expect(layerOf('dws_pay_summary_daily')).toBe('DWS')
    expect(layerOf('ads_kpi_report')).toBe('ADS')
  })

  it('字段名按表部分推导', () => {
    expect(layerOf('dwd_order_pay_detail.pay_amount')).toBe('DWD')
  })

  it('未知前缀兜底 ODS', () => {
    expect(layerOf('unknown_table')).toBe('ODS')
  })
})

describe('buildTableLineageDoc', () => {
  const doc = buildTableLineageDoc(tableLineage, metaTables)

  it('节点 = 边端点去重，类型按分层', () => {
    expect(doc.nodes).toHaveLength(6)
    expect(doc.nodes.find((n) => n.id === 'dwd_order_pay_detail')?.type).toBe('ln_dwd')
    expect(doc.nodes.find((n) => n.id === 'ads_kpi_report')?.type).toBe('ln_ads')
  })

  it('元数据富化：domain/rows/core 来自 metaTables', () => {
    const n = doc.nodes.find((x) => x.id === 'dwd_order_pay_detail')!
    expect(n.data.domain).toBe('交易域')
    expect(n.data.rows).toBe(3980000)
    expect(n.data.core).toBe(true)
  })

  it('未入工作流 → dep_unlinked 虚线边，其余 dep 且带任务标注', () => {
    const unlinked = doc.edges.find((e) => e.source === 'ods_oracle_gl_voucher')
    expect(unlinked?.kind).toBe('dep_unlinked')
    const linked = doc.edges.find((e) => e.source === 'ods_gdb_biz_trade_order')
    expect(linked?.kind).toBe('dep')
    expect(linked?.label).toBe('etl_dwd_order_pay_clean (ETL001)')
  })

  it('dagre LR 布局后节点坐标非全零', () => {
    expect(doc.nodes.some((n) => n.position.x !== 0 || n.position.y !== 0)).toBe(true)
  })
})

describe('buildFieldLineageDoc', () => {
  const doc = buildFieldLineageDoc(fieldLineage)

  it('节点 = 字段端点，边 kind=field_dep 且带转换表达式', () => {
    expect(doc.nodes).toHaveLength(3)
    expect(doc.edges).toHaveLength(2)
    expect(doc.edges[0].kind).toBe('field_dep')
    expect(doc.edges[0].label).toBe('amount - discount')
  })

  it('字段节点类型按表分层', () => {
    expect(doc.nodes.find((n) => n.id === 'dwd_order_pay_detail.pay_amount')?.type).toBe('ln_dwd')
  })
})

describe('filterByDepth', () => {
  const doc = buildTableLineageDoc(tableLineage, metaTables)

  it('下游 1 层：仅直接下游', () => {
    const out = filterByDepth(doc, 'dwd_order_pay_detail', 'down', 1)
    expect(out.nodes.map((n) => n.id).sort()).toEqual(['dwd_order_pay_detail', 'dws_pay_summary_daily'])
  })

  it('下游 2 层：含间接下游', () => {
    const out = filterByDepth(doc, 'dwd_order_pay_detail', 'down', 2)
    expect(out.nodes.map((n) => n.id).sort()).toEqual(['ads_kpi_report', 'dwd_order_pay_detail', 'dws_pay_summary_daily'])
  })

  it('上游 1 层：仅直接上游', () => {
    const out = filterByDepth(doc, 'dwd_order_pay_detail', 'up', 1)
    expect(out.nodes.map((n) => n.id).sort()).toEqual(['dwd_order_pay_detail', 'ods_gdb_biz_trade_order'])
  })

  it('叶子表下游为空（仅自身）', () => {
    const out = filterByDepth(doc, 'ads_kpi_report', 'down', 3)
    expect(out.nodes).toHaveLength(1)
    expect(out.edges).toHaveLength(0)
  })
})

describe('deriveImpact', () => {
  it('命中 impactExample 精确 shape', () => {
    const imp = deriveImpact('dwd_order_pay_detail', tableLineage, example)
    expect(imp.downTables[0].name).toBe('dws_pay_summary_daily')
    expect(imp.downIndicators[0].code).toBe('METRIC_002')
    expect(imp.reports).toContain('经营日报')
  })

  it('未命中时通用 BFS 推导下游表与任务', () => {
    const imp = deriveImpact('dws_pay_summary_daily', tableLineage, example)
    expect(imp.downTables.map((t) => t.name)).toEqual(['ads_kpi_report'])
    expect(imp.downTasks[0].name).toBe('etl_ads_kpi')
    expect(imp.downTasks[0].type).toBe('SQL任务')
  })

  it('叶子表无下游 → 空列表', () => {
    const imp = deriveImpact('ads_kpi_report', tableLineage, example)
    expect(imp.downTables).toHaveLength(0)
    expect(imp.downTasks).toHaveLength(0)
    expect(imp.downIndicators).toHaveLength(0)
  })
})

describe('impactSummary', () => {
  it('汇总计数', () => {
    const imp = deriveImpact('dwd_order_pay_detail', tableLineage, example)
    const s = impactSummary(imp)
    expect(s).toContain('1 张下游表')
    expect(s).toContain('1 个指标')
    expect(s).toContain('1 个报表')
  })

  it('空态文案', () => {
    const imp = deriveImpact('ads_kpi_report', tableLineage, example)
    expect(impactSummary(imp)).toBe('暂无血缘（该表无下游影响对象）')
  })
})