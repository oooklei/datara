/**
 * SQL IDE readonly contract client for the A5 rebuild/sql_ide API.
 * Scope: query and metadata operations only; DDL, row editing, and global parameters stay outside this client.
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

export interface DataSourceRef {
  id: number
  name: string
  /** 能力矩阵标记（design §7.1）：跨 Schema 补全/查询是否可用 */
  crossSchema: boolean
}

export interface DatabaseMeta {
  name: string
  defaultSchema?: string | null
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
}

export interface SqlResultPage {
  stmtIndex: number
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
}

export interface ScriptEntry {
  id: number
  name: string
  sqlText: string
  updatedAt: string
}

export interface LintItem {
  stmtIndex: number
  level: 'error' | 'warning'
  line: number
  col: number
  message: string
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
  return envelope.data as T
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
    withCredentials: false,
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
    const token = getToken()
    if (token) headers.token = token
    if (lastEventId) headers['Last-Event-ID'] = lastEventId
    try {
      const response = await fetch(url, { headers, signal: controller.signal })
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
] as const

export type R5AContractMethod = (typeof R5A_CONTRACT_METHODS)[number]

export interface SqlIdeContract {
  listDatabases: (datasourceId: number) => Promise<DatabaseMeta[]>
  listSchemas: (datasourceId: number, database: string) => Promise<SchemaMeta[]>
  listRelations: (datasourceId: number, database: string, schema: string | null, kind: 'table' | 'view') => Promise<RelationMeta[]>
  listColumns: (datasourceId: number, database: string, table: string, schema: string | null) => Promise<ColumnMeta[]>
  listRoutines: (datasourceId: number, database: string, schema: string | null, kind: RoutineMeta['kind']) => Promise<RoutineMeta[]>
  listIndexes: (datasourceId: number, database: string, table: string) => Promise<IndexMeta[]>
  searchObjects: (datasourceId: number, keyword: string) => Promise<{ kind: ObjectKind; name: string; parent: string | null }[]>
  lintSql: (datasourceId: number, sql: string) => Promise<LintItem[]>
  executeSql: (request: SqlExecuteRequest) => Promise<{ taskId: string }>
  cancelExecution: (taskId: string) => Promise<{ canceled: boolean }>
  /** SSE 只读流：返回 EventSource（token 沿 R3 runner 注入先例，禁止落 storage） */
  openEventStream: (taskId: string) => EventSource
  fetchResultPage: (historyId: number, stmtIndex: number, offset: number, limit: number) => Promise<SqlResultPage>
  listHistory: (datasourceId: number) => Promise<HistoryEntry[]>
  deleteHistory: (historyId: number) => Promise<void>
  listScripts: () => Promise<ScriptEntry[]>
  saveScript: (input: { id?: number; name: string; sqlText: string }) => Promise<ScriptEntry>
  deleteScript: (id: number) => Promise<void>
}

/* ---------- API 实现（方法清单见 R5A_CONTRACT_METHODS） ---------- */

/**
 * Creates the readonly SQL IDE client for the connected A5 endpoints.
 */
export function createSqlIdeContract(projectId = 1): SqlIdeContract {
  return {
    listDatabases: (datasourceId) => request(projectId, `/databases${query({ datasourceId })}`),
    listSchemas: (datasourceId, database) => request(projectId, `/schemas${query({ datasourceId, database })}`),
    listRelations: (datasourceId, database, schema, kind) => request(projectId, `/relations${query({ datasourceId, database, schema, kind })}`),
    listColumns: (datasourceId, database, table, schema) => request(projectId, `/columns${query({ datasourceId, database, table, schema })}`),
    listRoutines: (datasourceId, database, schema, kind) => request(projectId, `/routines${query({ datasourceId, database, schema, kind })}`),
    listIndexes: (datasourceId, database, table) => request(projectId, `/indexes${query({ datasourceId, database, table })}`),
    searchObjects: (datasourceId, keyword) => request(projectId, `/objects/search${query({ datasourceId, keyword })}`),
    lintSql: (datasourceId, sql) => request(projectId, '/lint', 'POST', { datasourceId, sql }),
    executeSql: (input) => request(projectId, '/executions', 'POST', input),
    cancelExecution: async (taskId) => {
      const response = await request<{ accepted: boolean; status: string }>(projectId, `/executions/${encodeURIComponent(taskId)}/cancel`, 'POST')
      return { canceled: response.accepted }
    },
    openEventStream: (taskId) => openAuthenticatedEventStream(projectId, taskId),
    fetchResultPage: (historyId, stmtIndex, offset, limit) => request(projectId, `/results/${historyId}${query({ stmtIndex, offset, limit })}`),
    listHistory: (datasourceId) => request(projectId, `/history${query({ datasourceId })}`),
    deleteHistory: async (historyId) => { await request(projectId, `/history/${historyId}`, 'DELETE') },
    listScripts: () => request(projectId, '/scripts'),
    saveScript: (input) => request(projectId, '/scripts', 'POST', input),
    deleteScript: async (id) => { await request(projectId, `/scripts/${id}`, 'DELETE') },
  }
}

/** Fetch execution status for the readonly page's execute → result-page flow. */
export function getSqlIdeExecutionStatus(projectId: number, taskId: string): Promise<{ status: string; historyId?: number | null }> {
  return request(projectId, `/executions/${encodeURIComponent(taskId)}`)
}

