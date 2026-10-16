/**
 * I8（流处理观摩/运行时）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/stream/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/I7-I9-前端消费面分析.md §1/§3
 * （job/attempt/checkpoint/metric 查询 + 观摩查询 + 故障恢复与漂移注入事件、长驻进程与位点恢复）
 * 与权威设计 §8.4 观摩查询接口结构基线（f475c76）：
 * 生产速率、消费速率、积压、偏移、窗口结果、成功/失败/跳过计数、错误样本。
 * RED 约定：所有 I/O 方法在后端接入前抛 I8_STREAM_NOT_WIRED，不发出任何真实请求。
 */
import { type MetricValue, type TimeWindowQuery } from './metricsApi'

/** Stream 契约签名复用 metricsApi 的 TimeWindowQuery；re-export 供 View 单源导入 */
export type { TimeWindowQuery }

/* ---------- 流作业（长驻进程面） ---------- */

export interface StreamJobRow {
  jobId: string
  /** source / fuse / output 等流角色 */
  kind: string
  /** running / paused / stopped / failed 等 */
  state: string
  startedAt: string | null
}

/** 作业尝试（含重启历史） */
export interface StreamAttemptRow {
  jobId: string
  attemptId: number
  startedAt: string
  endedAt: string | null
  exitReason: string | null
}

/** 位点/检查点（恢复面：分区位点与提交位点） */
export interface StreamCheckpointRow {
  jobId: string
  partition: string
  committedOffset: MetricValue
  currentOffset: MetricValue
  checkpointedAt: string
}

/** 流指标时间序列点 */
export interface StreamMetricPoint {
  jobId: string
  metric: string
  value: MetricValue
  capturedAt: string
}

/* ---------- §8.4 观摩结构 ---------- */

/** 窗口结果 */
export interface StreamWindowResult {
  windowKey: string
  windowStart: string
  windowEnd: string
  /** success / failure / skipped（允许后端扩展枚举） */
  status: string
  recordsIn: MetricValue
  recordsOut: MetricValue
}

/** 错误样本（流向：consumed/emitted/failed/dead-letter，允许后端扩展枚举） */
export interface StreamErrorSampleRow {
  jobId: string
  sample: string
  flow: string
  capturedAt: string
}

/**
 * 观摩查询接口返回结构（权威设计 §8.4 基线，f475c76）。
 * R8/R2-06 生产观摩方案冻结时可按现行增量体系调整，但不得低于本结构的信息完备度。
 */
export interface StreamObservation {
  produceRate: MetricValue
  consumeRate: MetricValue
  lag: MetricValue
  offset: { current: MetricValue; committed: MetricValue }
  windowResults: StreamWindowResult[]
  counters: { success: MetricValue; failure: MetricValue; skipped: MetricValue }
  errorSamples: StreamErrorSampleRow[]
}

/* ---------- 故障恢复 / 漂移注入事件 ---------- */

export interface StreamRecoveryEventRow {
  eventId: string
  jobId: string
  /** recovery / offset-drift / restart 等 */
  kind: string
  detail: string
  occurredAt: string
}

/* ---------- RED 哨兵 ---------- */

export const I8_STREAM_NOT_WIRED = 'I8_STREAM_NOT_WIRED: rebuild/stream contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const I8_CONTRACT_METHODS = [
  'listStreamJobs',
  'listStreamAttempts',
  'listStreamCheckpoints',
  'listStreamMetrics',
  'queryStreamObservation',
  'listStreamRecoveryEvents',
] as const

export type I8ContractMethod = (typeof I8_CONTRACT_METHODS)[number]

export interface StreamContract {
  listStreamJobs: (window: TimeWindowQuery) => Promise<StreamJobRow[]>
  listStreamAttempts: (window: TimeWindowQuery, jobId?: string) => Promise<StreamAttemptRow[]>
  listStreamCheckpoints: (window: TimeWindowQuery, jobId?: string) => Promise<StreamCheckpointRow[]>
  listStreamMetrics: (window: TimeWindowQuery, jobId?: string) => Promise<StreamMetricPoint[]>
  queryStreamObservation: (window: TimeWindowQuery, jobId?: string) => Promise<StreamObservation>
  listStreamRecoveryEvents: (window: TimeWindowQuery, jobId?: string) => Promise<StreamRecoveryEventRow[]>
}

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 I8_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(I8_STREAM_NOT_WIRED)
}

/**
 * I8 契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（StreamValidationView）不感知切换。
 */
export function createStreamContract(): StreamContract {
  return {
    listStreamJobs: notWired,
    listStreamAttempts: notWired,
    listStreamCheckpoints: notWired,
    listStreamMetrics: notWired,
    queryStreamObservation: notWired,
    listStreamRecoveryEvents: notWired,
  }
}
