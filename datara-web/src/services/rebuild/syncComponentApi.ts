/**
 * R4-SYNC（同步组件表单）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/sync/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/R4-SYNC-API-contract-pending.md（Codex 草案 §2-§4）
 * 与 docs/increments/2026-10-16-纠偏重构方案设计.md §2.2 客户要求 #2：
 * 选源/目标连接 → 探查表字段 → 生成初始映射 → 用户调整 → 随工作流版本保存 → 预览/运行。
 * RED 约定：所有 I/O 方法在后端接入前抛 R4_SYNC_NOT_WIRED，不发出任何真实请求；
 * 列匹配建议、映射行编辑等纯前端逻辑可真实运行（见 SyncFormValidationView）。
 */

/* ---------- 对象身份（三元组，草案 §3.1） ---------- */

export interface SyncObjectIdentity {
  datasourceId: number
  schema: string
  table: string
}

/* ---------- 列元数据（草案 §3.1：ordinal/name/type/nullable/precision/scale/comment） ---------- */

export interface SyncColumn {
  ordinal: number
  name: string
  type: string
  nullable: boolean
  precision?: number | null
  scale?: number | null
  comment?: string | null
}

/* ---------- 探查（POST /probes，草案 §3.1） ---------- */

export type SyncProbeMode = 'source_table' | 'target_table' | 'file'

export interface SyncProbeRequest {
  projectId: number
  mode: SyncProbeMode
  source: SyncObjectIdentity
  /** target-led 探查另带显式候选 schema 列表（草案 §3.1） */
  candidateSchemas?: string[]
}

export interface SyncProbeResult {
  mode: SyncProbeMode
  /** 候选对象全名（target 同名跨 schema 返回全部候选，不自动选中） */
  candidates: SyncObjectIdentity[]
  columns: SyncColumn[]
}

/* ---------- 计划与映射（草案 §3.2） ---------- */

export type SyncStrategy = 'full' | 'incremental'
export type SyncWriteMode = 'append' | 'upsert' | 'replace_table'
export type SyncTargetPolicy = 'existing_only' | 'create_from_source_schema'

export type SyncMappingOperation = 'map' | 'constant' | 'ignore'

export interface SyncMappingItem {
  /** 目标序号显式定位（草案 §3.2） */
  targetOrdinal: number
  operation: SyncMappingOperation
  sourceColumn?: string
  targetColumn?: string
  constantValue?: string
  /** 允许的转换集合由能力声明提供（草案 §3.2） */
  conversion?: string
}

export interface SyncIncrementalBoundary {
  watermarkColumn: string
  comparison: string
  lowerBound?: string | null
  upperBound?: string | null
  lowerInclusive: boolean
  upperInclusive: boolean
  /** 首次运行策略固化进 plan digest，不读运行时动态值（草案 §3.2） */
  initialPolicy: string
}

export interface SyncPlanDraft {
  projectId: number
  mode: SyncProbeMode
  source: SyncObjectIdentity
  target: SyncObjectIdentity
  strategy: SyncStrategy
  writeMode: SyncWriteMode
  targetPolicy: SyncTargetPolicy
  mapping: SyncMappingItem[]
  incremental?: SyncIncrementalBoundary
}

export interface SyncPlanVersion {
  planId: number
  version: number
  planDigest: string
  /** 服务端重验后的字段级诊断（草案 §2 稳定错误码） */
  diagnostics: Array<{ field: string; code: string; message: string }>
}

/* ---------- 预览（POST /plans/{plan_id}/preview，草案 §2） ---------- */

/** R4 初版 preview 仅返回列元数据与统计，禁止回传源数据样本值（草案 §2） */
export interface SyncPreviewResult {
  planId: number
  planVersion: number
  planDigest: string
  sourceColumns: SyncColumn[]
  targetColumns: SyncColumn[]
  mappingSummary: SyncMappingItem[]
  rowCountEstimate: number
}

/* ---------- 运行与 attempt（草案 §2/§4） ---------- */

export type SyncRunStatus = 'queued' | 'running' | 'cancel_requested' | 'succeeded' | 'failed' | 'cancelled'

export interface SyncRunCounts {
  sourceRead: number
  targetWritten: number
  inserted: number
  updated: number
  skipped: number
  failed: number
}

export interface SyncRunRequest {
  projectId: number
  planId: number
  planVersion: number
  planDigest: string
  idempotencyKey: string
  /** workflow dispatch 必须另带四身份且属同一 project（草案 §2/§4）；手动运行可空 */
  workflowId?: number
  workflowVersion?: number
  taskInstanceId?: number
  taskId?: string
}

export interface SyncRunSummary {
  runId: number
  status: SyncRunStatus
  attemptId: number
  counts: SyncRunCounts
  startedAt?: string | null
  finishedAt?: string | null
}

export interface SyncAttemptDetail {
  runId: number
  attemptId: number
  status: SyncRunStatus
  counts: SyncRunCounts
  checkpointRef?: string | null
  errorCode?: string | null
  createdAt: string
  finishedAt?: string | null
}

/* ---------- checkpoint / 恢复（草案 §2） ---------- */

export interface SyncCheckpoint {
  runId: number
  attemptId: number
  /** opaque checkpoint（不泄漏凭据或源行 payload） */
  checkpoint: string
  planDigest: string
  sourceIdentity: SyncObjectIdentity
  watermarkRule: SyncIncrementalBoundary
}

export interface SyncResumeRequest {
  idempotencyKey: string
  checkpointRef: string
}

/* ---------- RED 哨兵 ---------- */

export const R4_SYNC_NOT_WIRED = 'R4_SYNC_NOT_WIRED: rebuild/sync contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R4_SYNC_CONTRACT_METHODS = [
  'getCapabilities',
  'probe',
  'savePlan',
  'getPlan',
  'previewPlan',
  'runPlan',
  'getRun',
  'getAttempt',
  'cancelRun',
  'getCheckpoint',
  'resumeRun',
] as const

export type R4SyncContractMethod = (typeof R4_SYNC_CONTRACT_METHODS)[number]

export interface SyncComponentContract {
  getCapabilities: (projectId: number) => Promise<Record<string, unknown>>
  probe: (request: SyncProbeRequest) => Promise<SyncProbeResult>
  savePlan: (draft: SyncPlanDraft) => Promise<SyncPlanVersion>
  getPlan: (planId: number, projectId: number) => Promise<SyncPlanDraft & SyncPlanVersion>
  previewPlan: (planId: number, planVersion: number, planDigest: string, projectId: number) => Promise<SyncPreviewResult>
  runPlan: (request: SyncRunRequest) => Promise<SyncRunSummary>
  getRun: (runId: number, projectId: number) => Promise<SyncRunSummary>
  getAttempt: (runId: number, attemptId: number, projectId: number) => Promise<SyncAttemptDetail>
  cancelRun: (runId: number, projectId: number) => Promise<{ accepted: boolean; status: SyncRunStatus }>
  getCheckpoint: (runId: number, projectId: number) => Promise<SyncCheckpoint>
  resumeRun: (runId: number, projectId: number, request: SyncResumeRequest) => Promise<SyncRunSummary>
}

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 R4_SYNC_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(R4_SYNC_NOT_WIRED)
}

/**
 * R4-SYNC 契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（SyncFormValidationView）不感知切换。
 */
export function createSyncComponentContract(): SyncComponentContract {
  return {
    getCapabilities: notWired,
    probe: notWired,
    savePlan: notWired,
    getPlan: notWired,
    previewPlan: notWired,
    runPlan: notWired,
    getRun: notWired,
    getAttempt: notWired,
    cancelRun: notWired,
    getCheckpoint: notWired,
    resumeRun: notWired,
  }
}

/* ---------- 纯前端逻辑：初始映射建议（客户 #2「生成初始映射 → 用户调整」） ---------- */

/**
 * 按列名（大小写不敏感）+ 序号生成初始映射建议：
 * 仅 operation=map 的建议行，用户可在 UI 调整/改为 constant/ignore。
 * 这是本地纯函数，不依赖后端；服务端保存时会重验列存在性与唯一性（草案 §3.2）。
 */
export function suggestInitialMapping(source: SyncColumn[], target: SyncColumn[]): SyncMappingItem[] {
  const byLowerName = new Map(source.map((col) => [col.name.toLowerCase(), col]))
  return target.map((targetColumn) => {
    const matched = byLowerName.get(targetColumn.name.toLowerCase())
    return {
      targetOrdinal: targetColumn.ordinal,
      operation: 'map',
      sourceColumn: matched?.name,
      targetColumn: targetColumn.name,
    }
  })
}
