/**
 * R7（统计/质量/血缘报告）契约层 — GREEN 接线（接线计划 Task 5，R7 批次）。
 * 端点与映射依据：docs/increments/2026-10-17-R系列GREEN接线计划.md §1.1 原语 + Task 5 契约面表；
 * 包络 {code,msg,data} 沿 R2 批次固化（datara-backend rebuild 域全域实证）。
 * 本文件语义源自 docs/increments/I7-I9-前端消费面分析.md §1/§3
 * （4 张统计表 + 质量规则结果链 + 运行回写血缘 + A7 Step 1 unknown/estimated 口径）。
 * A7 Step 1 口径：MetricValue 透传不加工（known=false=unknown、estimated 透传，FE 禁止推导）；
 * TimeWindowQuery.from/to 格式与 offset/limit 分页口径为 B2 缺口 #4 开放点——契约层原样透传不加工。
 * R7_METRICS_NOT_WIRED 常量保留（View 横幅引用兼容）。
 */

import { camelToSnake, ContractApiError, snakeToCamel, wireIdToString } from './adapterKit'
import { getToken } from '../http'

/* ---------- A7 Step 1 口径：unknown/estimated 标记透传 ---------- */

/** 统计值包装：known=false 表示后端口径 unknown，estimated=true 表示估算值（非精确统计） */
export interface MetricValue {
  value: number
  known: boolean
  estimated: boolean
}

/* ---------- 时间窗查询（分页 + 时间窗） ---------- */

export interface TimeWindowQuery {
  from: string
  to: string
  offset: number
  limit: number
}

/* ---------- 4 张统计表（plan I9） ---------- */

/** 表 1：workflow_result_stat（工作流结果统计：成功/失败/跳过/重试） */
export interface WorkflowResultStatRow {
  workflowId: number
  runDate: string
  successCount: number
  failureCount: number
  skippedCount: number
  retryCount: number
}

/** 表 2：task_instance_data_stat（实例数据量统计） */
export interface TaskInstanceDataStatRow {
  instanceId: number
  taskId: string
  rowsIn: MetricValue
  rowsOut: MetricValue
  errorRows: MetricValue
  elapsedMs: MetricValue
}

/** 表 3：task_data_stat_segment（数据量分段统计） */
export interface TaskDataStatSegmentRow {
  instanceId: number
  taskId: string
  segmentKey: string
  rowCount: MetricValue
}

/** 表 4：task_data_error_sample（错误样本） */
export interface TaskDataErrorSampleRow {
  instanceId: number
  taskId: string
  errorType: string
  sampleData: string
  capturedAt: string
}

/* ---------- 质量规则结果 → 统计/告警链 ---------- */

export interface QualityRuleResultLink {
  ruleId: number
  ruleName: string
  /** 关联的统计记录引用（表+主键） */
  statRef: string
  /** 结果是否已进入告警链 */
  alertSent: boolean
  resultAt: string
}

/* ---------- 运行回写血缘（SQL/同步/工作流运行维度） ---------- */

export interface LineageWritebackEntry {
  runId: string
  runKind: 'sql' | 'sync' | 'workflow'
  sourceEntity: string
  targetEntity: string
  writebackAt: string
}

/* ---------- RED 哨兵 ---------- */

export const R7_METRICS_NOT_WIRED = 'R7_METRICS_NOT_WIRED: rebuild/metrics contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R7_CONTRACT_METHODS = [
  'queryWorkflowResultStats',
  'queryTaskInstanceDataStats',
  'queryTaskDataStatSegments',
  'queryTaskDataErrorSamples',
  'listQualityRuleLinks',
  'listLineageWritebacks',
] as const

export type R7ContractMethod = (typeof R7_CONTRACT_METHODS)[number]

export interface MetricsContract {
  queryWorkflowResultStats: (window: TimeWindowQuery) => Promise<WorkflowResultStatRow[]>
  queryTaskInstanceDataStats: (window: TimeWindowQuery) => Promise<TaskInstanceDataStatRow[]>
  queryTaskDataStatSegments: (window: TimeWindowQuery) => Promise<TaskDataStatSegmentRow[]>
  queryTaskDataErrorSamples: (window: TimeWindowQuery) => Promise<TaskDataErrorSampleRow[]>
  listQualityRuleLinks: (window: TimeWindowQuery) => Promise<QualityRuleResultLink[]>
  listLineageWritebacks: (window: TimeWindowQuery, kind: LineageWritebackEntry['runKind'] | 'all') => Promise<LineageWritebackEntry[]>
}

/* ---------- GREEN 统一原语（沿 R2 固化版；BASE 换 metrics 域） ---------- */

/** 端点前缀（Task 5 契约面表） */
const BASE = '/api/v1/rebuild/metrics'

const TIMEOUT_MS = 15000

/** 后端成功包络（rebuild 域全域实证形态） */
interface ApiEnvelope {
  code?: number
  msg?: string
  data?: unknown
}

/** 统一 JSON fetch 原语：15s AbortController 超时 + token header（'token'，与 http.ts 同源）+ 包络解包 + 归一错误 */
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers.token = token
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...headers, ...(init?.headers as Record<string, string>) },
      signal: ctrl.signal,
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => '')
      throw new ContractApiError({ httpStatus: res.status, code: res.status, msg: `HTTP ${res.status} ${path}`, raw })
    }
    const envelope = (await res.json()) as ApiEnvelope
    if (typeof envelope.code === 'number' && envelope.code !== 0 && envelope.code !== 200) {
      throw new ContractApiError({ httpStatus: res.status, code: envelope.code, msg: envelope.msg ?? path, raw: envelope })
    }
    return (envelope.data ?? envelope) as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ContractApiError({ httpStatus: 0, code: 'TIMEOUT', msg: `请求超时（${TIMEOUT_MS / 1000}s）${path}` })
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** POST：请求体深度 camel→snake，响应深度 snake→camel（R7 六方法全 POST，无 GET 原语需求） */
async function sendJson<T>(path: string, body: unknown): Promise<T> {
  return snakeToCamel(await requestJson<unknown>(path, { method: 'POST', body: JSON.stringify(camelToSnake(body)) })) as T
}

/**
 * R7 契约工厂 — GREEN：6 方法接线至 P1 冻结契约的后端实现（Task 5 契约面表），
 * 签名与返回类型不动，UI 层（MetricsValidationView）不感知切换。
 * A7 Step 1：MetricValue 透传不加工；listLineageWritebacks 的 runId 经 wireIdToString 归一（FE string 契约）。
 */
export function createMetricsContract(): MetricsContract {
  return {
    queryWorkflowResultStats: (window) =>
      sendJson<WorkflowResultStatRow[]>('/workflow-result-stats', window),
    queryTaskInstanceDataStats: (window) =>
      sendJson<TaskInstanceDataStatRow[]>('/task-instance-data-stats', window),
    queryTaskDataStatSegments: (window) =>
      sendJson<TaskDataStatSegmentRow[]>('/task-data-stat-segments', window),
    queryTaskDataErrorSamples: (window) =>
      sendJson<TaskDataErrorSampleRow[]>('/task-data-error-samples', window),
    listQualityRuleLinks: (window) =>
      sendJson<QualityRuleResultLink[]>('/quality-rule-links', window),
    listLineageWritebacks: (window, kind) =>
      sendJson<LineageWritebackEntry[]>('/lineage-writebacks', { ...window, kind }).then((rows) =>
        rows.map((row) => ({ ...row, runId: wireIdToString(row.runId, 'runId') })),
      ),
  }
}
