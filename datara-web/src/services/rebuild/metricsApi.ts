/**
 * I9（统计/质量/血缘报告）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/metrics/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/I7-I9-前端消费面分析.md §1/§3
 * （4 张统计表 + 质量规则结果链 + 运行回写血缘 + A7 Step 1 unknown/estimated 口径）。
 * RED 约定：所有 I/O 方法在后端接入前抛 I9_METRICS_NOT_WIRED，不发出任何真实请求。
 */

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

export const I9_METRICS_NOT_WIRED = 'I9_METRICS_NOT_WIRED: rebuild/metrics contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const I9_CONTRACT_METHODS = [
  'queryWorkflowResultStats',
  'queryTaskInstanceDataStats',
  'queryTaskDataStatSegments',
  'queryTaskDataErrorSamples',
  'listQualityRuleLinks',
  'listLineageWritebacks',
] as const

export type I9ContractMethod = (typeof I9_CONTRACT_METHODS)[number]

export interface MetricsContract {
  queryWorkflowResultStats: (window: TimeWindowQuery) => Promise<WorkflowResultStatRow[]>
  queryTaskInstanceDataStats: (window: TimeWindowQuery) => Promise<TaskInstanceDataStatRow[]>
  queryTaskDataStatSegments: (window: TimeWindowQuery) => Promise<TaskDataStatSegmentRow[]>
  queryTaskDataErrorSamples: (window: TimeWindowQuery) => Promise<TaskDataErrorSampleRow[]>
  listQualityRuleLinks: (window: TimeWindowQuery) => Promise<QualityRuleResultLink[]>
  listLineageWritebacks: (window: TimeWindowQuery, kind: LineageWritebackEntry['runKind'] | 'all') => Promise<LineageWritebackEntry[]>
}

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 I9_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(I9_METRICS_NOT_WIRED)
}

/**
 * I9 契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（MetricsValidationView）不感知切换。
 */
export function createMetricsContract(): MetricsContract {
  return {
    queryWorkflowResultStats: notWired,
    queryTaskInstanceDataStats: notWired,
    queryTaskDataStatSegments: notWired,
    queryTaskDataErrorSamples: notWired,
    listQualityRuleLinks: notWired,
    listLineageWritebacks: notWired,
  }
}
