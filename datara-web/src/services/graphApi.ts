/**
 * graphApi（F9）：IGraphService 的真实后端实现 + 列表/变量/实例辅助 API。
 * 契约零改动：get/save/listVersions/rollback 签名与 mock 一致（src/services/types.ts）。
 * 端点（对齐 datara-backend/api/wf_definition.py、wf_variable.py、instance.py 实测形状）：
 * - GET /workflow-definitions/{id}                → data 即 GraphDocument
 * - PUT /workflow-definitions/{id}/save           → body {doc, remark} → {version}
 * - GET /workflow-definitions/{id}/versions       → [{version, updatedAt, operator, remark}]
 * - POST /workflow-definitions/{id}/rollback      → body {version} → 回滚后 GraphDocument
 * - GET/POST /workflow-definitions、DELETE /workflow-definitions/{id}
 * - GET/POST/PUT/DELETE /workflow-variables（query/body 参数名 = wf）
 * - GET /instances?page_no=&page_size=
 */
import type { GraphDocument } from '../graph/model'
import type { IGraphService, WfVariable } from './types'
import { http, toLocalMinute } from './http'

/** I6 同步任务标签（对齐 datara-backend/api/sync.py SYNC_TAG，C23 保存打标与 F34 列表过滤共用） */
export const SYNC_TAG = '同步'
/** F56d ETL 任务标签：etl profile 画布保存时自动打标（任务中心候选池过滤依据） */
export const ETL_TAG = 'ETL'
/** F56d 流任务标签：stream profile 画布保存时自动打标（任务中心候选池过滤依据） */
export const STREAM_TAG = '流'

/* ---------- 后端 DTO ---------- */

interface DefRow {
  id: string
  name: string
  version: number
  releaseState?: string
  owner?: string
  updatedAt?: string
  tags?: string[]
  /** I3 §12 回填：最新 online schedule 的 crontab（无则空） */
  cron?: string | null
  /** I3 §12 回填：graph_json 节点数 */
  nodeCount?: number
}

interface DefVersionRow {
  version: number
  updatedAt?: string
  operator?: string
  remark?: string
}

interface PageData<T> { total: number; list: T[] }

/** 工作流定义列表行（任务中心/变量复制工作流下拉共用） */
export interface DefinitionMeta {
  id: string
  name: string
  version: number
  owner?: string
  status?: string
  /** 最新 online schedule 的 crontab（无 = '-'） */
  cron?: string
  nodeCount?: number
  /** 数字编码（定时/补数/运行路由 {wf} 参数可兼用 id 与 code） */
  code?: number
  /** F56d：定义标签（同步/ETL/流；任务中心候选池过滤依据） */
  tags?: string[]
  updatedAt: string
}

/* ---------- IGraphService 真实实现 ---------- */

export const realGraphService: IGraphService = {
  async get(id) {
    const doc = await http.get<GraphDocument | null>(`/workflow-definitions/${encodeURIComponent(id)}`)
    return doc ?? null
  },

  async save(doc, remark) {
    /* I6/F56d：保存自动打标 —— 含同步节点（C17 直拖 / C23 模板展开）打「同步」；
       ETL/流画布按 meta.profile 打「ETL」/「流」；合并去重。
       集合非空才传 tags 字段（后端语义：缺省不改动既有标签）。 */
    const tags = new Set<string>()
    if (doc.meta?.profile === 'etl') tags.add(ETL_TAG)
    if (doc.meta?.profile === 'stream') tags.add(STREAM_TAG)
    if ((doc.nodes ?? []).some((n) => n.type === 'sync' || n.type === 'sync_template')) tags.add(SYNC_TAG)
    const r = await http.put<{ version: number }>(
      `/workflow-definitions/${encodeURIComponent(doc.id)}/save`,
      { doc, remark: remark ?? '', ...(tags.size ? { tags: [...tags] } : {}) },
    )
    return { version: r.version }
  },

  async listVersions(id) {
    const rows = await http.get<DefVersionRow[]>(`/workflow-definitions/${encodeURIComponent(id)}/versions`)
    return rows.map((v) => ({
      version: v.version,
      updatedAt: toLocalMinute(v.updatedAt),
      operator: v.operator ?? '-',
      remark: v.remark,
    }))
  },

  async rollback(id, version) {
    const doc = await http.post<GraphDocument>(
      `/workflow-definitions/${encodeURIComponent(id)}/rollback`,
      { version },
    )
    return doc
  },
}

/* ---------- 定义列表 / 变量 / 实例（列表页与变量面板用） ---------- */

export async function listDefinitions(params?: { pageNo?: number; pageSize?: number; search?: string; tag?: string }): Promise<DefinitionMeta[]> {
  const q = new URLSearchParams()
  const tag = params?.tag
  /* 后端 PageQuery 上限 200（传大页 422）：定义量几十级，钳制 200 后客户端过滤足够 */
  if (tag) {
    /* F56d：后端无 tag 筛选参数 —— 一次拉满页后客户端过滤 */
    q.set('page_no', '1')
    q.set('page_size', '200')
  } else {
    q.set('page_no', String(params?.pageNo ?? 1))
    q.set('page_size', String(Math.min(params?.pageSize ?? 200, 200)))
  }
  if (params?.search) q.set('search', params.search)
  const page = await http.get<PageData<DefRow>>(`/workflow-definitions?${q.toString()}`)
  const rows = page.list.map((r) => ({
    id: r.id,
    name: r.name,
    version: r.version,
    owner: r.owner,
    status: r.releaseState,
    cron: r.cron ?? '-',
    nodeCount: r.nodeCount ?? 0,
    tags: r.tags ?? [],
    updatedAt: toLocalMinute(r.updatedAt),
  }))
  return tag ? rows.filter((r) => (r.tags ?? []).includes(tag)) : rows
}

export async function createDefinition(name: string): Promise<{ id: string }> {
  return http.post<{ id: string }>('/workflow-definitions', { name })
}

export async function deleteDefinition(id: string): Promise<void> {
  await http.delete<void>(`/workflow-definitions/${encodeURIComponent(id)}`)
}

/* ---- 工作流变量（t_wf_variable，§12 WfVarPanel） ---- */

/** 后端变量行形状（与前端 WfVariable 对齐，options 为 json） */
interface VarRow {
  id: string
  wf?: string
  name: string
  value: string
  type: string
  encrypted?: boolean
  options?: string[] | string | null
  desc?: string
}

function mapVar(v: VarRow, wf: string): WfVariable {
  let options: string[] = []
  if (Array.isArray(v.options)) options = v.options
  else if (typeof v.options === 'string' && v.options.trim()) {
    try { options = JSON.parse(v.options) as string[] } catch { options = v.options.split(/[,，]/).map((s) => s.trim()).filter(Boolean) }
  }
  return {
    id: v.id,
    wf: v.wf ?? wf,
    name: v.name,
    value: v.value,
    type: (['日期', '文本', '数值', '加密', '下拉'].includes(v.type) ? v.type : '文本') as WfVariable['type'],
    encrypted: !!v.encrypted,
    options,
    desc: v.desc ?? '',
  }
}

export async function listVariables(wf: string): Promise<WfVariable[]> {
  const rows = await http.get<VarRow[]>(`/workflow-variables?wf=${encodeURIComponent(wf)}`)
  return rows.map((v) => mapVar(v, wf))
}

export async function saveVariable(row: WfVariable): Promise<void> {
  const body = { wf: row.wf, name: row.name, value: row.value, type: row.type, encrypted: row.encrypted, options: row.options, desc: row.desc }
  if (row.id) await http.put<void>(`/workflow-variables/${encodeURIComponent(row.id)}`, body)
  else await http.post<void>('/workflow-variables', body)
}

export async function deleteVariable(id: string): Promise<void> {
  await http.delete<void>(`/workflow-variables/${encodeURIComponent(id)}`)
}

/* ---- 运行实例（F61 页面化演示页数据源） ---- */

export interface InstanceRow {
  id?: number
  instanceId: string
  wfCode?: number
  wfVersion?: number
  state?: string
  runMode?: 'manual' | 'schedule' | 'complement' | string
  scheduleTime?: string
  startTime?: string
  endTime?: string
  host?: string
  commandType?: string
  /** 详情接口附带：实例级变量（含 varSnapshot 汇总） */
  variables?: Record<string, unknown> | null
  recovery?: number
  /** 详情接口 taskInstances（任务行全集，I3 补 loopIter/delayUntil） */
  taskInstances?: {
    id: number
    instanceId: string
    nodeId: string
    nodeType: string
    name: string
    state: string
    attempt: number
    loopIter: number
    delayUntil?: string | null
    startTime?: string | null
    endTime?: string | null
    host?: string | null
    logPath?: string | null
    outputs?: Record<string, unknown> | null
  }[]
}

/** 实例分页列表（含 total，分页条用） */
export async function listInstancesPage(params?: {
  pageNo?: number
  pageSize?: number
  wfCode?: string
  runMode?: string
  state?: string
}): Promise<PageData<InstanceRow>> {
  const q = new URLSearchParams()
  q.set('page_no', String(params?.pageNo ?? 1))
  q.set('page_size', String(params?.pageSize ?? 50))
  if (params?.wfCode) q.set('wf_code', params.wfCode)
  if (params?.runMode) q.set('run_mode', params.runMode)
  if (params?.state) q.set('state', params.state)
  return http.get<PageData<InstanceRow>>(`/instances?${q.toString()}`)
}

export async function listInstances(params?: {
  pageNo?: number
  pageSize?: number
  wfCode?: string
  runMode?: string
  state?: string
}): Promise<InstanceRow[]> {
  const q = new URLSearchParams()
  q.set('page_no', String(params?.pageNo ?? 1))
  q.set('page_size', String(params?.pageSize ?? 50))
  if (params?.wfCode) q.set('wf_code', params.wfCode)
  if (params?.runMode) q.set('run_mode', params.runMode)
  if (params?.state) q.set('state', params.state)
  const page = await http.get<PageData<InstanceRow>>(`/instances?${q.toString()}`)
  return page.list
}

/* ============================================================
 * I3 调度执行引擎（§12/§13）：定时 / 运行 / 补数 / 实例操作 / 任务日志 / 运行时节点
 * {wf} 路径参数兼容定义 id 与数字 code（后端 _resolve_wf）
 * ============================================================ */

/* ---- 定时调度（t_wf_schedule） ---- */

export interface ScheduleRow {
  id: number
  wfCode: number
  name: string
  crontab: string
  startTime?: string | null
  endTime?: string | null
  state: 'online' | 'offline' | string
  priority: number
  workerGroup?: string | null
  failRetryTimes: number
  failRetryInterval: number
  createTime?: string
  updateTime?: string
  /** 新建/更新响应附带：未来 3 次触发预览 */
  nextFireTimes?: string[]
}

export interface ScheduleBody {
  name?: string
  crontab: string
  start_time?: string
  end_time?: string
  priority?: number
  worker_group?: string
  fail_retry_times?: number
  fail_retry_interval?: number
}

export async function listSchedules(wf: string): Promise<ScheduleRow[]> {
  return http.get<ScheduleRow[]>(`/workflow-definitions/${encodeURIComponent(wf)}/schedules`)
}

export async function createSchedule(wf: string, body: ScheduleBody): Promise<ScheduleRow> {
  return http.post<ScheduleRow>(`/workflow-definitions/${encodeURIComponent(wf)}/schedules`, body)
}

export async function updateSchedule(scheduleId: number, body: ScheduleBody): Promise<ScheduleRow> {
  return http.put<ScheduleRow>(`/schedules/${scheduleId}`, body)
}

export async function deleteSchedule(scheduleId: number): Promise<void> {
  await http.delete<void>(`/schedules/${scheduleId}`)
}

export async function onlineSchedule(scheduleId: number): Promise<ScheduleRow> {
  return http.post<ScheduleRow>(`/schedules/${scheduleId}/online`)
}

export async function offlineSchedule(scheduleId: number): Promise<ScheduleRow> {
  return http.post<ScheduleRow>(`/schedules/${scheduleId}/offline`)
}

/** crontab 校验 + 未来 3 次触发预览 */
export async function previewCrontab(crontab: string): Promise<{ valid: boolean; nextFireTimes: string[] }> {
  return http.post('/crontab-preview', { crontab })
}

/* ---- 运行 / 补数（api 写命令，master 消费） ---- */

export async function runWorkflow(
  wf: string,
  body?: { env_group_id?: number; priority?: number },
): Promise<{ commandId?: number; mode?: 'batch' | 'stream'; streamJobId?: number; name?: string; restarted?: boolean }> {
  return http.post(`/workflow-definitions/${encodeURIComponent(wf)}/run`, body ?? {})
}

export async function complementWorkflow(
  wf: string,
  body: { date_from: string; date_to: string; parallel?: boolean; env_group_id?: number; priority?: number },
): Promise<{ commandId: number; instances: number }> {
  return http.post(`/workflow-definitions/${encodeURIComponent(wf)}/complement`, body)
}

/* ---- 实例操作（停止/重跑/失败重跑） ---- */

export async function getInstanceDetail(instanceId: string): Promise<InstanceRow> {
  return http.get<InstanceRow>(`/instances/${encodeURIComponent(instanceId)}`)
}

export async function stopInstance(instanceId: string): Promise<{ commandId: number }> {
  return http.post(`/instances/${encodeURIComponent(instanceId)}/stop`, {})
}

export async function rerunInstance(instanceId: string, priority = 3): Promise<{ commandId: number }> {
  return http.post(`/instances/${encodeURIComponent(instanceId)}/rerun`, { priority })
}

export async function rerunFailedTasks(instanceId: string, priority = 3): Promise<{ commandId: number }> {
  return http.post(`/instances/${encodeURIComponent(instanceId)}/rerun-failed`, { priority })
}

/* ---- 任务日志（实时增量：前端 2s 轮询正文） ---- */

export async function getTaskLog(taskId: number): Promise<{ taskInstanceId: number; instanceId: string; logPath: string; content: string }> {
  return http.get(`/logs/task/${taskId}`)
}

/* ---- 运行时节点（C14 SSH 表单下拉，只读） ---- */

export interface RuntimeNodeRow {
  id: number
  name: string
  kind: string
  host: string
  port: number
  user?: string
  runtimeDir?: string | null
  status?: string
  lastHeartbeat?: string | null
}

export async function listRuntimeNodes(): Promise<RuntimeNodeRow[]> {
  return http.get<RuntimeNodeRow[]>('/runtime-nodes')
}

/* ---- SSH 运行节点（I7 F53：管理面 + C14「执行节点标签」下拉数据源） ---- */

export interface SshNodeRow {
  id: number
  name: string
  host: string
  port: number
  sshUser: string
  cred?: string
  tags: string[]
  enabled: boolean
  heartbeatState: 'online' | 'offline' | 'unknown'
  lastSeen?: string | null
  createTime?: string | null
}

export async function listSshNodes(): Promise<SshNodeRow[]> {
  return http.get<SshNodeRow[]>('/ssh-nodes')
}

export interface SshNodeBody {
  name: string
  host: string
  port: number
  sshUser: string
  cred?: string
  tags: string[]
  enabled: boolean
}

export async function createSshNode(body: SshNodeBody): Promise<SshNodeRow> {
  return http.post<SshNodeRow>('/ssh-nodes', body)
}

export async function updateSshNode(id: number, body: SshNodeBody): Promise<SshNodeRow> {
  return http.put<SshNodeRow>(`/ssh-nodes/${id}`, body)
}

export async function deleteSshNode(id: number): Promise<boolean> {
  return http.delete<boolean>(`/ssh-nodes/${id}`)
}

export async function probeSshNode(id: number): Promise<{ ok: boolean; message: string }> {
  return http.post<{ ok: boolean; message: string }>(`/ssh-nodes/${id}/probe`, {})
}

/* ---- 节点监控聚合（I7 F55：master/worker ZK live + Redis 指标 + ssh 注册表） ---- */

export interface MonitorNodeRow {
  module: 'master' | 'worker' | 'ssh'
  node: string
  cpu: number | null
  mem: number | null
  memUsedMb: number | null
  memTotalMb: number | null
  disk: number | null
  heartbeat: string
  lastSeen: string | null
  tags: string[]
}

export async function fetchMonitorNodes(): Promise<{ zkAvailable: boolean; nodes: MonitorNodeRow[] }> {
  return http.get<{ zkAvailable: boolean; nodes: MonitorNodeRow[] }>('/monitor/nodes')
}
