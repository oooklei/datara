/**
 * R5-B DDL 契约（sqlIdeDdlApi）——16.1 波2 契约转绿。
 *
 * 五方法契约（R5B_CONTRACT_METHODS 冻结，A6 纪律）：
 *  - getDefinition        POST /api/v1/projects/{projectId}/sql-ide/definitions    （复用 R5-A shared read）
 *  - validatePolicy       POST /api/v1/rebuild/sql-ide-ddl/validate-policy
 *  - previewImpact        POST /api/v1/rebuild/sql-ide-ddl/preview-impact
 *  - submitConfirm        POST /api/v1/rebuild/sql-ide-ddl/confirm
 *  - listExecutionRecords POST /api/v1/rebuild/sql-ide-ddl/execution-records
 *
 * wire 纪律：
 *  - 请求体 camelCase 原样发送（BE pydantic 请求模型顶层 camel，objectRef 为 dict 透传）；
 *  - 响应经 normalizeResponse 递归 snake→camel 归一（#23 嵌套 objectRef.datasource_id 等）；
 *  - 非零包络经 ContractApiError 转译为 SqlIdeDdlApiError（code/errorCode 透传）。
 *
 * A7 红线（验收 v4）：
 *  - submitConfirm 确认短语空/空白在契约层拒发（CONFIRM_PHRASE_INVALID 400，不发请求）；
 *  - previewImpact 仅回传影响关系与元数据，不回传样本值；
 *  - getDefinition 缺 sourceVersion 即 fail-closed（SOURCE_VERSION_UNAVAILABLE 502），拒入写链。
 */
import { ContractApiError, request as httpRequest } from '../http'

/** DDL 目标对象类别（与 BE ObjectRef.kind 对齐）。 */
export type DdlObjectKind = 'table' | 'view' | 'function' | 'procedure' | 'trigger'

/** 策略结论级别（BE PolicyFinding.level：block/warn/info）。 */
export type PolicyLevel = 'block' | 'warn' | 'info'

/** DDL 目标对象引用（请求侧 camel 发送；响应侧经归一）。 */
export interface DdlObjectRef {
  datasourceId: number
  database: string
  catalog?: string | null
  schema?: string | null
  kind: DdlObjectKind
  name: string
  parent?: string | null
}

/** 策略发现（= BE #22 findings wire 形，逐字保留）。 */
export interface DdlPolicyFinding {
  level: PolicyLevel
  code: string
  message: string
  impacts: string[]
}

/** 策略快照报告（#22）。 */
export interface DdlPolicyReport {
  snapshotId: string
  findings: DdlPolicyFinding[]
  blocked: boolean
}

/** 影响关系类型（BE relation_type：dependent/downstream/permission）。 */
export type DdlImpactRelationType = 'dependent' | 'downstream' | 'permission'

/** 影响项（#23；仅关系与元数据，不含样本值——A7）。 */
export interface DdlImpactItem {
  objectRef: DdlObjectRef
  relationType: DdlImpactRelationType
  detail: string
}

/** 影响快照报告（#23）。 */
export interface DdlImpactReport {
  snapshotId: string
  impacts: DdlImpactItem[]
  unknownReasons: string[]
}

/** #22/#23 请求体（camel 原样发送）。 */
export interface DdlValidationRequest {
  datasourceId: number
  objectRef: DdlObjectRef
  sourceVersion: string
  nextDdlText: string
}

/** #24 请求体（= BE SubmitConfirmRequest 字段逐一对应）。 */
export interface DdlConfirmRequest extends DdlValidationRequest {
  policySnapshotId: string
  impactSnapshotId: string
  confirmPhrase: string
}

/** 执行记录状态（BE ExecutionRecord.status 五态）。 */
export type DdlExecutionStatus = 'success' | 'failure' | 'rolled-back' | 'compensated' | 'recovery-failed'

/** #24 响应（= BE SubmitConfirmResponse）。 */
export interface DdlExecutionOutcome {
  recordId: string
  status: DdlExecutionStatus
}

/** #25 执行记录（v3 §4 七字段）。 */
export interface DdlExecutionRecord {
  recordId: string
  actorId: number
  action: string
  scriptHash: string
  executedAt: string
  status: DdlExecutionStatus
  failureSummary: string | null
}

/** #25 分页响应。 */
export interface DdlExecutionRecordPage {
  items: DdlExecutionRecord[]
  page: {
    nextCursor: string | null
    hasMore: boolean
  }
}

/** #21 请求载荷。 */
export interface DdlDefinitionRequest {
  datasourceId: number
  objectRef: DdlObjectRef
}

/** #21 定义快照（sourceVersion 必在——fail-closed 保证）。 */
export interface DdlDefinitionSnapshot {
  objectRef: DdlObjectRef
  definition: string
  sourceVersion: string
  capability: string
  constraints: string[]
}

/** #25 查询载荷。 */
export interface DdlExecutionRecordQuery {
  datasourceId: number
  objectRef?: DdlObjectRef
  page?: number
  pageSize?: number
}

// ========== A6 冻结面（方法名与权限矩阵逐字保留纪律） ==========

export const R5B_CONTRACT_METHODS = ['getDefinition', 'validatePolicy', 'previewImpact', 'submitConfirm', 'listExecutionRecords'] as const

export type R5BContractMethod = (typeof R5B_CONTRACT_METHODS)[number]

export const R5B_PERMISSION_MATRIX = {
  getDefinition: 'VIEW_ALL',
  validatePolicy: 'EDIT_DEFINITION',
  previewImpact: 'VIEW_ALL',
  submitConfirm: 'EDIT_DEFINITION',
  listExecutionRecords: 'VIEW_ALL',
} as const satisfies Record<R5BContractMethod, 'VIEW_ALL' | 'EDIT_DEFINITION'>

// ========== 传输层 ==========

const API_BASE = '/projects'
const RB_BASE = '/rebuild/sql-ide-ddl'
const DEFAULT_PAGE = 1
const DEFAULT_PAGE_SIZE = 50
const MAX_PAGE_SIZE = 200

/** R5-B DDL 契约错误（code=HTTP/包络码，errorCode=域稳定码，details=包络 details）。 */
export class SqlIdeDdlApiError extends Error {
  readonly code: number
  readonly errorCode?: string
  readonly details?: unknown
  constructor(message: string, code: number, errorCode?: string, details?: unknown) {
    super(message)
    this.name = 'SqlIdeDdlApiError'
    this.code = code
    this.errorCode = errorCode
    this.details = details
  }
}

/** 响应键形递归归一：snake_case → camelCase（#23 嵌套 objectRef.datasource_id 等）。 */
function normalizeResponse(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeResponse)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()), normalizeResponse(item),
  ]))
}

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  try {
    const data = await httpRequest<T>(path, { method, json: body, preserveEnvelopeCode: true })
    return normalizeResponse(data) as T
  } catch (error) {
    if (error instanceof ContractApiError) {
      const raw = error.raw as { data?: { errorCode?: string; details?: unknown } } | undefined
      throw new SqlIdeDdlApiError(error.message, Number(error.code), raw?.data?.errorCode, raw?.data?.details)
    }
    throw error
  }
}

// ========== 契约 ==========

export interface SqlIdeDdlContract {
  getDefinition: (datasourceId: number, objectRef: DdlObjectRef) => Promise<DdlDefinitionSnapshot>
  validatePolicy: (input: DdlValidationRequest) => Promise<DdlPolicyReport>
  previewImpact: (input: DdlValidationRequest) => Promise<DdlImpactReport>
  submitConfirm: (input: DdlConfirmRequest) => Promise<DdlExecutionOutcome>
  listExecutionRecords: (query: DdlExecutionRecordQuery) => Promise<DdlExecutionRecordPage>
}

export function createSqlIdeDdlContract(projectId = 1): SqlIdeDdlContract {
  return {
    getDefinition: async (datasourceId, objectRef) => {
      const result = await request<{
        objectRef?: DdlObjectRef
        definitionText?: string
        definition?: string
        sourceVersion?: string
        capability: string
        constraints: string[]
      }>(`${API_BASE}/${projectId}/sql-ide/definitions`, 'POST', {
        datasourceId,
        database: objectRef.database,
        objectKind: objectRef.kind,
        objectRef,
      })
      const definition = result.definitionText ?? result.definition
      if (definition === undefined) throw new SqlIdeDdlApiError('定义响应缺少 definitionText', 502, 'INVALID_RESPONSE')
      const sourceVersion = result.sourceVersion
      if (!sourceVersion || sourceVersion.trim() === '') {
        throw new SqlIdeDdlApiError('定义响应缺少 sourceVersion，DDL 写链 fail-closed', 502, 'SOURCE_VERSION_UNAVAILABLE')
      }
      return { objectRef: result.objectRef ?? objectRef, definition, sourceVersion, capability: result.capability, constraints: result.constraints ?? [] }
    },

    validatePolicy: (input) => request<DdlPolicyReport>(`${RB_BASE}/validate-policy`, 'POST', input),

    previewImpact: (input) => request<DdlImpactReport>(`${RB_BASE}/preview-impact`, 'POST', input),

    submitConfirm: async (input) => {
      if (!input.confirmPhrase || input.confirmPhrase.trim() === '') {
        throw new SqlIdeDdlApiError('确认短语为空，拒绝提交 DDL 写操作', 400, 'CONFIRM_PHRASE_INVALID')
      }
      return request<DdlExecutionOutcome>(`${RB_BASE}/confirm`, 'POST', input)
    },

    listExecutionRecords: async (query) => {
      if (query.page !== undefined && (!Number.isInteger(query.page) || query.page < 1)) {
        throw new RangeError(`page 必须为 ≥1 的整数，收到 ${query.page}`)
      }
      if (query.pageSize !== undefined && (!Number.isInteger(query.pageSize) || query.pageSize < 1 || query.pageSize > MAX_PAGE_SIZE)) {
        throw new RangeError(`pageSize 必须为 1..${MAX_PAGE_SIZE} 的整数，收到 ${query.pageSize}`)
      }
      const body: { datasourceId: number; objectRef?: DdlObjectRef; page: number; pageSize: number } = {
        datasourceId: query.datasourceId,
        page: query.page ?? DEFAULT_PAGE,
        pageSize: query.pageSize ?? DEFAULT_PAGE_SIZE,
      }
      if (query.objectRef !== undefined) body.objectRef = query.objectRef
      return request<DdlExecutionRecordPage>(`${RB_BASE}/execution-records`, 'POST', body)
    },
  }
}
