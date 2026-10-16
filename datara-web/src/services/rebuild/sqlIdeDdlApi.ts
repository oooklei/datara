/**
 * R5-B（SQL IDE DDL 写路径）契约层 — RED 阶段。
 * 语义源自 docs/increments/R5-IDE-开始前影响分析.md §4 与 plan I6（rebuild/sql_ide/ddl.py、ddl_policy.py 草案）。
 * RED 约定与 R5-A 相同：A5 接入前统一抛 R5B_BACKEND_NOT_WIRED，不发任何真实请求。
 * 红线：确认/执行/回滚全部需要用户人工闸（分工规则 5）——契约层不提供绕过通道。
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

/* ---------- RED 实现 ---------- */

const notWired = async (): Promise<never> => {
  throw new Error(R5B_BACKEND_NOT_WIRED)
}

export function createSqlIdeDdlContract(): SqlIdeDdlContract {
  return {
    getDefinition: notWired,
    validatePolicy: notWired,
    previewImpact: notWired,
    submitConfirm: notWired,
    listExecutionRecords: notWired,
  }
}
