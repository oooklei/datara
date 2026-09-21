/**
 * ideApi（I10 G1~G24）：可视化 IDE 完整版端点封装。
 * 端点对齐 datara-backend 源码（契约唯一权威）：api/ide.py、api/datasource.py、api/meta_ops.py、api/params.py。
 * 响应包 {code,msg,data} 由 http.ts 统一解包；SSE/导出 Blob 走专用 fetch。
 * 保留既有导出函数名（executeIde/listIdeHistory/exportIdeCsv，其他文件引用不破坏），语义升级为 I10 异步契约。
 */
import { http, getToken } from './http'
import type { DsRow } from './datasourceApi'

/* ---------- 执行（异步任务 + SSE，api/ide.py §4.2） ---------- */

export interface IdeExecuteBody {
  datasourceId: number
  db?: string | null
  sql: string
  /** auto=逐语句自动提交 / manual=事务包裹 */
  mode: 'auto' | 'manual'
  /** 全局参数环境分组 */
  env: 'dev' | 'staging' | 'prod'
}

/** POST /ide/execute → {taskId}（并发超限 429，由 http 层 throw msg） */
export async function executeIde(body: IdeExecuteBody): Promise<{ taskId: string }> {
  return http.post<{ taskId: string }>('/ide/execute', body)
}

/** POST /ide/cancel/{taskId} → {canceled, killed?} */
export async function cancelIdeTask(taskId: string): Promise<{ canceled: boolean; killed?: boolean }> {
  return http.post<{ canceled: boolean; killed?: boolean }>(`/ide/cancel/${encodeURIComponent(taskId)}`)
}

/* ---------- SSE（GET /ide/stream/{taskId}?token=xxx） ---------- */

/** log 事件 data.type = start|end|error|txn（vars 信息并入 start 的 varSnapshot） */
export interface IdeLogEvent {
  stmtIndex?: number
  type?: 'start' | 'end' | 'error' | 'txn'
  sql?: string
  rendered?: string | null
  varSnapshot?: { name: string; value: string; source: string; resolved: boolean }[] | null
  kind?: 'query' | 'exec'
  affected?: number
  rowsTotal?: number
  elapsedMs?: number
  warnings?: string[]
  error?: string
  canceled?: boolean
  action?: 'COMMIT' | 'ROLLBACK'
  reason?: string
}

export interface IdeResultEvent {
  stmtIndex: number
  kind: 'query'
  columns: string[]
  rows: unknown[][]
  rowsTotal: number
  elapsedMs: number
}

export interface IdeDoneEvent {
  status: 'success' | 'failure' | 'canceled'
  elapsedMs: number
  historyId: number | null
  affectedTotal: number
  rowsTotal: number
  stmtCount: number
}

/** 构造 SSE 订阅地址（EventSource 无法带 header，token 走 query——api/auth.py 兜底口径） */
export function buildStreamUrl(taskId: string): string {
  return `/api/v1/ide/stream/${encodeURIComponent(taskId)}?token=${encodeURIComponent(getToken())}`
}

/* ---------- 语法预检 / 结果重放分页 ---------- */

export interface IdeLintItem {
  stmtIndex: number
  ok: boolean
  error: string | null
  line: number | null
  col: number | null
}

/** POST /ide/lint {sql} → 逐语句 {stmtIndex, ok, error, line, col} */
export async function lintSql(sql: string): Promise<IdeLintItem[]> {
  return http.post<IdeLintItem[]>('/ide/lint', { sql })
}

export interface IdeResultPage {
  stmtIndex: number
  columns: string[]
  rows: unknown[][]
  offset: number
  limit: number
  rowsTotal: number
}

/** GET /ide/result/{historyId}/{stmtIndex}?offset=&limit=（重放分页，页间可能漂移） */
export async function fetchResultPage(
  historyId: number, stmtIndex: number, offset: number, limit: number,
): Promise<IdeResultPage> {
  const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  return http.get<IdeResultPage>(
    `/ide/result/${historyId}/${stmtIndex}?${q.toString()}`,
  )
}

/* ---------- 执行历史（G5） ---------- */

export interface IdeHistoryRow {
  id: number
  datasourceId: number
  dbName: string | null
  sqlText: string
  status: string
  elapsedMs: number
  rowsTotal: number
  affectedTotal: number
  exported: boolean
  error: string | null
  createTime: string
}

/** 历史详情：log_text 解析后的逐条语句记录（语句序号/状态/耗时/错误/警告/变量快照） */
export interface IdeHistoryLogEntry {
  stmtIndex?: number
  sql?: string
  rendered?: string
  status?: string
  kind?: string
  elapsedMs?: number
  warnings?: string[]
  error?: string
  affected?: number
  rowsTotal?: number
  varSnapshot?: { name: string; value: string; source: string; resolved: boolean }[]
}

export interface IdeHistoryDetail extends IdeHistoryRow {
  logText: IdeHistoryLogEntry[]
}

export interface PageData<T> { total: number; list: T[] }

/** GET /ide/history?datasourceId=&keyword=&page_no=&page_size=（PageQuery 用 page_no/page_size） */
export async function listIdeHistory(params?: {
  datasourceId?: number
  keyword?: string
  pageNo?: number
  pageSize?: number
}): Promise<PageData<IdeHistoryRow>> {
  const q = new URLSearchParams()
  if (params?.datasourceId) q.set('datasourceId', String(params.datasourceId))
  if (params?.keyword) q.set('keyword', params.keyword)
  q.set('page_no', String(params?.pageNo ?? 1))
  q.set('page_size', String(params?.pageSize ?? 20))
  return http.get<PageData<IdeHistoryRow>>(`/ide/history?${q.toString()}`)
}

/** GET /ide/history/{id}（详情多返回 logText[]） */
export async function getIdeHistoryDetail(id: number): Promise<IdeHistoryDetail> {
  return http.get<IdeHistoryDetail>(`/ide/history/${id}`)
}

/** DELETE /ide/history/{id}（二次确认由前端承担） */
export async function deleteIdeHistory(id: number): Promise<void> {
  await http.delete<void>(`/ide/history/${id}`)
}

/* ---------- 导出（GET /ide/export?historyId=&format=csv|json|xlsx，Blob） ---------- */

export type IdeExportFormat = 'csv' | 'json' | 'xlsx'

/** 导出 Blob（重放 SQL；响应为文件流而非 {code,msg,data} 包裹 → 绕过 http 封装） */
export async function exportIdeResult(historyId: number, format: IdeExportFormat): Promise<Blob> {
  const res = await fetch(
    `/api/v1/ide/export?historyId=${historyId}&format=${format}`,
    { headers: { token: getToken() } },
  )
  if (!res.ok) {
    // 错误时后端仍返回 JSON 包裹（ApiError 处理器），读出 msg 提示
    try {
      const json = (await res.json()) as { msg?: string }
      throw new Error(json.msg || `导出失败（HTTP ${res.status}）`)
    } catch (err) {
      if (err instanceof Error && err.message && !err.message.startsWith('Unexpected')) throw err
      throw new Error(`导出失败（HTTP ${res.status}）`)
    }
  }
  return res.blob()
}

/** 兼容保留：CSV 导出（旧调用点；同 format=csv） */
export async function exportIdeCsv(historyId: number): Promise<Blob> {
  return exportIdeResult(historyId, 'csv')
}

/** 触发浏览器下载（后缀随 format；调用方负责 revokeObjectURL） */
export function downloadBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/* ---------- 命名脚本 CRUD（G16，api/ide.py /ide/scripts） ---------- */

export interface IdeScriptRow {
  id: number
  name: string
  datasourceId: number | null
  dbName: string | null
  content: string
  createTime: string | null
  updateTime: string | null
}

export interface IdeScriptBody {
  name: string
  datasourceId?: number | null
  dbName?: string | null
  content: string
}

export async function listIdeScripts(keyword?: string): Promise<IdeScriptRow[]> {
  const q = keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''
  return http.get<IdeScriptRow[]>(`/ide/scripts${q}`)
}

export async function createIdeScript(body: IdeScriptBody): Promise<IdeScriptRow> {
  return http.post<IdeScriptRow>('/ide/scripts', body)
}

export async function updateIdeScript(id: number, body: IdeScriptBody): Promise<IdeScriptRow> {
  return http.put<IdeScriptRow>(`/ide/scripts/${id}`, body)
}

export async function deleteIdeScript(id: number): Promise<void> {
  await http.delete<void>(`/ide/scripts/${id}`)
}

/* ---------- 数据源懒加载元数据族（api/datasource.py I10 扩展端点） ---------- */

export interface DsMeta {
  id: number
  name: string
  type: string
  host: string | null
  port: number | null
  version: string | null
  defaultSchema: string | null
  timeoutSec: number
  isolation: string | null
}

export async function getDsMeta(dsId: number): Promise<DsMeta> {
  return http.get<DsMeta>(`/datasources/${dsId}/meta`)
}

/** 库列表（系统库已过滤） */
export async function listDsDatabases(dsId: number): Promise<string[]> {
  return http.get<string[]>(`/datasources/${dsId}/databases`)
}

export interface DsTableItem {
  name: string
  kind: 'table' | 'view'
  /** InnoDB 估算行数，仅展示 */
  rows: number | null
  comment: string
}

export async function listDsTables(
  dsId: number, dbName: string, kind?: 'table' | 'view', keyword?: string, limit = 200,
): Promise<DsTableItem[]> {
  const q = new URLSearchParams()
  if (kind) q.set('kind', kind)
  if (keyword) q.set('keyword', keyword)
  q.set('limit', String(limit))
  return http.get<DsTableItem[]>(
    `/datasources/${dsId}/databases/${encodeURIComponent(dbName)}/tables?${q.toString()}`,
  )
}

export interface DsColumnMeta {
  name: string
  dataType: string
  columnType: string
  length: number | null
  nullable: boolean
  key: string
  comment: string
  extra: string
  defaultValue: string | null
}

export async function listDsColumns(
  dsId: number, dbName: string, tableName: string,
): Promise<DsColumnMeta[]> {
  return http.get<DsColumnMeta[]>(
    `/datasources/${dsId}/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/columns`,
  )
}

/** 跨库表检索（树未加载时后端查 INFORMATION_SCHEMA） */
export interface DsSearchItem { db: string; name: string; kind: 'table' | 'view' }

export async function searchDsTables(dsId: number, q: string, limit = 50): Promise<DsSearchItem[]> {
  return http.get<DsSearchItem[]>(
    `/datasources/${dsId}/search?q=${encodeURIComponent(q)}&limit=${limit}`,
  )
}

/** 在线实例（IDE 实例下拉口径：status='online' 且连接型） */
export function filterOnlineDs(rows: DsRow[]): DsRow[] {
  return rows.filter((r) => r.status === 'online' && (r.type === 'mysql' || r.type === 'greatdb'))
}

/* ---------- 表操作（api/meta_ops.py） ---------- */

export async function getTableDdl(
  dsId: number, dbName: string, tableName: string,
): Promise<{ kind: 'table' | 'view'; ddl: string }> {
  return http.get<{ kind: 'table' | 'view'; ddl: string }>(
    `/datasources/${dsId}/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/ddl`,
  )
}

export async function getTableCount(dsId: number, dbName: string, tableName: string): Promise<number> {
  const resp = await http.get<{ count: number }>(
    `/datasources/${dsId}/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/count`,
  )
  return resp.count
}

export interface AuditCheck { level: 'block' | 'warn' | 'info'; code: string; message: string }

export interface AuditResult { pass: boolean; checks: AuditCheck[] }

/** POST /datasources/{id}/audit {db, tb, op: drop|truncate} → {pass, checks[]} */
export async function auditTable(
  dsId: number, dbName: string, tableName: string, op: 'drop' | 'truncate',
): Promise<AuditResult> {
  return http.post<AuditResult>(`/datasources/${dsId}/audit`, { db: dbName, tb: tableName, op })
}

export interface TableRowsResp {
  columns: string[]
  rows: unknown[][]
  total: number
  pks: string[]
  offset: number
}

/** GET .../tables/{tb}/rows（主键序分页；无主键表分页可能漂移） */
export async function getTableRows(
  dsId: number, dbName: string, tableName: string, offset = 0, limit = 200,
): Promise<TableRowsResp> {
  const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  return http.get<TableRowsResp>(
    `/datasources/${dsId}/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/rows?${q.toString()}`,
  )
}

export interface ApplyRowsBody {
  inserts: Record<string, string | number | null>[]
  updates: { keys: Record<string, string | number | null>; data: Record<string, string | number | null> }[]
  deletes: Record<string, string | number | null>[]
}

export interface ApplyRowsResp {
  status: 'success' | 'rolled_back'
  applied: number
  error: string | null
  results: { op: string; index: number; ok: boolean; affected?: number; error?: string }[]
}

/** POST .../rows/apply（事务内逐条应用，失败整体回滚） */
export async function applyTableRows(
  dsId: number, dbName: string, tableName: string, body: ApplyRowsBody,
): Promise<ApplyRowsResp> {
  return http.post<ApplyRowsResp>(
    `/datasources/${dsId}/databases/${encodeURIComponent(dbName)}/tables/${encodeURIComponent(tableName)}/rows/apply`,
    body,
  )
}

export interface ImportCsvResult { imported: number; columns: string[] }

/**
 * POST /datasources/{id}/import-csv（multipart：file/db_name/table_name/mapping/has_header）。
 * FormData 不手设 Content-Type（浏览器自动补 boundary）；token 手带头。
 */
export async function importCsv(
  dsId: number, dbName: string, tableName: string, mapping: Record<string, string>,
  hasHeader: boolean, file: File,
): Promise<ImportCsvResult> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('db_name', dbName)
  fd.append('table_name', tableName)
  fd.append('mapping', JSON.stringify(mapping))
  fd.append('has_header', String(hasHeader))
  const res = await fetch(`/api/v1/datasources/${dsId}/import-csv`, {
    method: 'POST',
    headers: { token: getToken() },
    body: fd,
  })
  const json = (await res.json().catch(() => null)) as { code?: number; msg?: string; data?: ImportCsvResult } | null
  if (!json) throw new Error(`导入失败（HTTP ${res.status}）`)
  if (json.code !== 0) throw new Error(json.msg || `导入失败（code=${json.code}）`)
  return json.data as ImportCsvResult
}

/* ---------- 全局参数（api/params.py /params/global） ---------- */

export interface GlobalParamRow {
  id: number
  name: string
  value: string
  type: string
  env: 'dev' | 'staging' | 'prod' | string
  desc: string | null
  createTime: string | null
  updateTime: string | null
}

export interface GlobalParamBody {
  name: string
  value: string
  type: string
  env: string
  desc?: string | null
}

export async function listGlobalParams(env?: string): Promise<GlobalParamRow[]> {
  const q = env ? `?env=${encodeURIComponent(env)}` : ''
  return http.get<GlobalParamRow[]>(`/params/global${q}`)
}

export async function createGlobalParam(body: GlobalParamBody): Promise<GlobalParamRow> {
  return http.post<GlobalParamRow>('/params/global', body)
}

export async function updateGlobalParam(id: number, body: GlobalParamBody): Promise<GlobalParamRow> {
  return http.put<GlobalParamRow>(`/params/global/${id}`, body)
}

export async function deleteGlobalParam(id: number): Promise<void> {
  await http.delete<void>(`/params/global/${id}`)
}
