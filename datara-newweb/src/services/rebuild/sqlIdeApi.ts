/**
 * SQL IDE readonly contract client for the A5 rebuild/sql_ide API.
 * GREEN 已接线（FE-01 修订 2026-10-19）。
 * Scope: query and metadata operations only; DDL, row editing, and global parameters stay outside this client.
 * FE-07a 拆分登记：本文件为 R5-A 只读换芯契约权威（23 个 contract 方法）。
 * 正式页 /ide 换芯（IdeView.vue → MetaTree/SqlEditor/ResultGrid/HistoryDrawer）归 FE-07a；
 * DDL 写路径归 FE-07b（sqlIdeDdlApi.ts，待 R5-B D 阶段解禁）。
 */

/* ---------- 对象与元数据类型（design §7 对象范围 9 类） ---------- */

export type ObjectKind =
  | 'database'
  | 'schema'
  | 'table'
  | 'view'
  | 'column'
  | 'index'
  | 'function'
  | 'procedure'
  | 'trigger'

export type DefinitionObjectKind = 'table' | 'view' | 'function' | 'procedure' | 'trigger'

export interface DataSourceRef {
  id: number
  name: string
  /** 能力矩阵标记（design §7.1）：跨 Schema 补全/查询是否可用 */
  crossSchema: boolean
}

export interface DatabaseMeta {
  id?: number
  name: string
  capability?: string
  constraints?: string[]
  defaultSchema?: string | null
}

export interface MetadataPage {
  nextCursor: string | null
  hasMore: boolean
  pageSize?: number
}

export interface MetadataEnvelope<T> {
  items: T[]
  capability: 'supported' | 'conditional' | 'unsupported' | string
  constraints: string[]
  page: MetadataPage
}

export interface SchemaMeta {
  database: string
  name: string
}

export interface RelationMeta {
  kind: 'table' | 'view'
  schema: string | null
  name: string
  rowsApprox?: number | null
  comment?: string | null
  capability?: string
  constraints?: string[]
}

export interface ColumnMeta {
  table: string
  name: string
  dataType: string
  nullable: boolean
  key?: 'PRI' | 'UNI' | 'MUL' | null
  comment?: string | null
}

export interface RoutineMeta {
  kind: 'function' | 'procedure' | 'trigger'
  schema: string | null
  name: string
  /** R5-A 只读展示 DDL（SHOW CREATE 等价）；编辑能力归 R5-B */
  ddlPreview?: string | null
}

export interface IndexMeta {
  table: string
  name: string
  columns: string[]
  unique: boolean
}

/* ---------- 执行与结果（legacy ideApi 异步 + SSE 契约的只读子集） ---------- */

export interface SqlExecuteRequest {
  datasourceId: number
  db?: string | null
  sql: string
  /** R5-A 只读：执行上下文默认 auto；事务型 manual 属正式 IDE 融合范围 */
  mode?: 'auto'
  sessionId: string
  clientRequestId: string
}

export interface SqlLogEvent {
  stmtIndex?: number
  type?: 'start' | 'end' | 'error' | 'txn'
  sql?: string
  kind?: 'query' | 'exec'
  affected?: number
  rowsTotal?: number
  elapsedMs?: number
  error?: string
  canceled?: boolean
}

export interface SqlResultEvent {
  stmtIndex: number
  resultSetId: string
  columns: string[]
  rows: unknown[][]
  rowsTotal: number
  elapsedMs: number
}

export interface SqlDoneEvent {
  status: 'succeeded' | 'failed' | 'canceled'
  elapsedMs: number
  historyId: number | null
  stmtCount: number
  resultSets?: Array<{ resultSetId: string; stmtIndex: number; columns: string[]; rowsTotal: number; elapsedMs?: number }>
}

export interface SqlResultPage {
  stmtIndex: number
  resultSetId: string
  columns: string[]
  rows: unknown[][]
  rowsTotal: number
  offset: number
  limit: number
}

export interface HistoryEntry {
  historyId: number
  datasourceId: number
  db: string | null
  sqlText: string
  status: 'succeeded' | 'failed' | 'canceled'
  stmtCount: number
  elapsedMs: number
  createdAt: string
  resultSets?: SqlDoneEvent['resultSets']
}

export interface ScriptEntry {
  id: number
  name: string
  sqlText: string
  updatedAt: string
  revision: number
}

export interface LintItem {
  stmtIndex: number
  level: 'error' | 'warning'
  line: number
  col: number
  message: string
  severity: 'error' | 'warning' | 'info'
  code: string
}

export interface SqlDiagnostic {
  stmtIndex: number
  line: number
  col: number
  severity: 'error' | 'warning' | 'info'
  code: string
  message: string
}

export interface ExportResult {
  exportId: string
  status: 'ready' | 'completed' | 'pending' | 'failed'
  expiresAt: string
  downloadUrl?: string
}

import { getToken } from '../http'

const API_BASE = '/api/v1/projects'

export class SqlIdeApiError extends Error {
  readonly code: number
  readonly errorCode?: string
  readonly details?: unknown

  constructor(message: string, code: number, errorCode?: string, details?: unknown) {
    super(message)
    this.name = 'SqlIdeApiError'
    this.code = code
    this.errorCode = errorCode
    this.details = details
  }
}

async function request<T>(projectId: number, path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.token = token
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_BASE}/${projectId}/sql-ide${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const envelope = await response.json().catch(() => null) as { code?: number; msg?: string; data?: T & { errorCode?: string; details?: unknown } } | null
  if (!envelope || !response.ok || envelope.code !== 0) {
    throw new SqlIdeApiError(
      envelope?.msg || `SQL IDE request failed (HTTP ${response.status})`,
      envelope?.code ?? response.status,
      envelope?.data?.errorCode,
      envelope?.data?.details,
    )
  }
  return normalizeResponse(envelope.data) as T
}

function normalizeResponse(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeResponse)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()),
    normalizeResponse(item),
  ]))
}

function query(values: Record<string, string | number | boolean | null | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null) params.set(key, String(value))
  }
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}

function openAuthenticatedEventStream(projectId: number, taskId: string): EventSource {
  const url = `${API_BASE}/${projectId}/sql-ide/executions/${encodeURIComponent(taskId)}/events`
  const controller = new AbortController()
  const callbacks = new Map<string, Set<EventListenerOrEventListenerObject>>()
  let readyState: number = EventSource.CONNECTING
  let lastEventId = ''
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  const stream = {
    url,
    withCredentials: true,
    get readyState() { return readyState },
    onopen: null as ((event: Event) => void) | null,
    onmessage: null as ((event: MessageEvent) => void) | null,
    onerror: null as ((event: Event) => void) | null,
    close() {
      controller.abort()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      readyState = EventSource.CLOSED
    },
    addEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
      if (!listener) return
      const group = callbacks.get(type) ?? new Set<EventListenerOrEventListenerObject>()
      group.add(listener)
      callbacks.set(type, group)
    },
    removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
      if (listener) callbacks.get(type)?.delete(listener)
    },
    dispatchEvent(event: Event) {
      const group = callbacks.get(event.type)
      group?.forEach((listener) => typeof listener === 'function' ? listener.call(stream, event) : listener.handleEvent(event))
      const handler = event.type === 'message' ? stream.onmessage : event.type === 'open' ? stream.onopen : event.type === 'error' ? stream.onerror : null
      handler?.call(stream, event as MessageEvent)
      return !event.defaultPrevented
    },
  } as unknown as EventSource

  const connect = async () => {
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    if (lastEventId) headers['Last-Event-ID'] = lastEventId
    try {
      const response = await fetch(url, { headers, credentials: 'same-origin', signal: controller.signal })
    if (!response.ok || !response.body) {
      const envelope = await response.json().catch(() => null) as { code?: number; msg?: string; data?: { errorCode?: string; details?: unknown } } | null
      throw new SqlIdeApiError(envelope?.msg || `SQL IDE event stream failed (HTTP ${response.status})`, envelope?.code ?? response.status, envelope?.data?.errorCode, envelope?.data?.details)
    }
    readyState = EventSource.OPEN
    stream.dispatchEvent(new Event('open'))
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventName = 'message'
    let data: string[] = []
    const flush = () => {
      if (eventName === 'reset-required') lastEventId = ''
      if (data.length) {
        const event = new MessageEvent(eventName, { data: data.join('\n') })
        Object.defineProperty(event, 'lastEventId', { value: lastEventId })
        stream.dispatchEvent(event)
      }
      eventName = 'message'
      data = []
    }
    while (!controller.signal.aborted) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line) flush()
        else if (line.startsWith('event:')) eventName = line.slice(6).trim() || 'message'
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
        else if (line.startsWith('id:')) lastEventId = line.slice(3).trim()
      }
    }
    if (!controller.signal.aborted) reconnectTimer = setTimeout(() => void connect(), 250)
    } catch (error: unknown) {
      if (controller.signal.aborted) return
      readyState = EventSource.CONNECTING
      stream.dispatchEvent(new ErrorEvent('error', { error, message: error instanceof Error ? error.message : String(error) }))
      reconnectTimer = setTimeout(() => void connect(), 250)
    }
  }
  void connect()
  return stream
}

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R5A_CONTRACT_METHODS = [
  'listDatabases',
  'listSchemas',
  'listRelations',
  'listColumns',
  'listRoutines',
  'listIndexes',
  'searchObjects',
  'lintSql',
  'executeSql',
  'cancelExecution',
  'openEventStream',
  'fetchResultPage',
  'listHistory',
  'deleteHistory',
  'listScripts',
  'saveScript',
  'deleteScript',
  'getDefinition',
  'exportResult',
  'exportTable',
  'getExport',
  'getExportDownloadUrl',
  'cancelExport',
] as const

export type R5AContractMethod = (typeof R5A_CONTRACT_METHODS)[number]

export interface SqlIdeContract {
  listDatabases: (datasourceId: number, cursor?: string) => Promise<MetadataEnvelope<DatabaseMeta>>
  listSchemas: (datasourceId: number, database: string, cursor?: string) => Promise<MetadataEnvelope<SchemaMeta>>
  listRelations: (datasourceId: number, database: string, schema: string | null, kind: 'table' | 'view', cursor?: string) => Promise<MetadataEnvelope<RelationMeta>>
  listColumns: (datasourceId: number, database: string, table: string, schema: string | null, cursor?: string) => Promise<MetadataEnvelope<ColumnMeta>>
  listRoutines: (datasourceId: number, database: string, schema: string | null, kind: RoutineMeta['kind'], cursor?: string) => Promise<MetadataEnvelope<RoutineMeta>>
  listIndexes: (datasourceId: number, database: string, table: string, schema: string | null, cursor?: string) => Promise<MetadataEnvelope<IndexMeta>>
  searchObjects: (datasourceId: number, keyword: string, cursor?: string) => Promise<MetadataEnvelope<{ kind: ObjectKind; name: string; parent: string | null }>>
  lintSql: (datasourceId: number, sql: string) => Promise<SqlDiagnostic[]>
  executeSql: (request: SqlExecuteRequest) => Promise<{ taskId: string }>
  cancelExecution: (taskId: string) => Promise<{ canceled: boolean }>
  /** SSE 只读流：返回 EventSource（token 沿 R3 runner 注入先例，禁止落 storage） */
  openEventStream: (taskId: string) => EventSource
  fetchResultPage: (historyId: number, resultSetId: string, offset: number, limit: number) => Promise<SqlResultPage>
  listHistory: (datasourceId: number) => Promise<HistoryEntry[]>
  deleteHistory: (historyId: number) => Promise<void>
  listScripts: () => Promise<ScriptEntry[]>
  saveScript: (input: { id?: number; name: string; sqlText: string; revision?: number }) => Promise<ScriptEntry>
  deleteScript: (id: number, expectedRevision: number) => Promise<void>
  getDefinition: (input: { datasourceId: number; database: string; objectKind: DefinitionObjectKind; objectRef: Record<string, unknown> }) => Promise<{ definition: string; capability: string; constraints: string[] }>
  exportResult: (input: { historyId: number; resultSetId: string; format: 'csv' | 'json' | 'xlsx' }) => Promise<ExportResult>
  exportTable: (input: { datasourceId: number; objectRef: Record<string, unknown>; format: 'csv' | 'json' | 'xlsx'; rowLimit?: number }) => Promise<ExportResult>
  getExport: (exportId: string) => Promise<ExportResult>
  getExportDownloadUrl: (exportId: string) => string
  cancelExport: (exportId: string) => Promise<void>
}

/* ---------- API 实现（方法清单见 R5A_CONTRACT_METHODS） ---------- */

/**
 * Creates the readonly SQL IDE client for the connected A5 endpoints.
 */
export function createSqlIdeContract(projectId = 1): SqlIdeContract {
  return {
    listDatabases: (datasourceId, cursor) => request(projectId, `/databases${query({ datasourceId, cursor })}`),
    listSchemas: (datasourceId, database, cursor) => request(projectId, `/schemas${query({ datasourceId, database, cursor })}`),
    listRelations: (datasourceId, database, schema, kind, cursor) => request(projectId, `/relations${query({ datasourceId, database, schema, kind, cursor })}`),
    listColumns: (datasourceId, database, table, schema, cursor) => request(projectId, `/columns${query({ datasourceId, database, table, schema, cursor })}`),
    listRoutines: (datasourceId, database, schema, kind, cursor) => request(projectId, `/routines${query({ datasourceId, database, schema, kind, cursor })}`),
    listIndexes: (datasourceId, database, table, schema, cursor) => request(projectId, `/indexes${query({ datasourceId, database, table, schema, cursor })}`),
    searchObjects: (datasourceId, keyword, cursor) => request(projectId, `/objects/search${query({ datasourceId, keyword, cursor })}`),
    lintSql: async (datasourceId, sql) => {
      const response = await request<SqlDiagnostic[] | { diagnostics: Array<SqlDiagnostic & { column?: number }> }>(projectId, '/lint', 'POST', { datasourceId, sql })
      const items = Array.isArray(response) ? response : response.diagnostics
      return items.map((item) => ({ ...item, col: item.col ?? (item as SqlDiagnostic & { column?: number }).column ?? 1 }))
    },
    executeSql: (input) => request(projectId, '/executions', 'POST', input),
    cancelExecution: async (taskId) => {
      const response = await request<{ accepted: boolean; status: string }>(projectId, `/executions/${encodeURIComponent(taskId)}/cancel`, 'POST')
      return { canceled: response.accepted }
    },
    openEventStream: (taskId) => openAuthenticatedEventStream(projectId, taskId),
    fetchResultPage: async (historyId, resultSetId, offset, limit) => {
      if (!resultSetId) throw new TypeError('resultSetId is required to read a result snapshot')
      if (!Number.isInteger(offset) || offset < 0) throw new RangeError('offset must be a non-negative integer')
      if (!Number.isInteger(limit) || limit < 1 || limit > 500) throw new RangeError('limit must be an integer from 1 to 500')
      const result = await request<SqlResultPage & {
        totalRows?: number
        rowCount?: number | { value?: number; kind?: string }
        page?: { offset?: number; limit?: number }
      }>(projectId, `/results/${historyId}${query({ resultSetId, offset, limit })}`)
      const rowCount = typeof result.rowCount === 'number' ? result.rowCount : result.rowCount?.value
      return { ...result, rowsTotal: result.rowsTotal ?? rowCount ?? result.totalRows ?? 0, offset: result.offset ?? result.page?.offset ?? offset, limit: result.limit ?? result.page?.limit ?? limit }
    },
    listHistory: (datasourceId) => request(projectId, `/history${query({ datasourceId })}`),
    deleteHistory: async (historyId) => { await request(projectId, `/history/${historyId}`, 'DELETE') },
    listScripts: async () => (await request<Array<ScriptEntry & { scriptId?: number }>>(projectId, '/scripts')).map((item) => ({ ...item, id: item.id ?? item.scriptId ?? 0 })),
    saveScript: async (input) => {
      const saved = await request<ScriptEntry & { scriptId?: number }>(projectId, '/scripts', 'POST', { id: input.id, name: input.name, sqlText: input.sqlText, expectedRevision: input.revision })
      return { ...saved, id: saved.id ?? saved.scriptId ?? input.id ?? 0 }
    },
    deleteScript: async (id, expectedRevision) => { await request(projectId, `/scripts/${id}${query({ expectedRevision })}`, 'DELETE') },
  getDefinition: async (input) => {
      const result = await request<{ definition?: string; definitionText?: string; capability: string; constraints: string[] }>(projectId, '/definitions', 'POST', input)
      const definition = result.definitionText ?? result.definition
      if (definition === undefined) throw new SqlIdeApiError('定义响应缺少 definitionText', 502, 'INVALID_RESPONSE')
      return { definition, capability: result.capability, constraints: result.constraints ?? [] }
    },
    exportResult: (input) => request(projectId, '/exports', 'POST', input),
    exportTable: (input) => request(projectId, '/table-exports', 'POST', input),
    getExport: (exportId) => request(projectId, `/exports/${encodeURIComponent(exportId)}`),
    getExportDownloadUrl: (exportId) => `${API_BASE}/${projectId}/sql-ide/exports/${encodeURIComponent(exportId)}/download`,
    cancelExport: async (exportId) => { await request(projectId, `/exports/${encodeURIComponent(exportId)}`, 'DELETE') },
  }
}

/** Fetch execution status for the readonly page's execute → result-page flow. */
export function getSqlIdeExecutionStatus(projectId: number, taskId: string): Promise<{ status: string; historyId?: number | null }> {
  return request(projectId, `/executions/${encodeURIComponent(taskId)}`)
}

