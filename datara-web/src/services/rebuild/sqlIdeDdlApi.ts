/**
 * R5-B（SQL IDE DDL 写路径）契约层 — GREEN。
 * 语义源自 docs/increments/R5-IDE-开始前影响分析.md §4 与 plan I6（rebuild/sql_ide/ddl.py、ddl_policy.py 草案）。
 * 红线：确认/执行/回滚全部需要用户人工闸（分工规则 5）——契约层不提供绕过通道。
 * FE-07b 拆分登记：DDL 八步闸（编辑→管控结果→影响预览→确认闸 confirmPhrase→执行→回滚记录）。
 * 前置：R5-B D 阶段解禁（本契约转 GREEN）；InstanceBar/GlobalParamDrawer 保留去向裁定待 D 阶段交付后。
 */

/* ---------- DDL 对象与校验 ---------- */

export type DdlObjectKind = 'table' | 'view' | 'function' | 'procedure' | 'trigger'

export interface DdlDefinition {
  objectKind: DdlObjectKind
  schema: string | null
  name: string
  /** SHOW CREATE 等价产物 */
  ddlText: string
  updatedAt?: string | null
}

export type PolicyLevel = 'block' | 'warn' | 'info'

export interface DdlPolicyFinding {
  /** legacy AuditCheck 语义：block 拒绝进入确认闸 / warn 需显式知晓 / info 仅提示 */
  level: PolicyLevel
  code: string
  message: string
  /** 依赖/影响对象清单（design §7.1 依赖分析） */
  impacts: string[]
}

export interface DdlPolicyReport {
  findings: DdlPolicyFinding[]
  /** 校验快照（回滚依据） */
  snapshotId: string | null
  blocked: boolean
}

export interface DdlConfirmRequest {
  datasourceId: number
  definition: DdlDefinition
  /** 编辑后的新 DDL 文本 */
  nextDdlText: string
  policyReport: DdlPolicyReport
  /** 人工确认短语（用户下发，agent 不得代写） */
  confirmPhrase: string
}

export interface DdlExecutionRecord {
  recordId: number
  status: 'success' | 'failure' | 'rolled-back'
  ddlText: string
  elapsedMs: number
  createdAt: string
  /** 失败时的补偿脚本（仅展示，执行同样走人工闸） */
  compensationDdl?: string | null
  rollbackDdl?: string | null
}

/** @deprecated 保留导出以兼容旧验证页与插件；新代码不再使用哨兵。 */
export const R5B_BACKEND_NOT_WIRED = 'R5B_BACKEND_NOT_WIRED: A5 (rebuild/sql_ide/ddl) contract not connected yet'

/* ---------- 影响预览（权威设计 §7.2 R5-B 能力面；纠偏执行附录 §2 追踪表「影响预览」） ---------- */

export interface DdlImpactItem {
  kind: 'dependent-view' | 'dependent-routine' | 'lineage-downstream' | 'permission-scope'
  name: string
  detail: string
}

export const R5B_CONTRACT_METHODS = [
  'getDefinition',
  'validatePolicy',
  'previewImpact',
  'submitConfirm',
  'listExecutionRecords',
] as const

export type R5BContractMethod = (typeof R5B_CONTRACT_METHODS)[number]

export interface SqlIdeDdlContract {
  getDefinition: (datasourceId: number, objectKind: DdlObjectKind, schema: string | null, name: string) => Promise<DdlDefinition>
  validatePolicy: (datasourceId: number, nextDdlText: string) => Promise<DdlPolicyReport>
  /** 影响预览（只读）：DDL 生效将波及的依赖视图/例程/血缘下游/权限范围；提交确认前必须展示 */
  previewImpact: (datasourceId: number, nextDdlText: string) => Promise<DdlImpactItem[]>
  /** 确认闸提交：block 级 finding 存在时服务端必须拒绝；confirmPhrase 由用户输入 */
  submitConfirm: (request: DdlConfirmRequest) => Promise<DdlExecutionRecord>
  listExecutionRecords: (datasourceId: number) => Promise<DdlExecutionRecord[]>
}

/* ---------- GREEN HTTP 实现 ---------- */

import { http } from '../http'

export interface SqlIdeDdlContext {
  /** 目标对象信息用于绑定策略快照；默认值仅供验证页使用。 */
  database?: string
  schema?: string | null
  name?: string
  sourceVersion?: string
  objectKind?: DdlObjectKind
}

const objectRef = (datasourceId: number, kind: DdlObjectKind, schema: string | null, name: string, context: SqlIdeDdlContext) => ({
  datasourceId,
  database: context.database ?? '',
  schema: context.schema ?? schema,
  kind: context.objectKind ?? kind,
  name: context.name ?? name,
})

export function createSqlIdeDdlContract(projectId = 1, context: SqlIdeDdlContext = {}): SqlIdeDdlContract {
  const ref = (datasourceId: number, kind: DdlObjectKind, schema: string | null, name: string) => objectRef(datasourceId, kind, schema, name, context)
  const sourceVersion = () => context.sourceVersion ?? 'ui-draft'
  return {
    getDefinition: async (datasourceId, objectKind, schema, name) => {
      const result = await http.post<{ objectRef?: Record<string, unknown>; sourceKind?: string; definitionText?: string; definition?: string; sourceVersion?: string; capability?: string; constraints?: string[] }>(
        `/projects/${projectId}/sql-ide/definitions`,
        { datasourceId, database: context.database ?? '', objectKind, objectRef: ref(datasourceId, objectKind, schema, name) },
      )
      return {
        objectKind,
        schema,
        name,
        ddlText: result.definitionText ?? result.definition ?? '',
        updatedAt: result.sourceVersion ?? null,
      }
    },
    validatePolicy: async (datasourceId, nextDdlText) => {
      const result = await http.post<{ snapshotId: string; findings?: DdlPolicyFinding[]; blocked: boolean }>('/rebuild/sql-ide-ddl/validate-policy', {
        datasourceId, projectId, objectRef: ref(datasourceId, context.objectKind ?? 'table', context.schema ?? null, context.name ?? ''), sourceVersion: sourceVersion(), nextDdlText,
      })
      return { snapshotId: result.snapshotId ?? null, findings: result.findings ?? [], blocked: Boolean(result.blocked) }
    },
    previewImpact: async (datasourceId, nextDdlText) => {
      const result = await http.post<{ snapshotId?: string; impacts?: Array<{ objectRef?: { kind?: string; name?: string }; relationType?: string; detail?: string }> }>('/rebuild/sql-ide-ddl/preview-impact', {
        datasourceId, projectId, objectRef: ref(datasourceId, context.objectKind ?? 'table', context.schema ?? null, context.name ?? ''), sourceVersion: sourceVersion(), nextDdlText,
      })
      return (result.impacts ?? []).map((item) => ({
        kind: (item.relationType === 'dependent-routine' || item.relationType === 'lineage-downstream' || item.relationType === 'permission-scope' ? item.relationType : 'dependent-view') as DdlImpactItem['kind'],
        name: item.objectRef?.name ?? '', detail: item.detail ?? '',
      }))
    },
    submitConfirm: async (request) => {
      const result = await http.post<{ recordId: string | number; status: DdlExecutionRecord['status'] }>('/rebuild/sql-ide-ddl/confirm', {
        datasourceId: request.datasourceId, objectRef: ref(request.datasourceId, request.definition.objectKind, request.definition.schema, request.definition.name), sourceVersion: request.definition.updatedAt ?? sourceVersion(), nextDdlText: request.nextDdlText,
        policySnapshotId: request.policyReport.snapshotId ?? '', impactSnapshotId: '', confirmPhrase: request.confirmPhrase,
      })
      const numericRecordId = Number(result.recordId)
      return { recordId: Number.isFinite(numericRecordId) ? numericRecordId : 0, status: result.status, ddlText: request.nextDdlText, elapsedMs: 0, createdAt: new Date().toISOString() }
    },
    listExecutionRecords: async (datasourceId) => {
      const result = await http.post<{ items?: Array<Record<string, unknown>> }>('/rebuild/sql-ide-ddl/execution-records', { datasourceId, page: 1, pageSize: 50 })
      return (result.items ?? []).map((item) => ({ recordId: Number(item.recordId ?? item.id ?? 0), status: (item.status ?? 'failure') as DdlExecutionRecord['status'], ddlText: String(item.ddlText ?? ''), elapsedMs: Number(item.elapsedMs ?? 0), createdAt: String(item.createdAt ?? ''), compensationDdl: item.compensationDdl as string | null | undefined, rollbackDdl: item.rollbackDdl as string | null | undefined }))
    },
  }
}
