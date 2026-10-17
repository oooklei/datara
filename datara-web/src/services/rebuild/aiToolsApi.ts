/**
 * R8-A（AI 八工具统一契约）FE 消费面 — RED 态（R8-B 悬浮助手测试页 GREEN 前证据）。
 * 契约真源：docs/increments/2026-10-17-R8-A八工具契约.md（v1 冻结面，tool_version=1）：
 *   §2.1 端点 GET /api/v1/rebuild/ai/tools + POST /api/v1/rebuild/ai/tool-calls（统一前缀 /api/v1/rebuild/ai，监督 #147 裁定一；单一调用端点，信封层统一
 *        权限/审计/预算/错误归一）；§2.2/§2.3 请求/响应信封；§2.4 注册表条目；§5 错误码空间；
 *        §6 超时/重试/预算；§7 八工具差异契约。
 * 红线（冻结不可豁免）：八工具全部经统一调用链路，不另建执行引擎；BE 未接线（P1-3 ai_copilot
 * 桥接后接线）前本工厂全部方法拒绝 R8A_BACKEND_NOT_WIRED，不存在半连通状态。
 * mock 契约面验证走 views/rebuild/validation/ai-assistant/mockAgent.ts（假 Agent，无 LLM，隔离于 K1）。
 */

/* ---------- §2.2 工具名单与上下文（冻结词形） ---------- */

/** 八工具名单（§2.2 tool 枚举，冻结顺序） */
export const R8A_TOOLS = [
  'search_schema',
  'validate_sql',
  'run_sql',
  'get_workflow',
  'validate_workflow',
  'inspect_workflow_run',
  'get_task_metrics',
  'get_lineage',
] as const

export type R8ATool = (typeof R8A_TOOLS)[number]

/** 十类 page_context（§2.2 context_type，设计 §11 十类上下文） */
export const R8A_CONTEXT_TYPES = [
  'PROJECT',
  'WORKFLOW',
  'NODE',
  'SQL',
  'DATASOURCE',
  'VARIABLE',
  'RUN',
  'METRICS',
  'METADATA',
  'LINEAGE',
] as const

export type R8AContextType = (typeof R8A_CONTEXT_TYPES)[number]

/** 契约版本（§1 版本规则：契约级变更须再冻结并递增） */
export const R8A_TOOL_VERSION = 1

/* ---------- §2.2/§2.3 信封类型 ---------- */

export interface R8APageContext {
  contextType: R8AContextType
  /** 按 context_type 携带对应实体标识；悬浮入口无页面上下文时可为 null */
  contextRef: Record<string, unknown> | null
}

export interface R8AToolCallRequest<P = Record<string, unknown>> {
  /** FE 生成，ULID/uuid，幂等与追踪键 */
  toolCallId: string
  tool: R8ATool
  toolVersion: number
  params: P
  pageContext: R8APageContext | null
}

export interface R8AToolCallError {
  code: string
  message: string
  details?: Record<string, unknown>
  /** FE 重试决策唯一依据 */
  retryable: boolean
}

export interface R8AToolCallResponse<T = Record<string, unknown>> {
  toolCallId: string
  tool: string
  toolVersion: number
  status: 'SUCCESS' | 'ERROR'
  result?: T
  error?: R8AToolCallError
  /** 成功与失败均返回（§2.3） */
  auditId: string
  serverTime: string
}

/* ---------- §2.4 注册表条目 ---------- */

export interface R8ARetryPolicy {
  maxAttempts: number
  backoffMs: number
}

export interface R8ARegistryEntry {
  name: string
  version: number
  description: string
  enabled: boolean
  /** 权限点词形为 N-C（P2）冻结面，冻结前可为空数组（§8） */
  requiredPermissions: string[]
  timeoutMs: number
  retryPolicy: R8ARetryPolicy
  budget: Record<string, unknown>
}

/* ---------- §5 错误码空间（冻结词形，禁新增未登记码） ---------- */

export const R8A_ERROR_CODES = [
  'TOOL_NOT_FOUND',
  'TOOL_VERSION_MISMATCH',
  'TOOL_DISABLED',
  'INVALID_PARAMS',
  'PERMISSION_DENIED',
  'BUDGET_EXCEEDED',
  'NOT_FOUND',
  'DEPENDENCY_UNAVAILABLE',
  'EXECUTION_TIMEOUT',
  'EXECUTION_FAILED',
  'EXECUTION_CANCELLED',
  'INTERNAL_ERROR',
] as const

export type R8AErrorCode = (typeof R8A_ERROR_CODES)[number]

/* ---------- §7 PoC 三工具返回结构（最小工具集，P1-0 步骤 3/4） ---------- */

export interface R8ASearchSchemaEntry {
  kind: 'TABLE' | 'VIEW'
  schemaName: string
  tableName: string
  tableComment?: string
  columns?: { name: string; type: string; nullable: boolean; comment?: string }[]
  digest: string
}

export interface R8ASearchSchemaResult {
  entries: R8ASearchSchemaEntry[]
  nextCursor?: string
}

export interface R8AValidateSqlIssue {
  severity: 'ERROR' | 'WARN' | 'INFO'
  line: number
  column: number
  message: string
  code: string
}

export interface R8AValidateSqlResult {
  valid: boolean
  issues: R8AValidateSqlIssue[]
  lintRef: string
}

export interface R8ARunSqlResult {
  executionId: string
  columns: { name: string; type: string }[]
  rows: unknown[][]
  rowCount: number
  truncated: boolean
  durationMs: number
  sqlStatementDigest: string
}

/* ---------- RED 哨兵与契约方法 ---------- */

export const R8A_BACKEND_NOT_WIRED = 'R8A_BACKEND_NOT_WIRED: rebuild/ai unified tool endpoint not connected yet'

/** 契约方法清单（测试与 UI 横幅共用）：八工具 + 注册表发现（§2.1 两端点） */
export const R8A_CONTRACT_METHODS = [
  'discoverRegistry',
  'searchSchema',
  'validateSql',
  'runSql',
  'getWorkflow',
  'validateWorkflow',
  'inspectWorkflowRun',
  'getTaskMetrics',
  'getLineage',
] as const

export type R8AContractMethod = (typeof R8A_CONTRACT_METHODS)[number]

export interface R8AToolsContract {
  /** GET /api/v1/rebuild/ai/tools（§2.4 条目数组） */
  discoverRegistry: () => Promise<R8ARegistryEntry[]>
  searchSchema: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<R8ASearchSchemaResult>
  validateSql: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<R8AValidateSqlResult>
  runSql: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<R8ARunSqlResult>
  getWorkflow: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<Record<string, unknown>>
  validateWorkflow: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<Record<string, unknown>>
  inspectWorkflowRun: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<Record<string, unknown>>
  getTaskMetrics: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<Record<string, unknown>>
  getLineage: (params: Record<string, unknown>, pageContext: R8APageContext | null) => Promise<Record<string, unknown>>
}

/** 统一信封调用原语（POST /api/v1/rebuild/ai/tool-calls；信封层统一权限/审计/预算/错误归一） */
export type R8AToolCallInvoker = (request: R8AToolCallRequest) => Promise<R8AToolCallResponse>

/**
 * RED 工厂：BE 统一端点接线前（P1-3 桥接 + 信封层落地）全部方法拒绝 R8A_BACKEND_NOT_WIRED。
 * 各方法异步 rejected promise（与既有契约「异步拒绝」形态一致，UI .catch() 链不因接线改变）。
 */
export function createAiToolsContract(): R8AToolsContract {
  const refuse = async (): Promise<never> => {
    throw new Error(R8A_BACKEND_NOT_WIRED)
  }
  return {
    discoverRegistry: refuse,
    searchSchema: refuse,
    validateSql: refuse,
    runSql: refuse,
    getWorkflow: refuse,
    validateWorkflow: refuse,
    inspectWorkflowRun: refuse,
    getTaskMetrics: refuse,
    getLineage: refuse,
  }
}
