/**
 * lineageUtils 纯函数单测（todo 10）
 * 覆盖：分层推导、表级/字段级图构建（dep_unlinked 与元数据富化）、影响分析（精确/通用/叶子空态）、
 * Task 7 数据面富化（ds/tmp/wfs/sources）与一键聚焦边高亮（focusAllEdges）、
 * Task 8 实例追溯边标注（annotateStmtNo 升序去重 / 无命中不动 / 原文档不变）。
 */
import { describe, it, expect } from 'vitest'
import {
  annotateStmtNo,
  buildFieldLineageDoc,
  buildLineageGraphDoc,
  buildTableLineageDoc,
  deriveImpact,
  focusAllEdges,
  graphEdgesToRows,
  impactSummary,
  layerOf,
  matchCenter,
} from '../mock/lineageUtils'
import type { LineageGraphResult } from '../lineageApi'
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

  // 行为锚定（O(V+E) 重构不变量）：BFS 发现序 / 菱形首路径胜出 / 重复边忽略 /
  // 回环·自环安全 / 不可达子图排除 / 同名任务跨边去重 / task 取 split(' ')[0]。
  it('分支/菱形/重复边/回环下 BFS 发现序与字段取值', () => {
    const rows: TableLineage[] = [
      { from: 'a', to: 'b', task: 'etl_b (E1)', wf: 'W1' },
      { from: 'a', to: 'c', task: 'etl_c (E2)', wf: 'W1' },
      { from: 'b', to: 'd', task: 'etl_d (E3)', wf: 'W2' },
      { from: 'c', to: 'd', task: 'etl_d2 (E4)', wf: 'W3' },  // 菱形：d 已发现 → 跳过
      { from: 'a', to: 'b', task: 'etl_b2 (E9)', wf: 'W9' },  // 重复边：b 已发现 → 跳过
      { from: 'b', to: 'a', task: 'etl_a (EB)', wf: 'WB' },   // 回环：a 已 visited → 跳过
      { from: 'a', to: 'a', task: 'etl_self (EA)', wf: 'WA' },  // 自环：跳过
      { from: 'd', to: 'g', task: 'etl_c (E5)', wf: 'W5' },   // 任务名 etl_c 跨边复用 → downTasks 不新增
      { from: 'e', to: 'f', task: 'etl_f (EX)', wf: 'WX' },   // 不可达子图：不入结果
    ]
    const imp = deriveImpact('a', rows, null)
    expect(imp).toEqual({
      table: 'a',
      downTables: [
        { name: 'b', task: 'etl_b (E1)' },
        { name: 'c', task: 'etl_c (E2)' },
        { name: 'd', task: 'etl_d (E3)' },
        { name: 'g', task: 'etl_c (E5)' },
      ],
      downTasks: [
        { name: 'etl_b', wf: 'W1', type: 'SQL任务' },
        { name: 'etl_c', wf: 'W1', type: 'SQL任务' },
        { name: 'etl_d', wf: 'W2', type: 'SQL任务' },
      ],
      downIndicators: [],
      reports: [],
    })
  })

  it('重复同 (from,to) 行：首条任务名胜出（发现序即行序）', () => {
    const rows: TableLineage[] = [
      { from: 'a', to: 'b', task: 'etl_first (F1)', wf: 'WF1' },
      { from: 'a', to: 'b', task: 'etl_second (F2)', wf: 'WF2' },
    ]
    const imp = deriveImpact('a', rows, null)
    expect(imp.downTables).toEqual([{ name: 'b', task: 'etl_first (F1)' }])
    expect(imp.downTasks).toEqual([{ name: 'etl_first', wf: 'WF1', type: 'SQL任务' }])
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

/* ---------- Task 5：GET /lineage/graph 聚合结果 → 图文档（来源视觉体系） ---------- */

const graphRes: LineageGraphResult = {
  nodes: [
    { fq: 'ods_order', ds: '', table: 'ods_order', tmpFlag: 0, sources: ['runtime'], wfs: [101] },
    { fq: 'dwd_order_pay_detail', ds: '', table: 'dwd_order_pay_detail', tmpFlag: 0,
      sources: ['design', 'runtime'], wfs: [101, 102] },
    { fq: 'dim_user', ds: '', table: 'dim_user', tmpFlag: 0, sources: ['design'], wfs: [102] },
  ],
  // 契约：同 (from,to) 一条聚合边 —— ods→dwd 合并为单条双源边（refs 两条溯源）
  edges: [
    { from: 'ods_order', to: 'dwd_order_pay_detail', level: 'table',
      sources: ['design', 'runtime'],
      refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 0 }, { wfCode: 102, nodeId: 'n_sql_3', stmtNo: 1 }] },
    { from: 'ods_order', to: 'dim_user', level: 'table',
      sources: ['design'], refs: [{ wfCode: 102, nodeId: 'n_sql_2', stmtNo: 0 }] },
  ],
  opaques: [],
  truncated: false,
}

describe('buildLineageGraphDoc（Task 5 三态样式 + 未验证标记）', () => {
  it('双源聚边 → dep 实线 + label「（双源）」；仅 design → dep_design 虚线', () => {
    const doc = buildLineageGraphDoc(graphRes)
    // ods→dwd 单条双源聚边：dep 实线，label = refs 合成 + （双源）徽标
    const dual = doc.edges.find((e) => e.id === 'gle1')
    expect(dual).toBeTruthy()
    expect(dual!.kind).toBe('dep')
    expect(dual!.label).toBe('wf101·n_sql_1 / wf102·n_sql_3（双源）')
    // ods_order → dim_user（sources=design）虚线 dep_design
    const dg = doc.edges.find((e) => e.target === 'dim_user')
    expect(dg).toBeTruthy()
    expect(dg!.kind).toBe('dep_design')
    expect(dg!.label).toBe('wf102·n_sql_2')
  })

  it('runtime 独占 → dep 实线（无双源徽标）；双源 + 空 refs 徽标仍保留（M-3）', () => {
    const doc = buildLineageGraphDoc({
      nodes: [
        { fq: 'ods_order', ds: '', table: 'ods_order', tmpFlag: 0, sources: ['runtime'], wfs: [101] },
        { fq: 'ads_order_daily', ds: '', table: 'ads_order_daily', tmpFlag: 0, sources: ['runtime'], wfs: [101] },
      ],
      edges: [
        { from: 'ods_order', to: 'ads_order_daily', level: 'table',
          sources: ['runtime'], refs: [{ wfCode: 101, nodeId: 'n_sql_4', stmtNo: 0 }] },
        { from: 'ods_b', to: 'ads_b', level: 'table',
          sources: ['design', 'runtime'], refs: [] },
      ],
      opaques: [],
      truncated: false,
    })
    const rt = doc.edges.find((e) => e.kind === 'dep' && e.label === 'wf101·n_sql_4')
    expect(rt).toBeTruthy()
    // 双源 + 空 refs：base 空时徽标不丢（旧实现兜底「设计推导」会吞掉「（双源）」）
    const dualBare = doc.edges.find((e) => e.id === 'gle2')
    expect(dualBare!.kind).toBe('dep')
    expect(dualBare!.label).toBe('（双源）')
  })

  it('节点 sources 仅 design → data.unverified=true（「未验」角标输入）；双源/运行节点不标', () => {
    const doc = buildLineageGraphDoc(graphRes)
    const byId = Object.fromEntries(doc.nodes.map((n) => [n.id, n]))
    expect(byId['dim_user']!.data.unverified).toBe(true)
    expect(byId['ods_order']!.data.unverified).toBe(false)
    expect(byId['dwd_order_pay_detail']!.data.unverified).toBe(false)
  })

  it('Task 7 数据面富化：ds/tmp/wfs/sources 注入节点 data（tmpFlag=0 → tmp=false；空 ds 不落键）', () => {
    const doc = buildLineageGraphDoc({
      nodes: [
        { fq: 'mysql_biz.dwd_tmp_1', ds: 'mysql_biz', table: 'dwd_tmp_1', tmpFlag: 1,
          sources: ['runtime'], wfs: [201, 202] },
        { fq: 'mysql_biz.dwd_t2', ds: '', table: 'dwd_t2', tmpFlag: 0, sources: ['design'], wfs: [] },
      ],
      edges: [{
        from: 'mysql_biz.dwd_tmp_1', to: 'mysql_biz.dwd_t2', level: 'table',
        sources: ['runtime'], refs: [{ wfCode: 201, nodeId: 'n1', stmtNo: 0 }],
      }],
      opaques: [],
      truncated: false,
    })
    const byId = Object.fromEntries(doc.nodes.map((n) => [n.id, n]))
    expect(byId['mysql_biz.dwd_tmp_1']!.data.tmp).toBe(true)
    expect(byId['mysql_biz.dwd_tmp_1']!.data.ds).toBe('mysql_biz')
    expect(byId['mysql_biz.dwd_tmp_1']!.data.wfs).toEqual([201, 202])
    expect(byId['mysql_biz.dwd_tmp_1']!.data.sources).toEqual(['runtime'])
    expect(byId['mysql_biz.dwd_t2']!.data.tmp).toBe(false)
    expect(byId['mysql_biz.dwd_t2']!.data.ds).toBeUndefined()
    expect(byId['mysql_biz.dwd_t2']!.data.wfs).toEqual([])
  })

  it('lastCollected 透传到 node.data（graph 节点 → 图文档）；null 缺数据不落键', () => {
    const doc = buildLineageGraphDoc({
      nodes: [
        { fq: 'ods_order', ds: '', table: 'ods_order', tmpFlag: 0, sources: ['runtime'], wfs: [101],
          lastCollected: '2026-09-30 10:00:00' },
        { fq: 'dwd_order_pay_detail', ds: '', table: 'dwd_order_pay_detail', tmpFlag: 0,
          sources: ['runtime'], wfs: [101], lastCollected: null },
      ],
      edges: [],
      opaques: [],
      truncated: false,
    })
    const byId = Object.fromEntries(doc.nodes.map((n) => [n.id, n]))
    expect(byId['ods_order']!.data.lastCollected).toBe('2026-09-30 10:00:00')
    expect(byId['dwd_order_pay_detail']!.data.lastCollected).toBeUndefined()
  })

  it('field 级边 → field_dep + transform label；元数据富化 domain/rows/core', () => {
    const doc = buildLineageGraphDoc({
      nodes: [
        { fq: 'dwd_order_pay_detail.pay_amount', ds: '', table: '', tmpFlag: 0,
          sources: ['runtime'], wfs: [101] },
        { fq: 'ods_order.amount', ds: '', table: '', tmpFlag: 0,
          sources: ['runtime'], wfs: [101] },
      ],
      edges: [{
        from: 'ods_order.amount', to: 'dwd_order_pay_detail.pay_amount', level: 'field',
        sources: ['runtime'],
        refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 0, transform: 'amount * 0.9' }],
      }],
      opaques: [],
      truncated: false,
    })
    expect(doc.edges[0]!.kind).toBe('field_dep')
    expect(doc.edges[0]!.label).toBe('amount * 0.9')
  })

  it('metaTables 按表名富化（domain/rows/core 透传）', () => {
    const meta: MetaTable[] = [{
      id: 'T9', name: 'ods_order', layer: 'ODS', domain: '交易域', rows: 4100000,
      size: '1.2GB', owner: '王工', tags: ['核心'], yesterdayOk: true, desc: '', sample: [],
    }]
    const doc = buildLineageGraphDoc(graphRes, meta)
    const n = doc.nodes.find((x) => x.id === 'ods_order')!
    expect(n.data.domain).toBe('交易域')
    expect(n.data.rows).toBe(4100000)
    expect(n.data.core).toBe(true)
    // 未命中元数据的节点安全兜底（不富化也不炸）
    const bare = doc.nodes.find((x) => x.id === 'dim_user')!
    expect(bare.data.domain).toBe('')
  })
})

describe('graphEdgesToRows（影响分析 BFS 输入）', () => {
  it('table 级聚边 → TableLineage 四键行（task/wf 用 refs 合成）', () => {
    const rows = graphEdgesToRows(graphRes)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({
      from: 'ods_order', to: 'dwd_order_pay_detail', task: 'wf101·n_sql_1', wf: '101',
    })
  })

  it('field 级边不入影响分析行；空 refs 兜底「设计推导」', () => {
    const rows = graphEdgesToRows({
      nodes: [], opaques: [], truncated: false,
      edges: [
        { from: 'a', to: 'b', level: 'field', sources: ['runtime'], refs: [] },
        { from: 'a', to: 'b', level: 'table', sources: ['design'], refs: [] },
      ],
    })
    expect(rows).toHaveLength(1)
    expect(rows[0]!.task).toBe('设计推导')
    expect(rows[0]!.wf).toBe('-')
  })
})

describe('matchCenter（深链 ?table= 裸表名归一）', () => {
  // real 模式 graph 文档：节点 id = 数据源点分 fq（ds.table），入口深链传裸表名
  const fqRes: LineageGraphResult = {
    nodes: [
      { fq: 'mysql_biz.dwd_order', ds: 'mysql_biz', table: 'dwd_order', tmpFlag: 0,
        sources: ['runtime'], wfs: [101] },
      { fq: 'mysql_biz.ads_order_daily', ds: 'mysql_biz', table: 'ads_order_daily', tmpFlag: 0,
        sources: ['runtime'], wfs: [101] },
    ],
    edges: [{
      from: 'mysql_biz.dwd_order', to: 'mysql_biz.ads_order_daily', level: 'table',
      sources: ['runtime'], refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 0 }],
    }],
    opaques: [],
    truncated: false,
  }

  it('裸表名命中 fq 节点并归一为全名（中心表下推重拉前提）', () => {
    const doc = buildLineageGraphDoc(fqRes)
    expect(doc.nodes.some((n) => n.id === 'dwd_order')).toBe(false)
    const hit = doc.nodes.find((n) => matchCenter(n.id, 'dwd_order'))
    expect(hit).toBeTruthy()
    expect(hit!.id).toBe('mysql_biz.dwd_order')
  })

  it('fq 反查与全名精确命中（追溯旧路径裸名 id 场景不回退）', () => {
    expect(matchCenter('dwd_order', 'mysql_biz.dwd_order')).toBe(true)
    expect(matchCenter('mysql_biz.dwd_order', 'mysql_biz.dwd_order')).toBe(true)
    expect(matchCenter('mysql_biz.ads_order_daily', 'dwd_order')).toBe(false)
  })
})

describe('focusAllEdges（Task 7 一键聚焦高亮）', () => {
  it('dep/dep_design → dep_focus（label 保留）；field_dep/dep_unlinked 不动；不改原文档', () => {
    const doc = buildLineageGraphDoc({
      ...graphRes,
      edges: [
        ...graphRes.edges,
        { from: 'x', to: 'y', level: 'field', sources: ['runtime'], refs: [] },
      ],
      nodes: [
        ...graphRes.nodes,
        { fq: 'x', ds: '', table: 'x', tmpFlag: 0, sources: ['runtime'], wfs: [] },
        { fq: 'y', ds: '', table: 'y', tmpFlag: 0, sources: ['runtime'], wfs: [] },
      ],
    })
    const snap = JSON.stringify(doc.edges)
    const out = focusAllEdges(doc)
    expect(out.edges.filter((e) => e.kind === 'dep_focus')).toHaveLength(2)  // 双源 dep + design dep_design
    expect(out.edges.find((e) => e.id === 'gle3')!.kind).toBe('field_dep')  // field 边语义不动
    expect(out.edges.find((e) => e.kind === 'dep_focus')!.label).toBe('wf101·n_sql_1 / wf102·n_sql_3（双源）')
    expect(JSON.stringify(doc.edges)).toBe(snap)  // 原文档未被修改（computed 层浅拷贝语义）
  })
})

describe('annotateStmtNo（Task 8 实例追溯边标注）', () => {
  const doc = buildTableLineageDoc([
    { from: 'a', to: 'b', task: 'etl_ab (E1)', wf: 'W' },
    { from: 'b', to: 'c', task: 'etl_bc (E1)', wf: 'W' },
  ])

  it('同 (from,to) 多语句升序去重追加 #n；无命中边不动；不改原文档', () => {
    const snap = JSON.stringify(doc.edges)
    const out = annotateStmtNo(doc, [
      { from: 'a', to: 'b', stmtNo: 2 },
      { from: 'a', to: 'b', stmtNo: 1 },
      { from: 'a', to: 'b', stmtNo: 1 },  // 重复去重
      { from: 'x', to: 'y', stmtNo: 5 },  // 图中无此边 → 忽略
    ])
    expect(out.edges.find((e) => e.source === 'a')!.label).toBe('etl_ab (E1) #1 #2')
    expect(out.edges.find((e) => e.source === 'b')!.label).toBe('etl_bc (E1)')  // 无 stmt 命中不改
    expect(JSON.stringify(doc.edges)).toBe(snap)  // 原文档未被修改（浅拷贝语义）
  })

  it('空追溯行（mock 样例无实例维度）→ 边 label 原样', () => {
    const out = annotateStmtNo(doc, [])
    expect(out.edges.map((e) => e.label)).toEqual(['etl_ab (E1)', 'etl_bc (E1)'])
  })
})