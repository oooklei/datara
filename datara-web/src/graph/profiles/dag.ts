/**
 * dag profile：DAG 工作流编排视角（对齐 DolphinScheduler / n8n 最佳实践）。
 * I1 palette 重构（§11）：
 * - 逻辑控制 10 个全可用（C1~C10，补组件编号）；
 * - 移除 sub_process（意见③ 不设）与全部 ETL 算子节点类型（spark/flink/cdc/datax/dq/qgate 等）；
 * - I3：数据计算 C11~C14（SQL/Shell/Python/SSH）转可用；
 * - I4：C15/C16/C22（存储过程/HTTP/文件读取）转可用，表单对齐 worker 执行器参数键；
 * - I6：C17 数据同步/C23 同步编排模板转可用（业务表单 + 两套模板 build，palette 解禁）；
 * - I7：C21 变量组件注册（var-table 业务表单+示例行+palette 解禁）；C9 dependent 表单升级（deps-list 依赖项编辑器）；
 * - I8：C18~C20 流处理注册转可用（四源/五算子/四通道分型表单 + 页面化运行浮窗/实时数据展示页）+ 流子图校验；
 * - I12 T11：C24 文件同步 / C25 数据校验（master 内联 success/failure 双出口）/ C26 通知注册转可用（page_board 让出 C24 编号）；
 * - F63 模板：demo_pipeline（拖入 → 模式选择 → 设计时物化展开为普通节点链）。
 */
import { detectCycle, findBrokenEdges, findDuplicateEdges, findIsolated, uid } from '../model'
import type { GraphDocument, GEdge, GNode } from '../model'
import type { BranchDef, DependentDef, NodeSchema, VarDef, ViewProfile } from './types'
import { c17IsConnReader, c17IsFileReader, c17OnReaderTypeChange, c17SqlPreview, c22OnModeChange, requiredMissing, tmpRefHint } from './formLinkage'
import NodeRunDetailPage from '../workbench/pages/NodeRunDetailPage.vue'
import SqlPreviewPage from '../workbench/pages/SqlPreviewPage.vue'
import TmpPreviewPage from '../workbench/pages/TmpPreviewPage.vue'
import StreamNodePage from '../workbench/pages/StreamNodePage.vue'
import StreamDataPage from '../workbench/pages/StreamDataPage.vue'
import BoardPage from '../workbench/pages/BoardPage.vue'
import SourceBasePanel from '../workbench/panels/SourceBasePanel.vue'
import TargetBasePanel from '../workbench/panels/TargetBasePanel.vue'

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

/** C17 节点 data 默认值（键名对齐 worker/executors/sync.py 参数契约；文件参数/增量条件平铺键） */
const syncDefaults = (strategy: 'union' | 'src_flag'): Record<string, unknown> => ({
  readerType: 'mysql', readerDs: '', readerTable: '',
  readerFormat: 'csv', readerPath: '', readerEncoding: 'utf-8', readerDelimiter: ',', readerHeader: true, readerSheet: '',
  readerSchemasText: '', autoSchema: true,
  incrementalColumn: '', incrementalExpr: '',
  writerType: 'mysql', writerDs: '', writerTable: '',
  autoCreate: true, truncate: false,
  strategy, flagColumn: 'src_schema',
  fieldMap: [] as Record<string, string>[],
  batchSize: 1000, errorThreshold: 0,
})

/** C23 模板链构造（设计 §3.2）：开始 → 数据同步 → 对账校验 → 结束，差异仅 C17 defaults 策略 */
const buildSyncChain = (strategy: 'union' | 'src_flag') =>
  (ctx: { doc: GraphDocument; pos: { x: number; y: number } }): { nodes: GNode[]; edges: GEdge[] } => {
    const base = ctx.pos
    const nStart: GNode = { id: uid('nd'), type: 'start', position: { x: base.x, y: base.y }, data: { name: '开始' } }
    const nSync: GNode = { id: uid('nd'), type: 'sync', position: { x: base.x + 200, y: base.y }, data: { name: '数据同步', ...syncDefaults(strategy) } }
    const nSql: GNode = {
      id: uid('nd'), type: 'sql', position: { x: base.x + 400, y: base.y },
      data: { name: '对账校验', datasource: '', pre: '', post: '', sql: '-- 对账校验：比对源与目标行数（数据源与目标表名请替换）\nSELECT COUNT(*) AS target_rows FROM 目标表' },
    }
    const nEnd: GNode = { id: uid('nd'), type: 'end', position: { x: base.x + 600, y: base.y }, data: { name: '结束' } }
    const e1: GEdge = { id: uid('e'), source: nStart.id, target: nSync.id, kind: 'flow' }
    const e2: GEdge = { id: uid('e'), source: nSync.id, target: nSql.id, kind: 'flow' }
    const e3: GEdge = { id: uid('e'), source: nSql.id, target: nEnd.id, kind: 'flow' }
    return { nodes: [nStart, nSync, nSql, nEnd], edges: [e1, e2, e3] }
  }

const portsOf = (data: Record<string, unknown>) =>
  branchListOf(data).map((b) => ({ id: b.id, label: b.name }))

/* I12 R1 归属约定：C24 file_sync=['sync','general']；C25 assert=['etl','general']；C26 notify=['general','stream','etl']（T11 已注册三组件，page_board 不再占用编号） */

const nodeTypes: Record<string, NodeSchema> = {
  /* ================= A 逻辑控制（C1~C10，全可用） ================= */
  start: {
    type: 'start', label: '开始', icon: '▶', color: '#16a34a', code: 'C1', categories: ['general', 'sync', 'etl'], desc: '工作流启动节点（运行实例编号 instance_id 由此生成）',
    form: [], defaults: {},
    summary: () => '工作流入口',
    /* F61 页面化演示位：节点运行详情（real 走 /api/v1/instances，mock 空态） */
    page: { title: '节点运行详情', comp: NodeRunDetailPage, w: 560, h: 340 },
  },
  end: {
    type: 'end', label: '结束', icon: '■', color: '#64748b', code: 'C2', categories: ['general', 'sync', 'etl'], desc: '工作流结束节点',
    form: [], defaults: {},
    summary: () => '工作流出口',
  },
  conditions: {
    type: 'conditions', label: '条件分支', icon: '⑃', color: '#d97706', code: 'C3', categories: ['general', 'sync', 'etl'],
    desc: '按条件走向不同分支（对齐 DS 条件分支 / n8n IF）',
    defaults: {
      branches: [
        { id: 'br_yes', name: '满足', expr: '${var} > 0' },
        { id: 'br_no', name: '不满足', expr: '' },
      ] as BranchDef[],
    },
    form: [{ key: 'branches', label: '条件分支（每分支独立端点）', type: 'branches' }],
    ports: portsOf,
    summary: (d) => branchListOf(d).map((b) => b.name).join(' / ') || '未配置分支',
  },
  switch: {
    type: 'switch', label: '切换', icon: '⑄', color: '#b45309', code: 'C4', categories: ['general', 'sync', 'etl'],
    desc: '按变量值匹配多路分发（对齐 DS Switch）',
    defaults: {
      branches: [
        { id: 'sw_a', name: 'A', expr: 'A' },
        { id: 'sw_b', name: 'B', expr: 'B' },
        { id: 'sw_d', name: '默认', expr: '*' },
      ] as BranchDef[],
    },
    form: [{ key: 'branches', label: '分发分支（匹配值）', type: 'branches' }],
    ports: portsOf,
    summary: (d) => `${branchListOf(d).length} 路分发`,
  },
  fork: {
    type: 'fork', label: '并行分叉', icon: '⋔', color: '#ca8a04', code: 'C5', categories: ['general', 'sync', 'etl'],
    desc: '单输入多路并行下发（下游同时触发）',
    defaults: { parallel: 2 },
    form: [{ key: 'parallel', label: '并行度', type: 'number' }],
    summary: (d) => `并行度 ${d.parallel ?? 2}`,
  },
  join: {
    type: 'join', label: '汇合（AND）', icon: '⨝', color: '#0f766e', code: 'C6', categories: ['general', 'sync', 'etl'],
    desc: '等待全部上游分支完成后触发',
    defaults: {},
    form: [],
    summary: () => '全部上游完成（AND）',
  },
  merge: {
    type: 'merge', label: '合并（OR）', icon: '∪', color: '#0284c7', code: 'C7', categories: ['general', 'sync', 'etl'],
    desc: '任一上游完成即触发（抢先合并）',
    defaults: {},
    form: [],
    summary: () => '任一上游完成（OR）',
  },
  delay: {
    type: 'delay', label: '延时执行', icon: '⏱', color: '#57534e', code: 'C8', categories: ['general', 'sync', 'etl'],
    desc: '延时/定时后再执行下游（支持时间变量到点延时）',
    defaults: { duration: 60, unit: '秒' },
    form: [
      { key: 'duration', label: '延时时长', type: 'number' },
      { key: 'unit', label: '单位', type: 'select', options: [
        { value: '秒', label: '秒' }, { value: '分', label: '分' }, { value: '时', label: '时' },
      ] },
    ],
    summary: (d) => `延时 ${d.duration ?? 0}${String(d.unit ?? '秒')}`,
  },
  dependent: {
    type: 'dependent', label: '依赖', icon: '⧉', color: '#7c3aed', code: 'C9', categories: ['general', 'sync', 'etl'],
    desc: '依赖其他工作流/节点产出：所配依赖各自最近一次实例中节点终态=success 即通过（I7 简化语义，周期/批次走变量条件）',
    defaults: { deps: [] as DependentDef[] },
    form: [{ key: 'deps', label: '依赖项列表', type: 'deps-list' }],
    summary: (d) => depSummary(d),
  },
  loop: {
    type: 'loop', label: '循环迭代', icon: '↻', color: '#c2410c', code: 'C10', categories: ['general', 'sync', 'etl'],
    desc: '按批次/条件循环执行子链路（自创，海豚无原生）',
    defaults: { collection: '', batchSize: 100 },
    form: [
      { key: 'collection', label: '迭代集合/参数', type: 'text', placeholder: '${loop_items}' },
      { key: 'batchSize', label: '批大小', type: 'number' },
    ],
    summary: (d) => `批次 ${d.batchSize ?? 0}`,
  },

  /* ================= B 数据计算（C11~C14 I3；C15/C16/C22 I4 注册转可用） ================= */
  sql: {
    type: 'sql', label: 'SQL', icon: '⌨', color: '#334155', code: 'C11', categories: ['etl', 'general', 'sync'],
    desc: '选择数据源执行 SQL（查询/非查询/DDL），页面化浮窗展示查询结果前 200 行',
    defaults: { datasource: '', sql: '', pre: '', post: '' },
    form: [
      { key: 'datasource', label: '数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'] },
      /* I12 T12：库/表侧栏选择器——经 GET /datasources/{id}/tree 点选库/表，把 SELECT 骨架插入 SQL 编辑器（追加不覆盖手写） */
      { key: 'sqlInsert', label: '库/表侧栏选择器（点选插入，不替代手写）', type: 'token-insert',
        pick: { dsKey: 'datasource', insertKey: 'sql' }, showIf: (d) => !!d.datasource },
      { key: 'sql', label: 'SQL 语句', type: 'textarea', placeholder: "INSERT INTO ... SELECT ..." },
      { key: 'pre', label: '前置 SQL', type: 'textarea' },
      { key: 'post', label: '后置 SQL', type: 'textarea' },
    ],
    summary: (d) => String(d.datasource ?? ''),
    /* F61 页面化：SQL 结果预览（worker result_preview 前 200 行，real 走实例详情） */
    page: { title: 'SQL 结果预览', comp: SqlPreviewPage, w: 620, h: 380 },
  },
  shell: {
    type: 'shell', label: 'Shell', icon: '❯', color: '#7c3aed', code: 'C12', categories: ['general', 'etl'],
    desc: '在运行时节点执行 Shell 脚本',
    defaults: { script: '' },
    form: [{ key: 'script', label: '脚本内容', type: 'textarea', placeholder: '#!/bin/bash ...' }],
    summary: () => 'Shell 脚本',
  },
  python: {
    type: 'python', label: 'Python', icon: 'Py', color: '#2563eb', code: 'C13', categories: ['general', 'etl'],
    desc: '在运行时节点执行 Python 脚本',
    defaults: { script: '' },
    form: [{ key: 'script', label: '脚本内容', type: 'textarea' }],
    summary: () => 'Python 脚本',
  },
  ssh: {
    type: 'ssh', label: 'SSH 脚本', icon: '⌖', color: '#475569', code: 'C14', categories: ['general', 'etl'],
    desc: '依托运行时节点 SSH 执行远程脚本；I7 支持按执行节点标签多主机路由（F53）',
    defaults: { runtimeNode: '', execNodeTag: '', script: '' },
    form: [
      { key: 'execNodeTag', label: '执行节点标签', type: 'exec-node-tag', placeholder: '留空则按下方运行时节点直连' },
      {
        key: 'runtimeNode', label: '运行时节点', type: 'runtime-node',
        showIf: (d) => !String(d.execNodeTag ?? '').trim(),
      },
      { key: 'script', label: '脚本内容', type: 'textarea', placeholder: '远端 bash 执行的脚本（经 stdin 下发）' },
    ],
    summary: (d) => (d.execNodeTag ? `SSH @ 标签:${d.execNodeTag}` : d.runtimeNode ? `SSH @ ${d.runtimeNode}` : 'SSH 远程脚本'),
  },
  procedure: {
    type: 'procedure', label: '存储过程', icon: '⚙', color: '#6d28d9', code: 'C15', categories: ['general', 'etl'],
    desc: '调用数据源存储过程（CALL），OUT 参数注册为输出参数 out_{key} 供下游引用',
    defaults: { datasource: '', db: '', procedure: '', args: [] },
    form: [
      { key: 'datasource', label: '数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'] },
      { key: 'db', label: '目标库（留空 = 数据源默认库）', type: 'text' },
      { key: 'procedure', label: '过程名', type: 'text', placeholder: '如 sp_i4_demo' },
      { key: 'args', label: '过程参数（IN 传值 / OUT 回读）', type: 'args-table' },
    ],
    summary: (d) => `${d.procedure || '未配置过程'} @ ${d.datasource || '未选数据源'}`,
  },
  http: {
    type: 'http', label: 'HTTP', icon: '⊕', color: '#4f46e5', code: 'C16', categories: ['general', 'etl'],
    desc: '调用外部 HTTP 接口：成功码校验 + 点路径提取响应子集为输出参数',
    defaults: {
      url: '', method: 'GET', headers: [], body: '', bodyType: 'json',
      successCodes: '2xx', extract: [], timeout: 30,
    },
    form: [
      { key: 'url', label: 'URL', type: 'text', placeholder: 'http://…' },
      { key: 'method', label: '方法', type: 'select', options: [
        { value: 'GET', label: 'GET' }, { value: 'HEAD', label: 'HEAD' },
        { value: 'POST', label: 'POST' }, { value: 'PUT', label: 'PUT' },
        { value: 'DELETE', label: 'DELETE' }, { value: 'PATCH', label: 'PATCH' },
      ] },
      { key: 'headers', label: '请求头（键值表）', type: 'kv-table' },
      { key: 'bodyType', label: '请求体类型', type: 'select',
        showIf: (d) => !['GET', 'HEAD'].includes(String(d.method ?? 'GET')),
        options: [{ value: 'json', label: 'JSON' }, { value: 'form', label: 'FORM' }] },
      { key: 'body', label: '请求体', type: 'textarea', placeholder: 'JSON 串或表单文本',
        showIf: (d) => !['GET', 'HEAD'].includes(String(d.method ?? 'GET')) },
      { key: 'successCodes', label: '成功状态码', type: 'text', placeholder: '逗号分隔，如 2xx,200（空 = 2xx）' },
      { key: 'extract', label: '响应提取（输出名 → 点路径）', type: 'kv-table' },
      { key: 'timeout', label: '超时（秒）', type: 'number' },
    ],
    summary: (d) => `${d.method ?? 'GET'} ${d.url || ''}`,
  },
  file: {
    type: 'file', label: '文件读取', icon: '▦', color: '#0e7490', code: 'C22', categories: ['general', 'etl'],
    desc: '读取 CSV/TXT/Excel 注册为临时工作数据，下游以 ${tmp.<名>} 引用；页面化预览检验网格',
    defaults: {
      mode: 'datasource', datasource: '',
      path: '', format: 'csv', encoding: 'utf-8', delimiter: ',', header: true, sheet: '',
      register: true, tmpName: '', kind: 'table', targetDs: '内置数仓-datara_dw',
      retention: 'immediate', keepDays: 7,
    },
    form: [
      { key: 'mode', label: '来源模式', type: 'select', options: [
        { value: 'datasource', label: '数据源中心文件源' },
        { value: 'manual', label: '手动参数' },
      ], onChange: c22OnModeChange },
      { key: 'datasource', label: '文件源数据源', type: 'datasource', dsTypes: ['file'],
        showIf: (d) => d.mode === 'datasource' },
      { key: 'path', label: '文件路径（/datara/files 相对）', type: 'text',
        placeholder: '如 samples/orders.csv', showIf: (d) => d.mode === 'manual' },
      { key: 'format', label: '格式', type: 'select', options: [
        { value: 'csv', label: 'CSV' }, { value: 'txt', label: 'TXT' }, { value: 'excel', label: 'Excel' },
      ], showIf: (d) => d.mode === 'manual' },
      { key: 'encoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }, { value: 'gb18030', label: 'GB18030' },
      ], showIf: (d) => d.mode === 'manual' },
      { key: 'delimiter', label: '分隔符', type: 'text', placeholder: ',',
        showIf: (d) => d.mode === 'manual' && String(d.format) !== 'excel' },
      { key: 'header', label: '首行表头', type: 'bool', placeholder: '首行为列名',
        showIf: (d) => d.mode === 'manual' && String(d.format) !== 'excel' },
      { key: 'sheet', label: 'Sheet 名称（留空 = 首个）', type: 'text',
        showIf: (d) => d.mode === 'manual' && String(d.format) === 'excel' },
      { key: 'register', label: '注册临时数据', type: 'bool', placeholder: '勾选后下游可用 ${tmp.<名>} 引用' },
      { key: 'tmpName', label: '临时数据名', type: 'text', placeholder: '小写字母开头 3~32 位 a-z0-9_',
        showIf: (d) => !!d.register },
      { key: 'kind', label: '临时数据形态', type: 'select', options: [
        { value: 'table', label: '临时表（全量物化）' },
        { value: 'resultset', label: '结果集引用（抽样 JSON）' },
        { value: 'file', label: '文件登记（仅路径+schema）' },
      ], showIf: (d) => !!d.register },
      { key: 'targetDs', label: '物化目标数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'],
        showIf: (d) => !!d.register && String(d.kind) === 'table' },
      { key: 'retention', label: '保留策略', type: 'select', options: [
        { value: 'immediate', label: '立即清理（实例终态清扫）' },
        { value: 'days', label: '保留 N 天' },
        { value: 'keep', label: '转正式表（实例成功后 RENAME）' },
      ], showIf: (d) => !!d.register },
      { key: 'keepDays', label: '保留天数', type: 'number',
        showIf: (d) => !!d.register && String(d.retention) === 'days' },
      { key: 'keepHint', label: '', type: 'hint',
        text: (d) => `转正式表：实例成功后临时表 RENAME 去前缀，正式表名 = 临时数据名 ${String(d.tmpName || '?')}（仅 table 形态生效）`,
        showIf: (d) => !!d.register && String(d.retention) === 'keep' },
      { key: 'tmpHint', label: '', type: 'hint', text: tmpRefHint, showIf: (d) => !!tmpRefHint(d) },
    ],
    summary: (d) => {
      const src = d.mode === 'manual' ? String(d.path || '未配置路径') : String(d.datasource || '未选数据源')
      return d.register ? `${src} → ${d.tmpName || '?'}（${String(d.kind ?? 'table')}）` : `${src}（不注册）`
    },
    /* F61 页面化：数据预览检验网格（t_tmp_data 抽样 + schema 推断 + 空值统计） */
    page: { title: '数据预览检验', comp: TmpPreviewPage, w: 680, h: 440 },
  },

  /* ================= C 数据同步（C17 I6 注册；C23 模板聚合） ================= */
  sync: {
    type: 'sync', label: '数据同步', icon: '⇄', color: '#0891b2', code: 'C17', categories: ['sync', 'general'],
    desc: '读写器分离的异构数据源同步（MySQL/GreatDB/文件 → MySQL/GreatDB；动态 schema 返选 + union/标识列/分区三策略）',
    defaults: syncDefaults('union'),
    form: [
      /* —— 读端 —— */
      { key: 'readerType', label: '读端类型', type: 'select', options: [
        { value: 'mysql', label: 'MySQL' }, { value: 'greatdb', label: 'GreatDB' },
        { value: 'csv', label: 'CSV 文件' }, { value: 'txt', label: 'TXT 文件' }, { value: 'excel', label: 'Excel 文件' },
      ], onChange: c17OnReaderTypeChange },
      { key: 'readerDs', label: '读端数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'], showIf: c17IsConnReader },
      { key: 'readerTable', label: '读端表名', type: 'table-picker', showIf: c17IsConnReader,
        pick: { dsKey: 'readerDs', writeAs: 'table' } },
      { key: 'readerSchemasText', label: '参与 schema（逗号分隔，留空 = 数据源默认库）', type: 'text',
        placeholder: '如 ec_retail_east,ec_retail_south', showIf: c17IsConnReader },
      { key: 'autoSchema', label: '新增 schema 自动纳入', type: 'bool',
        placeholder: '运行时 SHOW DATABASES 差集探测同名表自动加入分支', showIf: c17IsConnReader },
      { key: 'incrementalColumn', label: '增量列（可选）', type: 'text', placeholder: '如 create_time', showIf: c17IsConnReader },
      { key: 'incrementalExpr', label: '增量条件表达式', type: 'text', placeholder: '如 ${yyyyMMdd-1}（运行时变量替换后 > 比较）',
        showIf: (d) => c17IsConnReader(d) && !!d.incrementalColumn },
      { key: 'readerPath', label: '文件路径（/datara/files 相对）', type: 'text', placeholder: '如 samples/orders.csv', showIf: c17IsFileReader },
      { key: 'readerEncoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }, { value: 'gb18030', label: 'GB18030' },
      ], showIf: c17IsFileReader },
      { key: 'readerDelimiter', label: '分隔符', type: 'text', placeholder: ',',
        showIf: (d) => c17IsFileReader(d) && String(d.readerType) !== 'excel' },
      { key: 'readerHeader', label: '首行表头', type: 'bool', placeholder: '首行为列名',
        showIf: (d) => c17IsFileReader(d) && String(d.readerType) !== 'excel' },
      { key: 'readerSheet', label: 'Sheet 名称（留空 = 首个）', type: 'text',
        showIf: (d) => c17IsFileReader(d) && String(d.readerType) === 'excel' },
      /* —— 写端 —— */
      { key: 'writerType', label: '写端类型', type: 'select', options: [
        { value: 'mysql', label: 'MySQL' }, { value: 'greatdb', label: 'GreatDB' },
      ] },
      { key: 'writerDs', label: '写端数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'] },
      { key: 'writerTable', label: '目标表名', type: 'table-picker',
        pick: { dsKey: 'writerDs', writeAs: 'table' } },
      { key: 'autoCreate', label: '自动建表', type: 'bool', placeholder: '目标表不存在时按源结构创建' },
      { key: 'truncate', label: '写入前清空目标（TRUNCATE）', type: 'bool' },
      /* —— I8 反选探测：目标表为基准，探测源库同名/前缀匹配表并回填（见 Inspector probe 控件） —— */
      { key: 'probe', label: '反选探测（目标表 → 源库匹配）', type: 'probe', showIf: c17IsConnReader,
        probe: { dsKey: 'readerDs', tableKey: 'writerTable' } },
      /* —— 合并策略 —— */
      { key: 'strategy', label: '合并策略', type: 'select', options: [
        { value: 'union', label: 'union 合并（追加，不带来源标识）' },
        { value: 'src_flag', label: '标识列（每行落源 schema 标识）' },
        { value: 'partition', label: '分区隔离（按 schema 拆独立目标表）' },
      ] },
      { key: 'flagColumn', label: '标识列名', type: 'text', showIf: (d) => d.strategy === 'src_flag' },
      { key: 'sqlPreview', label: '', type: 'hint', text: c17SqlPreview,
        showIf: (d) => c17IsConnReader(d) && !!d.readerTable && ['union', 'src_flag'].includes(String(d.strategy)) },
      /* —— 字段映射 / 运行参数 —— */
      { key: 'fieldMap', label: '字段映射（源 → 目标，留空 = 同名全列）', type: 'kv-table' },
      { key: 'batchSize', label: '批大小', type: 'number' },
      { key: 'errorThreshold', label: '错误阈值（坏行容忍条数）', type: 'number' },
    ],
    summary: (d) => {
      const src = c17IsConnReader(d) ? `${d.readerDs || '未选源'}:${d.readerTable || '?'}` : `${d.readerType || '?'}:${d.readerPath || '未配置路径'}`
      return `${src} → ${d.writerTable || '未配置目标表'}（${String(d.strategy ?? 'union')}）`
    },
    /* F61 页面化：同步运行详情（读写行数/速率/坏行数/参与 schema，复用节点运行详情数据通道） */
    page: { title: '同步运行详情', comp: NodeRunDetailPage, w: 620, h: 420 },
  },
  sync_template: {
    type: 'sync_template', label: '同步编排', icon: '⇉', color: '#0369a1', code: 'C23', categories: ['sync'],
    desc: '同步编排模板：拖入选择模式展开为 开始 → 数据同步 → 对账校验 → 结束 节点链（设计时物化，保存自动打「同步」标签）',
    form: [],
    template: {
      modes: [
        {
          key: 'source_base', label: '源表基准', desc: '已知源库表，配置读写端一次到位（union 追加合并）',
          build: buildSyncChain('union'),
        },
        {
          key: 'target_base', label: '目标表基准', desc: '以目标表为基准动态返选多 schema 源（标识列 + 新增 schema 自动纳入）',
          build: buildSyncChain('src_flag'),
        },
      ],
    },
    summary: () => '同步编排模板',
  },

  /* ================= D 流处理（C18~C20：I8 注册转可用，四源/五算子/四通道） ================= */
  stream_input: {
    type: 'stream_input', label: '流输入', icon: '⇥', color: '#0d9488', code: 'C18', categories: ['stream'],
    desc: '流输入源（Source）：Kafka 消费 / CDC binlog / HTTP 拉取 / 文件尾随 / 模拟数据 / Redis Stream / MQTT（分型表单，行事件统一 {source, ts, data}）',
    defaults: {
      srcType: 'kafka',
      dsRef: '',  // 连接性注册化（09-21）：kafka/redis/mqtt/http 引用数据源中心注册源；空 = 内联高级模式
      /* kafka 分型（groupOverride：I12 T12 引用注册源时覆盖默认消费组开关） */
      brokers: '', topic: '', group: 'datara-flink', groupOverride: false, startFrom: 'earliest',
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
      { key: 'dsRef', label: '数据源引用（Kafka 注册源）', type: 'datasource', dsTypes: ['kafka'], showIf: (d) => d.srcType === 'kafka' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 Kafka 源（连接性由注册层保证，启动预检只校验引用与状态）；不选则下方手动填写连接参数（内联高级模式）。引用后 brokers 由注册源固定带出只读（连接层归一），topic 从注册源枚举选择，消费组默认 datara-flink（开「覆盖默认消费组」才可改）',
        showIf: (d) => d.srcType === 'kafka' },
      { key: 'brokers', label: 'Broker 地址（高级内联）', type: 'text', placeholder: 'host:9092（逗号分隔多个）', showIf: (d) => d.srcType === 'kafka' && !d.dsRef },
      /* I12 T12：引用注册源后 topic 升级 topic-select（注册源枚举带出）；内联模式保留手填 */
      { key: 'topic', label: 'Topic（注册源枚举）', type: 'topic-select', required: true,
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
      { key: 'cdcDs', label: 'CDC 数据源（引用 I4 注册）', type: 'datasource', dsTypes: ['mysql', 'greatdb'], required: true, showIf: (d) => d.srcType === 'cdc' },
      { key: 'schemasText', label: '库白名单（逗号分隔，留空 = 全库）', type: 'text', showIf: (d) => d.srcType === 'cdc' },
      { key: 'tablesText', label: '表白名单（逗号分隔，留空 = 全表）', type: 'text', showIf: (d) => d.srcType === 'cdc' },
      { key: 'posMode', label: 'binlog 位点', type: 'select', options: [
        { value: 'latest', label: '最新（当前 file:pos）' }, { value: 'earliest', label: '最早' },
        { value: 'custom', label: '指定 file:pos' },
      ], showIf: (d) => d.srcType === 'cdc' },
      { key: 'posFile', label: 'binlog 文件', type: 'text', placeholder: '如 binlog.000003', showIf: (d) => d.srcType === 'cdc' && d.posMode === 'custom' },
      { key: 'posPos', label: '位点偏移', type: 'number', showIf: (d) => d.srcType === 'cdc' && d.posMode === 'custom' },
      /* —— http —— */
      { key: 'dsRef', label: '数据源引用（HTTP 注册源）', type: 'datasource', dsTypes: ['http'], showIf: (d) => d.srcType === 'http' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 HTTP 服务（baseUrl 与鉴权头由注册层提供）；URL 可填相对业务路径（如 /api/v1/orders）与 baseUrl 拼接，留空直打 baseUrl，完整 http(s) URL 则覆盖',
        showIf: (d) => d.srcType === 'http' },
      { key: 'httpUrl', label: '业务路径 / URL', type: 'text', placeholder: '引用模式：/api/v1/orders；内联：http://…', showIf: (d) => d.srcType === 'http' && !d.dsRef },
      { key: 'httpMethod', label: '方法', type: 'select', options: [
        { value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' },
      ], showIf: (d) => d.srcType === 'http' },
      { key: 'intervalSec', label: '轮询间隔（秒）', type: 'number', showIf: (d) => d.srcType === 'http' },
      { key: 'headers', label: '请求头（键值表）', type: 'kv-table', showIf: (d) => d.srcType === 'http' },
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
      { key: 'dsRef', label: '数据源引用（Redis 注册源）', type: 'datasource', dsTypes: ['redis'], showIf: (d) => d.srcType === 'redis' },
      { key: 'dsRefHint', label: '', type: 'hint',
        text: () => '引用在数据源中心注册并测试通过的 Redis 实例（地址/密码由注册层提供）；不选则下方手动填写地址（内联高级模式）',
        showIf: (d) => d.srcType === 'redis' },
      { key: 'redisUrl', label: 'Redis 地址（高级内联）', type: 'text', placeholder: 'redis://redis:6379/0', showIf: (d) => d.srcType === 'redis' && !d.dsRef },
      { key: 'streamsText', label: 'Stream 键（逗号分隔多个）', type: 'text', placeholder: '如 order_stream,user_stream', required: true, showIf: (d) => d.srcType === 'redis' },
      { key: 'redisGroup', label: '消费组（XREADGROUP，位点由组管理）', type: 'text', showIf: (d) => d.srcType === 'redis' },
      { key: 'redisConsumer', label: '消费者名', type: 'text', showIf: (d) => d.srcType === 'redis' },
      /* —— mqtt（MQTT 订阅源）—— */
      { key: 'dsRef', label: '数据源引用（MQTT 注册源）', type: 'datasource', dsTypes: ['mqtt'], showIf: (d) => d.srcType === 'mqtt' },
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
    type: 'stream_fuse', label: '流融合', icon: '⊞', color: '#0f766e', code: 'C19', categories: ['stream'],
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
      { key: 'alignMap', label: '字段对齐映射（目标 ← 来源，留空 = 同名透传）', type: 'kv-table',
        showIf: (d) => d.fuseType === 'union' },
      /* I12 T12：join 键升级 field-select（列枚举自直接上游流输入的 CDC 源表；非 CDC 上游降级为可直接输入），
         单选写回字符串对齐 worker ops.py joinKeyLeft/Right 单键契约；union 对齐映射维持 kv-table（W1 语义标注不变） */
      { key: 'joinKeyLeft', label: '左流关联键', type: 'field-select', required: true, showIf: (d) => d.fuseType === 'join',
        pick: { src: 'upstream', upstreamIndex: 0, multiple: false } },
      { key: 'joinKeyRight', label: '右流关联键', type: 'field-select', required: true, showIf: (d) => d.fuseType === 'join',
        pick: { src: 'upstream', upstreamIndex: 1, multiple: false } },
      { key: 'joinWindowSec', label: '关联窗口（秒，窗口内缓存匹配）', type: 'number', showIf: (d) => d.fuseType === 'join' },
      { key: 'joinType', label: '关联类型', type: 'select', options: [
        { value: 'inner', label: 'inner（交集）' }, { value: 'left', label: 'left（保留左流未匹配）' },
      ], showIf: (d) => d.fuseType === 'join' },
      { key: 'filterExpr', label: '过滤条件表达式', type: 'textarea', placeholder: '如 amount > 0 && status == \'paid\'',
        required: true, showIf: (d) => d.fuseType === 'filter' },
      { key: 'fieldMap', label: '字段转换表达式表（目标字段 ← 表达式，如 upper(name)）', type: 'kv-table',
        showIf: (d) => d.fuseType === 'map' },
      { key: 'groupKeys', label: '分组键（逗号分隔，留空 = 全局聚合）', type: 'text', showIf: (d) => d.fuseType === 'window' },
      { key: 'aggs', label: '聚合函数表（键=字段，值=函数:别名，如 amount:sum:amt_total）', type: 'kv-table',
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
    type: 'stream_output', label: '流输出', icon: '⇨', color: '#059669', code: 'C20', categories: ['stream'],
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
      { key: 'outDs', label: '目标数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'], required: true, showIf: (d) => d.outType === 'table' },
      { key: 'outTable', label: '目标表名', type: 'table-picker', required: true, showIf: (d) => d.outType === 'table',
        pick: { dsKey: 'outDs', writeAs: 'table' } },
      { key: 'outFieldMap', label: '字段映射（目标 ← 流字段，留空 = 同名全列）', type: 'kv-table', showIf: (d) => d.outType === 'table' },
      { key: 'uniqueKey', label: '唯一键列（填则 upsert，留空 = 追加插入）', type: 'text', showIf: (d) => d.outType === 'table' },
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
    type: 'page_board', label: '页面组件', icon: '▤', color: '#0e7490', categories: ['stream'],
    desc: '实时看板页面组件：消费本画布流任务 API 输出通道数据，指标卡/趋势曲线/分布/告警/明细按字段特征自适应渲染（不参与管道装配）',
    defaults: { preset: 'ecommerce' },
    form: [
      { key: 'preset', label: '看板模板', type: 'select', options: [
        { value: 'ecommerce', label: '电商实时大盘' }, { value: 'iot', label: 'IoT 设备监控' },
        { value: 'visit', label: '站点访问分析' }, { value: 'custom', label: '自定义（按字段自适应）' },
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
    type: 'variable', label: '变量组件', icon: '$', color: '#7c2d12', code: 'C21', categories: ['general', 'sync', 'etl'],
    desc: '运行至本节点时将变量表注入实例运行时变量存储（工作流级层），供下游与条件区块引用',
    defaults: {
      vars: [
        { name: 'wf.period', value: '20261001', type: 'literal', override: false },
      ] as VarDef[],
    },
    form: [
      { key: 'vars', label: '变量表（名/值/类型/覆盖）', type: 'var-table' },
      { key: 'varHint', label: '', type: 'hint',
        text: () => '下游以 $[wf.变量名] 引用；类型=字面量原样注入 / 表达式运行时求值 / 时间变量按 F49 模板（如 yyyyMMdd-1）；覆盖开关控制同名定义级变量取值；引用优先级：节点参数>工作流变量>环境组>全局' },
    ],
    summary: (d) => varSummary(d),
  },

  /* ================= G I12 新组件（C24 文件同步 / C25 数据校验 / C26 通知） ================= */
  file_sync: {
    type: 'file_sync', label: '文件同步', icon: '⇥', color: '#0d9488', code: 'C24', categories: ['sync', 'general'],
    desc: 'Excel/CSV/TXT 文件 → 库表入仓：共享卷直读或运行时节点 SFTP 拉取暂存，自动建表 + 三种写入模式，日志输出读/写/忽略三行数（批次号=instance_id）',
    defaults: {
      runtimeNode: '', filePath: '', fileName: '', stagedPath: '',
      fileType: 'csv', delimiter: ',', encoding: 'utf-8', headerRows: 1,
      targetDs: '', targetSchema: '', targetTable: '',
      autoCreate: true, ddl: '', writeMode: 'append', flagColumn: 'src_schema',
      fieldMap: [] as Record<string, string>[],
    },
    form: [
      /* —— 文件来源（目录/路径 与 上传暂存 二选一：均非必填，showIf 互斥切必填，I12 T11 修） —— */
      { key: 'runtimeNode', label: '运行时节点（SFTP 取文件）', type: 'runtime-node',
        placeholder: '文件不在 /datara/files 共享卷时必配', showIf: (d) => !d.stagedPath },
      { key: 'filePath', label: '文件来源目录/路径', type: 'dir-select',
        pick: { nodeKey: 'runtimeNode' }, required: true, showIf: (d) => !d.stagedPath,
        placeholder: '共享卷相对路径（如 samples/orders.csv）或经节点浏览的远端目录' },
      { key: 'fileName', label: '文件名（来源为目录时）', type: 'text', placeholder: '如 orders_2026.csv',
        showIf: (d) => !d.stagedPath },
      { key: 'stagedPath', label: '上传暂存路径（/datara/files 相对）', type: 'text',
        required: true, showIf: (d) => !d.filePath,
        placeholder: '如 staging/orders_20260922.csv（先经文件管理上传，与来源目录二选一）' },
      /* —— 文件解析 —— */
      { key: 'fileType', label: '文件类型', type: 'select', options: [
        { value: 'csv', label: 'CSV' }, { value: 'txt', label: 'TXT' }, { value: 'excel', label: 'Excel' },
      ] },
      { key: 'delimiter', label: '分隔符', type: 'text', placeholder: ',',
        showIf: (d) => String(d.fileType) !== 'excel' },
      { key: 'encoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }, { value: 'gb18030', label: 'GB18030' },
      ], showIf: (d) => String(d.fileType) !== 'excel' },
      { key: 'headerRows', label: '表头行数', type: 'number', placeholder: '缺省 1（0 = 无表头）' },
      /* —— 目标端 —— */
      { key: 'targetDs', label: '目标数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'], required: true },
      { key: 'targetTable', label: '目标 schema → 表', type: 'table-picker', required: true,
        pick: { dsKey: 'targetDs', writeAs: 'schemaTable' } },
      { key: 'autoCreate', label: '自动建表', type: 'bool',
        placeholder: '目标表不存在时按自定义 DDL（可编辑）或文件表头推断创建' },
      { key: 'ddl', label: 'DDL 预览（留空按文件头自动推断）', type: 'textarea',
        showIf: (d) => !!d.autoCreate,
        placeholder: '目标表不存在时执行，如 CREATE TABLE `ods_orders` (`id` BIGINT NULL, `name` TEXT NULL)；留空则运行时按文件表头推断类型建表' },
      { key: 'writeMode', label: '写入模式', type: 'select', options: [
        { value: 'append', label: '追加（union 合并）' },
        { value: 'overwrite', label: '覆盖（先 TRUNCATE）' },
        { value: 'src_flag', label: '标识列（每行落来源文件标识）' },
      ] },
      { key: 'flagColumn', label: '标识列名', type: 'text', showIf: (d) => d.writeMode === 'src_flag' },
      /* —— 字段映射 —— */
      { key: 'fieldMap', label: '字段映射（文件列 → 目标列，留空 = 按表头同名对齐）', type: 'kv-table' },
    ],
    summary: (d) => {
      const t = d.targetTable
      const tbl = t && typeof t === 'object'
        ? `${(t as Record<string, string>).schema ?? ''}.${(t as Record<string, string>).table ?? ''}`
        : String(t ?? '')
      return `${String(d.filePath || d.stagedPath || '未配置文件')} → ${tbl || '未配置目标表'} @ ${String(d.targetDs || '未选数据源')}`
    },
  },
  assert: {
    type: 'assert', label: '数据校验', icon: '⚑', color: '#dc2626', code: 'C25', categories: ['etl', 'general'],
    desc: '数据校验闸门（master 内联）：行数区间/主键唯一/非空率/自定义 SQL 断言；通过走「通过」出口，不达标走「不通过」出口或断流失败（onFail）',
    defaults: {
      assertSrc: 'upstream', assertUpstream: '', assertDs: '', assertTable: '',
      rules: [{ key: 'rows', value: 'min=1,max=1000000', note: '行数区间' }] as Record<string, string>[],
      ruleColumns: [] as string[],
      onFail: 'fail',
    },
    ports: () => [{ id: 'success', label: '通过' }, { id: 'failure', label: '不通过' }],
    form: [
      { key: 'assertSrc', label: '校验对象', type: 'select', options: [
        { value: 'upstream', label: '上游节点（自动取目标表）' },
        { value: 'manual', label: '手选数据源与表' },
      ] },
      /* I12 T11 修：上游节点引用下拉（Inspector 取画布直接上游，选中写回节点 id；空=自动扫描兜底） */
      { key: 'assertUpstream', label: '上游节点引用（可选）', type: 'upstream-ref',
        showIf: (d) => d.assertSrc !== 'manual' },
      { key: 'assertDs', label: '校验数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'],
        required: true, showIf: (d) => d.assertSrc === 'manual' },
      { key: 'assertTable', label: '校验表（schema → 表）', type: 'table-picker', required: true,
        pick: { dsKey: 'assertDs', writeAs: 'schemaTable' }, showIf: (d) => d.assertSrc === 'manual' },
      { key: 'rules', label: '规则集（key=规则，value=参数）', type: 'kv-table', required: true },
      /* I12 T11 修：规则列参考——仅手选模式（表已定）可勾选列名辅助填参；上游模式对象表运行时才定，参数手填 */
      { key: 'ruleColumns', label: '规则列参考（手选表字段，可选）', type: 'field-select',
        pick: { dsKey: 'assertDs', tableKey: 'assertTable' }, showIf: (d) => d.assertSrc === 'manual' },
      { key: 'rulesHint', label: '', type: 'hint', text: () =>
        '规则 key 与参数：rows（min=1,max=1000 行数区间）/ unique（列名，逗号分隔联合唯一）/ not_null（列名,阈值%，如 name,95）/ sql（断言语句，首行首列=1 通过）；'
        + '校验对象=上游时可显式指定「上游节点引用」（未选则自动解析 C17 写端表 / C24 目标表 / SQL 声明结果表）；'
        + '手选模式可先在「规则列参考」勾选列名再填入 unique/not_null 参数；上游引用模式对象表运行时才定，规则参数手填' },
      { key: 'onFail', label: '不达标动作', type: 'select', options: [
        { value: 'fail', label: '断流失败（节点 failure）' },
        { value: 'warn', label: '告警继续（走「不通过」出口）' },
      ] },
    ],
    summary: (d) => {
      const n = Array.isArray(d.rules) ? (d.rules as unknown[]).length : 0
      if (String(d.assertSrc ?? 'upstream') !== 'manual') return `校验上游目标表（${n} 项规则）`
      const t = d.assertTable
      const tbl = t && typeof t === 'object'
        ? `${(t as Record<string, string>).schema ?? ''}.${(t as Record<string, string>).table ?? ''}`
        : String(t ?? '')
      return `校验 ${tbl || '未选表'} @ ${String(d.assertDs || '未选数据源')}（${n} 项规则）`
    },
  },
  notify: {
    type: 'notify', label: '通知', icon: '✉', color: '#7c3aed', code: 'C26', categories: ['general', 'stream', 'etl'],
    desc: '工作流/分支收尾通知：webhook POST 或仅日志（触发时机留痕；webhook 失败默认仅告警不断流，可开断流开关）',
    defaults: { channel: 'log', url: '', template: '', trigger: 'on_success', failHard: false },
    form: [
      { key: 'channel', label: '通道', type: 'select', options: [
        { value: 'log', label: '仅日志' }, { value: 'webhook', label: 'Webhook' },
      ] },
      { key: 'url', label: 'Webhook URL', type: 'text', placeholder: 'http://…（支持 ${var} 变量引用）',
        required: true, showIf: (d) => d.channel === 'webhook' },
      { key: 'trigger', label: '触发时机', type: 'select', options: [
        { value: 'on_success', label: '上游成功' }, { value: 'on_failure', label: '上游失败' },
        { value: 'always', label: '无论成败' },
      ] },
      { key: 'template', label: '消息模板', type: 'textarea',
        placeholder: '${wf.name} 实例 ${instance_id} 节点 ${node.name} ${node.status} @ ${sys.now}' },
      { key: 'notifyHint', label: '', type: 'hint', text: () =>
        'webhook 以 {"text": 消息} JSON POST（超时 10s，失败不重试）；消息经四级变量链解析：${wf.name} ${instance_id} ${node.name} ${node.status} ${sys.now}' },
      { key: 'failHard', label: '通知失败断流', type: 'bool',
        placeholder: '开启后 webhook 发送失败将节点置 failure（缺省仅告警）' },
    ],
    summary: (d) => (d.channel === 'webhook' ? `webhook → ${String(d.url || '未配置 URL')}` : '仅日志'),
  },

  /* ================= F63 模板（demo_pipeline，可拖；展开后不保留占位节点） ================= */
  demo_pipeline: {
    type: 'demo_pipeline', label: '示例管道模板', icon: '✦', color: '#16a34a', code: '', categories: ['general'],
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
    /* C7：中心数据源表单浮窗（源端可开拓新表 / 目标端表必须存在），经工具栏「更多」打开；
       propsOf 只传 selectedId，面板自行按选中节点解析活跃 node（与 Inspector 同契约） */
    { id: 'source_base', label: '源表基准', comp: SourceBasePanel, w: 420, h: 460, propsOf: ({ selectedId }) => ({ selectedId }) },
    { id: 'target_base', label: '目标表基准', comp: TargetBasePanel, w: 420, h: 460, propsOf: ({ selectedId }) => ({ selectedId }) },
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
      { type: 'sync' },
      { type: 'sync_template' },
      { type: 'file_sync' },
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
    /* W1 必填完整性：required 字段在当前分型下为空即「未配置」（画布角标/校验面板/保存闸门共用判定） */
    (doc) => doc.nodes.flatMap((n) => {
      const s = nodeTypes[n.type]
      if (!s) return []
      return requiredMissing(s, n.data).map((lb) => ({
        level: 'warn' as const,
        msg: `「${String(n.data.name ?? n.id)}」必填项未配置：${lb}`,
        nodeId: n.id,
      }))
    }),
    /* 分支完整性：条件/多路分支须配置分支，且每个分支端点应连接下游 */
    (doc: GraphDocument) => {
      const issues: { level: 'error' | 'warn'; msg: string; nodeId?: string }[] = []
      doc.nodes.forEach((n) => {
        const schema = nodeTypes[n.type]
        if (!schema?.ports) return
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
