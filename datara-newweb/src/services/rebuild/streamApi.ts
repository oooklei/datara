/**
 * I8（流处理观摩/运行时）契约层 — GREEN 已接线（FE-01 修订 2026-10-19）。
 * 端点前缀 /api/v1/rebuild/stream/*；
 * 本文件语义源自 docs/increments/I7-I9-前端消费面分析.md §1/§3
 * （job/attempt/checkpoint/metric 查询 + 观摩查询 + 故障恢复与漂移注入事件、长驻进程与位点恢复）
 * 与权威设计 §8.4 观摩查询接口结构基线（f475c76）：
 * 生产速率、消费速率、积压、偏移、窗口结果、成功/失败/跳过计数、错误样本。
 * GREEN 接线：I8_CONTRACT_METHODS 6 方法经真实 fetch + 统一包络 {code,msg,data}；
 * I8_STREAM_NOT_WIRED 仅保留为 404 分支错误提示（端点未挂载时），不再作为 RED 活哨兵。
 * 调用方换绑目标：正式 /stream 页应由 services/streamApi.ts（F40/F41 旧契约）换绑至本文件（FE-10 裁定）。
 */
import { type MetricValue, type TimeWindowQuery } from './metricsApi'
import { ContractApiError, snakeToCamel, wireIdToString } from './adapterKit'
import { getToken } from '../http'

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
  processRate: MetricValue
  inputCount: MetricValue
  outputCount: MetricValue
  duplicateCount: MetricValue
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

/* ---------- GREEN 接线；保留未挂载时的兼容哨兵 ---------- */

const BASE = '/api/v1/rebuild/stream'

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.token = token
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  if (!response.ok) {
    const raw = await response.text().catch(() => '')
    if (response.status === 404) throw new Error(`${I8_STREAM_NOT_WIRED}: ${path}`)
    throw new ContractApiError({ httpStatus: response.status, code: response.status, msg: `HTTP ${response.status} ${path}`, raw })
  }
  const envelope = await response.json() as { code?: number; msg?: string; data?: unknown }
  if (typeof envelope.code === 'number' && envelope.code !== 0 && envelope.code !== 200) {
    throw new ContractApiError({ httpStatus: response.status, code: envelope.code, msg: envelope.msg ?? path, raw: envelope })
  }
  return snakeToCamel(envelope.data ?? envelope) as T
}

const metric = (value: unknown): MetricValue => ({
  value: typeof value === 'number' ? value : Number(value ?? 0), known: value !== null && value !== undefined, estimated: false,
})

const query = (window: TimeWindowQuery) => `?from=${encodeURIComponent(window.from)}&to=${encodeURIComponent(window.to)}&limit=${window.limit}`

async function jobsFor(jobId?: string): Promise<Array<{ id: number; name: string; workflowId: number; mqTopic: string; runtimeConfig: Record<string, unknown>; state: string; attemptNo: number; startedAt: string | null; finishedAt: string | null }>> {
  const jobs = await request<Array<{ id: number; name: string; workflowId: number; mqTopic: string; runtimeConfig: Record<string, unknown>; state: string; attemptNo: number; startedAt: string | null; finishedAt: string | null }>>('/jobs')
  return jobId ? jobs.filter((job) => String(job.id) === jobId) : jobs
}

/**
 * I8 契约工厂：端点统一使用 /api/v1/rebuild/stream，UI 继续依赖原契约接口。
 */
export function createStreamContract(): StreamContract {
  return {
    listStreamJobs: async () => (await jobsFor()).map((job) => ({
      jobId: wireIdToString(job.id, 'jobId'), kind: String(job.runtimeConfig.mode ?? 'stream'), state: job.state, startedAt: job.startedAt,
    })),
    listStreamAttempts: async (_window, jobId) => (await Promise.all((await jobsFor(jobId)).map((job) =>
      request<Array<{ jobId: number; attemptId: number; startedAt: string | null; endedAt: string | null; exitReason: string | null }>>(`/jobs/${job.id}/attempts`),
    ))).flat().map((row) => ({ ...row, jobId: wireIdToString(row.jobId, 'jobId'), startedAt: row.startedAt ?? '', endedAt: row.endedAt })),
    listStreamCheckpoints: async (_window, jobId) => (await Promise.all((await jobsFor(jobId)).map((job) =>
      request<Array<{ jobId: number; partitionId: string; offsetValue: number; eventTime: string }>>(`/jobs/${job.id}/checkpoints`),
    ))).flat().map((row) => ({
      jobId: wireIdToString(row.jobId, 'jobId'), partition: row.partitionId,
      committedOffset: metric(row.offsetValue), currentOffset: metric(row.offsetValue), checkpointedAt: row.eventTime,
    })),
    listStreamMetrics: async (window, jobId) => (await Promise.all((await jobsFor(jobId)).map((job) =>
      request<Array<{ jobId: number; metric: string; value: number; capturedAt: string }>>(`/jobs/${job.id}/metrics${query(window)}`),
    ))).flat().map((row) => ({ ...row, jobId: wireIdToString(row.jobId, 'jobId'), value: metric(row.value) })),
    queryStreamObservation: async (window, jobId) => {
      const jobs = await jobsFor(jobId)
      const job = jobs[0]
      if (!job) throw new Error('stream job not found')
      const raw = await request<Record<string, unknown>>(`/jobs/${job.id}/observe`, 'POST', { from: window.from, to: window.to })
      const windowResult = (raw.windowResult && typeof raw.windowResult === 'object' ? raw.windowResult : {}) as Record<string, unknown>
      const samples = Array.isArray(raw.errorSamples) ? raw.errorSamples as Array<Record<string, unknown>> : []
      return {
        produceRate: metric(raw.produceRate), consumeRate: metric(raw.consumeRate), processRate: metric(raw.processRate),
        inputCount: metric(raw.inputCount), outputCount: metric(raw.outputCount), duplicateCount: metric(raw.duplicateCount),
        lag: metric(raw.backlog),
        offset: { current: metric(raw.offsetValue), committed: metric(raw.offsetValue) },
        windowResults: Object.entries(windowResult).map(([windowKey, value]) => ({
          windowKey, windowStart: '', windowEnd: '', status: 'success', recordsIn: metric(0), recordsOut: metric(value),
        })),
        counters: { success: metric(raw.successCount), failure: metric(raw.failureCount), skipped: metric(raw.skippedCount) },
        errorSamples: samples.map((sample) => ({
          jobId: wireIdToString(sample.jobId ?? job.id, 'jobId'), sample: JSON.stringify(sample.sampleData ?? sample),
          flow: String(sample.errorType ?? 'failed'), capturedAt: String(sample.eventTime ?? ''),
        })),
      }
    },
    listStreamRecoveryEvents: async (window, jobId) => (await Promise.all((await jobsFor(jobId)).map((job) =>
      request<Array<{ eventId: string; jobId: number; kind: string; detail: string; occurredAt: string }>>(`/jobs/${job.id}/recovery-events${query(window)}`),
    ))).flat().map((row) => ({ ...row, eventId: wireIdToString(row.eventId, 'eventId'), jobId: wireIdToString(row.jobId, 'jobId') })),
  }
}
