/**
 * R4-DEPENDENCY（依赖组件表单）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/dependency/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/2026-10-16-纠偏重构方案设计.md §2.2 客户要求 #5 与 §5.3：
 * 参考 DolphinScheduler 依赖表单——选工作流/任务、周期/日期范围、AND/OR 条件组合、
 * 执行前预览最终依赖表达式和解析结果；覆盖满足/失败/超时。
 * RED 约定：所有 I/O 方法在后端接入前抛 R4_DEPENDENCY_NOT_WIRED，不发出任何真实请求；
 * 表达式草稿拼装等纯前端逻辑可真实运行（见 DependencyFormValidationView）。
 */

/* ---------- 周期 / 日期范围（DolphinScheduler 依赖窗口） ---------- */

export type DependencyPeriodType = 'hour' | 'day' | 'week' | 'month'

/** 相对上游任务计划时间的窗口：offset 0=当前周期，-1=上一周期（day/hour/week/month 各自解释） */
export interface DependencyDateRange {
  periodType: DependencyPeriodType
  beginOffset: number
  endOffset: number
}

/* ---------- 依赖条件与组 ---------- */

export interface DependencyCondition {
  upstreamWorkflowId: number
  /** 固定上游版本；缺省表示随上游最新已发布版本（后端冻结前为草案语义） */
  upstreamWorkflowVersion?: number
  /** 可选：依赖上游某具体任务；缺省为整工作流成功 */
  upstreamTaskCode?: string
  dateRange: DependencyDateRange
}

/** 组内条件按 join 连接；多组之间约定为 AND（草案语义，后端冻结前不改） */
export interface DependencyGroup {
  join: 'AND' | 'OR'
  conditions: DependencyCondition[]
}

/* ---------- 表达式预览 / 判定 ---------- */

export type DependencyVerdict = 'satisfied' | 'pending' | 'failed' | 'timeout'

export interface DependencyExpressionPreview {
  /** 服务端拼装的最终依赖表达式（执行前所见即执行所判） */
  expression: string
  resolved: Array<{
    upstreamWorkflowId: number
    upstreamTaskCode?: string
    windowStart: string
    windowEnd: string
    verdict: DependencyVerdict
  }>
  verdict: DependencyVerdict
}

export interface DependencySaveInput {
  projectId: number
  /** 依赖配置随工作流版本保存（客户 #2/#5 同语义） */
  workflowId: number
  workflowVersion: number
  taskId: string
  groups: DependencyGroup[]
}

export interface DependencyEvaluateRequest {
  projectId: number
  workflowId: number
  workflowVersion: number
  taskId: string
  groups: DependencyGroup[]
  /** 预演时刻（ISO 字符串），用于服务端解析窗口 */
  asOf?: string
}

/* ---------- RED 哨兵 ---------- */

export const R4_DEPENDENCY_NOT_WIRED = 'R4_DEPENDENCY_NOT_WIRED: rebuild/dependency contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R4_DEPENDENCY_CONTRACT_METHODS = [
  'listCandidateWorkflows',
  'listWorkflowTasks',
  'previewExpression',
  'saveDependency',
  'evaluateDependency',
] as const

export type R4DependencyContractMethod = (typeof R4_DEPENDENCY_CONTRACT_METHODS)[number]

export interface DependencyContract {
  listCandidateWorkflows: (projectId: number) => Promise<Array<{ workflowId: number; name: string; latestVersion: number }>>
  listWorkflowTasks: (projectId: number, workflowId: number, workflowVersion?: number) => Promise<Array<{ taskCode: string; name: string }>>
  previewExpression: (projectId: number, workflowId: number, workflowVersion: number, taskId: string, groups: DependencyGroup[]) => Promise<DependencyExpressionPreview>
  saveDependency: (input: DependencySaveInput) => Promise<{ saved: true; version: number }>
  evaluateDependency: (request: DependencyEvaluateRequest) => Promise<DependencyExpressionPreview & { evaluatedAt: string }>
}

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 R4_DEPENDENCY_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(R4_DEPENDENCY_NOT_WIRED)
}

/**
 * R4-DEPENDENCY 契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（DependencyFormValidationView）不感知切换。
 */
export function createDependencyContract(): DependencyContract {
  return {
    listCandidateWorkflows: notWired,
    listWorkflowTasks: notWired,
    previewExpression: notWired,
    saveDependency: notWired,
    evaluateDependency: notWired,
  }
}

/* ---------- 纯前端逻辑：表达式草稿拼装（执行前预览的本地草稿，非服务端终判） ---------- */

function describeCondition(condition: DependencyCondition): string {
  const task = condition.upstreamTaskCode ? ` task(${condition.upstreamTaskCode})` : ''
  const { periodType, beginOffset, endOffset } = condition.dateRange
  return `wf(${condition.upstreamWorkflowId})${task} ${periodType}[${beginOffset}..${endOffset}]`
}

/**
 * 本地拼装人类可读依赖表达式草稿：组内按 join 连接，组间 AND。
 * 仅用于表单即时反馈；最终表达式与窗口解析以服务端 previewExpression 为准（后端冻结前）。
 */
export function composeExpressionDraft(groups: DependencyGroup[]): string {
  return groups
    .map((group) => (group.conditions.length === 1 ? describeCondition(group.conditions[0]) : `(${group.conditions.map(describeCondition).join(` ${group.join} `)})`))
    .join(' AND ')
}
