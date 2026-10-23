/**
 * 质量五项批 A（WBS 增量 14 包 14.4 批 A）质量域契约层 — IMPL-v4-07。
 *
 * 端点实证：`datara-backend/rebuild/governance/api.py`
 *   router prefix = `/api/v1/rebuild/governance`（L184）
 *   POST /projects/{project_id}/quality-rules                  L1632（201；EDIT_DEFINITION）
 *   GET  /projects/{project_id}/quality-rules                  L1678（VIEW_ALL；page/page_size）
 *   GET  /projects/{project_id}/quality-runs                   L1728（VIEW_ALL；page/page_size）
 *   POST /projects/{project_id}/quality-rules/{rule_id}/run    L1768（201；EDIT_DEFINITION）
 *
 * 包络：`{code,msg,data}` 三态（R2 批次冻结口径）；非 2xx 经 `preserveEnvelopeCode`
 *   保后端码透出（A2 §2/§4 错误映射）——本域错误码为 4xxx 业务段（4041/4091），
 *   不透出则前端只能拿到 HTTP 状态码，无法定位「重名 / 规则停用 / 不存在」。
 *
 * 命名口径：FE 面 camelCase ↔ wire snake_case，经 adapterKit 冻结原语深度转换
 *   （请求 `camelToSnake` / 响应 `snakeToCamel`）。后端 pydantic 输入模型无
 *   `alias_generator`（api.py L119-124 `QualityRuleInput` 为 snake_case），
 *   故 wire 词形唯一为 snake_case。
 *
 * structural 语义红线（验收 ④；后端 L1755-1757 注释 + L1785-1793 实现）：
 *   run 端点只做**结构谓词校验**，`checked_rows/success_rows/failed_rows/skipped_rows`
 *   四字段**恒 0**，`summary.engine` 恒为 `"structural"`；行级采样需绑定数据源，属后续增量。
 *   前端**不得**把四字段渲染成真实行级结果，也不得据 `summary` 推导未返回的行级语义。
 */

import { camelToSnake, snakeToCamel } from './adapterKit'
import { deleteJson, getJson, postJson, putJson } from '../http'

/* ---------- 类型面 ---------- */

export type QualitySeverity = 'info' | 'warning' | 'error'

export type QualityRunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

/** 质量域权限点（与后端 `Permission` 枚举词形一致）。 */
export type QualityRulePermission = 'VIEW_ALL' | 'EDIT_DEFINITION'

/** 建规则入参（wire 词形 `asset_id`；severity 后端 pattern `^(info|warning|error)$`）。 */
export interface QualityRuleDraft {
  assetId: number
  name: string
  expression: string
  severity: QualitySeverity
  enabled: boolean
}

/** 规则记录（POST 返回含 `projectId`；GET 列表项不含 `projectId`，故为可选）。 */
export interface QualityRuleRecord {
  id: number
  projectId?: number
  assetId: number
  name: string
  expression: string
  severity: QualitySeverity
  enabled: boolean
  createdAt: string | null
  updatedAt: string | null
}

/** 运行摘要（structural 引擎：`issues` 为命中的禁用词列表，恒为数组）。 */
export interface QualityRunSummary {
  engine: 'structural'
  message: string
  issues: string[]
}

/** 运行记录（行级四字段恒 0，见文件头 structural 红线）。 */
export interface QualityRunRecord {
  id: number
  assetId: number
  ruleId: number | null
  status: QualityRunStatus
  checkedRows: number
  successRows: number
  failedRows: number
  skippedRows: number
  summary: QualityRunSummary
  generatedAt: string | null
}

export interface QualityRulePage {
  total: number
  list: QualityRuleRecord[]
}

export interface QualityRunPage {
  total: number
  list: QualityRunRecord[]
}

/* ---------- 资产、标签、血缘 ---------- */

export type AssetType = string

export interface AssetField {
  id: number
  fieldName: string
  ordinalPosition: number
  dataType: string
  nullable: boolean
  description: string
  createdAt: string | null
  updatedAt: string | null
}

export interface AssetTag {
  id: number
  namespace: string
  tagKey: string
  displayName: string
  description: string
  createdAt: string | null
  updatedAt: string | null
}

export interface AssetRecord {
  id: number
  projectId: number
  sourceSystem: string
  databaseName: string
  schemaName: string
  assetName: string
  assetType: AssetType
  displayName: string
  description: string
  ownerName: string
  domainName: string
  rowCount: number | null
  createdAt: string | null
  updatedAt: string | null
  tags?: AssetTag[]
  fields?: AssetField[]
  qualityRuns?: QualityRunRecord[]
}

export interface AssetPage {
  total: number
  page: number
  pageSize: number
  list: AssetRecord[]
}

export interface LineageNode extends AssetRecord {}

export interface LineageEdge {
  id: number
  externalId: string
  sourceAssetId: number
  targetAssetId: number
  sourceFieldName: string
  targetFieldName: string
  lineageType: string
  processRef: string
  createdAt: string | null
}

export interface LineageGraph {
  assetId: number
  direction: 'upstream' | 'downstream' | 'both'
  depth: number
  nodes: LineageNode[]
  edges: LineageEdge[]
}

export interface GovernanceTagDefinition {
  id: number
  namespace: string
  tagKey: string
  displayName: string
  description: string
  createdAt: string | null
  updatedAt: string | null
}

export interface TagDraft {
  namespace?: string
  tagKey: string
  displayName: string
  description?: string
  assetId?: number | null
}

/* ---------- 标准、指标 ---------- */

export type DefinitionStatus = 'draft' | 'active' | 'retired'

export interface StandardDefinition {
  id: number
  projectId: number
  code: string
  name: string
  dataType: string
  expression: string
  description: string
  status: DefinitionStatus
  createdAt: string | null
  updatedAt: string | null
}

export interface MetricDefinition {
  id: number
  projectId: number
  code: string
  name: string
  formula: string
  description: string
  status: DefinitionStatus
  createdAt: string | null
  updatedAt: string | null
}

export interface StandardCheckResult {
  standardId: number
  code: string
  passed: boolean
  engine: string
  findings: unknown[]
  checkedAt: string | null
}

/** 审计事件（`GET /projects/{id}/audit`；`resource_id` 后端为字符串列）。 */
export interface AuditEventRecord {
  id: number
  actorId: number
  action: string
  resourceType: string
  resourceId: string
  requestId: string
  after: unknown
  generatedAt: string | null
}

export interface AuditEventPage {
  total: number
  list: AuditEventRecord[]
}

export interface StandardPage {
  total: number
  list: StandardDefinition[]
}

export interface MetricPage {
  total: number
  list: MetricDefinition[]
}

/* ---------- 冻结面（权限矩阵 / 错误码 / structural 口径） ---------- */

/** 质量域四端点 → 权限点（只读面 VIEW_ALL，写面 EDIT_DEFINITION）。 */
export const QUALITY_PERMISSION_MATRIX = Object.freeze({
  listRules: 'VIEW_ALL',
  createRule: 'EDIT_DEFINITION',
  runRule: 'EDIT_DEFINITION',
  listRuns: 'VIEW_ALL',
} as const satisfies Record<string, QualityRulePermission>)

/** 质量域错误码（后端 `fail()` 第二段；1003 为项目成员鉴权失败）。 */
export const QUALITY_ERROR_CODES = Object.freeze({
  permissionDenied: 1003,
  notFound: 4041,
  duplicateName: 4091,
  disabled: 4091,
  runPersistFailed: 4091,
  invalidInput: 4103,
} as const)

/**
 * structural 引擎口径常量（验收 ④ 单一事实源）：前端文案与断言均引用本常量，
 * 不各自硬编码英文串。
 */
export const QUALITY_STRUCTURAL_ONLY = Object.freeze({
  engine: 'structural',
  message: 'structural predicate validation only; row-level sampling requires a bound datasource',
} as const)

/* ---------- 端点面 ---------- */

const BASE = '/rebuild/governance'
const PRESERVE_ERROR = { preserveEnvelopeCode: true } as const

/**
 * 质量规则 / 运行记录契约层（项目域，四端点）。
 *
 * 响应方向在**解析后**做 snake→camel 深度转换（`await` 之后，非作用在 Promise 上）；
 * 请求方向在建规则时做 camel→snake。
 */
export const governanceApi = {
  /* ---------- 资产 ---------- */
  async listAssets(
    projectId: number,
    params: { q?: string; assetType?: string; domain?: string; tag?: string; page?: number; pageSize?: number } = {},
  ): Promise<AssetPage> {
    const data = await getJson<unknown>(
      `${BASE}/projects/${projectId}/assets`,
      {
        q: params.q,
        assetType: params.assetType,
        domain: params.domain,
        tag: params.tag,
        page: params.page ?? 1,
        pageSize: params.pageSize ?? 50,
      },
      PRESERVE_ERROR,
    )
    return snakeToCamel(data) as AssetPage
  },

  async getAsset(assetId: number): Promise<AssetRecord> {
    const data = await getJson<unknown>(`${BASE}/assets/${assetId}`, undefined, PRESERVE_ERROR)
    return snakeToCamel(data) as AssetRecord
  },

  async createAsset(
    projectId: number,
    body: {
      sourceSystem: string
      databaseName: string
      schemaName?: string
      assetName: string
      assetType: string
      displayName?: string
      description?: string
      ownerName?: string
      domainName?: string
      rowCount?: number | null
      fields?: Array<{
        fieldName: string
        ordinalPosition: number
        dataType?: string
        nullable?: boolean
        description?: string
      }>
    },
  ): Promise<AssetRecord> {
    const data = await postJson<unknown>(`${BASE}/projects/${projectId}/assets`, camelToSnake(body), PRESERVE_ERROR)
    return snakeToCamel(data) as AssetRecord
  },

  /* ---------- 标签 ---------- */
  async createTag(projectId: number, draft: TagDraft): Promise<GovernanceTagDefinition> {
    const data = await postJson<unknown>(`${BASE}/projects/${projectId}/tags`, camelToSnake(draft), PRESERVE_ERROR)
    return snakeToCamel(data) as GovernanceTagDefinition
  },

  async assignAssetTags(assetId: number, tagIds: number[]): Promise<{ assetId: number; tagIds: number[] }> {
    const data = await putJson<unknown>(`${BASE}/assets/${assetId}/tags`, { tagIds }, PRESERVE_ERROR)
    return snakeToCamel(data) as { assetId: number; tagIds: number[] }
  },

  /* ---------- 血缘 ---------- */
  async createLineage(
    projectId: number,
    body: {
      externalId: string
      sourceAssetId: number
      targetAssetId: number
      sourceFieldName?: string
      targetFieldName?: string
      lineageType: string
      processRef?: string
    },
  ): Promise<{ id: number } & Record<string, unknown>> {
    const data = await postJson<unknown>(`${BASE}/projects/${projectId}/lineage`, camelToSnake(body), PRESERVE_ERROR)
    return snakeToCamel(data) as { id: number } & Record<string, unknown>
  },

  async getLineage(
    assetId: number,
    params: { direction?: 'upstream' | 'downstream' | 'both'; depth?: number } = {},
  ): Promise<LineageGraph> {
    const data = await getJson<unknown>(
      `${BASE}/assets/${assetId}/lineage`,
      {
        direction: params.direction ?? 'both',
        depth: params.depth ?? 3,
      },
      PRESERVE_ERROR,
    )
    return snakeToCamel(data) as LineageGraph
  },

  /* ---------- 标准 ---------- */
  async listStandards(projectId: number, page = 1, pageSize = 50): Promise<StandardPage> {
    const data = await getJson<unknown>(`${BASE}/projects/${projectId}/standards`, { page, pageSize }, PRESERVE_ERROR)
    return snakeToCamel(data) as StandardPage
  },

  async createStandard(
    projectId: number,
    body: { code: string; name: string; dataType: string; expression?: string; description?: string; status?: DefinitionStatus },
  ): Promise<StandardDefinition> {
    const data = await postJson<unknown>(`${BASE}/projects/${projectId}/standards`, camelToSnake(body), PRESERVE_ERROR)
    return snakeToCamel(data) as StandardDefinition
  },

  async checkStandard(projectId: number, body: { standardId?: number; code?: string; expression?: string; dataType?: string; sample?: unknown }): Promise<StandardCheckResult[]> {
    const data = await postJson<unknown>(`${BASE}/projects/${projectId}/standards/check`, camelToSnake(body), PRESERVE_ERROR)
    return snakeToCamel(data) as StandardCheckResult[]
  },

  /* ---------- 指标 ---------- */
  async listMetrics(projectId: number, page = 1, pageSize = 50): Promise<MetricPage> {
    const data = await getJson<unknown>(`${BASE}/projects/${projectId}/metrics`, { page, pageSize }, PRESERVE_ERROR)
    return snakeToCamel(data) as MetricPage
  },

  async createMetric(
    projectId: number,
    body: { code: string; name: string; formula: string; description?: string; status?: DefinitionStatus },
  ): Promise<MetricDefinition> {
    const data = await postJson<unknown>(`${BASE}/projects/${projectId}/metrics`, camelToSnake(body), PRESERVE_ERROR)
    return snakeToCamel(data) as MetricDefinition
  },

  /* ---------- 审计 ---------- */
  /** `GET /projects/{projectId}/audit`（VIEW_ALL；`{total,list}` 分页包络，倒序）。 */
  async listAudit(projectId: number, page = 1, pageSize = 50): Promise<AuditEventPage> {
    const data = await getJson<unknown>(`${BASE}/projects/${projectId}/audit`, { page, pageSize }, PRESERVE_ERROR)
    return snakeToCamel(data) as AuditEventPage
  },

  /* ---------- 质量规则 ---------- */
  /** `GET /projects/{projectId}/quality-rules`（VIEW_ALL；`{total,list}` 分页包络）。 */  async listRules(projectId: number, page = 1, pageSize = 50): Promise<QualityRulePage> {
    const data = await getJson<unknown>(
      `${BASE}/projects/${projectId}/quality-rules`,
      { page, pageSize },
      PRESERVE_ERROR,
    )
    return snakeToCamel(data) as QualityRulePage
  },

  /** `POST /projects/{projectId}/quality-rules`（EDIT_DEFINITION；201）。 */
  async createRule(projectId: number, draft: QualityRuleDraft): Promise<QualityRuleRecord> {
    const data = await postJson<unknown>(
      `${BASE}/projects/${projectId}/quality-rules`,
      camelToSnake(draft),
      PRESERVE_ERROR,
    )
    return snakeToCamel(data) as QualityRuleRecord
  },

  /** `GET /projects/{projectId}/quality-runs`（VIEW_ALL；`{total,list}` 分页包络）。 */
  async listRuns(projectId: number, page = 1, pageSize = 50): Promise<QualityRunPage> {
    const data = await getJson<unknown>(
      `${BASE}/projects/${projectId}/quality-runs`,
      { page, pageSize },
      PRESERVE_ERROR,
    )
    return snakeToCamel(data) as QualityRunPage
  },

  /** `POST /projects/{projectId}/quality-rules/{ruleId}/run`（EDIT_DEFINITION；201；无请求体）。 */
  async runRule(projectId: number, ruleId: number): Promise<QualityRunRecord> {
    const data = await postJson<unknown>(
      `${BASE}/projects/${projectId}/quality-rules/${ruleId}/run`,
      undefined,
      PRESERVE_ERROR,
    )
    return snakeToCamel(data) as QualityRunRecord
  },
}
