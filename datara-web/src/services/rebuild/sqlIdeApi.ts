/**
 * R5-A（SQL IDE 只读能力）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/sql-ide/*），最终以 Codex A5（rebuild/sql_ide/）契约为权威；
 * 本文件语义源自 docs/increments/R5-IDE-开始前影响分析.md §3（legacy ideApi.ts 只读子集 + routines 扩展）。
 * RED 约定：所有 I/O 方法在 A5 后端接入前抛 R5A_BACKEND_NOT_WIRED，不发出任何真实请求。
 * 边界：只读子集——不包含 DDL 写路径（R5-B）、表数据编辑（rows/apply）、全局参数（params）。
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
  status: 'success' | 'failure' | 'canceled'
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
  status: 'success' | 'failure' | 'canceled'
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

/* ---------- RED 哨兵 ---------- */

export const R5A_BACKEND_NOT_WIRED = 'R5A_BACKEND_NOT_WIRED: A5 (rebuild/sql_ide) contract not connected yet'

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

/* ---------- RED 实现（A5 接入前统一抛哨兵；方法清单见 R5A_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(R5A_BACKEND_NOT_WIRED)
}

/** 同步契约方法（openEventStream 返回 EventSource 实例，非 Promise） */
const notWiredSync = (): never => {
  throw new Error(R5A_BACKEND_NOT_WIRED)
}

/**
 * R5-A 契约工厂（原型态）：签名与类型已冻结，实现在 Codex A5（rebuild/sql_ide/）就绪后
 * 按本接口逐方法替换，UI 层（SqlIdeReadonlyView）不感知切换。
 */
export function createSqlIdeContract(): SqlIdeContract {
  return {
    listDatabases: notWired,
    listSchemas: notWired,
    listRelations: notWired,
    listColumns: notWired,
    listRoutines: notWired,
    listIndexes: notWired,
    searchObjects: notWired,
    lintSql: notWired,
    executeSql: notWired,
    cancelExecution: notWired,
    openEventStream: notWiredSync,
    fetchResultPage: notWired,
    listHistory: notWired,
    deleteHistory: notWired,
    listScripts: notWired,
    saveScript: notWired,
    deleteScript: notWired,
  }
}

