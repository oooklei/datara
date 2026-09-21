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
 * - F63 模板：demo_pipeline（拖入 → 模式选择 → 设计时物化展开为普通节点链）。
 */
import { detectCycle, findBrokenEdges, findDuplicateEdges, findIsolated, uid } from '../model'
import type { GraphDocument, GEdge, GNode } from '../model'
import type { BranchDef, DependentDef, NodeSchema, VarDef, ViewProfile } from './types'
import { c17IsConnReader, c17IsFileReader, c17OnReaderTypeChange, c17SqlPreview, c22OnModeChange, tmpRefHint } from './formLinkage'
import NodeRunDetailPage from '../workbench/pages/NodeRunDetailPage.vue'
import SqlPreviewPage from '../workbench/pages/SqlPreviewPage.vue'
import TmpPreviewPage from '../workbench/pages/TmpPreviewPage.vue'
import StreamNodePage from '../workbench/pages/StreamNodePage.vue'
import StreamDataPage from '../workbench/pages/StreamDataPage.vue'

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

/** I8 流组件类型集合（C18~C20） */
const STREAM_TYPES = ['stream_input', 'stream_fuse', 'stream_output']

export interface StreamIssue { level: 'error' | 'warn'; msg: string; nodeId?: string }

/**
 * I8 流子图校验（纯函数，试运行/保存共用语义，F40 §3.4）：
 * - 流组件与批处理组件不可混编（start/end 除外，I8 简化裁定）；
 * - 至少 1 个流输入 + 1 个流输出；
 * - C19 join 须有两条入边（两路流）；所有流组件须处于 源→汇 连通路径上（无游离）。
 */
export function streamSubgraphIssues(doc: GraphDocument): StreamIssue[] {
  const streamNodes = doc.nodes.filter((n) => STREAM_TYPES.includes(n.type))
  if (!streamNodes.length) return []
  const issues: StreamIssue[] = []
  const batch = doc.nodes.filter((n) => !STREAM_TYPES.includes(n.type) && n.type !== 'start' && n.type !== 'end')
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
  if (t === 'kafka') return `Kafka ${d.topic || '未配置 topic'} @ ${d.brokers || '未配置 broker'}`
  if (t === 'cdc') return `CDC ${d.cdcDs || '未选数据源'}（${String(d.tablesText || '全库表')}）`
  if (t === 'http') return `HTTP ${d.httpUrl || '未配置 URL'}（${numOr(d.intervalSec, 10)}s 轮询）`
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

const nodeTypes: Record<string, NodeSchema> = {
  /* ================= A 逻辑控制（C1~C10，全可用） ================= */
  start: {
    type: 'start', label: '开始', icon: '▶', color: '#16a34a', code: 'C1', desc: '工作流启动节点（运行实例编号 instance_id 由此生成）',
    form: [], defaults: {},
    summary: () => '工作流入口',
    /* F61 页面化演示位：节点运行详情（real 走 /api/v1/instances，mock 空态） */
    page: { title: '节点运行详情', comp: NodeRunDetailPage, w: 560, h: 340 },
  },
  end: {
    type: 'end', label: '结束', icon: '■', color: '#64748b', code: 'C2', desc: '工作流结束节点',
    form: [], defaults: {},
    summary: () => '工作流出口',
  },
  conditions: {
    type: 'conditions', label: '条件分支', icon: '⑃', color: '#d97706', code: 'C3',
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
    type: 'switch', label: '切换', icon: '⑄', color: '#b45309', code: 'C4',
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
    type: 'fork', label: '并行分叉', icon: '⋔', color: '#ca8a04', code: 'C5',
    desc: '单输入多路并行下发（下游同时触发）',
    defaults: { parallel: 2 },
    form: [{ key: 'parallel', label: '并行度', type: 'number' }],
    summary: (d) => `并行度 ${d.parallel ?? 2}`,
  },
  join: {
    type: 'join', label: '汇合（AND）', icon: '⨝', color: '#0f766e', code: 'C6',
    desc: '等待全部上游分支完成后触发',
    defaults: {},
    form: [],
    summary: () => '全部上游完成（AND）',
  },
  merge: {
    type: 'merge', label: '合并（OR）', icon: '∪', color: '#0284c7', code: 'C7',
    desc: '任一上游完成即触发（抢先合并）',
    defaults: {},
    form: [],
    summary: () => '任一上游完成（OR）',
  },
  delay: {
    type: 'delay', label: '延时执行', icon: '⏱', color: '#57534e', code: 'C8',
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
    type: 'dependent', label: '依赖', icon: '⧉', color: '#7c3aed', code: 'C9',
    desc: '依赖其他工作流/节点产出：所配依赖各自最近一次实例中节点终态=success 即通过（I7 简化语义，周期/批次走变量条件）',
    defaults: { deps: [] as DependentDef[] },
    form: [{ key: 'deps', label: '依赖项列表', type: 'deps-list' }],
    summary: (d) => depSummary(d),
  },
  loop: {
    type: 'loop', label: '循环迭代', icon: '↻', color: '#c2410c', code: 'C10',
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
    type: 'sql', label: 'SQL', icon: '⌨', color: '#334155', code: 'C11',
    desc: '选择数据源执行 SQL（查询/非查询/DDL），页面化浮窗展示查询结果前 200 行',
    defaults: { datasource: '', sql: '', pre: '', post: '' },
    form: [
      { key: 'datasource', label: '数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'] },
      { key: 'sql', label: 'SQL 语句', type: 'textarea', placeholder: "INSERT INTO ... SELECT ..." },
      { key: 'pre', label: '前置 SQL', type: 'textarea' },
      { key: 'post', label: '后置 SQL', type: 'textarea' },
    ],
    summary: (d) => String(d.datasource ?? ''),
    /* F61 页面化：SQL 结果预览（worker result_preview 前 200 行，real 走实例详情） */
    page: { title: 'SQL 结果预览', comp: SqlPreviewPage, w: 620, h: 380 },
  },
  shell: {
    type: 'shell', label: 'Shell', icon: '❯', color: '#7c3aed', code: 'C12',
    desc: '在运行时节点执行 Shell 脚本',
    defaults: { script: '' },
    form: [{ key: 'script', label: '脚本内容', type: 'textarea', placeholder: '#!/bin/bash ...' }],
    summary: () => 'Shell 脚本',
  },
  python: {
    type: 'python', label: 'Python', icon: 'Py', color: '#2563eb', code: 'C13',
    desc: '在运行时节点执行 Python 脚本',
    defaults: { script: '' },
    form: [{ key: 'script', label: '脚本内容', type: 'textarea' }],
    summary: () => 'Python 脚本',
  },
  ssh: {
    type: 'ssh', label: 'SSH 脚本', icon: '⌖', color: '#475569', code: 'C14',
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
    type: 'procedure', label: '存储过程', icon: '⚙', color: '#6d28d9', code: 'C15',
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
    type: 'http', label: 'HTTP', icon: '⊕', color: '#4f46e5', code: 'C16',
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
    type: 'file', label: '文件读取', icon: '▦', color: '#0e7490', code: 'C22',
    desc: '读取 CSV/TXT/Excel 注册为临时工作数据，下游以 ${tmp.<名>} 引用；页面化预览检验网格',
    defaults: {
      mode: 'datasource', datasource: '',
      path: '', format: 'csv', encoding: 'utf-8', delimiter: ',', header: true, sheet: '',
      register: true, name: '', kind: 'table', targetDs: '内置数仓-datara_dw',
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
      { key: 'name', label: '临时数据名', type: 'text', placeholder: '小写字母开头 3~32 位 a-z0-9_',
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
        text: (d) => `转正式表：实例成功后临时表 RENAME 去前缀，正式表名 = 临时数据名 ${String(d.name || '?')}（仅 table 形态生效）`,
        showIf: (d) => !!d.register && String(d.retention) === 'keep' },
      { key: 'tmpHint', label: '', type: 'hint', text: tmpRefHint, showIf: (d) => !!tmpRefHint(d) },
    ],
    summary: (d) => {
      const src = d.mode === 'manual' ? String(d.path || '未配置路径') : String(d.datasource || '未选数据源')
      return d.register ? `${src} → ${d.name || '?'}（${String(d.kind ?? 'table')}）` : `${src}（不注册）`
    },
    /* F61 页面化：数据预览检验网格（t_tmp_data 抽样 + schema 推断 + 空值统计） */
    page: { title: '数据预览检验', comp: TmpPreviewPage, w: 680, h: 440 },
  },

  /* ================= C 数据同步（C17 I6 注册；C23 模板聚合） ================= */
  sync: {
    type: 'sync', label: '数据同步', icon: '⇄', color: '#0891b2', code: 'C17',
    desc: '读写器分离的异构数据源同步（MySQL/GreatDB/文件 → MySQL/GreatDB；动态 schema 返选 + union/标识列/分区三策略）',
    defaults: syncDefaults('union'),
    form: [
      /* —— 读端 —— */
      { key: 'readerType', label: '读端类型', type: 'select', options: [
        { value: 'mysql', label: 'MySQL' }, { value: 'greatdb', label: 'GreatDB' },
        { value: 'csv', label: 'CSV 文件' }, { value: 'txt', label: 'TXT 文件' }, { value: 'excel', label: 'Excel 文件' },
      ], onChange: c17OnReaderTypeChange },
      { key: 'readerDs', label: '读端数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'], showIf: c17IsConnReader },
      { key: 'readerTable', label: '读端表名', type: 'text', placeholder: '如 ods_order', showIf: c17IsConnReader },
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
      { key: 'writerTable', label: '目标表名', type: 'text', placeholder: '如 ods_order_sync' },
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
    type: 'sync_template', label: '同步编排', icon: '⇉', color: '#0369a1', code: 'C23',
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
    type: 'stream_input', label: '流输入', icon: '⇥', color: '#0d9488', code: 'C18',
    desc: '常驻流输入源：Kafka 消费 / CDC binlog / HTTP 拉取 / 文件尾随（分型表单，位点持久化 t_stream_offset）',
    defaults: {
      srcType: 'kafka',
      /* kafka 分型 */
      brokers: '', topic: '', group: 'datara-flink', startFrom: 'earliest',
      format: 'json', delimiter: ',',
      /* cdc 分型（引用 I4 注册数据源） */
      cdcDs: '', schemasText: '', tablesText: '', posMode: 'latest', posFile: '', posPos: 0,
      /* http 拉取分型 */
      httpUrl: '', httpMethod: 'GET', intervalSec: 10, headers: [] as Record<string, string>[],
      dataPath: '', cursorParam: '', cursorPath: '',
      /* 文件尾随分型 */
      filePath: '', fileEncoding: 'utf-8', fileDelimiter: ',', fileHeader: true,
    },
    form: [
      { key: 'srcType', label: '源分型', type: 'select', options: [
        { value: 'kafka', label: 'Kafka 消费' }, { value: 'cdc', label: 'CDC（MySQL/GreatDB binlog）' },
        { value: 'http', label: 'HTTP 拉取' }, { value: 'file', label: '文件尾随' },
      ] },
      /* —— kafka —— */
      { key: 'brokers', label: 'Broker 地址', type: 'text', placeholder: 'host:9092（逗号分隔多个）', showIf: (d) => d.srcType === 'kafka' },
      { key: 'topic', label: 'Topic', type: 'text', placeholder: '如 orders', showIf: (d) => d.srcType === 'kafka' },
      { key: 'group', label: '消费组', type: 'text', showIf: (d) => d.srcType === 'kafka' },
      { key: 'startFrom', label: '起始位点', type: 'select', options: [
        { value: 'earliest', label: 'earliest（最早）' }, { value: 'latest', label: 'latest（最新）' },
      ], showIf: (d) => d.srcType === 'kafka' },
      { key: 'format', label: '反序列化格式', type: 'select', options: [
        { value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV（分隔符切分为字段）' },
      ], showIf: (d) => d.srcType === 'kafka' },
      { key: 'delimiter', label: 'CSV 分隔符', type: 'text', placeholder: ',',
        showIf: (d) => d.srcType === 'kafka' && d.format === 'csv' },
      /* —— cdc —— */
      { key: 'cdcDs', label: 'CDC 数据源（引用 I4 注册）', type: 'datasource', dsTypes: ['mysql', 'greatdb'], showIf: (d) => d.srcType === 'cdc' },
      { key: 'schemasText', label: '库白名单（逗号分隔，留空 = 全库）', type: 'text', showIf: (d) => d.srcType === 'cdc' },
      { key: 'tablesText', label: '表白名单（逗号分隔，留空 = 全表）', type: 'text', showIf: (d) => d.srcType === 'cdc' },
      { key: 'posMode', label: 'binlog 位点', type: 'select', options: [
        { value: 'latest', label: '最新（当前 file:pos）' }, { value: 'earliest', label: '最早' },
        { value: 'custom', label: '指定 file:pos' },
      ], showIf: (d) => d.srcType === 'cdc' },
      { key: 'posFile', label: 'binlog 文件', type: 'text', placeholder: '如 binlog.000003', showIf: (d) => d.srcType === 'cdc' && d.posMode === 'custom' },
      { key: 'posPos', label: '位点偏移', type: 'number', showIf: (d) => d.srcType === 'cdc' && d.posMode === 'custom' },
      /* —— http —— */
      { key: 'httpUrl', label: 'URL', type: 'text', placeholder: 'http://…', showIf: (d) => d.srcType === 'http' },
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
      { key: 'filePath', label: '文件路径（/datara/files 相对）', type: 'text', placeholder: '如 logs/app.log', showIf: (d) => d.srcType === 'file' },
      { key: 'fileEncoding', label: '编码', type: 'select', options: [
        { value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' },
      ], showIf: (d) => d.srcType === 'file' },
      { key: 'fileDelimiter', label: '分隔符（留空 = 整行一列）', type: 'text', placeholder: ',', showIf: (d) => d.srcType === 'file' },
      { key: 'fileHeader', label: '首行为列名', type: 'bool', showIf: (d) => d.srcType === 'file' },
      { key: 'hint', label: '', type: 'hint',
        text: () => '行事件统一为 {source, ts, data} 进入流管道；位点（partition offset / file:pos / cursor / 字节偏移）处理后周期落 t_stream_offset，重启续跑' },
    ],
    summary: streamInputSummary,
    /* I8 页面化：消费速率/位点/滞后 运行浮窗 */
    page: { title: '流输入运行详情', comp: StreamNodePage, w: 620, h: 460 },
  },
  stream_fuse: {
    type: 'stream_fuse', label: '流融合', icon: '⊞', color: '#0f766e', code: 'C19',
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
        { value: 'union', label: 'union 合并（多路对齐）' }, { value: 'join', label: 'join 关联（两路流）' },
        { value: 'window', label: '窗口聚合' }, { value: 'filter', label: 'filter 过滤' },
        { value: 'map', label: 'map 字段映射' },
      ] },
      { key: 'alignMap', label: '字段对齐映射（目标 ← 来源，留空 = 同名透传）', type: 'kv-table',
        showIf: (d) => d.fuseType === 'union' },
      { key: 'joinKeyLeft', label: '左流关联键', type: 'text', showIf: (d) => d.fuseType === 'join' },
      { key: 'joinKeyRight', label: '右流关联键', type: 'text', showIf: (d) => d.fuseType === 'join' },
      { key: 'joinWindowSec', label: '关联窗口（秒，窗口内缓存匹配）', type: 'number', showIf: (d) => d.fuseType === 'join' },
      { key: 'joinType', label: '关联类型', type: 'select', options: [
        { value: 'inner', label: 'inner（交集）' }, { value: 'left', label: 'left（保留左流未匹配）' },
      ], showIf: (d) => d.fuseType === 'join' },
      { key: 'filterExpr', label: '过滤条件表达式', type: 'textarea', placeholder: '如 amount > 0 && status == \'paid\'',
        showIf: (d) => d.fuseType === 'filter' },
      { key: 'fieldMap', label: '字段转换表达式表（目标字段 ← 表达式，如 upper(name)）', type: 'kv-table',
        showIf: (d) => d.fuseType === 'map' },
      { key: 'groupKeys', label: '分组键（逗号分隔，留空 = 全局聚合）', type: 'text', showIf: (d) => d.fuseType === 'window' },
      { key: 'aggs', label: '聚合函数表（键=字段，值=函数:别名，如 amount:sum:amt_total）', type: 'kv-table',
        showIf: (d) => d.fuseType === 'window' },
      { key: 'windowType', label: '窗口类型', type: 'select', options: [
        { value: 'tumbling', label: '滚动窗口' }, { value: 'sliding', label: '滑动窗口' },
      ], showIf: (d) => d.fuseType === 'window' },
      { key: 'windowSizeSec', label: '窗口大小（秒）', type: 'number', showIf: (d) => d.fuseType === 'window' },
      { key: 'slideSec', label: '滑动步长（秒）', type: 'number', showIf: (d) => d.fuseType === 'window' && d.windowType === 'sliding' },
      { key: 'watermarkSec', label: '水位线允许延迟（秒）', type: 'number', showIf: (d) => d.fuseType === 'window' },
      { key: 'sessHint', label: '', type: 'hint',
        text: () => '会话窗口暂不支持（表单保留语义，后置增量）；表达式经沙箱求值（simpleeval 安全子集）' },
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
    type: 'stream_output', label: '流输出', icon: '⇨', color: '#059669', code: 'C20',
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
      { key: 'outDs', label: '目标数据源', type: 'datasource', dsTypes: ['mysql', 'greatdb'], showIf: (d) => d.outType === 'table' },
      { key: 'outTable', label: '目标表名', type: 'text', placeholder: '如 ods_order_rt', showIf: (d) => d.outType === 'table' },
      { key: 'outFieldMap', label: '字段映射（目标 ← 流字段，留空 = 同名全列）', type: 'kv-table', showIf: (d) => d.outType === 'table' },
      { key: 'uniqueKey', label: '唯一键列（填则 upsert，留空 = 追加插入）', type: 'text', showIf: (d) => d.outType === 'table' },
      { key: 'outBatchSize', label: '批量触发（条数，另 1s 定时兜底）', type: 'number', showIf: (d) => d.outType === 'table' },
      /* —— kafka —— */
      { key: 'kafkaBrokers', label: 'Broker 地址', type: 'text', placeholder: 'host:9092', showIf: (d) => d.outType === 'kafka' },
      { key: 'kafkaTopic', label: '目标 Topic', type: 'text', showIf: (d) => d.outType === 'kafka' },
      /* —— file —— */
      { key: 'outPath', label: '输出文件路径（/datara/files 相对）', type: 'text', placeholder: '如 out/rt_orders.jsonl', showIf: (d) => d.outType === 'file' },
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

  /* ================= E 变量（C21：I7 注册转可用） ================= */
  variable: {
    type: 'variable', label: '变量组件', icon: '$', color: '#7c2d12', code: 'C21',
    desc: '运行至本节点时将变量表注入实例运行时变量存储（工作流级层），供下游与条件区块引用',
    defaults: {
      vars: [
        { name: 'wf.period', value: '20261001', type: 'literal', override: false },
      ] as VarDef[],
    },
    form: [
      { key: 'vars', label: '变量表（名/值/类型/覆盖）', type: 'var-table' },
      { key: 'varHint', label: '', type: 'hint',
        text: () => '下游以 $[wf.变量名] 引用；类型=字面量原样注入 / 表达式运行时求值 / 时间变量按 F49 模板（如 yyyyMMdd-1）；覆盖开关控制同名定义级变量取值' },
    ],
    summary: (d) => varSummary(d),
  },

  /* ================= F63 模板（demo_pipeline，可拖；展开后不保留占位节点） ================= */
  demo_pipeline: {
    type: 'demo_pipeline', label: '示例管道模板', icon: '✦', color: '#16a34a', code: '',
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
      { type: 'procedure' }, { type: 'http' }, { type: 'file' },
    ] },
    { name: '数据同步', items: [
      { type: 'sync' },
      { type: 'sync_template' },
    ] },
    { name: '流处理', items: [
      { type: 'stream_input' }, { type: 'stream_fuse' }, { type: 'stream_output' },
    ] },
    { name: '变量', items: [
      { type: 'variable' },
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
