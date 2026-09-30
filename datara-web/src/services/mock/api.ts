/**
 * mock 模式的**列表读路径**实现（补 `services/mock/api` 缺失方法：workflow-definitions / sync-tasks / runtime-nodes / datasources）
 *
 * 背景：`VITE_API_MODE=mock` 时此前只有 `graphService` 对象被切换，`graphApi` 等独立函数仍直连真实后端 → 502 错误
 * 修复目标：让 mock 模式下这些读路径返回真实数据（seed/seedDataStore），且 **不触发任何真实网络请求**
 */
import type { DefinitionMeta, RuntimeNodeRow, CategoryRow } from '../graphApi'
import type { WfVariable } from '../types'
import type { SyncTaskRow } from '../syncApi'
import type { DsRow } from '../datasourceApi'
import type { GlobalParamRow } from '../ideApi'
import type { BaselineProgressResult, BaselineDraft, BaselineSaveResult, BaselineCheckResult, BaselinePublishResult, LineageDeclResult, BaselineStatus } from '../baselineApi'
import type { ComponentDetail, ComponentDraft, ComponentVersionsResult } from '../componentApi'
import type { LineageGraphEdge, LineageGraphParams, LineageGraphResult } from '../lineageApi'
import { dataStore } from './dataStore'
import { listSeedTaskDocs, seedWorkflows } from './seed'

/** 业务类型 → 任务标签（与 `services/index.ts` 导出的 SYNC_TAG/ETL_TAG/STREAM_TAG 同值） */
const TAG_OF_TYPE: Record<string, string> = { sync: '同步', etl: 'etl', stream: '流' }

/** 工作流定义列表：以 seed 文档为全集（带业务类型），用 `seedWorkflows` 补 cron/owner/status/version 等字段 */
export async function mockListDefinitions(params?: { pageNo?: number; pageSize?: number; search?: string; tag?: string }): Promise<DefinitionMeta[]> {
  const kw = params?.search?.trim().toLowerCase()
  const tag = params?.tag
  const pageSize = Math.min(params?.pageSize ?? 200, 200)
  const pageNo = Math.max(params?.pageNo ?? 1, 1)

  // 1. 从 seed 文档中提取工作流定义（listSeedTaskDocs 已按 profile 过滤），补全 DefinitionMeta 所需字段
  const wfMap = new Map(seedWorkflows.map((w) => [w.id, w]))
  const rows: DefinitionMeta[] = listSeedTaskDocs()
    .map((d) => {
      const w = wfMap.get(d.id)
      return {
        id: d.id,
        name: d.name,
        version: w?.version ?? 1,
        owner: w?.owner,
        status: w?.status ?? 'offline',
        cron: w?.cron ?? '-',
        nodeCount: w?.nodes ?? 0,
        tags: tag ? [TAG_OF_TYPE[d.type ?? 'batch']] : [],
        updatedAt: w?.updatedAt ?? ''  // 必须补齐
      }
    })

  // 2. 客户端过滤（与真实后端行为一致）
  let result = rows
  if (kw) {
    result = result.filter((r) =>
      r.name.toLowerCase().includes(kw) ||
      r.id.toLowerCase().includes(kw)
    )
  }
  if (tag) result = result.filter((r) => (r.tags ?? []).includes(tag))

  // 按分页返回
  return result.slice((pageNo - 1) * pageSize, pageNo * pageSize)
}

/** 同步任务列表（PageData 形状），仅含 sync 类型任务 */
export async function mockListSyncTasks(params?: { pageNo?: number; pageSize?: number; keyword?: string }): Promise<{ total: number; list: SyncTaskRow[] }> {
  const kw = params?.keyword?.trim().toLowerCase()
  const rows = listSeedTaskDocs()
    .filter((d) => d.type === 'sync')
    .filter((d) => !kw || d.name.toLowerCase().includes(kw))
    .map((d, i) => ({
      wfCode: i + 1,
      name: d.name,
      tags: ['同步'],
      instanceCount: 0,
      lastInstanceId: null,
      lastState: null,
      lastTime: null,
      readRows: 0,
      writeRows: 0,
      badRows: 0,
      schemas: [],
    }))
  const pageSize = Math.min(params?.pageSize ?? 50, 200)
  const pageNo = Math.max(params?.pageNo ?? 1, 1)
  return { total: rows.length, list: rows.slice((pageNo - 1) * pageSize, pageNo * pageSize) }
}

/** 数据源列表：直接读内存库（datasources） */
export async function mockListDataSources(params?: {
  keyword?: string
  env?: string
  group?: string
  type?: string
}): Promise<DsRow[]> {
  let rows = await dataStore.list<DsRow>('datasources')
  if (params?.keyword) {
    const kw = params.keyword.trim().toLowerCase()
    rows = rows.filter((r) => `${r.name ?? ''}`.toLowerCase().includes(kw))
  }
  if (params?.env) rows = rows.filter((r) => r.env === params.env)
  if (params?.group) rows = rows.filter((r) => r.group === params.group)
  if (params?.type) rows = rows.filter((r) => r.type === params.type)
  return rows
}

/** 运行时节点：内存库 runtimeNodes 的 id 是字符串 → 转为 number（RuntimeNodeRow 要求 number） */
export async function mockListRuntimeNodes(): Promise<RuntimeNodeRow[]> {
  const raw = await dataStore.list<Record<string, unknown>>('runtimeNodes')
  return raw.map((r, i) => ({
    id: i + 1,
    name: String(r.name ?? ''),
    kind: String(r.kind ?? ''),
    host: String(r.host ?? ''),
    port: Number(r.port ?? 0),
    user: r.user as string | undefined,
    runtimeDir: (r.runtimeDir as string | null) ?? null,
    status: r.status as string | undefined,
    lastHeartbeat: (r.lastHeartbeat as string | null) ?? null,
  }))
}

/** 内置分类目录（mock 下固定渲染） */
export async function mockListCategories(): Promise<CategoryRow[]> {
  return [
    { id: 'cat_wf', name: '工作流定义', builtin: true },
    { id: 'cat_sched', name: '调度引擎', builtin: true },
    { id: 'cat_sync', name: '同步任务', builtin: true },
    { id: 'cat_ds', name: '数据源', builtin: true },
    { id: 'cat_rt', name: '运行时节点', builtin: true },
  ]
}

/* ================= M-B0 基线化 / 组件设计 mock =================
 * 背景：baselineApi / componentApi 是 M-B0 新增端点，此前 mock 模式下穿透 vite proxy → 502，
 * 工作台/设计器在本机（无后端）空转。数据快照取自 datara-backend/common/dag_catalog.json
 * （catalogHash=83929cf7c3c5c660）与 docs/组件基线化/README.md 进度台账（M-B1 九组件 ⏳、M-B2 九组件 🔵）。
 */

const MOCK_TS = '2026-09-29 10:00:00'

/** dag profile 35 type 紧凑快照：[type, code, label, categories(|), executionModel, executor, paletteVisible, runtimeOnly] */
const DAG_35: [string, string, string, string, string, string, boolean, boolean][] = [
  ['start', 'C1', '开始', 'general|sync|etl', 'dag-engine', '', true, false],
  ['end', 'C2', '结束', 'general|sync|etl', 'dag-engine', '', true, false],
  ['conditions', 'C3', '条件分支', 'general|sync|etl', 'dag-engine', '', true, false],
  ['switch', 'C4', '切换', 'general|sync|etl', 'dag-engine', '', true, false],
  ['fork', 'C5', '并行分叉', 'general|sync|etl', 'dag-engine', '', true, false],
  ['join', 'C6', '汇合（AND）', 'general|sync|etl', 'dag-engine', '', true, false],
  ['merge', 'C7', '合并（OR）', 'general|sync|etl', 'dag-engine', '', true, false],
  ['delay', 'C8', '延时执行', 'general|sync|etl', 'dag-engine', '', true, false],
  ['dependent', 'C9', '依赖', 'general|sync|etl', 'dag-engine', '', true, false],
  ['loop', 'C10', '循环迭代', 'general|sync|etl', 'dag-engine', '', true, false],
  ['sql', 'C11', 'SQL', 'etl|general|sync', 'dag-engine', 'sql', true, false],
  ['shell', 'C12', 'Shell', 'general|etl', 'dag-engine', 'shell', true, false],
  ['python', 'C13', 'Python', 'general|etl', 'dag-engine', 'python', true, false],
  ['ssh', 'C14', 'SSH 脚本', 'general|etl', 'dag-engine', 'ssh', true, false],
  ['procedure', 'C15', '存储过程', 'general|etl', 'dag-engine', 'procedure', true, false],
  ['http', 'C16', 'HTTP', 'general|etl', 'dag-engine', 'http', true, false],
  ['file', 'C22', '文件读取', 'general|etl', 'dag-engine', 'file', true, false],
  ['assert', 'C25', '数据校验', 'etl|general', 'dag-engine', '', true, false],
  ['src_base_orch', 'C29', '源表基准编排', 'sync', 'template', '', true, false],
  ['tgt_base_orch', 'C30', '目标表基准编排', 'sync', 'template', '', true, false],
  ['file_sync_orch', 'C31', '文件同步编排', 'sync', 'template', '', true, false],
  ['endpoint_select', 'C37', '端点选择', 'sync', 'passthrough', '', true, false],
  ['field_map', 'C34', '字段映射-复制', 'sync', 'passthrough', '', true, false],
  ['field_map_union', 'C36', '字段映射-联合', 'sync', 'passthrough', '', true, false],
  ['condition_set', 'C35', '条件设定', 'sync', 'passthrough', '', true, false],
  ['stream_input', 'C18', '流输入', 'stream', 'dag-engine', '', true, false],
  ['stream_fuse', 'C19', '流融合', 'stream', 'dag-engine', '', true, false],
  ['stream_output', 'C20', '流输出', 'stream', 'dag-engine', '', true, false],
  ['page_board', '', '页面组件', 'stream', 'passthrough', '', true, false],
  ['variable', 'C21', '变量组件', 'general|sync|etl', 'dag-engine', '', true, false],
  ['notify', 'C26', '通知', 'general|stream|etl', 'dag-engine', 'notify', true, false],
  ['smoke', 'C38', '冒烟', 'general', 'dag-engine', 'smoke', true, false],
  ['demo_pipeline', '', '示例管道模板', 'general', 'template', '', true, false],
  ['file_sync', 'C24', '文件入仓执行', 'sync', 'dag-engine', 'file_sync', false, true],
  ['sync', 'C17', '同步执行', 'sync', 'dag-engine', 'sync', false, true],
]

/** 基线化进度台账快照：M-B1 九组件 confirming / M-B2 九组件 designing / 其余 pending */
const CONFIRMING = new Set(['endpoint_select', 'field_map', 'field_map_union', 'condition_set', 'src_base_orch', 'tgt_base_orch', 'file_sync_orch', 'sync', 'file_sync'])
const DESIGNING = new Set(['sql', 'shell', 'python', 'ssh', 'procedure', 'http', 'file', 'assert', 'notify'])

function mockStatusOf(type: string): BaselineStatus {
  if (CONFIRMING.has(type)) return 'confirming'
  if (DESIGNING.has(type)) return 'designing'
  return 'pending'
}

export async function mockBaselineProgress(): Promise<BaselineProgressResult> {
  const items = DAG_35.map(([type, code, label, cats, em, executor, pal, ro]) => {
    const status = mockStatusOf(type)
    return {
      type, code, label,
      categories: cats ? cats.split('|') : [],
      executionModel: em,
      executor: executor || null,
      paletteVisible: pal,
      runtimeOnly: ro,
      status,
      draftRev: status === 'pending' ? 0 : 1,
      hasDraft: status !== 'pending',
      publishedVersion: 0, // mock 快照无已发组件（status 仅 pending/designing/confirming）
      confirmedBy: null,
      confirmedAt: null,
      updatedAt: MOCK_TS,
    }
  })
  const byStatus: Record<string, number> = {}
  for (const it of items) byStatus[it.status] = (byStatus[it.status] ?? 0) + 1
  return { items, stats: { total: items.length, byStatus } }
}

export async function mockBaselineDraft(type: string): Promise<BaselineDraft> {
  const status = mockStatusOf(type)
  return { type, status, draftRev: status === 'pending' ? 0 : 1, spec: {}, specHash: 'mock0' + type, checkReport: null, testRecords: [], updatedAt: MOCK_TS }
}

export async function mockBaselineSave(_type: string): Promise<BaselineSaveResult> {
  return { draftRev: 2, specHash: 'mock1', status: 'designing' }
}

/** 十项体检（与后端 baseline.py run_checks 同名同序）——mock 恒全过 */
export async function mockBaselineCheck(type: string): Promise<BaselineCheckResult> {
  const ok = (check: string, msg: string) => ({ check, ok: true, msg })
  return {
    checkedAt: MOCK_TS,
    items: [
      ok('pure_data', 'spec 为纯数据声明（无函数/类引用）'),
      ok('form_whitelist', '控件类型均在白名单（9 基元）'),
      ok('drop_policy', 'dropPolicy 键/枚举/占位符合法'),
      ok('contract', 'contract=dag-engine+binding 一致'),
      ok('catalog_consistency', '与 dag_catalog.json 条目一致'),
      ok('references', 'refs 引用键均存在于三段字段'),
      ok('lineage_decl', '血缘声明锚点字段存在'),
      ok('exports_consistency', 'exports 与执行器产出键一致'),
      ok('permission', '发布动作由 publish_component 权限承载（认可发版时校验）'),
      ok('draft_lock', '底稿乐观锁由保存端点承载'),
    ].map((x) => ({ ...x, msg: `${type}：${x.msg}` })),
  }
}

export async function mockBaselinePublish(type: string): Promise<BaselinePublishResult> {
  return { type, publishedVersion: 1, specHash: 'mock1', checkItems: (await mockBaselineCheck(type)).items, confirmedAt: MOCK_TS }
}

export async function mockBaselineLineage(type: string): Promise<LineageDeclResult> {
  return { type, baselineState: mockStatusOf(type) === 'published' ? 'published' : 'unbaseline', lineage: null }
}

function findDag(type: string): [string, string, string, string, string, string, boolean, boolean] | undefined {
  return DAG_35.find((r) => r[0] === type)
}

export async function mockComponentDetail(type: string): Promise<ComponentDetail> {
  const row = findDag(type)
  if (!row) throw Object.assign(new Error(`component ${type} not found`), { code: 404 })
  const [t, code, label, cats, em, executor, pal, ro] = row
  return {
    type: t, profile: 'dag', dagRelevant: true,
    executionModel: (em === 'template' || em === 'passthrough' ? 'dag-engine' : em) as ComponentDetail['executionModel'],
    executionNote: 'mock 快照',
    code: code || '', label,
    icon: 'box', color: '#64748b', desc: label,
    categories: cats ? cats.split('|') : [],
    shape: 'rect', runtimeOnly: ro,
    route: 'master', executor: executor || null,
    paletteVisible: pal, paletteGroup: null,
    formFieldCount: 0, requiredFieldCount: 0,
    flags: {}, formFields: [],
  }
}

export async function mockComponentDraft(type: string): Promise<ComponentDraft> {
  const row = findDag(type)
  if (!row) throw Object.assign(new Error(`component ${type} not found`), { code: 404 })
  const [, , label] = row
  return {
    type, name: label, category: null, profile: 'dag', scope: 'builtin',
    executionModel: 'dag-engine', executor: null, executable: true,
    state: 'draft', publishedVersion: null,
    draftRev: 1, draftVersion: 1, description: null, tags: [],
    spec: {}, specHash: 'mock0' + type, updatedAt: MOCK_TS,
  }
}

export async function mockComponentVersions(type: string): Promise<ComponentVersionsResult> {
  return { type, publishedVersion: null, items: [] }
}

/* ---- 变量读路径（画布「引用变量」面板数据源；此前 mock 模式穿透 502） ---- */

/** 工作流变量（GET /workflow-variables?wf=）：mock 每个工作流给两条示例（${var} 下拉可引用） */
export async function mockListVariables(wf: string): Promise<WfVariable[]> {
  return [
    { id: `mv1_${wf}`, wf, name: 'biz_date', value: '${system.bizdate}', type: '日期', encrypted: false, options: [], desc: '业务日期（示例）' },
    { id: `mv2_${wf}`, wf, name: 'batch_size', value: '1000', type: '数值', encrypted: false, options: [], desc: '批大小（示例）' },
  ]
}

/** 全局参数（GET /params/global）：mock 两条示例（dev/prod 各一） */
export async function mockListGlobalParams(_env?: string): Promise<GlobalParamRow[]> {
  return [
    { id: 1, name: 'dw_host', value: 'greatdb-dw:3306', type: '文本', env: 'dev', desc: '数仓地址（示例）', createTime: MOCK_TS, updateTime: MOCK_TS },
    { id: 2, name: 'alarm_webhook', value: 'https://hooks.example.com/x', type: '加密', env: 'prod', desc: '告警 webhook（示例）', createTime: MOCK_TS, updateTime: MOCK_TS },
  ]
}

/* ================= Task 5 血缘图聚合 mock（GET /lineage/graph） =================
 * design+runtime 双源样例（表名对齐 dataStore.tableLineage 链路，影响分析/元数据富化可复用）：
 * 三态边齐全 —— 双源（实线+徽标）/ 纯运行（实线）/ 纯设计（虚线，端点节点「未验证」）。 */

const MOCK_GRAPH_EDGES: LineageGraphEdge[] = [
  { from: 'ods_gdb_biz_trade_order', to: 'dwd_order_pay_detail', level: 'table',
    sources: ['design', 'runtime'], refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 0 }] },
  { from: 'ods_gdb_biz_pay_record', to: 'dwd_order_pay_detail', level: 'table',
    sources: ['runtime'], refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 1 }] },
  { from: 'ods_gdb_biz_user_info', to: 'dim_user', level: 'table',
    sources: ['design'], refs: [{ wfCode: 102, nodeId: 'n_sql_2', stmtNo: 0 }] },
  { from: 'dim_user', to: 'dwd_order_pay_detail', level: 'table',
    sources: ['runtime'], refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 2 }] },
  { from: 'dwd_order_pay_detail', to: 'dws_pay_summary_daily', level: 'table',
    sources: ['design', 'runtime'], refs: [{ wfCode: 103, nodeId: 'n_sql_3', stmtNo: 0 }] },
  { from: 'dws_pay_summary_daily', to: 'ads_kpi_report', level: 'table',
    sources: ['runtime'], refs: [{ wfCode: 104, nodeId: 'n_sql_4', stmtNo: 0 }] },
  { from: 'ods_oracle_gl_voucher', to: 'dwd_gl_voucher_detail', level: 'table',
    sources: ['design'], refs: [{ wfCode: 105, nodeId: 'n_sql_5', stmtNo: 0 }] },
]

/** 按 params 过滤聚合：source 行级过滤 → 中心表（_bare/endsWith）BFS 扩散（direction/depth）
 * → limit 截断置位；语义对齐后端 lineage_graph 的可观测子集。 */
export async function mockLineageGraph(params: LineageGraphParams): Promise<LineageGraphResult> {
  const src = params.source ?? 'all'
  const edges = MOCK_GRAPH_EDGES.filter(
    (e) => src === 'all' || e.sources.includes(src as 'design' | 'runtime'),
  )
  const sources = new Map<string, Set<string>>()
  edges.forEach((e) => {
    // source 过滤后节点 sources 只聚合剩余行来源（对齐后端行级过滤再聚合口径）
    const ss = src === 'all' ? e.sources : [src as 'design' | 'runtime']
    for (const fq of [e.from, e.to]) {
      if (!sources.has(fq)) sources.set(fq, new Set())
      ss.forEach((s) => sources.get(fq)!.add(s))
    }
  })
  let nodes = [...sources.keys()].sort()
  let truncated = false

  const table = (params.table ?? '').trim()
  if (table) {
    const bare = table.includes('.') ? table.split('.').pop()! : table
    let seeds = nodes.filter((fq) => (fq.includes('.') ? fq.split('.').pop()! : fq) === bare)
    if (!seeds.length) seeds = nodes.filter((fq) => fq.includes(table))
    const kept = new Set(seeds)
    const adjOut = new Map<string, string[]>()
    const adjIn = new Map<string, string[]>()
    edges.forEach((e) => {
      if (!adjOut.has(e.from)) adjOut.set(e.from, [])
      adjOut.get(e.from)!.push(e.to)
      if (!adjIn.has(e.to)) adjIn.set(e.to, [])
      adjIn.get(e.to)!.push(e.from)
    })
    const queue: [string, number][] = seeds.map((s) => [s, 0])
    while (queue.length) {
      const [cur, hops] = queue.shift()!
      if (params.depth && hops >= params.depth) continue
      const nexts = [
        ...(params.direction === 'upstream' ? [] : adjOut.get(cur) ?? []),
        ...(params.direction === 'downstream' ? [] : adjIn.get(cur) ?? []),
      ]
      for (const nxt of nexts) {
        if (kept.has(nxt)) continue
        if (params.limit && kept.size >= params.limit) { truncated = true; queue.length = 0; break }
        kept.add(nxt)
        queue.push([nxt, hops + 1])
      }
    }
    nodes = nodes.filter((fq) => kept.has(fq))
  } else if (params.limit && nodes.length > params.limit) {
    truncated = true
    nodes = nodes.slice(0, params.limit)
  }
  const keptSet = new Set(nodes)
  return {
    nodes: nodes.map((fq) => ({
      fq, ds: fq.split('.').length > 1 ? fq.split('.')[0] : '', table: fq,
      tmpFlag: 0,
      sources: [...sources.get(fq)!].sort() as ('design' | 'runtime')[],
      wfs: [...new Set(edges.filter((e) => e.from === fq || e.to === fq)
        .flatMap((e) => e.refs.map((r) => r.wfCode)))].sort((a, b) => a - b),
    })),
    edges: edges.filter((e) => keptSet.has(e.from) && keptSet.has(e.to)),
    opaques: [],
    truncated,
  }
}