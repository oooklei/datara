/**
 * R8-B 假 Agent（无 LLM mock 适配层）— 悬浮助手测试页 GREEN 前证据（P1-0 步骤 4）。
 * 依据：R8-A 八工具契约 v1 §2-§7（构造注册表+假 handler，逐工具断言请求/响应 schema、
 * 错误映射、预算拦截、审计回链）+ P1-2 主权四条的 mock 镜像（上下文显式传入，缺失即抛）。
 * 边界（隔离于 K1）：零 LLM、零网络、零 ai_copilot 依赖——本文件为 R8-B 测试页专属 mock，
 * 真实适配层（vanna_adapter）与桥接（P1-3）由 BE 侧提供；真实 LLM 联调归 P1-5。
 * 确定性：全部 ID/digest 由调用序号与 djb2 摘要生成，重放可复现。
 */

import {
  R8A_TOOL_VERSION,
  type R8APageContext,
  type R8ARegistryEntry,
  type R8ATool,
  type R8AToolCallRequest,
  type R8AToolCallResponse,
} from '../aiToolsApi'
import { snakeToCamel } from '../adapterKit'

/* ---------- 主权镜像（P1-2 主权第三条 mock 对齐） ---------- */

/** 上下文（project_id）未显式传入时拒绝——与真实适配层 SovereigntyContextMissing 同语义 */
export const MOCK_SOVEREIGNTY_CONTEXT_MISSING = 'MOCK_SOVEREIGNTY_CONTEXT_MISSING: user/project context must be explicit'

/* ---------- 确定性原语 ---------- */

let callSeq = 0

function nextId(prefix: string): string {
  callSeq += 1
  return `${prefix}-mock-${String(callSeq).padStart(6, '0')}`
}

/** djb2 摘要（确定性，仅 mock 语义，非密码学） */
export function mockDigest(input: string): string {
  let h = 5381
  for (let i = 0; i < input.length; i++) {
    h = ((h << 5) + h + input.charCodeAt(i)) | 0
  }
  return `md5x-${(h >>> 0).toString(16).padStart(8, '0')}`
}

/* ---------- 假 generate_sql（规则式 NL→SQL，无 LLM） ---------- */

export interface MockGeneratedSql {
  sql: string
  explanation: string
}

/** 提取目标表：contextRef.table_name → NL 中「表 X」 → 缺省 canned 表；均确定性 */
function resolveTargetTable(nl: string, pageContext: R8APageContext | null): string {
  const fromContext = pageContext?.contextRef
  if (fromContext && typeof fromContext['table_name'] === 'string' && fromContext['table_name'] !== '') {
    return fromContext['table_name']
  }
  const mentioned = /表\s*([A-Za-z_][A-Za-z0-9_.]*)/.exec(nl)
  if (mentioned && mentioned[1]) {
    return mentioned[1]
  }
  return 'dim_customer'
}

/**
 * 规则式 NL→SQL（无 LLM 假 Agent 核心）：按关键词映射查询形态。
 * 返回 SQL 文本，不执行（P1-2 主权第二条镜像：执行只经 R8-A 授权通道 tool-calls 信封）。
 */
export function generateSqlMock(nl: string, pageContext: R8APageContext | null, userId?: string): MockGeneratedSql {
  if (!userId || !pageContext || !pageContext.contextRef || typeof pageContext.contextRef['project_id'] !== 'number') {
    throw new Error(MOCK_SOVEREIGNTY_CONTEXT_MISSING)
  }
  const table = resolveTargetTable(nl, pageContext)
  if (/多少|行数|count|统计/i.test(nl)) {
    return {
      sql: `SELECT COUNT(*) AS row_count FROM ${table}`,
      explanation: `识别到统计意图（关键词 行数/多少），生成对 ${table} 的行数统计查询；目标表来自页面上下文。`,
    }
  }
  if (/最近|最新|top|前\s*\d+/i.test(nl)) {
    return {
      sql: `SELECT * FROM ${table} ORDER BY 1 DESC LIMIT 10`,
      explanation: `识别到「最近/Top」意图，生成 ${table} 按首列倒序取 10 行的查询（mock 预算 row_limit 内）。`,
    }
  }
  return {
    sql: `SELECT * FROM ${table} LIMIT 200`,
    explanation: `默认查询意图：对 ${table} 全列抽样 200 行（R8-A run_sql 默认 row_limit=200）。`,
  }
}

/* ---------- 注册表（§2.4 条目 + §6 v1 数值，PoC 三工具启用） ---------- */

/** PoC 最小工具集（P1-0 步骤 3）：search_schema/validate_sql/run_sql；其余五工具 enabled=false（TOOL_DISABLED） */
export const MOCK_ENABLED_TOOLS: readonly R8ATool[] = ['search_schema', 'validate_sql', 'run_sql']

const RETRY_IDEMPOTENT = { maxAttempts: 2, backoffMs: 500 }

function registryBudget(tool: R8ATool): Record<string, unknown> {
  switch (tool) {
    case 'search_schema':
      return { limit_max: 100, cursor_paging: true }
    case 'validate_sql':
      return { sql_max_kb: 100 }
    case 'run_sql':
      return { row_limit_default: 200, row_limit_max: 1000, timeout_ms_max: 30000 }
    case 'get_workflow':
      return {}
    case 'validate_workflow':
      return { capacity: 'inherit_validate_graph' }
    case 'inspect_workflow_run':
      return { tasks_max: 1000 }
    case 'get_task_metrics':
      return { time_window_days_max: 90 }
    case 'get_lineage':
      return { depth_max: 5, nodes_max: 500 }
  }
}

export function mockRegistry(): R8ARegistryEntry[] {
  return [
    { name: 'search_schema', version: 1, description: '元数据检索（复用 R5-A 元数据目录）', enabled: true, requiredPermissions: [], timeoutMs: 10000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('search_schema') },
    { name: 'validate_sql', version: 1, description: 'SQL 校验（与 R5-A lintSql 同链路）', enabled: true, requiredPermissions: [], timeoutMs: 10000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('validate_sql') },
    { name: 'run_sql', version: 1, description: 'SQL 执行（统一执行链路，不自动重试）', enabled: true, requiredPermissions: [], timeoutMs: 30000, retryPolicy: { maxAttempts: 1, backoffMs: 0 }, budget: registryBudget('run_sql') },
    { name: 'get_workflow', version: 1, description: '工作流定义读取', enabled: false, requiredPermissions: [], timeoutMs: 5000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('get_workflow') },
    { name: 'validate_workflow', version: 1, description: '工作流校验（复用 validate_graph）', enabled: false, requiredPermissions: [], timeoutMs: 15000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('validate_workflow') },
    { name: 'inspect_workflow_run', version: 1, description: '运行记录诊断（Q9 状态词形）', enabled: false, requiredPermissions: [], timeoutMs: 5000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('inspect_workflow_run') },
    { name: 'get_task_metrics', version: 1, description: '任务统计（读四表不推导）', enabled: false, requiredPermissions: [], timeoutMs: 10000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('get_task_metrics') },
    { name: 'get_lineage', version: 1, description: '血缘分析（读血缘存储不推导）', enabled: false, requiredPermissions: [], timeoutMs: 10000, retryPolicy: { ...RETRY_IDEMPOTENT }, budget: registryBudget('get_lineage') },
  ]
}

/* ---------- 审计（§4 字段冻结，成功与失败均写一条） ---------- */

export interface MockAuditRecord {
  auditId: string
  toolCallId: string
  tool: string
  toolVersion: number
  userId: string
  roles: string[]
  projectId: number | null
  requestPayload: Record<string, unknown>
  outcome: 'SUCCESS' | 'ERROR'
  errorCode?: string
  startedAt: string
  finishedAt: string
  latencyMs: number
  budget: Record<string, unknown>
  refs: Record<string, unknown>
}

/* ---------- 信封调用（§2.3 响应 + §5 错误归一 + §6 预算拦截） ---------- */

interface EnvelopeError {
  code: string
  message: string
  details?: Record<string, unknown>
  retryable: boolean
}

class MockEnvelopeError extends Error {
  readonly payload: EnvelopeError
  constructor(payload: EnvelopeError) {
    super(payload.code)
    this.name = 'MockEnvelopeError'
    this.payload = payload
  }
}

function str(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new MockEnvelopeError({ code: 'INVALID_PARAMS', message: `${field} must be a non-empty string`, retryable: false })
  }
  return value
}

function intIn(value: unknown, field: string, min: number, max: number, dflt: number): number {
  if (value === undefined || value === null) return dflt
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) {
    throw new MockEnvelopeError({ code: 'BUDGET_EXCEEDED', message: `${field} out of budget [${min}, ${max}]`, retryable: false })
  }
  return value
}

/** canned 元数据（search_schema handler 数据源，确定性） */
const CANNED_SCHEMA = [
  {
    kind: 'TABLE' as const,
    schemaName: 'dw',
    tableName: 'dim_customer',
    tableComment: '客户维表（canned）',
    columns: [
      { name: 'customer_id', type: 'BIGINT', nullable: false },
      { name: 'customer_name', type: 'VARCHAR(128)', nullable: false },
      { name: 'region', type: 'VARCHAR(32)', nullable: true },
    ],
  },
  {
    kind: 'TABLE' as const,
    schemaName: 'dw',
    tableName: 'fact_order',
    tableComment: '订单事实表（canned）',
    columns: [
      { name: 'order_id', type: 'BIGINT', nullable: false },
      { name: 'customer_id', type: 'BIGINT', nullable: false },
      { name: 'amount', type: 'DECIMAL(18,2)', nullable: true },
    ],
  },
]

function handleSearchSchema(params: Record<string, unknown>): Record<string, unknown> {
  str(params['project_id'] !== undefined ? String(params['project_id']) : '', 'project_id')
  void intIn(params['limit'], 'limit', 1, 100, 20)
  const keyword = typeof params['keyword'] === 'string' ? params['keyword'].toLowerCase() : ''
  const entries = CANNED_SCHEMA.filter(
    (t) => keyword === '' || t.tableName.toLowerCase().includes(keyword) || (t.tableComment ?? '').includes(keyword),
  ).map((t) => ({ ...t, digest: mockDigest(`${t.schemaName}.${t.tableName}`) }))
  return { entries, next_cursor: undefined }
}

function handleValidateSql(params: Record<string, unknown>): Record<string, unknown> {
  const sql = str(params['sql'], 'sql')
  str(params['datasource_id'] as string, 'datasource_id')
  str(params['project_id'] !== undefined ? String(params['project_id']) : '', 'project_id')
  if (sql.length > 100 * 1024) {
    throw new MockEnvelopeError({ code: 'BUDGET_EXCEEDED', message: 'sql exceeds 100 KB budget', retryable: false })
  }
  const issues: Record<string, unknown>[] = []
  const trimmed = sql.trim().toLowerCase()
  if (!trimmed.startsWith('select')) {
    issues.push({ severity: 'WARN', line: 1, column: 1, message: 'mock lint: non-SELECT statement (write semantics governed by permission point)', code: 'MOCK_NON_SELECT' })
  }
  return { valid: issues.length === 0, issues, lint_ref: mockDigest(sql) }
}

function handleRunSql(params: Record<string, unknown>): Record<string, unknown> {
  const sql = str(params['sql'], 'sql')
  const datasourceId = str(params['datasource_id'], 'datasource_id')
  const projectId = params['project_id']
  if (typeof projectId !== 'number') {
    throw new MockEnvelopeError({ code: 'INVALID_PARAMS', message: 'project_id must be a number', retryable: false })
  }
  if (datasourceId !== 'ds-1') {
    throw new MockEnvelopeError({ code: 'NOT_FOUND', message: `datasource ${datasourceId} not found (canned: ds-1)`, retryable: false })
  }
  const rowLimit = intIn(params['row_limit'], 'row_limit', 1, 1000, 200)
  intIn(params['timeout_ms'], 'timeout_ms', 1, 30000, 30000)
  const totalRows = 2
  const rows = [
    [1, '客户A', '华东'],
    [2, '客户B', '华北'],
  ].slice(0, Math.min(rowLimit, totalRows))
  return {
    execution_id: nextId('exec'),
    columns: [
      { name: 'customer_id', type: 'BIGINT' },
      { name: 'customer_name', type: 'VARCHAR(128)' },
      { name: 'region', type: 'VARCHAR(32)' },
    ],
    rows,
    row_count: rows.length,
    truncated: rowLimit < totalRows,
    duration_ms: 3,
    sql_statement_digest: mockDigest(sql),
  }
}

/** 权限上下文快照（§3；信封层由 Backend 注入并校验，mock 层按显式入参承载） */
export interface MockCallContext {
  userId: string
  roles: string[]
}

export interface MockAgent {
  registry: () => R8ARegistryEntry[]
  /** 统一信封调用（§2.3）：成功与失败均回审计回链 auditId */
  call: (request: R8AToolCallRequest, ctx: MockCallContext) => Promise<R8AToolCallResponse>
  auditRecords: () => MockAuditRecord[]
}

export function createMockAgent(): MockAgent {
  const audit: MockAuditRecord[] = []
  const registry = mockRegistry()
  return {
    registry: () => registry,
    auditRecords: () => audit,
    async call(request, ctx) {
      const startedAt = new Date('2026-10-17T00:00:00Z')
      const auditId = nextId('audit')
      const respond = (status: 'SUCCESS' | 'ERROR', result?: Record<string, unknown>, error?: EnvelopeError, refs: Record<string, unknown> = {}) => {
        const finishedAt = new Date('2026-10-17T00:00:00Z')
        const record: MockAuditRecord = {
          auditId,
          toolCallId: request.toolCallId,
          tool: request.tool,
          toolVersion: request.toolVersion,
          userId: ctx.userId,
          roles: [...ctx.roles],
          projectId: typeof request.params['project_id'] === 'number' ? request.params['project_id'] : null,
          requestPayload: { ...request.params },
          outcome: status,
          errorCode: error?.code,
          startedAt: startedAt.toISOString(),
          finishedAt: finishedAt.toISOString(),
          latencyMs: 0,
          budget: {},
          refs,
        }
        audit.push(record)
        // FE 视角（模拟完整 wire+适配路径）：handler 产 wire snake_case → snakeToCamel 归一（adapterKit §2.1）
        const response: R8AToolCallResponse = {
          toolCallId: request.toolCallId,
          tool: request.tool,
          toolVersion: request.toolVersion,
          status,
          auditId,
          serverTime: finishedAt.toISOString(),
        }
        if (result !== undefined) response.result = snakeToCamel(result)
        if (error !== undefined) response.error = { ...error }
        return response
      }
      try {
        const entry = registry.find((e) => e.name === request.tool)
        if (!entry) {
          return respond('ERROR', undefined, { code: 'TOOL_NOT_FOUND', message: `tool ${request.tool} not in registry`, retryable: false })
        }
        if (request.toolVersion !== R8A_TOOL_VERSION) {
          return respond('ERROR', undefined, { code: 'TOOL_VERSION_MISMATCH', message: `tool_version ${request.toolVersion} != registry ${R8A_TOOL_VERSION}`, retryable: false })
        }
        if (!entry.enabled) {
          return respond('ERROR', undefined, { code: 'TOOL_DISABLED', message: `tool ${request.tool} disabled in PoC minimal set`, retryable: false })
        }
        if (!request.toolCallId || typeof request.toolCallId !== 'string') {
          return respond('ERROR', undefined, { code: 'INVALID_PARAMS', message: 'tool_call_id must be a non-empty string', retryable: false })
        }
        let result: Record<string, unknown>
        if (request.tool === 'search_schema') {
          result = handleSearchSchema(request.params)
        } else if (request.tool === 'validate_sql') {
          result = handleValidateSql(request.params)
        } else if (request.tool === 'run_sql') {
          result = handleRunSql(request.params)
        } else {
          return respond('ERROR', undefined, { code: 'INTERNAL_ERROR', message: 'no handler', retryable: false })
        }
        return respond('SUCCESS', result, undefined, { datasource_id: request.params['datasource_id'] })
      } catch (e) {
        if (e instanceof MockEnvelopeError) {
          return respond('ERROR', undefined, e.payload)
        }
        return respond('ERROR', undefined, { code: 'INTERNAL_ERROR', message: e instanceof Error ? e.message : String(e), retryable: false })
      }
    },
  }
}
