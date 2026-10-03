/**
 * dag profile：DAG 工作流编排视角（对齐 DolphinScheduler / n8n 最佳实践）。
 * I1 palette 重构（§11）：
 * - 逻辑控制 10 个全可用（C1~C10，补组件编号）；
 * - 移除 sub_process（意见③ 不设）与全部 ETL 算子节点类型（spark/flink/cdc/datax/dq/qgate 等）；
 * - I3：数据计算 C11~C14（SQL/Shell/Python/SSH）转可用；
 * - I4：C15/C16/C22（存储过程/HTTP/文件读取）转可用，表单对齐 worker 执行器参数键；
 * - I6：同步组件族注册（历史，原 C17 数据同步/C23 同步编排已被同步编排重构取代）；
 * - I7：C21 变量组件注册（var-table 业务表单+示例行+palette 解禁）；C9 dependent 表单升级（deps-list 依赖项编辑器）；
 * - I8：C18~C20 流处理注册转可用（四源/五算子/四通道分型表单 + 页面化运行浮窗/实时数据展示页）+ 流子图校验；
 * - I12 T11：C24 文件同步（后演进为「文件入仓执行」）/ C25 数据校验（master 内联 success/failure 双出口）/ C26 通知注册转可用；
 * - 同步编排重构：删除「数据同步/同步编排/文件同步/源表基准/目标表基准」5 个旧专业组件，
 *   新增 3 个编排组件（C29 源表基准编排 / C30 目标表基准编排 / C31 文件同步编排，拖入即物化细项节点链）；
 * - 同步编排端点合一与设计态/运行态分离（docs/同步编排端点合一与设计态分离设计.md）：
 *   删除 C32 源端选择/C33 目标端选择，合一为 C37 端点选择（baseMode 分拣表单，具名输出 sourceRef/targetRef）；
 *   C17/C24 标记 runtimeOnly（运行态执行组件：palette/画布/校验排除，schema 保留供运行实例详情渲染）；
 *   编排链新拓扑：开始→前置清理(sql)→端点选择→字段映射→条件设定→对账校验→结束，对账「不通过」→消息通知。
 * - F63 模板：demo_pipeline（拖入 → 模式选择 → 设计时物化展开为普通节点链）。
 */
import { detectCycle, findBrokenEdges, findDuplicateEdges, findIsolated, uid } from '../model'
import type { GraphDocument, GEdge, GNode } from '../model'
import type { BranchDef, DependentDef, NodeSchema, VarDef, ViewProfile } from './types'
import { onEdgeCreated, requiredMissing } from './formLinkage'
import NodeRunDetailPage from '../workbench/pages/NodeRunDetailPage.vue'
import SqlPreviewPage from '../workbench/pages/SqlPreviewPage.vue'
import TmpPreviewPage from '../workbench/pages/TmpPreviewPage.vue'
import StreamNodePage from '../workbench/pages/StreamNodePage.vue'
import StreamDataPage from '../workbench/pages/StreamDataPage.vue'
import BoardPage from '../workbench/pages/BoardPage.vue'

/** 读取节点分支列表（老数据无 branches 时回退空数组） */
export function branchListOf(data: Record<string, unknown>): BranchDef[] {
  return Array.isArray(data.branches) ? (data.branches as BranchDef[]) : []
}

/** I7 C21 变量表读取（老数据无 vars 时回退空数组） */
export function varRowsOf(data: Record<string, unknown>): VarDef[] {
  return Array.isArray(data.vars) ? (data.vars as VarDef[]) : []
}

/** I7 C9 依赖项读取（老数据 deps 为字符串占位时归一化为空数组） */
export function depRowsOf(data: Record<string, unknown>): DependentDef[] {
  return Array.isArray(data.deps) ? (data.deps as DependentDef[]) : []
}

/** C21 摘要：变量名清单（空表回退未配置） */
export function varSummary(data: Record<string, unknown>): string {
  const names = varRowsOf(data).map((r) => r.name).filter(Boolean)
  return names.length ? `注入 ${names.join('、')}` : '未配置变量'
}

/** C9 摘要：依赖清单「工作流名/节点名」（空表回退未配置） */
export function depSummary(data: Record<string, unknown>): string {
  const rows = depRowsOf(data)
  if (!rows.length) return '未配置依赖'
  return rows.map((r) => `${r.wfName || r.wf || '?'}/${r.nodeName || r.node || '?'}`).join('、')
}

/** I8 流组件类型集合（C18~C20）；I11 展示型节点（C24 页面组件）合法共存但不参与管道语义 */
const STREAM_TYPES = ['stream_input', 'stream_fuse', 'stream_output']
const DISPLAY_TYPES = ['page_board']

export interface StreamIssue { level: 'error' | 'warn'; msg: string; nodeId?: string }

/**
 * I8 流子图校验（纯函数，试运行/保存共用语义，F40 §3.4）：
 * - 流组件与批处理组件不可混编（start/end/page_board 除外，I11 同口径后端 DISPLAY_TYPES）；
 * - 至少 1 个流输入 + 1 个流输出；
 * - C19 join 须有两条入边（两路流）；所有流组件须处于 源→汇 连通路径上（无游离）。
 */
export function streamSubgraphIssues(doc: GraphDocument): StreamIssue[] {
  const streamNodes = doc.nodes.filter((n) => STREAM_TYPES.includes(n.type))
  if (!streamNodes.length) return []
  const issues: StreamIssue[] = []
  const batch = doc.nodes.filter((n) => !STREAM_TYPES.includes(n.type) && !DISPLAY_TYPES.includes(n.type)
    && n.type !== 'start' && n.type !== 'end')
  if (batch.length) {
    issues.push({
      level: 'error',
      msg: `流组件与批处理组件不可混编（${batch.map((n) => n.data.name).join('、')}），请拆分画布`,
      nodeId: batch[0].id,
    })
  }
  const sources = streamNodes.filter((n) => n.type === 'stream_input')
  const sinks = streamNodes.filter((n) => n.type === 'stream_output')
  if (!sources.length) issues.push({ level: 'error', msg: '流子图缺少「流输入」（C18）节点' })
  if (!sinks.length) issues.push({ level: 'error', msg: '流子图缺少「流输出」（C20）节点' })
  // C19 join 两条入边
  streamNodes.filter((n) => n.type === 'stream_fuse').forEach((n) => {
    const fuseType = String(n.data.fuseType ?? 'union')
    const inDeg = doc.edges.filter((e) => e.target === n.id).length
    if (fuseType === 'join' && inDeg < 2) {
      issues.push({ level: 'error', msg: `「${n.data.name}」join 融合须接入两路流（当前 ${inDeg} 条入边）`, nodeId: n.id })
    }
  })
  // 连通性：每个流节点都要能在 源→汇 路径上（简化判定：无入边且非源 = 游离；无出边且非汇 = 游离）
  streamNodes.forEach((n) => {
    const inDeg = doc.edges.filter((e) => e.target === n.id).length
    const outDeg = doc.edges.filter((e) => e.source === n.id).length
    if (n.type !== 'stream_input' && inDeg === 0) {
      issues.push({ level: 'error', msg: `「${n.data.name}」未接入上游流（游离节点）`, nodeId: n.id })
    }
    if (n.type !== 'stream_output' && outDeg === 0) {
      issues.push({ level: 'error', msg: `「${n.data.name}」未连接下游流组件`, nodeId: n.id })
    }
  })
  return issues
}

/** C18 节点分型摘要文案（表单联动共用） */
function streamInputSummary(d: Record<string, unknown>): string {
  const t = String(d.srcType ?? 'kafka')
  if (t === 'kafka') {
    const conn = d.dsRef ? `注册源「${d.dsRef}」` : String(d.brokers || '未配置 broker')
    return `Kafka ${d.topic || '未配置 topic'} @ ${conn}`
  }
  if (t === 'cdc') return `CDC ${d.cdcDs || '未选数据源'}（${String(d.tablesText || '全库表')}）`
  if (t === 'redis') {
    const conn = d.dsRef ? `注册源「${d.dsRef}」` : String(d.redisUrl || '未配置地址')
    return `Redis Stream ${d.streamsText || '未配置 Stream 键'} @ ${conn}`
  }
  if (t === 'mqtt') {
    const conn = d.dsRef ? `注册源「${d.dsRef}」` : String(d.mqttHost || '未配置 broker')
    return `MQTT ${d.mqttTopics || '未配置订阅'} @ ${conn}`
  }
  if (t === 'http') {
    const conn = d.dsRef ? `注册源「${d.dsRef}」` : String(d.httpUrl || '未配置 URL')
    return `HTTP ${conn}（${numOr(d.intervalSec, 10)}s 轮询）`
  }
  return `文件尾随 ${d.filePath || '未配置路径'}`
}

const numOr = (v: unknown, dft: number): number => {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? n : dft
}

/** C17 同步执行节点 data 默认值（运行态兜底参数；业务主配置由 master 运行时合并自 endpoint_select） */
const syncExecDefaults = (): Record<string, unknown> => ({
  readerType: 'mysql', writerType: 'mysql',
  batchSize: 1000, errorThreshold: 0, truncate: false,
})

/** 同步编排链节点快速构造（统一 data.name + 展开坐标步进 200px） */
function chainNode(type: string, name: string, data: Record<string, unknown>, x: number, y: number): GNode {
  return { id: uid('nd'), type, position: { x, y }, data: { name, ...data } }
}

/**
 * 同步编排链新拓扑（端点合一 + 设计态/运行态分离）：
 * 开始 → 前置清理(sql) → 端点选择 → 字段映射 → 条件设定 → 对账校验 → 结束，对账校验「不通过」→ 消息通知。
 * 设计态画布不含执行组件（sync/file_sync 运行态由 master 引擎在 assert 入边处物化插入）。
 * 三链共用尾部：assert「通过」出口直连结束、「不通过」出口接通知（onFail=warn 告警继续，覆盖"写前清理 + 不达标告警"完整业务）。
 */
function chainEdgesWithNotify(nodes: GNode[]): GEdge[] {
  /* 锚点按 type 定位（不与 build 函数数组顺序隐式耦合）：assert 之前沿数组顺序线性连线，
     assert「通过」出口标注 success 端口（branch_true/通过→end），「不通过」出口接通知（branch_false/failure/不通过→notify） */
  const assertIdx = nodes.findIndex((n) => n.type === 'assert')
  const assertNode = nodes[assertIdx]!
  const endNode = nodes.find((n) => n.type === 'end')!
  const notifyNode = nodes.find((n) => n.type === 'notify')!
  const main: GEdge[] = []
  for (let i = 0; i < assertIdx; i++) {
    const src = nodes[i]!
    /* 端点选择双输出口（§3.2）：链内出边取源端表口 sourceRef（与用户从源端表口拖边同形态） */
    const epPort = src.type === 'endpoint_select' ? { sourceHandle: 'sourceRef' } : {}
    main.push({ id: uid('e'), source: src.id, target: nodes[i + 1]!.id, kind: 'flow', ...epPort })
  }
  main.push({ id: uid('e'), source: assertNode.id, target: endNode.id, kind: 'branch_true', label: '通过', sourceHandle: 'success' })
  const failEdge: GEdge = { id: uid('e'), source: assertNode.id, target: notifyNode.id, kind: 'branch_false', label: '不通过', sourceHandle: 'failure' }
  return [...main, failEdge]
}

/** C25 对账校验基础默认值（schema defaults 与编排链共用单一来源；工厂每次调用产生新 rules 数组，避免多节点共享可变数组） */
const ASSERT_BASE = (): Record<string, unknown> => ({
  assertSrc: 'upstream', assertUpstream: '', assertDs: '', assertTable: '',
  rules: [{ key: 'rows', value: 'min=1,max=1000000', note: '行数区间' }],
  ruleColumns: [],
  onFail: 'fail',
})

/** C26 消息通知基础默认值（schema defaults 与编排链共用单一来源；全为原始值可安全共享） */
const NOTIFY_BASE: Record<string, unknown> = {
  channel: 'log', url: '', template: '', trigger: 'on_success', failHard: false,
}

/** 对账校验链侧 data（基础默认值 + onFail=warn：不达标走「不通过」出口触发通知，不断流；schema 缺省仍为 fail 断流） */
const assertChainDefaults = (): Record<string, unknown> => ({ ...ASSERT_BASE(), onFail: 'warn' })

/** 消息通知链侧 data（沿基础默认值，仅日志通道兜底） */
const notifyChainDefaults = (): Record<string, unknown> => ({ ...NOTIFY_BASE })

/** C29 源表基准编排链：开始 → 前置清理 → 端点选择(src_base) → 字段映射-复制 → 条件设定 → 对账校验 → 结束（不通过→通知） */
const buildSrcBaseChain = (ctx: { pos: { x: number; y: number } }): { nodes: GNode[]; edges: GEdge[] } => {
  const { x, y } = ctx.pos
  const nodes = [
    chainNode('start', '开始', {}, x, y),
    chainNode('sql', '前置清理', { datasource: '', sql: '', pre: '', post: '' }, x + 200, y),
    chainNode('endpoint_select', '端点选择', { baseMode: 'src_base' }, x + 400, y),
    chainNode('field_map', '字段映射-复制', { inputs: [], fieldMap: [], outputs: [] }, x + 600, y),
    chainNode('condition_set', '条件设定', { inputs: [], outputs: [], filterExpr: '', incrementalColumn: '', incrementalExpr: '' }, x + 800, y),
    chainNode('assert', '对账校验', assertChainDefaults(), x + 1000, y),
    chainNode('end', '结束', {}, x + 1200, y),
    chainNode('notify', '消息通知', notifyChainDefaults(), x + 1200, y + 160),
  ]
  const edges = chainEdgesWithNotify(nodes)
  /* 拖边即引用（§3.3）：程序化建边与 onEdgeCreated 产生同一不变量（map/cond 的 data.inputs 引用） */
  edges.forEach((e) => onEdgeCreated({ nodes, edges }, e))
  return { nodes, edges }
}

/** C30 目标表基准编排链：开始 → 前置清理 → 端点选择(tgt_base) → 字段映射-联合 → 条件设定 → 对账校验 → 结束（不通过→通知） */
const buildTgtBaseChain = (ctx: { pos: { x: number; y: number } }): { nodes: GNode[]; edges: GEdge[] } => {
  const { x, y } = ctx.pos
  const nodes = [
    chainNode('start', '开始', {}, x, y),
    chainNode('sql', '前置清理', { datasource: '', sql: '', pre: '', post: '' }, x + 200, y),
    chainNode('endpoint_select', '端点选择', { baseMode: 'tgt_base' }, x + 400, y),
    chainNode('field_map_union', '字段映射-联合', { inputs: [], fieldMap: [], outputs: [], addSchemaFlag: true, srcSchemaField: 'src_schema', aggOperator: 'union_all' }, x + 600, y),
    chainNode('condition_set', '条件设定', { inputs: [], outputs: [], filterExpr: '', incrementalColumn: '', incrementalExpr: '' }, x + 800, y),
    chainNode('assert', '对账校验', assertChainDefaults(), x + 1000, y),
    chainNode('end', '结束', {}, x + 1200, y),
    chainNode('notify', '消息通知', notifyChainDefaults(), x + 1200, y + 160),
  ]
  const edges = chainEdgesWithNotify(nodes)
  /* 拖边即引用（§3.3）：程序化建边与 onEdgeCreated 产生同一不变量（map/cond 的 data.inputs 引用） */
  edges.forEach((e) => onEdgeCreated({ nodes, edges }, e))
  return { nodes, edges }
}

/** C31 文件同步编排链：开始 → 前置清理 → 端点选择(file_sync 文件源) → 字段映射-复制 → 条件设定 → 对账校验 → 结束（不通过→通知） */
const buildFileSyncChain = (ctx: { pos: { x: number; y: number } }): { nodes: GNode[]; edges: GEdge[] } => {
  const { x, y } = ctx.pos
  const nodes = [
    chainNode('start', '开始', {}, x, y),
    chainNode('sql', '前置清理', { datasource: '', sql: '', pre: '', post: '' }, x + 200, y),
    chainNode('endpoint_select', '端点选择', { baseMode: 'file_sync', filePath: 'samples/orders_part.csv' }, x + 400, y),
    chainNode('field_map', '字段映射-复制', { inputs: [], fieldMap: [], outputs: [] }, x + 600, y),
    chainNode('condition_set', '条件设定', { inputs: [], outputs: [], filterExpr: '', incrementalColumn: '', incrementalExpr: '' }, x + 800, y),
    chainNode('assert', '对账校验', assertChainDefaults(), x + 1000, y),
    chainNode('end', '结束', {}, x + 1200, y),
    chainNode('notify', '消息通知', notifyChainDefaults(), x + 1200, y + 160),
  ]
  const edges = chainEdgesWithNotify(nodes)
  /* 拖边即引用（§3.3）：程序化建边与 onEdgeCreated 产生同一不变量（map/cond 的 data.inputs 引用） */
  edges.forEach((e) => onEdgeCreated({ nodes, edges }, e))
  return { nodes, edges }
}

const portsOf = (data: Record<string, unknown>) =>
  branchListOf(data).map((b) => ({ id: b.id, label: b.name }))

/* I12 R1 归属约定：C24 file_sync=['sync','general']；C25 assert=['etl','general']；C26 notify=['general','stream','etl']（T11 已注册三组件，page_board 不再占用编号） */

const nodeTypes: Record<string, NodeSchema> = {
  /* ================= A 逻辑控制（C1~C10，全可用） ================= */
  start: {
    type: 'start',
    /* §11 模板初始化核查：form=[] 无业务 props 可创作（props 键须与 form/defaults 同名，
       G-03 禁幽灵字段），模板仅落图尺寸默认；sample={} 为无数据槽组件惯例 */
    initTemplate: { rect: { w: 160, h: 48 }, props: {}, sample: {} },
    label: '开始', icon: '▶', color: '#16a34a', code: 'C1', categories: ['general', 'sync', 'etl'], desc: '工作流启动节点（运行实例编号 instance_id 由此生成）',
    form: [], defaults: {},
    summary: () => '工作流入口',
    /* F61 页面化演示位：节点运行详情（real 走 /api/v1/instances，mock 空态） */
    page: { title: '节点运行详情', comp: NodeRunDetailPage, w: 560, h: 340 },
  },
  end: {
    type: 'end',
    /* §11 模板初始化核查：form=[] 无业务 props 可创作（G-03 禁幽灵字段），模板仅落图尺寸默认 */
    initTemplate: { rect: { w: 160, h: 48 }, props: {}, sample: {} },
    label: '结束', icon: '■', color: '#64748b', code: 'C2', categories: ['general', 'sync', 'etl'], desc: '工作流结束节点',
    form: [], defaults: {}, maxOut: 0,  // G-22：maxOut=0 → 禁止出边（与 G-25 validator 双保险）
    summary: () => '工作流出口',
  },
  conditions: {
    type: 'conditions',
    initTemplate: { rect: { w: 180, h: 56 }, props: { branches: [ { id: 'br_yes', name: '满足', expr: 'var.amount > 0' }, { id: 'br_no', name: '不满足', expr: '' } ] } },
    label: '条件分支', icon: '⑃', color: '#d97706', code: 'C3', categories: ['general', 'sync', 'etl'],
    desc: '按条件走向不同分支（对齐 DS 条件分支 / n8n IF）',
    defaults: {
      branches: [
        { id: 'br_yes', name: '满足', expr: '${var} > 0' },
        { id: 'br_no', name: '不满足', expr: '' },
      ] as BranchDef[],
    },
    form: [{ key: 'branches', label: '条件分支（每分支独立端点）', type: 'rows', rowsKind: 'branches' }],
    ports: portsOf,
    summary: (d) => branchListOf(d).map((b) => b.name).join(' / ') || '未配置分支',
  },
  switch: {
    type: 'switch',
    initTemplate: { rect: { w: 180, h: 56 }, props: { branches: [ { id: 'sw_a', name: 'A', expr: 'A' }, { id: 'sw_b', name: 'B', expr: 'B' }, { id: 'sw_d', name: '默认', expr: '*' } ] } },
    label: '切换', icon: '⑄', color: '#b45309', code: 'C4', categories: ['general', 'sync', 'etl'],
    desc: '按变量值匹配多路分发（对齐 DS Switch）',
    defaults: {
      branches: [
        { id: 'sw_a', name: 'A', expr: 'A' },
        { id: 'sw_b', name: 'B', expr: 'B' },
        { id: 'sw_d', name: '默认', expr: '*' },
      ] as BranchDef[],
    },
    form: [{ key: 'branches', label: '分发分支（匹配值）', type: 'rows', rowsKind: 'branches' }],
    ports: portsOf,
    summary: (d) => `${branchListOf(d).length} 路分发`,
  },
  fork: {
    type: 'fork',
    /* §11 模板初始化核查：form=[] 无业务 props 可创作（G-03 禁幽灵字段）；
       并行度由出边数天然表达（G-03 修复），无默认值可预置 */
    initTemplate: { rect: { w: 160, h: 48 }, props: {}, sample: {} },
    label: '并行分叉', icon: '⋔', color: '#ca8a04', code: 'C5', categories: ['general', 'sync', 'etl'],
    desc: '单输入多路并行下发（下游同时触发；并行度 = 出边数）',
    // G-03 修复：删除 parallel 幽灵字段——前端不据此生成端口，后端不据此限制/复制出边，
    // 并行度由出边数天然表达。摘要由 GraphWorkbench 运行时按实际出边数渲染（见 forkSummary）。
    defaults: {},
    form: [],
    summary: () => '并行分发（出边数 = 并行度）',
  },
  join: {
    type: 'join',
    initTemplate: { rect: { w: 160, h: 48 }, props: { policy: 'all_terminal' } },
    label: '汇合（AND）', icon: '⨝', color: '#0f766e', code: 'C6', categories: ['general', 'sync', 'etl'],
    desc: '等待上游分支完成后触发（默认 all_terminal：全部终态即放行，不要求全成功）',
    // G-05 修复：摘要随实际 policy 动态生成，消除"全部成功才触发"的语义误导；补 policy 表单（后端已支持三值）
    defaults: { policy: 'all_terminal' },
    form: [{
      key: 'policy', label: '汇聚策略', type: 'select',
      options: [
        { label: '全部完成（含跳过/失败）', value: 'all_terminal' },
        { label: '全部成功', value: 'all_success' },
        { label: '任一成功', value: 'any_success' },
      ],
    }],
    summary: (d) => {
      const p = d.policy || 'all_terminal'
      const label = { all_terminal: '全部完成（AND）', all_success: '全部成功（AND）', any_success: '任一成功' }
      return `${label[p as keyof typeof label] || '全部完成（AND）'}（可配策略）`
    },
  },
  merge: {
    type: 'merge',
    /* §11 模板初始化核查：form=[] 无业务 props 可创作（G-03 禁幽灵字段），模板仅落图尺寸默认 */
    initTemplate: { rect: { w: 160, h: 48 }, props: {}, sample: {} },
    label: '合并（OR）', icon: '∪', color: '#0284c7', code: 'C7', categories: ['general', 'sync', 'etl'],
    desc: '任一上游完成即触发（抢先合并）',
    defaults: {},
    form: [],
    summary: () => '任一上游完成（OR）',
  },
  delay: {
    type: 'delay',
    initTemplate: { rect: { w: 160, h: 56 }, props: { duration: 60, unit: '秒' } },
    label: '延时执行', icon: '⏱', color: '#57534e', code: 'C8', categories: ['general', 'sync', 'etl'],
    desc: '延时/定时后再执行下游（支持时间变量到点延时）',
    defaults: { duration: 60, unit: '秒' },
    form: [
      { key: 'duration', label: '延时时长', type: 'number' },
      { key: 'unit', label: '单位', type: 'select', options: [
        { value: '秒', label: '秒' }, { value: '分', label: '分' }, { value: '时', label: '时' },
      ] },
      /* G-06 修复：补 until 字段（后端已支持 4 种时间格式） */
      { key: 'until', label: '到点时间（留空 = 按延时时长计算）', type: 'text',
        placeholder: '支持：2026-12-31 23:59:59 / 2026-12-31 23:59 / 20261231 23:59:59 / 20261231235959（可含 ${var}）' },
      { key: 'untilHint', label: '', type: 'hint',
        text: () => '到点时间优先于延时时长；支持变量引用（如 ${yyyyMMdd} 23:59:59）；后端按 4 种格式依次尝试解析' },
    ],
    summary: (d) => d.until ? `到点 ${String(d.until).slice(0, 19)}` : `延时 ${d.duration ?? 0}${String(d.unit ?? '秒')}`,
  },
  dependent: {
    type: 'dependent',
    initTemplate: { rect: { w: 160, h: 48 }, props: { deps: [] } },
    label: '依赖', icon: '⧉', color: '#7c3aed', code: 'C9', categories: ['general', 'sync', 'etl'],
    desc: '依赖其他工作流/节点产出：所配依赖各自最近一次实例中节点终态=success 即通过（I7 简化语义，周期/批次走变量条件）',
    defaults: { deps: [] as DependentDef[] },
    form: [{ key: 'deps', label: '依赖项列表', type: 'rows', rowsKind: 'deps' }],
    summary: (d) => depSummary(d),
  },
  loop: {
    type: 'loop',
    initTemplate: { rect: { w: 180, h: 56 }, props: { collection: '', batchSize: 100, maxIterations: 100 } },
    label: '循环迭代', icon: '↻', color: '#c2410c', code: 'C10', categories: ['general', 'sync', 'etl'],
    desc: '按批次/条件循环执行子链路（自创，海豚无原生）',
    // G-08 修复：暴露 maxIterations——防死循环的唯一硬保护（后端 DEFAULT_MAX_ITERATIONS=100）
    defaults: { collection: '', batchSize: 100, maxIterations: 100 },
    form: [
      { key: 'collection', label: '迭代集合/参数', type: 'text', placeholder: '${loop_items}' },
      { key: 'batchSize', label: '批大小', type: 'number' },
      { key: 'maxIterations', label: '最大迭代次数', type: 'number', placeholder: '100（超出即 FAILURE）' },
    ],
    summary: (d) => `批次 ${d.batchSize ?? 0} · 上限 ${d.maxIterations ?? 100}`,
  },

  /* ================= B 数据计算（C11~C14 I3；C15/C16/C22 I4 注册转可用） ================= */
  sql: {
    type: 'sql',
    initTemplate: { rect: { w: 200, h: 64 }, props: { datasource: '', sql: 'SELECT 1', pre: '', post: '' }, bindings: { result: { kind: 'query', fallback: '查询结果集' } }, sample: { rows: [] } },
    label: 'SQL', icon: '⌨', color: '#334155', code: 'C11', categories: ['etl', 'general', 'sync'],
    desc: '选择数据源执行 SQL（查询/非查询/DDL），页面化浮窗展示查询结果前 200 行',
    /* F1 载体：连续 SQL 步骤同源场景——拖入时从逻辑上游快照预填数据源（§11 划界语义） */
    dropPolicy: { prefillFromUpstream: ['datasource'] },
    defaults: { datasource: '', sql: '', pre: '', post: '' },
    /* M-B2 八段 DSL 迁移：showIf → conditions；summary 函数 → render.summary */
    form: [
      { key: 'datasource', label: '数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] },
        group: '执行目标', groupHint: 'SQL 在哪个库上执行' },
      /* I12 T12：库/表侧栏选择器——经 GET /datasources/{id}/tree 点选库/表，把 SELECT 骨架插入 SQL 编辑器（追加不覆盖手写） */
      { key: 'sqlInsert', label: '库/表侧栏选择器（点选插入，不替代手写）', type: 'mapEditor', mapMode: 'insert',
        cap: { mode: 'columnInsert', dsKey: 'datasource', insertKey: 'sql' } },
      { key: 'sql', label: 'SQL 语句', type: 'text', multiline: true, group: 'SQL 脚本', groupHint: '主语句 + 可选前后置钩子',
        placeholder: 'INSERT INTO ... SELECT ...' },
      { key: 'pre', label: '前置 SQL', type: 'text', multiline: true, placeholder: '主语句前执行，如 TRUNCATE / 建临时表' },
      { key: 'post', label: '后置 SQL', type: 'text', multiline: true, placeholder: '主语句后执行，如 UPDATE 统计 / 校验' },
    ],
    conditions: [
      { id: 'c-sql-insert', when: { field: 'datasource', op: 'notEmpty' }, show: ['sqlInsert'] },
    ],
    render: { summary: 'SQL（查询/非查询/DDL，多语句顺序执行）' },
    /* F61 页面化：SQL 结果预览（worker result_preview 前 200 行，real 走实例详情） */
    page: { title: 'SQL 结果预览', comp: SqlPreviewPage, w: 620, h: 380 },
  },
  shell: {
    type: 'shell',
    initTemplate: { rect: { w: 200, h: 64 }, props: { script: 'echo hello', env: [] }, bindings: { output: { kind: 'static', fallback: '脚本输出' } }, sample: {} },
    label: 'Shell', icon: '❯', color: '#7c3aed', code: 'C12', categories: ['general', 'etl'],
    desc: '在运行时节点执行 Shell 脚本',
    defaults: { script: '', env: [] },
    /* M-B2 八段 DSL 迁移：summary 函数 → render.summary */
    form: [
      { key: 'script', label: '脚本内容', type: 'text', multiline: true, placeholder: '#!/bin/bash ...' },
      /* G-10 修复：补 env 环境变量表（后端 build_env 已消费） */
      { key: 'env', label: '环境变量（键值表，注入子进程）', type: 'rows', rowsKind: 'kv',
        group: '运行环境', groupHint: '传递给 shell 子进程的环境变量（如 DEPLOY_ENV=prod）' },
    ],
    conditions: [],
    render: { summary: 'Shell（bash 脚本执行）' },
  },
  python: {
    type: 'python',
    initTemplate: { rect: { w: 200, h: 64 }, props: { script: 'print(1)', env: [], requirements: '' }, bindings: { output: { kind: 'static', fallback: '脚本输出' } }, sample: {} },
    label: 'Python', icon: 'Py', color: '#2563eb', code: 'C13', categories: ['general', 'etl'],
    desc: '在运行时节点执行 Python 脚本',
    defaults: { script: '', env: [], requirements: '' },
    /* M-B2 八段 DSL 迁移：summary 函数 → render.summary；空 label hint → 固定文案 */
    form: [
      { key: 'script', label: '脚本内容', type: 'text', multiline: true },
      /* G-10 修复：补 env 环境变量表 + requirements 依赖清单（后端已消费） */
      { key: 'env', label: '环境变量（键值表，注入子进程）', type: 'rows', rowsKind: 'kv',
        group: '运行环境', groupHint: '传递给 python 子进程的环境变量（如 PYTHONPATH=/app）' },
      { key: 'requirements', label: '依赖清单（requirements.txt 格式，仅校验/留痕）', type: 'text', multiline: true, rows: 4,
        placeholder: 'requests>=2.28\npandas==1.5.0  # 依赖需预装镜像层，本期不运行时安装' },
      /* 决策 5：空 label hint → 固定文案 */
      { key: 'requirementsHint', label: '依赖需预装镜像层', type: 'hint',
        text: '依赖需预装镜像层，本期仅校验格式并打印日志提示' },
    ],
    conditions: [],
    render: { summary: 'Python（subprocess 执行）' },
  },
  /* G-12 修复：smoke 补 nodeTypes 条目（已在 WORKER_TYPES + 有 executor，但原无 palette 入口） */
  smoke: {
    type: 'smoke',
    initTemplate: { rect: { w: 160, h: 48 }, props: { name: '冒烟', delaySec: 1 }, sample: {} },
    label: '冒烟', icon: '☁', color: '#64748b', code: 'C38', categories: ['general'],
    desc: '冒烟测试节点：echo hello + 分片 sleep（用于链路连通性验证）',
    defaults: { name: '冒烟', delaySec: 1 },
    form: [
      { key: 'name', label: '任务名', type: 'text', placeholder: '冒烟' },
      { key: 'delaySec', label: '延时（秒，分片 1s 支持中断）', type: 'number', placeholder: '1' },
    ],
    summary: (d) => `冒烟 ${d.name || '未命名'}（${d.delaySec ?? 1}s）`,
  },
  ssh: {
    type: 'ssh',
    initTemplate: { rect: { w: 200, h: 64 }, props: { runtimeNode: '', execNodeTag: '', script: 'echo hello' }, bindings: { output: { kind: 'static', fallback: '脚本输出' } }, sample: {} },
    label: 'SSH 脚本', icon: '⌖', color: '#475569', code: 'C14', categories: ['general', 'etl'],
    desc: '依托运行时节点 SSH 执行远程脚本；I7 支持按执行节点标签多主机路由（F53）',
    defaults: { runtimeNode: '', execNodeTag: '', script: '' },
    /* M-B2 八段 DSL 迁移：showIf → conditions；summary 函数 → render.summary */
    form: [
      { key: 'execNodeTag', label: '执行节点标签', type: 'select', selectFrom: 'exec-node-tags', placeholder: '留空则按下方运行时节点直连' },
      { key: 'runtimeNode', label: '运行时节点', type: 'resource', cap: { mode: 'runtimeNode' } },
      { key: 'script', label: '脚本内容', type: 'text', multiline: true, placeholder: '远端 bash 执行的脚本（经 stdin 下发）' },
    ],
    conditions: [
      { id: 'c-runtime-node', when: { field: 'execNodeTag', op: 'empty' }, show: ['runtimeNode'] },
    ],
    render: {
      summary: 'SSH 远程脚本',
      /* M-B2：执行节点分型副标题（标签 → 运行时节点 → 通用兜底，声明序首条命中） */
      summaryRules: [
        { when: { field: 'execNodeTag', op: 'notEmpty' }, template: '标签 ${execNodeTag}' },
        { when: { field: 'runtimeNode', op: 'notEmpty' }, template: '节点 ${runtimeNode}' },
        { when: null, template: 'SSH 远程脚本' },
      ],
    },
  },
  procedure: {
    type: 'procedure',
    initTemplate: { rect: { w: 200, h: 64 }, props: { datasource: '', db: '', procedure: '', args: [] }, bindings: { outParams: { kind: 'static', fallback: 'OUT 参数回读' } }, sample: {} },
    label: '存储过程', icon: '⚙', color: '#6d28d9', code: 'C15', categories: ['general', 'etl'],
    desc: '调用数据源存储过程（CALL），OUT 参数注册为输出参数 out_{key} 供下游引用',
    /* F1 载体：存储过程常接在 SQL 步骤之后同源执行——拖入时快照预填数据源 */
    dropPolicy: { prefillFromUpstream: ['datasource'] },
    defaults: { datasource: '', db: '', procedure: '', args: [] },
    /* M-B2 八段 DSL 迁移：summary 函数 → render.summary */
    form: [
      { key: 'datasource', label: '数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] } },
      { key: 'db', label: '目标库（留空 = 数据源默认库）', type: 'text' },
      { key: 'procedure', label: '过程名', type: 'text', placeholder: '如 sp_i4_demo' },
      { key: 'args', label: '过程参数（IN 传值 / OUT 回读）', type: 'rows', rowsKind: 'args' },
    ],
    conditions: [],
    render: { summary: '存储过程（CALL）' },
  },
  http: {
    type: 'http',
    initTemplate: { rect: { w: 160, h: 56 }, props: { method: 'GET', url: 'https://', timeout: 30 }, bindings: { response: { kind: 'static', fallback: '响应体' } }, sample: {} },
    label: 'HTTP', icon: '⊕', color: '#4f46e5', code: 'C16', categories: ['general', 'etl'],
    desc: '调用外部 HTTP 接口：成功码校验 + 点路径提取响应子集为输出参数',
    defaults: {
      url: '', method: 'GET', headers: [], body: '', bodyType: 'json',
      successCodes: '2xx', extract: [], timeout: 30,
    },
    /* M-B2 八段 DSL 迁移：showIf → conditions；summary 函数 → render.summary */
    form: [
      { key: 'url', label: 'URL', type: 'text', placeholder: 'http://…' },
      { key: 'method', label: '方法', type: 'select', options: [
        { value: 'GET', label: 'GET' }, { value: 'HEAD', label: 'HEAD' },
        { value: 'POST', label: 'POST' }, { value: 'PUT', label: 'PUT' },
        { value: 'DELETE', label: 'DELETE' }, { value: 'PATCH', label: 'PATCH' },
      ] },
      { key: 'headers', label: '请求头（键值表）', type: 'rows', rowsKind: 'kv' },
      { key: 'bodyType', label: '请求体类型', type: 'select',
        options: [{ value: 'json', label: 'JSON' }, { value: 'form', label: 'FORM' }] },
      { key: 'body', label: '请求体', type: 'text', multiline: true, placeholder: 'JSON 串或表单文本' },
      { key: 'successCodes', label: '成功状态码', type: 'text', placeholder: '逗号分隔，如 2xx,200（空 = 2xx）' },
      { key: 'extract', label: '响应提取（输出名 → 点路径）', type: 'rows', rowsKind: 'kv' },
      { key: 'timeout', label: '超时（秒）', type: 'number' },
    ],
    conditions: [
      { id: 'c-body-type', when: { field: 'method', op: 'notIn', value: ['GET', 'HEAD'] }, show: ['bodyType'] },
      { id: 'c-body', when: { field: 'method', op: 'notIn', value: ['GET', 'HEAD'] }, show: ['body'] },
    ],
    render: { summary: 'HTTP 调用' },
  },
  file: {
    type: 'file',
    initTemplate: { rect: { w: 200, h: 64 }, props: { mode: 'datasource', datasource: '', path: '', format: 'csv', encoding: 'utf-8', delimiter: ',', header: true, sheet: '', register: true, tmpName: '', kind: 'table', targetDs: '内置数仓-datara_dw', retention: 'immediate', keepDays: 7 }, bindings: { rows: { kind: 'query', fallback: '文件数据' } }, sample: { rows: [] } },
    label: '文件读取', icon: '▦', color: '#0e7490', code: 'C22', categories: ['general', 'etl'],
    desc: '读取 CSV/TXT/Excel 注册为临时工作数据，下游以 ${tmp.<名>} 引用；页面化预览检验网格',
    defaults: {
      mode: 'datasource', datasource: '',
      path: '', format: 'csv', encoding: 'utf-8', delimiter: ',', header: true, sheet: '',
      register: true, tmpName: '', kind: 'table', targetDs: '内置数仓-datara_dw',
      retention: 'immediate', keepDays: 7,
    },
    /* M-B2 八段 DSL 迁移：showIf/onChange → conditions；summary 函数 → render.summary；hint 函数字面量化 */
    form: [
      { key: 'mode', label: '来源模式', type: 'select', options: [
        { value: 'datasource', label: '数据源中心文件源' },
        { value: 'manual', label: '手动参数' },
      ] },
      { key: 'datasource', label: '文件源数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['file'] } },
      { key: 'path', label: '文件路径（/datara/files 相对）', type: 'text', placeholder: '如 samples/orders.csv' },
      { key: 'format', label: '格式', type: 'select', options: [
        { value: 'csv', label: 'CSV' }, { value: 'txt', label: 'TXT' }, { value: 'excel', label: 'Excel' },
      ] },
      { key: 'encoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }, { value: 'gb18030', label: 'GB18030' },
      ] },
      { key: 'delimiter', label: '分隔符', type: 'text', placeholder: ',' },
      { key: 'header', label: '首行表头', type: 'bool', placeholder: '首行为列名' },
      { key: 'sheet', label: 'Sheet 名称（留空 = 首个）', type: 'text' },
      { key: 'register', label: '注册临时数据', type: 'bool', placeholder: '勾选后下游可用 ${tmp.<名>} 引用' },
      { key: 'tmpName', label: '临时数据名', type: 'text', placeholder: '小写字母开头 3~32 位 a-z0-9_' },
      { key: 'kind', label: '临时数据形态', type: 'select', options: [
        { value: 'table', label: '临时表（全量物化）' },
        { value: 'resultset', label: '结果集引用（抽样 JSON）' },
        { value: 'file', label: '文件登记（仅路径+schema）' },
      ] },
      { key: 'targetDs', label: '物化目标数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] } },
      { key: 'retention', label: '保留策略', type: 'select', options: [
        { value: 'immediate', label: '立即清理（实例终态清扫）' },
        { value: 'days', label: '保留 N 天' },
        { value: 'keep', label: '转正式表（实例成功后 RENAME）' },
      ] },
      { key: 'keepDays', label: '保留天数', type: 'number' },
      /* 决策 5：空 label hint → 固定文案 */
      { key: 'keepHint', label: '转正式表说明', type: 'hint',
        text: '转正式表：实例成功后临时表 RENAME 去前缀，正式表名 = 临时数据名（仅 table 形态生效）' },
      { key: 'tmpHint', label: '临时数据引用', type: 'hint',
        text: '下游以 ${tmp.<名>} 引用本节点注册的临时数据' },
    ],
    conditions: [
      { id: 'c-datasource', when: { field: 'mode', op: 'eq', value: 'datasource' }, show: ['datasource'] },
      { id: 'c-manual', when: { field: 'mode', op: 'eq', value: 'manual' }, show: ['path', 'format', 'encoding', 'delimiter', 'header', 'sheet'] },
      { id: 'c-delimiter', when: { field: 'format', op: 'notEq', value: 'excel' }, show: ['delimiter', 'header'] },
      { id: 'c-sheet', when: { field: 'format', op: 'eq', value: 'excel' }, show: ['sheet'] },
      { id: 'c-register', when: { field: 'register', op: 'eq', value: true }, show: ['tmpName', 'kind', 'targetDs', 'retention', 'keepDays', 'keepHint', 'tmpHint'] },
      { id: 'c-target-ds', when: { field: 'kind', op: 'eq', value: 'table' }, show: ['targetDs'] },
      { id: 'c-keep-days', when: { field: 'retention', op: 'eq', value: 'days' }, show: ['keepDays'] },
      { id: 'c-keep-hint', when: { field: 'retention', op: 'eq', value: 'keep' }, show: ['keepHint'] },
    ],
    render: { summary: '文件读取' },
    /* F61 页面化：数据预览检验网格（t_tmp_data 抽样 + schema 推断 + 空值统计） */
    page: { title: '数据预览检验', comp: TmpPreviewPage, w: 680, h: 440 },
  },

  /* ================= C 同步编排重构（C29~C31 编排组件；C37 端点选择等细项组件；C17/C24 运行态执行组件） ================= */
  sync: {
    type: 'sync',
    initTemplate: { rect: { w: 200, h: 64 }, props: { readerType: 'mysql', writerType: 'mysql', batchSize: 1000, errorThreshold: 0, truncate: false } },
    label: '同步执行', icon: '⇄', color: '#0891b2', code: 'C17', categories: ['sync'],
    /* 同步编排端点合一：sync 降级为运行态执行组件——设计态画布/palette/校验均排除，schema 保留供运行实例详情渲染；
       运行图由 master 引擎按 endpoint_select.baseMode 物化插入（id 前缀 sys_exec_） */
    runtimeOnly: true,
    desc: '运行态执行组件（runtimeOnly，设计态画布不出现）：读端/写端/字段映射/过滤条件由 master 引擎运行时合并自 endpoint_select（按 baseMode 分拣），此处仅保留运行兜底参数',
    defaults: syncExecDefaults(),
    form: [
      { key: 'chainHint', label: '', type: 'hint', text: () =>
        '业务配置在端点选择节点完成（基准类型分拣源端/目标端表单）→ 字段映射（复制或联合）→ 条件设定（WHERE 过滤/增量列）；本节点仅以下兜底参数生效（合并配置优先）' },
      { key: 'batchSize', label: '批大小', type: 'number', placeholder: '缺省 1000' },
      { key: 'errorThreshold', label: '错误阈值（坏行容忍条数）', type: 'number', placeholder: '缺省 0' },
      { key: 'truncate', label: '写入前清空目标（TRUNCATE）', type: 'bool' },
    ],
    summary: () => '同步执行（运行态，配置经 master 合并）',
    /* F61 页面化：同步运行详情（读写行数/速率/坏行数/参与 schema，复用节点运行详情数据通道） */
    page: { title: '同步运行详情', comp: NodeRunDetailPage, w: 620, h: 420 },
  },
  /* ================= C34~C37 同步编排细项组件（编排展开链的配置节点） ================= */
  /* C37 端点选择（合一组件，取代原 C32 源端选择/C33 目标端选择）：按基准类型分拣源端/目标端表单，
     具名输出端口 sourceRef/targetRef 供下游按端口语义引用（field_map/field_map_union 输入） */
  endpoint_select: {
    type: 'endpoint_select',
    initTemplate: { rect: { w: 200, h: 64 }, props: { baseMode: 'src_base', srcDs: '', srcTable: '', probe: false, matchType: 'exact', matchPrefix: '', probeResult: '', tgtDs: '', tgtTable: '', autoCreate: true } },
    label: '端点选择', icon: '⇤', color: '#0369a1', code: 'C37', categories: ['sync'],
    desc: '同步端点选择（合一组件）：按基准类型分拣源端/目标端表单；源表基准=源端选表+目标端选实例（表可新建）；目标表基准=目标端选表+源端选实例联动探测各 schema 匹配表；文件同步=文件源+目标端',
    outputs: [
      { id: 'sourceRef', label: '源端表' },
      { id: 'targetRef', label: '目标端表' },
    ],
    defaults: {
      baseMode: 'src_base',
      srcDs: '', srcTable: '', probe: false, matchType: 'exact', matchPrefix: '', probeResult: '',
      tgtDs: '', tgtTable: '', autoCreate: true,
      filePath: '', fileType: 'csv', fileDelimiter: ',', fileEncoding: 'utf-8', fileHeaderRows: 1, fileSheet: '',
    },
    form: [
      { key: 'baseMode', label: '基准类型', type: 'select', group: '同步基准', groupHint: '决定源端形态与目标表是否必选',
        options: [
        { value: 'src_base', label: '源表基准（源端选表）' },
        { value: 'tgt_base', label: '目标表基准（目标端选表，源端探测）' },
        { value: 'file_sync', label: '文件同步（文件源）' },
      ] },
      /* —— 源端区 —— */
      { key: 'srcDs', label: '源数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] }, required: true,
        group: '源端', groupHint: '待同步的数据从哪来',
        showIf: (d) => String(d.baseMode ?? 'src_base') !== 'file_sync' },
      { key: 'srcTable', label: '源表', type: 'resource', cap: { mode: 'table', dsKey: 'srcDs', writeAs: 'schemaTable' }, required: true,
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'src_base' },
      { key: 'probe', label: '联动探测匹配表', type: 'bool',
        placeholder: '选定目标表后探测该源实例各 schema 匹配表',
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'tgt_base' },
      { key: 'matchType', label: '匹配规则', type: 'select', options: [
        { value: 'exact', label: '完全同名（默认）' }, { value: 'prefix', label: '前部分命名相同（目标表名为前缀）' },
      ], showIf: (d) => String(d.baseMode ?? 'src_base') === 'tgt_base' && !!d.probe },
      { key: 'matchPrefix', label: '匹配前缀（留空 = 目标表名）', type: 'text',
        placeholder: '如 ods_order',
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'tgt_base' && !!d.probe && String(d.matchType) === 'prefix' },
      /* 探测候选确认：逗号分隔 schema.table 清单（留空 = 探测全部匹配）；探测回填联动由 Inspector 层演进 */
      { key: 'probeResult', label: '参与 schema/表（逗号分隔，留空 = 探测全部匹配）', type: 'text',
        placeholder: '如 ec_retail.order_detail, ec_retail_east.order_detail',
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'tgt_base' && !!d.probe },
      /* —— 文件源区 —— */
      { key: 'filePath', label: '文件路径（/datara/files 相对）', type: 'text', required: true,
        group: '文件源', groupHint: '仅文件同步：路径与解析规则',
        placeholder: '如 samples/orders.csv', showIf: (d) => String(d.baseMode ?? 'src_base') === 'file_sync' },
      { key: 'fileType', label: '文件类型', type: 'select', options: [
        { value: 'csv', label: 'CSV' }, { value: 'txt', label: 'TXT' }, { value: 'excel', label: 'Excel' },
      ], showIf: (d) => String(d.baseMode ?? 'src_base') === 'file_sync' },
      { key: 'fileDelimiter', label: '分隔符', type: 'text', placeholder: ',',
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'file_sync' && String(d.fileType) !== 'excel' },
      { key: 'fileEncoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }, { value: 'gb18030', label: 'GB18030' },
      ], showIf: (d) => String(d.baseMode ?? 'src_base') === 'file_sync' && String(d.fileType) !== 'excel' },
      { key: 'fileHeaderRows', label: '表头行数', type: 'number', placeholder: '缺省 1（0 = 无表头）',
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'file_sync' },
      { key: 'fileSheet', label: 'Sheet 名称（留空 = 首个）', type: 'text',
        placeholder: '如 Sheet1', showIf: (d) => String(d.baseMode ?? 'src_base') === 'file_sync' && String(d.fileType) === 'excel' },
      /* —— 目标端区 —— */
      { key: 'tgtDs', label: '目标数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] }, required: true,
        group: '目标端', groupHint: '数据落到哪；表不存在可按源结构新建' },
      /* 目标表双分型（required 契约为 boolean，保留两条 showIf 互斥渲染）：tgt_base 必选；src_base/file_sync 分型可留空（按源表同名/文件表头新建） */
      { key: 'tgtTable', label: '目标表', type: 'resource', cap: { mode: 'table', dsKey: 'tgtDs', writeAs: 'schemaTable' }, required: true,
        showIf: (d) => String(d.baseMode ?? 'src_base') === 'tgt_base' },
      { key: 'tgtTable', label: '目标表（留空 = 按源表同名/文件表头新建）', type: 'resource', cap: { mode: 'table', dsKey: 'tgtDs', writeAs: 'schemaTable' },
        showIf: (d) => String(d.baseMode ?? 'src_base') !== 'tgt_base' },
      { key: 'autoCreate', label: '目标表不存在则新建', type: 'bool',
        placeholder: '按源表/文件表头结构创建', showIf: (d) => String(d.baseMode ?? 'src_base') !== 'tgt_base' },
    ],
    summary: (d) => {
      const m = String(d.baseMode ?? 'src_base')
      const name = { src_base: '源表基准', tgt_base: '目标表基准', file_sync: '文件同步' }[m] ?? m
      const src = m === 'file_sync'
        ? String(d.filePath || '未配置路径')
        : `${d.srcDs || '未选源'}:${d.srcTable || d.probeResult || (d.probe ? '探测匹配表' : '未选表')}`
      return `${name}：${src} → ${d.tgtDs || '未选目标'}:${d.tgtTable || '(同名新建)'}`
    },
  },
  field_map: {
    type: 'field_map',
    initTemplate: { rect: { w: 200, h: 64 }, props: { inputs: [], fieldMap: [], outputs: [] } },
    label: '字段映射-复制', icon: '⇄', color: '#0369a1', code: 'C34', categories: ['sync'],
    desc: '源表→目标表字段映射（2 输入 + flex 布局字段对照 + 输入/输出选择）',
    defaults: { inputs: [], fieldMap: [], outputs: [] },
    form: [
      /* —— 输入选择（多选上游节点输出：[0]=源端表, [1]=目标端表） —— */
      /* 直通节点 inputs 非必填（wf97 422 根治 2026-10-01）：引擎 PASSTHROUGH 拍平容忍空
         inputs（留空=全量拍平，wf97 v5 250K 行实测），required 声明曾致存量文档重存 422 */
      { key: 'inputs', label: '输入（上游节点输出，前两个为源端表/目标端表）', type: 'resource', cap: { mode: 'upstreamOutputs', upstreamMax: 2 },
        group: '映射输入', groupHint: '源/目标两端表，顺序决定映射方向；留空=拍平直通' },
      /* —— 字段映射（flex布局，源字段→目标字段） —— */
      /* 端点合一：源/目标列枚举均取自 endpoint_select 节点（srcDs/srcTable 与 tgtDs/tgtTable 字段） */
      { key: 'fieldMap', label: '字段映射（源字段 → 目标字段）', type: 'mapEditor', mapMode: 'map',
        cap: { mode: 'columnMap', srcNodeType: 'endpoint_select', tgtNodeType: 'endpoint_select', srcDsKey: 'srcDs', srcTableKey: 'srcTable', tgtDsKey: 'tgtDs', tgtTableKey: 'tgtTable', fmSrcIndex: 0, fmTgtIndex: 1 } },
      /* —— 输出选择（默认为映射表全字段，可添加上游输出或选择字段） —— */
      { key: 'outputs', label: '输出（默认为映射后全字段）', type: 'resource', group: '映射输出', cap: { mode: 'upstreamOutputs', upstreamMax: 5 } },
    ],
    summary: (d) => {
      const n = Array.isArray(d.fieldMap) ? d.fieldMap.length : 0
      const ins = Array.isArray(d.inputs) ? d.inputs.length : 0
      return `${ins} 输入 → ${n ? `${n} 条字段映射` : '同名全列映射'}`
    },
  },
  field_map_union: {
    type: 'field_map_union',
    initTemplate: { rect: { w: 200, h: 64 }, props: { inputs: [], fieldMap: [], outputs: [], addSchemaFlag: true, srcSchemaField: 'src_schema', aggOperator: 'union_all' } },
    label: '字段映射-联合', icon: '⇉', color: '#0369a1', code: 'C36', categories: ['sync'],
    desc: '目标表基准专用：多 schema 源表 → 目标表字段联合映射，可增删列/数值转换；选择记录来源时自动追加来源 schema 标识列；聚合算子 union all（当前唯一）',
    defaults: { inputs: [], fieldMap: [], outputs: [], addSchemaFlag: true, srcSchemaField: 'src_schema', aggOperator: 'union_all' },
    form: [
      /* —— 输入选择（多选上游节点输出：[0]=目标端表, [1]=源端探测表） —— */
      /* 直通节点 inputs 非必填（同 field_map：引擎拍平容忍空 inputs，存量兼容） */
      { key: 'inputs', label: '输入（上游节点输出，前两个为目标端表/源端探测表）', type: 'resource', cap: { mode: 'upstreamOutputs', upstreamMax: 2 },
        group: '联合输入', groupHint: '多 schema 源表与目标表的配对顺序；留空=拍平直通' },
      /* —— 字段映射（flex布局，源字段→目标字段） —— */
      /* 端点合一：源/目标列枚举均取自 endpoint_select 节点（srcDs/srcTable 与 tgtDs/tgtTable 字段） */
      { key: 'fieldMap', label: '字段映射（源字段 → 目标字段，留空 = 同名全列）', type: 'mapEditor', mapMode: 'map',
        cap: { mode: 'columnMap', srcNodeType: 'endpoint_select', tgtNodeType: 'endpoint_select', srcDsKey: 'srcDs', srcTableKey: 'srcTable', tgtDsKey: 'tgtDs', tgtTableKey: 'tgtTable', fmSrcIndex: 1, fmTgtIndex: 0 } },
      /* —— 记录来源标识（需求：用户选择记录来源时系统必须增加来源 schema 字段） —— */
      { key: 'addSchemaFlag', label: '记录来源标识列', type: 'bool', group: '来源标识', groupHint: '多源合并后区分每行来自哪个 schema',
        placeholder: '开启后每行落来源 schema 标识（如 src_schema=ec_retail_east）' },
      /* dataScope: 标识列是系统追加列，不在上游列域内，故不声明 dataScope（避免误伤合法配置） */
      { key: 'srcSchemaField', label: '标识列名', type: 'text', placeholder: '缺省 src_schema',
        showIf: (d) => !!d.addSchemaFlag },
      /* —— 聚合算子（目标表基准第 4 步，G-13 修复：补 union_distinct 选项） —— */
      { key: 'aggOperator', label: '聚合算子', type: 'select', group: '合并与输出', options: [
        { value: 'union_all', label: 'union all（追加合并，默认）' },
        { value: 'union_distinct', label: 'union distinct（合并去重）' },
      ] },
      /* —— 输出选择 —— */
      { key: 'outputs', label: '输出（默认为映射后全字段 + 标识列）', type: 'resource', cap: { mode: 'upstreamOutputs', upstreamMax: 5 } },
    ],
    summary: (d) => {
      const n = Array.isArray(d.fieldMap) ? d.fieldMap.length : 0
      const flag = d.addSchemaFlag ? ` + 来源标识(${d.srcSchemaField || 'src_schema'})` : ''
      return `union all 联合${n ? ` ${n} 条映射` : '（同名全列）'}${flag}`
    },
  },
  condition_set: {
    type: 'condition_set',
    initTemplate: { rect: { w: 200, h: 64 }, props: { inputs: [], outputs: [], filterExpr: '', incrementalColumn: '', incrementalExpr: '' } },
    label: '条件设定', icon: '⚿', color: '#0369a1', code: 'C35', categories: ['sync'],
    desc: '源表数据筛选条件（默认全量）+ 增量列 + 输入/输出选择',
    defaults: { inputs: [], outputs: [], filterExpr: '', incrementalColumn: '', incrementalExpr: '' },
    form: [
      /* —— 输入选择（多选上游节点输出） —— */
      /* 直通节点 inputs 非必填（同 field_map：引擎拍平容忍空 inputs，存量兼容） */
      { key: 'inputs', label: '输入（上游节点输出）', type: 'resource',
        group: '数据流', groupHint: '筛选对象与下游可见的输出登记；留空=拍平直通',
        cap: { mode: 'upstreamOutputs', upstreamMax: 3 } },
      /* —— 输出选择（多选上游节点输出） —— */
      { key: 'outputs', label: '输出（上游节点输出）', type: 'resource', cap: { mode: 'upstreamOutputs', upstreamMax: 3 } },
      /* —— WHERE 条件 —— */
      { key: 'filterExpr', label: '筛选条件（WHERE，留空 = 全量同步）', type: 'text', multiline: true,
        group: '筛选与增量', groupHint: '留空即全量；增量列须是上游真实存在的列',
        placeholder: '如 create_time > ${last_sync_time} AND status = 1' },
      /* —— 增量列（dataScope: 增量列必须是上游真实存在的列，F3 值域闸门由此生效）—— */
      { key: 'incrementalColumn', label: '增量列名', type: 'text', dataScope: 'upstream-columns',
        placeholder: '如 create_time（留空 = 全量同步）' },
      { key: 'incrementalExpr', label: '增量条件表达式', type: 'text',
        placeholder: '如 ${yyyyMMdd-1}（运行时变量替换后 > 比较）',
        showIf: (d) => !!d.incrementalColumn },
    ],
    summary: (d) => {
      const ins = Array.isArray(d.inputs) ? d.inputs.length : 0
      const outs = Array.isArray(d.outputs) ? d.outputs.length : 0
      const cond = d.filterExpr ? `WHERE ${String(d.filterExpr).slice(0, 30)}...` : '全量同步'
      return `${ins} 输入 → ${outs} 输出，${cond}`
    },
  },
  /* ================= C29~C31 同步编排组件（拖入即物化对应细项节点链，设计时物化引擎零改动） ================= */
  src_base_orch: {
    type: 'src_base_orch',
    /* §11 模板初始化核查：F63 聚合模板组件，拖入即 materializeTemplate 展开节点链
       （不走 applyInitTemplate 链），form=[] 无业务 props 可创作（G-03 禁幽灵字段） */
    initTemplate: { rect: { w: 200, h: 64 }, props: {}, sample: {} },
    label: '源表基准编排', icon: '⇉', color: '#0891b2', code: 'C29', categories: ['sync'],
    desc: '源表基准同步场景：拖入物化为 开始 → 前置清理 → 端点选择(源表基准) → 字段映射-复制 → 条件设定 → 对账校验 → 结束 节点链（对账不通过 → 消息通知）',
    form: [],
    template: {
      modes: [{ key: 'src_base', label: '源表基准', desc: '已知源库表 → 目标表（可新建），字段复制映射 + 筛选条件', build: buildSrcBaseChain }],
    },
    summary: () => '源表基准编排模板',
  },
  tgt_base_orch: {
    type: 'tgt_base_orch',
    /* §11 模板初始化核查：F63 聚合模板组件，拖入即 materializeTemplate 展开节点链
       （不走 applyInitTemplate 链），form=[] 无业务 props 可创作（G-03 禁幽灵字段） */
    initTemplate: { rect: { w: 200, h: 64 }, props: {}, sample: {} },
    label: '目标表基准编排', icon: '⇉', color: '#0891b2', code: 'C30', categories: ['sync'],
    desc: '目标表基准同步场景：拖入物化为 开始 → 前置清理 → 端点选择(目标表基准，源端探测) → 字段映射-联合（union all + 来源 schema 标识列）→ 条件设定 → 对账校验 → 结束 节点链（对账不通过 → 消息通知）',
    form: [],
    template: {
      modes: [{ key: 'tgt_base', label: '目标表基准', desc: '以目标表为基准探测多 schema 源表，union all 联合 + 来源标识', build: buildTgtBaseChain }],
    },
    summary: () => '目标表基准编排模板',
  },
  file_sync_orch: {
    type: 'file_sync_orch',
    /* §11 模板初始化核查：F63 聚合模板组件，拖入即 materializeTemplate 展开节点链
       （不走 applyInitTemplate 链），form=[] 无业务 props 可创作（G-03 禁幽灵字段） */
    initTemplate: { rect: { w: 200, h: 64 }, props: {}, sample: {} },
    label: '文件同步编排', icon: '⇉', color: '#0891b2', code: 'C31', categories: ['sync'],
    desc: '文件同步场景（参考源表基准）：拖入物化为 开始 → 前置清理 → 端点选择(文件源) → 字段映射-复制 → 条件设定 → 对账校验 → 结束 节点链（对账不通过 → 消息通知）',
    form: [],
    template: {
      modes: [{ key: 'file_sync', label: '文件同步', desc: 'CSV/TXT/Excel 文件 → 库表入仓，字段复制映射 + 筛选条件', build: buildFileSyncChain }],
    },
    summary: () => '文件同步编排模板',
  },

  /* ================= D 流处理（C18~C20：I8 注册转可用，四源/五算子/四通道） ================= */
  stream_input: {
    type: 'stream_input',
    initTemplate: { rect: { w: 200, h: 64 }, props: { srcType: 'kafka', dsRef: '' }, bindings: { events: { kind: 'query', fallback: '流事件' } }, sample: { events: [] } },
    label: '流输入', icon: '⇥', color: '#0d9488', code: 'C18', categories: ['stream'],
    desc: '流输入源（Source）：Kafka 消费 / CDC binlog / HTTP 拉取 / 文件尾随 / 模拟数据 / Redis Stream / MQTT（分型表单，行事件统一 {source, ts, data}）',
    defaults: {
      srcType: 'kafka',
      dsRef: '',  // 连接性注册化（09-21）：kafka/redis/mqtt/http 引用数据源中心注册源；空 = 内联高级模式
      /* kafka 分型（G-15 修复：group 默认值改为后端下发；前端不再硬编码 'datara-flink'） */
      brokers: '', topic: '', group: '', groupOverride: false, startFrom: 'earliest',
      format: 'json', delimiter: ',',
      /* cdc 分型（引用 I4 注册数据源） */
      cdcDs: '', schemasText: '', tablesText: '', posMode: 'latest', posFile: '', posPos: 0,
      /* http 拉取分型 */
      httpUrl: '', httpMethod: 'GET', intervalSec: 10, headers: [] as Record<string, string>[],
      dataPath: '', cursorParam: '', cursorPath: '',
      /* 文件尾随分型 */
      filePath: '', fileEncoding: 'utf-8', fileDelimiter: ',', fileHeader: true,
      /* 模拟数据分型（I11：演示/联调） */
      simDataset: 'ecommerce', simEvents: '', simEps: 5,
      /* Redis Stream 分型 */
      redisUrl: 'redis://redis:6379/0', streamsText: '', redisGroup: 'datara-flink', redisConsumer: 'c1',
      /* MQTT 分型 */
      mqttHost: '', mqttPort: 1883, mqttTopics: '',
    },
    form: [
      { key: 'srcType', label: '源分型', type: 'select', options: [
        { value: 'kafka', label: 'Kafka 消费' }, { value: 'cdc', label: 'CDC（MySQL/GreatDB binlog）' },
        { value: 'http', label: 'HTTP 拉取' }, { value: 'file', label: '文件尾随' },
        { value: 'simulate', label: '模拟数据（演示/联调）' },
        { value: 'redis', label: 'Redis Stream' }, { value: 'mqtt', label: 'MQTT 订阅' },
      ] },
      /* —— kafka —— */
      { key: 'dsRef', label: '数据源引用（Kafka 注册源）', type: 'resource', cap: { mode: 'datasource', dsTypes: ['kafka'] }, showIf: (d) => d.srcType === 'kafka' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 Kafka 源（连接性由注册层保证，启动预检只校验引用与状态）；不选则下方手动填写连接参数（内联高级模式）。引用后 brokers 由注册源固定带出只读（连接层归一），topic 从注册源枚举选择，消费组默认 datara-flink（开「覆盖默认消费组」才可改）',
        showIf: (d) => d.srcType === 'kafka' },
      { key: 'brokers', label: 'Broker 地址（高级内联）', type: 'text', placeholder: 'host:9092（逗号分隔多个）', showIf: (d) => d.srcType === 'kafka' && !d.dsRef },
      /* I12 T12：引用注册源后 topic 升级 topic-select（注册源枚举带出）；内联模式保留手填 */
      { key: 'topic', label: 'Topic（注册源枚举）', type: 'resource', cap: { mode: 'topic' }, required: true,
        showIf: (d) => d.srcType === 'kafka' && !!d.dsRef },
      { key: 'topic', label: 'Topic', type: 'text', placeholder: '如 orders', required: true,
        showIf: (d) => d.srcType === 'kafka' && !d.dsRef },
      { key: 'groupOverride', label: '覆盖默认消费组', type: 'bool',
        placeholder: '开启后可自定义消费组；缺省 datara-flink（与后端缺省一致）',
        showIf: (d) => d.srcType === 'kafka' && !!d.dsRef,
        /* I12 评审修：关闭覆盖即清空残留自定义组（C22 onChange 清值先例），空值由后端回退 datara-flink（sources.py 缺省口径） */
        onChange: (d, v) => { if (!v) d.group = '' } },
      { key: 'group', label: '消费组', type: 'text', showIf: (d) => d.srcType === 'kafka' && (!d.dsRef || !!d.groupOverride) },
      { key: 'startFrom', label: '起始位点', type: 'select', options: [
        { value: 'earliest', label: 'earliest（最早）' }, { value: 'latest', label: 'latest（最新）' },
      ], showIf: (d) => d.srcType === 'kafka' },
      { key: 'format', label: '反序列化格式', type: 'select', options: [
        { value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV（分隔符切分为字段）' },
      ], showIf: (d) => d.srcType === 'kafka' },
      { key: 'delimiter', label: 'CSV 分隔符', type: 'text', placeholder: ',',
        showIf: (d) => d.srcType === 'kafka' && d.format === 'csv' },
      /* —— cdc —— */
      { key: 'cdcDs', label: 'CDC 数据源（引用 I4 注册）', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] }, required: true, showIf: (d) => d.srcType === 'cdc' },
      { key: 'schemasText', label: '库白名单（逗号分隔，留空 = 全库）', type: 'text', showIf: (d) => d.srcType === 'cdc' },
      { key: 'tablesText', label: '表白名单（逗号分隔，留空 = 全表）', type: 'text', showIf: (d) => d.srcType === 'cdc' },
      { key: 'posMode', label: 'binlog 位点', type: 'select', options: [
        { value: 'latest', label: '最新（当前 file:pos）' }, { value: 'earliest', label: '最早' },
        { value: 'custom', label: '指定 file:pos' },
      ], showIf: (d) => d.srcType === 'cdc' },
      { key: 'posFile', label: 'binlog 文件', type: 'text', placeholder: '如 binlog.000003', showIf: (d) => d.srcType === 'cdc' && d.posMode === 'custom' },
      { key: 'posPos', label: '位点偏移', type: 'number', showIf: (d) => d.srcType === 'cdc' && d.posMode === 'custom' },
      /* —— http —— */
      { key: 'dsRef', label: '数据源引用（HTTP 注册源）', type: 'resource', cap: { mode: 'datasource', dsTypes: ['http'] }, showIf: (d) => d.srcType === 'http' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 HTTP 服务（baseUrl 与鉴权头由注册层提供）；URL 可填相对业务路径（如 /api/v1/orders）与 baseUrl 拼接，留空直打 baseUrl，完整 http(s) URL 则覆盖',
        showIf: (d) => d.srcType === 'http' },
      { key: 'httpUrl', label: '业务路径 / URL', type: 'text', placeholder: '引用模式：/api/v1/orders；内联：http://…', showIf: (d) => d.srcType === 'http' && !d.dsRef },
      { key: 'httpMethod', label: '方法', type: 'select', options: [
        { value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' },
      ], showIf: (d) => d.srcType === 'http' },
      { key: 'intervalSec', label: '轮询间隔（秒）', type: 'number', showIf: (d) => d.srcType === 'http' },
      { key: 'headers', label: '请求头（键值表）', type: 'rows', rowsKind: 'kv', showIf: (d) => d.srcType === 'http' },
      { key: 'dataPath', label: '数据点路径（响应内数组，如 data.list，留空 = 整响应）', type: 'text', showIf: (d) => d.srcType === 'http' },
      { key: 'cursorParam', label: '游标请求参数名（留空 = 无游标）', type: 'text', showIf: (d) => d.srcType === 'http' },
      { key: 'cursorPath', label: '游标提取点路径（响应内，如 data.cursor）', type: 'text',
        showIf: (d) => d.srcType === 'http' && !!d.cursorParam },
      /* —— file —— */
      { key: 'filePath', label: '文件路径（/datara/files 相对）', type: 'text', placeholder: '如 logs/app.log', required: true, showIf: (d) => d.srcType === 'file' },
      { key: 'fileEncoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' },
      ], showIf: (d) => d.srcType === 'file' },
      { key: 'fileDelimiter', label: '分隔符（留空 = 整行一列）', type: 'text', placeholder: ',', showIf: (d) => d.srcType === 'file' },
      { key: 'fileHeader', label: '首行为列名', type: 'bool', showIf: (d) => d.srcType === 'file' },
      /* —— simulate（演示/联调模拟源）—— */
      { key: 'simDataset', label: '内置数据集', type: 'select', options: [
        { value: 'ecommerce', label: '电商（order_pay/user_click/cart_event）' },
        { value: 'iot', label: 'IoT（temp/press/vib/alert）' },
        { value: 'visit', label: '站点访问（order/visit）' },
      ], showIf: (d) => d.srcType === 'simulate' },
      { key: 'simEvents', label: '事件过滤（逗号分隔，留空 = 数据集全部事件）', type: 'text',
        placeholder: '如 order_pay,user_click', showIf: (d) => d.srcType === 'simulate' },
      { key: 'simEps', label: '事件速率（条/秒，0.5~200）', type: 'number', showIf: (d) => d.srcType === 'simulate' },
      { key: 'simHint', label: '', type: 'hint', text: () => '按内置 schema 与速率生成行事件，无需外部依赖；联调窗口聚合/看板链路用', showIf: (d) => d.srcType === 'simulate' },
      /* —— redis（Redis Stream 源）—— */
      { key: 'dsRef', label: '数据源引用（Redis 注册源）', type: 'resource', cap: { mode: 'datasource', dsTypes: ['redis'] }, showIf: (d) => d.srcType === 'redis' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 Redis 实例（地址/密码由注册层提供）；不选则下方手动填写地址（内联高级模式）',
        showIf: (d) => d.srcType === 'redis' },
      { key: 'redisUrl', label: 'Redis 地址（高级内联）', type: 'text', placeholder: 'redis://redis:6379/0', showIf: (d) => d.srcType === 'redis' && !d.dsRef },
      { key: 'streamsText', label: 'Stream 键（逗号分隔多个）', type: 'text', placeholder: '如 order_stream,user_stream', required: true, showIf: (d) => d.srcType === 'redis' },
      { key: 'redisGroup', label: '消费组（XREADGROUP，位点由组管理）', type: 'text', showIf: (d) => d.srcType === 'redis' },
      { key: 'redisConsumer', label: '消费者名', type: 'text', showIf: (d) => d.srcType === 'redis' },
      /* —— mqtt（MQTT 订阅源）—— */
      { key: 'dsRef', label: '数据源引用（MQTT 注册源）', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mqtt'] }, showIf: (d) => d.srcType === 'mqtt' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 MQTT Broker（地址/认证由注册层提供）；不选则下方手动填写（内联高级模式）',
        showIf: (d) => d.srcType === 'mqtt' },
      { key: 'mqttHost', label: 'Broker 地址（高级内联）', type: 'text', placeholder: '容器名（如 emqx）或 host', showIf: (d) => d.srcType === 'mqtt' && !d.dsRef },
      { key: 'mqttPort', label: '端口（高级内联）', type: 'number', showIf: (d) => d.srcType === 'mqtt' && !d.dsRef },
      { key: 'mqttTopics', label: 'Topic 订阅（逗号分隔，支持 +/# 通配）', type: 'text', placeholder: '如 factory/+/temp', required: true, showIf: (d) => d.srcType === 'mqtt' },
      { key: 'mqttHint', label: '', type: 'hint', text: () => 'MQTT 消息按 JSON 解析为行事件（source=topic）', showIf: (d) => d.srcType === 'mqtt' },
      { key: 'hint', label: '', type: 'hint',
        text: () => '行事件统一为 {source, ts, data} 进入流管道；Kafka/CDC/HTTP/文件位点周期落 t_stream_offset 重启续跑，Redis 位点由消费组管理，模拟源无位点' },
    ],
    summary: streamInputSummary,
    /* I8 页面化：消费速率/位点/滞后 运行浮窗 */
    page: { title: '流输入运行详情', comp: StreamNodePage, w: 620, h: 460 },
  },
  stream_fuse: {
    type: 'stream_fuse',
    initTemplate: { rect: { w: 200, h: 64 }, props: { fuseType: 'union', alignMap: [] } },
    label: '流融合', icon: '⊞', color: '#0f766e', code: 'C19', categories: ['stream'],
    desc: '流融合算子：union 对齐 / join 关联 / 窗口聚合 / filter 过滤 / map 字段映射（分型表单）',
    defaults: {
      fuseType: 'union',
      /* union：字段对齐映射（目标字段 ← 来源字段） */
      alignMap: [] as Record<string, string>[],
      /* join：两路流关联键 + 窗口 */
      joinKeyLeft: '', joinKeyRight: '', joinWindowSec: 60, joinType: 'inner',
      /* filter：条件表达式 */
      filterExpr: '',
      /* map：字段转换表达式表（目标字段 ← 表达式） */
      fieldMap: [] as Record<string, string>[],
      /* 窗口聚合：分组键 + 聚合函数表 + 滚动/滑动窗口 + 水位线 */
      groupKeys: '', aggs: [] as Record<string, string>[],
      windowType: 'tumbling', windowSizeSec: 60, slideSec: 10, watermarkSec: 5,
    },
    form: [
      { key: 'fuseType', label: '融合分型', type: 'select', options: [
        { value: 'union', label: 'union 归并（多路合流，不计算）' }, { value: 'join', label: 'join 关联（双流按键匹配）' },
        { value: 'window', label: '窗口聚合（单流：窗口+分组+聚合函数）' }, { value: 'filter', label: 'filter 过滤' },
        { value: 'map', label: 'map 字段映射' },
      ] },
      { key: 'alignMap', label: '字段对齐映射（目标 ← 来源，留空 = 同名透传）', type: 'rows', rowsKind: 'kv',
        showIf: (d) => d.fuseType === 'union' },
      /* I12 T12：join 键升级 field-select（列枚举自直接上游流输入的 CDC 源表；非 CDC 上游降级为可直接输入），
         单选写回字符串对齐 worker ops.py joinKeyLeft/Right 单键契约；union 对齐映射维持 kv-table（W1 语义标注不变） */
      { key: 'joinKeyLeft', label: '左流关联键', type: 'resource', cap: { mode: 'column', src: 'upstream', upstreamIndex: 0, multi: false }, required: true, showIf: (d) => d.fuseType === 'join' },
      { key: 'joinKeyRight', label: '右流关联键', type: 'resource', cap: { mode: 'column', src: 'upstream', upstreamIndex: 1, multi: false }, required: true, showIf: (d) => d.fuseType === 'join' },
      { key: 'joinWindowSec', label: '关联窗口（秒，窗口内缓存匹配）', type: 'number', showIf: (d) => d.fuseType === 'join' },
      /* G-16 修复：补 right / full 关联类型（CDC 场景常用） */
      { key: 'joinType', label: '关联类型', type: 'select', options: [
        { value: 'inner', label: 'inner（交集）' }, { value: 'left', label: 'left（保留左流未匹配）' },
        { value: 'right', label: 'right（保留右流未匹配）' }, { value: 'full', label: 'full（全外保留双侧）' },
      ], showIf: (d) => d.fuseType === 'join' },
      { key: 'filterExpr', label: '过滤条件表达式', type: 'text', multiline: true, placeholder: '如 amount > 0 && status == \'paid\'',
        required: true, showIf: (d) => d.fuseType === 'filter' },
      { key: 'fieldMap', label: '字段转换表达式表（目标字段 ← 表达式，如 upper(name)）', type: 'rows', rowsKind: 'kv',
        showIf: (d) => d.fuseType === 'map' },
      { key: 'groupKeys', label: '分组键（逗号分隔，留空 = 全局聚合）', type: 'text', showIf: (d) => d.fuseType === 'window' },
      { key: 'aggs', label: '聚合函数表（键=字段，值=函数:别名，如 amount:sum:amt_total）', type: 'rows', rowsKind: 'kv',
        required: true, showIf: (d) => d.fuseType === 'window' },
      { key: 'windowType', label: '窗口类型', type: 'select', options: [
        { value: 'tumbling', label: '滚动窗口' }, { value: 'sliding', label: '滑动窗口' },
      ], showIf: (d) => d.fuseType === 'window' },
      { key: 'windowSizeSec', label: '窗口大小（秒）', type: 'number', showIf: (d) => d.fuseType === 'window' },
      { key: 'slideSec', label: '滑动步长（秒）', type: 'number', showIf: (d) => d.fuseType === 'window' && d.windowType === 'sliding' },
      { key: 'watermarkSec', label: '水位线允许延迟（秒）', type: 'number', showIf: (d) => d.fuseType === 'window' },
      { key: 'sessHint', label: '', type: 'hint',
        text: () => '概念：window=单流内按窗口+分组键计算（产出带 win_start/win_end 的迟发窗口行）；union=多路归并不计算；join=双流按关联键在窗口内逐行匹配（不等同 union）。表达式经沙箱求值（simpleeval 安全子集）' },
    ],
    summary: (d) => {
      const t = String(d.fuseType ?? 'union')
      const label = ({ union: 'union 合并', join: 'join 关联', window: '窗口聚合', filter: 'filter 过滤', map: 'map 字段映射' } as Record<string, string>)[t] ?? t
      if (t === 'join') return `${label}（${d.joinKeyLeft || '?'} = ${d.joinKeyRight || '?'}，${numOr(d.joinWindowSec, 60)}s）`
      if (t === 'window') return `窗口聚合（${String(d.windowType ?? 'tumbling')} ${numOr(d.windowSizeSec, 60)}s）`
      return label
    },
    /* I8 页面化：吞吐/窗口触发 运行浮窗 */
    page: { title: '流融合运行详情', comp: StreamNodePage, w: 620, h: 460 },
  },
  stream_output: {
    type: 'stream_output',
    initTemplate: { rect: { w: 200, h: 64 }, props: { outType: 'api', keepLast: 100, schemaText: '' } },
    label: '流输出', icon: '⇨', color: '#059669', code: 'C20', categories: ['stream'],
    desc: '流输出汇：API 订阅（SSE/WS/轮询）/ 目标库表 / Kafka topic / 文件滚动（四通道）',
    defaults: {
      outType: 'api',
      /* api 通道 */
      keepLast: 100, schemaText: '',
      /* 库表通道 */
      outDs: '', outTable: '', outFieldMap: [] as Record<string, string>[], uniqueKey: '', outBatchSize: 500,
      /* kafka 通道 */
      kafkaBrokers: '', kafkaTopic: '',
      /* 文件通道 */
      outPath: '', rollBy: 'size', rollSizeMb: 10, rollMinutes: 60,
    },
    form: [
      { key: 'outType', label: '输出通道', type: 'select', options: [
        { value: 'api', label: 'API 订阅（SSE/WebSocket/轮询）' }, { value: 'table', label: '目标库表' },
        { value: 'kafka', label: 'Kafka topic' }, { value: 'file', label: '文件滚动' },
      ] },
      /* —— api —— */
      { key: 'keepLast', label: '保留窗口（Last-N 条）', type: 'number', showIf: (d) => d.outType === 'api' },
      { key: 'schemaText', label: '字段 schema 声明（逗号分隔，供大屏/前端列渲染）', type: 'text',
        placeholder: '如 category,amt,cnt', showIf: (d) => d.outType === 'api' },
      { key: 'apiHint', label: '', type: 'hint',
        text: () => '端点：GET /api/v1/stream-jobs/{id}/data?mode=poll|sse（+ /ws WebSocket）；鉴权沿用平台 token；页面化展示即大屏联调形态',
        showIf: (d) => d.outType === 'api' },
      /* —— table —— */
      { key: 'outDs', label: '目标数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] }, required: true, showIf: (d) => d.outType === 'table' },
      { key: 'outTable', label: '目标表名', type: 'resource', cap: { mode: 'table', dsKey: 'outDs', writeAs: 'table' }, required: true, showIf: (d) => d.outType === 'table' },
      { key: 'outFieldMap', label: '字段映射（目标 ← 流字段，留空 = 同名全列）', type: 'rows', rowsKind: 'kv', showIf: (d) => d.outType === 'table' },
      /* dataScope: 唯一键列必须在上游流表真实存在，否则 upsert 运行时才炸（配置期即拦） */
      { key: 'uniqueKey', label: '唯一键列（填则 upsert，留空 = 追加插入）', type: 'text', dataScope: 'upstream-columns', showIf: (d) => d.outType === 'table' },
      { key: 'outBatchSize', label: '批量触发（条数，另 1s 定时兜底）', type: 'number', showIf: (d) => d.outType === 'table' },
      /* —— kafka —— */
      { key: 'kafkaBrokers', label: 'Broker 地址', type: 'text', placeholder: 'host:9092', required: true, showIf: (d) => d.outType === 'kafka' },
      { key: 'kafkaTopic', label: '目标 Topic', type: 'text', required: true, showIf: (d) => d.outType === 'kafka' },
      /* —— file —— */
      { key: 'outPath', label: '输出文件路径（/datara/files 相对）', type: 'text', placeholder: '如 out/rt_orders.jsonl', required: true, showIf: (d) => d.outType === 'file' },
      { key: 'rollBy', label: '滚动策略', type: 'select', options: [
        { value: 'size', label: '按大小切分' }, { value: 'time', label: '按时间切分' },
      ], showIf: (d) => d.outType === 'file' },
      { key: 'rollSizeMb', label: '单文件上限（MB）', type: 'number', showIf: (d) => d.outType === 'file' && d.rollBy === 'size' },
      { key: 'rollMinutes', label: '滚动周期（分钟）', type: 'number', showIf: (d) => d.outType === 'file' && d.rollBy === 'time' },
    ],
    summary: (d) => {
      const t = String(d.outType ?? 'api')
      if (t === 'api') return `API 订阅（Last-${numOr(d.keepLast, 100)}）`
      if (t === 'table') return `库表 ${d.outTable || '未配置目标表'} @ ${d.outDs || '未选数据源'}`
      if (t === 'kafka') return `Kafka → ${d.kafkaTopic || '未配置 topic'}`
      return `文件 ${d.outPath || '未配置路径'}`
    },
    /* I8 页面化：实时数据展示页（SSE 刷新，大屏联调形态） */
    page: { title: '实时数据展示', comp: StreamDataPage, w: 680, h: 460 },
  },
  page_board: {
    type: 'page_board',
    initTemplate: { rect: { w: 200, h: 64 }, props: { preset: 'ecommerce', boardLayout: 'auto' }, sample: {} },
    label: '页面组件', icon: '▤', color: '#0e7490', categories: ['stream'],
    desc: '实时看板页面组件：消费本画布流任务 API 输出通道数据，指标卡/趋势曲线/分布/告警/明细按字段特征自适应渲染（不参与管道装配）',
    nonExecutable: true,  // G-22：第三渲染分类——不产生任务实例、不参与 _execute_node
    defaults: { preset: 'ecommerce', boardLayout: 'auto' },  // G-18：boardLayout 抽到 data 层（可版本化）
    form: [
      { key: 'preset', label: '看板模板', type: 'select', options: [
        { value: 'ecommerce', label: '电商实时大盘' }, { value: 'iot', label: 'IoT 设备监控' },
        { value: 'visit', label: '站点访问分析' }, { value: 'custom', label: '自定义（按字段自适应）' },
      ] },
      /* G-18 修复：boardLayout 抽到 data 层——布局可版本化/迁移（不再硬编码在 BoardPage 内） */
      { key: 'boardLayout', label: '布局模式', type: 'select', options: [
        { value: 'auto', label: '自适应（按字段特征自动选卡片+图表）' },
        { value: 'metrics', label: '仅指标卡' },
        { value: 'trend', label: '仅趋势曲线' },
        { value: 'full', label: '指标卡+趋势+分布' },
      ] },
      { key: 'boardHint', label: '', type: 'hint',
        text: () => '数据源 = 本画布流任务的 API 输出通道（SSE/轮询）；窗口行按 win_start 分桶：最新窗口渲染指标卡/分布，历史窗口渲染趋势曲线；告警等事件行单独列出' },
    ],
    summary: (d) => ({
      ecommerce: '电商实时大盘', iot: 'IoT 设备监控', visit: '站点访问分析',
    } as Record<string, string>)[String(d.preset ?? 'custom')] ?? '自定义看板',
    /* I11 页面化：实时看板浮窗（指标卡/曲线/饼图/告警/明细） */
    page: { title: '实时看板', comp: BoardPage, w: 820, h: 560 },
  },

  /* ================= E 变量（C21：I7 注册转可用） ================= */
  variable: {
    type: 'variable',
    initTemplate: { rect: { w: 160, h: 48 }, props: { vars: [ { name: 'wf.period', value: '20261001', type: 'literal', override: false } ] }, bindings: { body: { kind: 'variable', fallback: '变量值' } }, sample: {} },
    label: '变量组件', icon: '$', color: '#7c2d12', code: 'C21', categories: ['general', 'sync', 'etl'],
    desc: '运行至本节点时将变量表注入实例运行时变量存储（工作流级层），供下游与条件区块引用',
    defaults: {
      vars: [
        { name: 'wf.period', value: '20261001', type: 'literal', override: false },
      ] as VarDef[],
    },
    form: [
      { key: 'vars', label: '变量表（名/值/类型/覆盖）', type: 'rows', rowsKind: 'var' },
      { key: 'varHint', label: '', type: 'hint',
        text: () => '下游以 $[wf.变量名] 引用；类型=字面量原样注入 / 表达式运行时求值 / 时间变量按 F49 模板（如 yyyyMMdd-1）；覆盖开关控制同名定义级变量取值；引用优先级：节点参数>工作流变量>环境组>全局' },
    ],
    summary: (d) => varSummary(d),
  },

  /* ================= G I12 组件（C24 文件入仓执行 / C25 数据校验 / C26 通知） ================= */
  file_sync: {
    type: 'file_sync',
    initTemplate: { rect: { w: 200, h: 64 }, props: { fileType: 'csv', delimiter: ',', encoding: 'utf-8', headerRows: 1, autoCreate: true, writeMode: 'append', flagColumn: 'src_schema', fieldMap: [] } },
    label: '文件入仓执行', icon: '⇥', color: '#0d9488', code: 'C24', categories: ['sync'],
    /* 同步编排端点合一：file_sync 降级为运行态执行组件——设计态画布/palette/校验均排除，schema 保留供运行实例详情渲染；
       运行图由 master 引擎按 endpoint_select.baseMode=file_sync 物化插入（id 前缀 sys_exec_） */
    runtimeOnly: true,
    desc: '运行态执行组件（runtimeOnly，设计态画布不出现）：文件路径/类型/目标端由 master 引擎运行时合并自 endpoint_select（baseMode=file_sync），此处仅保留写入模式等兜底参数；Excel/CSV/TXT 共享卷直读或运行时节点 SFTP 拉取暂存，自动建表，日志输出读/写/忽略三行数（批次号=instance_id）',
    defaults: {
      fileType: 'csv', delimiter: ',', encoding: 'utf-8', headerRows: 1,
      autoCreate: true, writeMode: 'append', flagColumn: 'src_schema',
      fieldMap: [] as Record<string, string>[],
    },
    form: [
      { key: 'chainHint', label: '', type: 'hint', text: () =>
        '业务配置在端点选择节点完成（基准类型=文件同步：文件路径/类型/编码 + 目标端数据源/表/自动建表）；本节点仅以下兜底参数生效（合并配置优先）' },
      { key: 'writeMode', label: '写入模式', type: 'select', options: [
        { value: 'append', label: '追加（union 合并）' },
        { value: 'overwrite', label: '覆盖（先 TRUNCATE）' },
        { value: 'src_flag', label: '标识列（每行落来源文件标识）' },
      ] },
      { key: 'flagColumn', label: '标识列名', type: 'text', showIf: (d) => d.writeMode === 'src_flag' },
      { key: 'autoCreate', label: '目标表不存在时自动建表（按文件表头推断类型）', type: 'bool' },
    ],
    summary: (d) => `文件入仓（${String(d.writeMode ?? 'append')}，运行态，配置经 master 合并）`,
  },
  assert: {
    type: 'assert',
    initTemplate: { rect: { w: 180, h: 56 }, props: { assertSrc: 'upstream', assertUpstream: '', assertDs: '', assertTable: '', rules: [ { key: 'rows', value: 'min=1,max=1000000', note: '行数区间' } ], ruleColumns: [], onFail: 'fail' } },
    label: '数据校验', icon: '⚑', color: '#dc2626', code: 'C25', categories: ['etl', 'general'],
    desc: '数据校验闸门（master 内联）：行数区间/主键唯一/非空率/自定义 SQL 断言；通过走「通过」出口，不达标走「不通过」出口或断流失败（onFail）',
    defaults: ASSERT_BASE(),
    ports: () => [{ id: 'success', label: '通过' }, { id: 'failure', label: '不通过' }],
    /* M-B2 八段 DSL 迁移：showIf → conditions；summary 函数 → render.summary；hint 函数字面量化 */
    form: [
      { key: 'assertSrc', label: '校验对象', type: 'select', group: '校验对象', groupHint: '校验上游产出的表，还是手选一张表',
        options: [
        { value: 'upstream', label: '上游节点（自动取目标表）' },
        { value: 'manual', label: '手选数据源与表' },
      ] },
      /* I12 T11 修：上游节点引用下拉（Inspector 取画布直接上游，选中写回节点 id；空=自动扫描兜底） */
      { key: 'assertUpstream', label: '上游节点引用（可选）', type: 'resource', cap: { mode: 'upstreamNodes' } },
      { key: 'assertDs', label: '校验数据源', type: 'resource', cap: { mode: 'datasource', dsTypes: ['mysql', 'greatdb'] }, required: true },
      { key: 'assertTable', label: '校验表（schema → 表）', type: 'resource', cap: { mode: 'table', dsKey: 'assertDs', writeAs: 'schemaTable' }, required: true },
      { key: 'rules', label: '规则集（key=规则，value=参数）', type: 'rows', rowsKind: 'kv', required: true,
        group: '校验规则', groupHint: '行数/唯一/非空/自定义 SQL，按 key 逐行配置' },
      /* I12 T11 修：规则列参考——仅手选模式（表已定）可勾选列名辅助填参；上游模式对象表运行时才定，参数手填 */
      { key: 'ruleColumns', label: '规则列参考（手选表字段，可选）', type: 'resource',
        cap: { mode: 'column', dsKey: 'assertDs', tableKey: 'assertTable' } },
      /* 决策 5：空 label hint → 固定文案 */
      { key: 'rulesHint', label: '规则说明', type: 'hint', group: '校验规则',
        text: '规则 key 与参数：rows（min=1,max=1000 行数区间）/ unique（列名，逗号分隔联合唯一）/ not_null（列名,阈值%，如 name,95）/ sql（断言语句，首行首列=1 通过）；校验对象=上游时可显式指定「上游节点引用」（未选则自动解析 同步执行写端表 / 文件入仓目标表 / SQL 声明结果表）；手选模式可先在「规则列参考」勾选列名再填入 unique/not_null 参数；上游引用模式对象表运行时才定，规则参数手填' },
      { key: 'onFail', label: '不达标动作', type: 'select', group: '不达标处理', groupHint: '决定走「不通过」出口还是直接断流',
        options: [
        { value: 'fail', label: '断流失败（节点 failure）' },
        { value: 'warn', label: '告警继续（走「不通过」出口）' },
      ] },
    ],
    conditions: [
      { id: 'c-upstream', when: { field: 'assertSrc', op: 'eq', value: 'upstream' }, show: ['assertUpstream'] },
      { id: 'c-manual', when: { field: 'assertSrc', op: 'eq', value: 'manual' }, show: ['assertDs', 'assertTable', 'ruleColumns'] },
    ],
    render: { summary: '数据校验' },
  },
  notify: {
    type: 'notify',
    initTemplate: { rect: { w: 160, h: 48 }, props: { channel: 'log', url: '', template: '', trigger: 'on_success', failHard: false }, bindings: { body: { kind: 'variable', fallback: '通知内容' } }, sample: {} },
    label: '通知', icon: '✉', color: '#7c3aed', code: 'C26', categories: ['general', 'stream', 'etl'],
    desc: '工作流/分支收尾通知：webhook POST 或仅日志（触发时机留痕；webhook 失败默认仅告警不断流，可开断流开关）',
    defaults: { ...NOTIFY_BASE },
    /* M-B2 八段 DSL 迁移：showIf → conditions；summary 函数 → render.summary；hint 函数字面量化 */
    form: [
      { key: 'channel', label: '通道', type: 'select', group: '通知通道', groupHint: '仅留痕日志或推送到外部系统',
        options: [
        { value: 'log', label: '仅日志' }, { value: 'webhook', label: 'Webhook' },
      ] },
      { key: 'url', label: 'Webhook URL', type: 'text', placeholder: 'http://…（支持 ${var} 变量引用）', required: true },
      { key: 'trigger', label: '触发时机', type: 'select', group: '触发与内容', options: [
        { value: 'on_success', label: '上游成功' }, { value: 'on_failure', label: '上游失败' },
        { value: 'always', label: '无论成败' },
      ] },
      { key: 'template', label: '消息模板', type: 'text', multiline: true,
        placeholder: '${wf.name} 实例 ${instance_id} 节点 ${node.name} ${node.status} @ ${sys.now}' },
      /* 决策 5：空 label hint → 固定文案 */
      { key: 'notifyHint', label: '消息模板说明', type: 'hint', group: '触发与内容',
        text: 'webhook 以 {"text": 消息} JSON POST（超时 10s，失败不重试）；消息经四级变量链解析：${wf.name} ${instance_id} ${node.name} ${node.status} ${sys.now}' },
      { key: 'failHard', label: '通知失败断流', type: 'bool', group: '失败策略',
        placeholder: '开启后 webhook 发送失败将节点置 failure（缺省仅告警）' },
    ],
    conditions: [
      { id: 'c-webhook-url', when: { field: 'channel', op: 'eq', value: 'webhook' }, show: ['url'] },
    ],
    render: { summary: '通知' },
  },

  /* ================= F63 模板（demo_pipeline，可拖；展开后不保留占位节点） ================= */
  demo_pipeline: {
    type: 'demo_pipeline',
    /* §11 模板初始化核查：F63 聚合模板组件，拖入即 materializeTemplate 展开节点链
       （不走 applyInitTemplate 链），form=[] 无业务 props 可创作（G-03 禁幽灵字段） */
    initTemplate: { rect: { w: 200, h: 64 }, props: {}, sample: {} },
    label: '示例管道模板', icon: '✦', color: '#16a34a', code: '', categories: ['general'],
    desc: '演示模板：展开为 开始 → SQL 占位 → 结束 三节点链（设计时物化，引擎零改动）',
    form: [],
    template: {
      modes: [
        {
          key: 'min', label: '最小管道', desc: '开始 → SQL 占位 → 结束',
          build(ctx) {
            const base = ctx.pos
            const nStart: GNode = { id: uid('nd'), type: 'start', position: { x: base.x, y: base.y }, data: { name: '开始' } }
            const nSql: GNode = { id: uid('nd'), type: 'sql', position: { x: base.x + 200, y: base.y }, data: { name: 'SQL 节点', datasource: '', sql: '', pre: '', post: '' } }
            const nEnd: GNode = { id: uid('nd'), type: 'end', position: { x: base.x + 400, y: base.y }, data: { name: '结束' } }
            const e1: GEdge = { id: uid('e'), source: nStart.id, target: nSql.id, kind: 'flow' }
            const e2: GEdge = { id: uid('e'), source: nSql.id, target: nEnd.id, kind: 'flow' }
            return { nodes: [nStart, nSql, nEnd], edges: [e1, e2] }
          },
        },
      ],
    },
  },
}

export const dagProfile: ViewProfile = {
  id: 'dag',
  name: 'DAG 编排',
  mode: 'edit',
  defaultEdge: 'flow',
  layout: 'dagre',
  layoutDir: 'TB',
  floats: [
    /* 同步编排重构：原「源表基准/目标表基准」中心数据源浮窗（SourceBasePanel/TargetBasePanel）已删除，
       业务配置统一由 C29~C31 编排组件展开的细项节点表单承载 */
  ],
  edgeKinds: {
    flow: { kind: 'flow', label: '流程依赖', color: '#64748b' },
    branch: { kind: 'branch', label: '条件分支', color: '#d97706' },
    branch_true: { kind: 'branch_true', label: '满足分支', color: '#16a34a' },
    branch_false: { kind: 'branch_false', label: '不满足分支', color: '#e5484d' },
    dep: { kind: 'dep', label: '跨流依赖', color: '#7c3aed', dashed: true },
  },
  palette: [
    { name: '逻辑控制', items: [
      { type: 'start' }, { type: 'end' }, { type: 'conditions' }, { type: 'switch' }, { type: 'fork' },
      { type: 'join' }, { type: 'merge' }, { type: 'delay' }, { type: 'dependent' }, { type: 'loop' },
    ] },
    { name: '数据计算', items: [
      { type: 'sql' }, { type: 'shell' }, { type: 'python' }, { type: 'ssh' },
      { type: 'procedure' }, { type: 'http' }, { type: 'file' }, { type: 'assert' },
    ] },
    { name: '数据同步', items: [
      { type: 'src_base_orch' },
      { type: 'tgt_base_orch' },
      { type: 'file_sync_orch' },
      { type: 'endpoint_select' },
      { type: 'field_map' },
      { type: 'field_map_union' },
      { type: 'condition_set' },
    ] },
    { name: '流处理', items: [
      { type: 'stream_input' }, { type: 'stream_fuse' }, { type: 'stream_output' }, { type: 'page_board' },
    ] },
    { name: '变量', items: [
      { type: 'variable' },
    ] },
    { name: '通用', items: [
      { type: 'notify' },
    ] },
    { name: '运维/自检', items: [
      { type: 'smoke' },
    ] },
    { name: '模板', items: [
      { type: 'demo_pipeline' },
    ] },
  ],
  nodeTypes,
  validators: [
    (doc) => {
      const cyc = detectCycle(doc)
      return cyc.length ? [{
        level: 'error',
        msg: `依赖存在环：${cyc.map((id) => doc.nodes.find((n) => n.id === id)?.data.name ?? id).join('、')}（DAG 不允许成环）`,
        nodeId: cyc[0],
      }] : []
    },
    (doc) => findBrokenEdges(doc).map((eid) => ({
      level: 'error' as const, msg: '边引用了不存在的节点（断链）', edgeId: eid,
    })),
    (doc) => {
      const starts = doc.nodes.filter((n) => n.type === 'start')
      const issues = [] as { level: 'error' | 'warn'; msg: string; nodeId?: string }[]
      if (starts.length === 0) issues.push({ level: 'error', msg: '缺少「开始」节点' })
      if (starts.length > 1) issues.push({ level: 'error', msg: `「开始」节点只能有一个（当前 ${starts.length}）`, nodeId: starts[1].id })
      const ends = doc.nodes.filter((n) => n.type === 'end')
      if (ends.length > 1) issues.push({ level: 'warn', msg: `「结束」节点建议只保留一个（当前 ${ends.length}）`, nodeId: ends[1].id })
      return issues
    },
    (doc) => doc.nodes.length <= 2 ? [] : findIsolated(doc)
      .map((id) => ({ level: 'warn' as const, msg: `孤立节点「${doc.nodes.find((n) => n.id === id)?.data.name}」未接入流程`, nodeId: id })),
    (doc) => findDuplicateEdges(doc).map((eid) => ({
      level: 'warn' as const, msg: '存在重复依赖边', edgeId: eid,
    })),
    /* I8 流子图校验（混编/源汇缺失/join 入边/游离，保存与试运行共用语义） */
    (doc) => streamSubgraphIssues(doc),
    /* W1 必填完整性：required 字段在当前分型下为空即「未配置」（画布角标/校验面板/保存闸门共用判定）；
       端点合一：runtimeOnly 执行组件（sync/file_sync）不参与设计态画布校验 */
    (doc) => doc.nodes.flatMap((n) => {
      const s = nodeTypes[n.type]
      if (!s || s.runtimeOnly) return []
      return requiredMissing(s, n.data).map((lb) => ({
        level: 'warn' as const,
        msg: `「${String(n.data.name ?? n.id)}」必填项未配置：${lb}`,
        nodeId: n.id,
      }))
    }),
    /* G-25：「结束」节点出度必须为 0（语义：流程出口后不得再连出边）——G-22 统一为 maxOut 校验 */
    (doc) => doc.nodes.filter((n) => {
      const schema = nodeTypes[n.type]
      return schema && schema.maxOut === 0
    }).flatMap((n) => {
      const out = doc.edges.filter((e) => e.source === n.id)
      return out.length ? [{
        level: 'error' as const,
        msg: `「${String(n.data.name ?? n.id)}」是结束节点，后禁止连出边（当前 ${out.length} 条出边）`,
        nodeId: n.id,
      }] : []
    }),
    /* G-22：逐组件自定义 validators 执行（schema.validators 非空时追加） */
    (doc) => doc.nodes.flatMap((n) => {
      const schema = nodeTypes[n.type]
      if (!schema || !schema.validators) return []
      return schema.validators(n, doc).map((v) => ({ ...v, nodeId: n.id }))
    }),
    /* 分支完整性：条件/多路分支须配置分支，且每个分支端点应连接下游；runtimeOnly 执行组件同口径排除 */
    (doc: GraphDocument) => {
      const issues: { level: 'error' | 'warn'; msg: string; nodeId?: string }[] = []
      doc.nodes.forEach((n) => {
        const schema = nodeTypes[n.type]
        if (!schema || schema.runtimeOnly || !schema.ports) return
        const ports = schema.ports(n.data)
        if (ports.length === 0) {
          issues.push({ level: 'error', msg: `「${n.data.name}」未配置分支条件`, nodeId: n.id })
          return
        }
        const out = doc.edges.filter((e) => e.source === n.id)
        ports.forEach((p) => {
          const linked = out.some((e) => (e.sourceHandle ?? '') === p.id || e.label === p.label)
          if (!linked) issues.push({ level: 'warn', msg: `「${n.data.name}」分支「${p.label}」未连接下游`, nodeId: n.id })
        })
      })
      return issues
    },
  ],
}
