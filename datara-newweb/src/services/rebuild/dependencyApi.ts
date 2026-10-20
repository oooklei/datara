/**
 * R4-DEPENDENCY（依赖组件表单）契约层 — GREEN 接线（接线计划 Task 4，R4 批次）。
 * 端点与映射依据：docs/increments/2026-10-17-R系列GREEN接线计划.md Task 4 +
 * A2 v2.1 冻结契约（R4-DEP-RES-API-contract-pending.md §2/§3.1/§7，双线会签）；
 * 包络 {code,msg,data} 沿 R2/R7 批次固化。
 * upstreamTaskCode 为 FE string 契约、BE int 哨兵（0=workflow / -1=all_tasks / 正数=task code），
 * 接线时 Number() 转换（非十进制整数字符串 fail-fast 抛 ID_NORMALIZATION_FAILED）；
 * resolved.upstream_task_code 由 BE 仅在 selector=task 时以 string 下发，键名 snake→camel 归一。
 * 窄口径披露（与 BE 侧一致）：main 暂无 workflow 注册表/执行域，
 * listCandidateWorkflows/listWorkflowTasks 返回诚实空列表，随注册表域落地补真实数据。
 * R4_DEPENDENCY_NOT_WIRED 常量保留（View 横幅引用兼容）。
 */

import { camelToSnake, ContractApiError, ID_NORMALIZATION_FAILED, snakeToCamel } from './adapterKit'
import { getToken } from '../http'

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

/* ---------- GREEN 统一原语（沿 R2/R7 固化版；BASE 换 dependency 域） ---------- */

/** 端点前缀（A2 v2.1 冻结契约） */
const BASE = '/api/v1/rebuild/dependency'

const TIMEOUT_MS = 15000

/** 后端成功包络（rebuild 域全域实证形态） */
interface ApiEnvelope {
  code?: number | string
  msg?: string
  data?: unknown
}

/** 统一 JSON fetch 原语：15s AbortController 超时 + token header + 包络解包 + 归一错误 */
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers.token = token
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      method: init?.method ?? 'GET',
      headers: { ...headers, ...(init?.headers as Record<string, string>) },
      signal: ctrl.signal,
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => '')
      // 非 2xx 但包络含 code（DEP_*/4001/1001/1003/4041）时保码透出（A2 §2/§4 错误映射），
      // httpStatus 同步保留；非 JSON/无 code 再退回 HTTP 状态码错误。
      let parsed: ApiEnvelope | undefined
      try {
        parsed = JSON.parse(raw) as ApiEnvelope
      } catch {
        parsed = undefined
      }
      if (parsed && parsed.code !== undefined) {
        throw new ContractApiError({ httpStatus: res.status, code: parsed.code, msg: parsed.msg ?? path, raw: parsed })
      }
      throw new ContractApiError({ httpStatus: res.status, code: res.status, msg: `HTTP ${res.status} ${path}`, raw })
    }
    const envelope = (await res.json()) as ApiEnvelope
    if (envelope.code !== undefined && envelope.code !== 0 && envelope.code !== 200) {
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

/** POST：请求体深度 camel→snake，响应深度 snake→camel（preview/saves/evaluate 全 POST） */
async function sendJson<T>(path: string, body: unknown): Promise<T> {
  return snakeToCamel(await requestJson<unknown>(path, { method: 'POST', body: JSON.stringify(camelToSnake(body)) })) as T
}

/** GET：query 参数展开，响应深度 snake→camel（workflows/tasks 两查询） */
async function getJson<T>(path: string, params: Record<string, string>): Promise<T> {
  const query = new URLSearchParams(params).toString()
  return snakeToCamel(await requestJson<unknown>(query ? `${path}?${query}` : path)) as T
}

/**
 * upstreamTaskCode FE string → BE int 哨兵（A2 v2.1 §7.1）：
 * 仅接受十进制整数字符串（'0'/'-1'/正数），其余 fail-fast（R2.3 有损即拒绝口径）。
 */
function taskCodeToWire(value: string): number {
  const parsed = Number(value)
  if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(parsed)) {
    throw new ContractApiError({
      httpStatus: 0,
      code: ID_NORMALIZATION_FAILED,
      msg: `upstreamTaskCode must be a decimal integer sentinel string (workflow=0 / all_tasks=-1 / task=positive), got "${value}"`,
      raw: value,
    })
  }
  return parsed
}

/** FE 条件 → wire 条件：upstreamTaskCode string→int；其余键名交给 camelToSnake 深度转换 */
function conditionToWire(condition: DependencyCondition): Record<string, unknown> {
  const wire: Record<string, unknown> = { ...condition }
  if (condition.upstreamTaskCode !== undefined) {
    wire.upstreamTaskCode = taskCodeToWire(condition.upstreamTaskCode)
  }
  return wire
}

/** FE 组 → wire 组 */
function groupsToWire(groups: DependencyGroup[]): Array<{ join: string; conditions: Record<string, unknown>[] }> {
  return groups.map((group) => ({ join: group.join, conditions: group.conditions.map(conditionToWire) }))
}

/**
 * R4-DEPENDENCY 契约工厂 — GREEN：5 方法接线至 A2 v2.1 冻结契约的后端实现（Task 4 契约面表），
 * 签名与返回类型不动，UI 层（DependencyFormValidationView）不感知切换。
 * 窄口径：main 无 workflow 注册表 → 两个 list 方法当前返回诚实空列表（后端已披露）。
 */
export function createDependencyContract(): DependencyContract {
  return {
    listCandidateWorkflows: (projectId) =>
      getJson<Array<{ workflowId: number; name: string; latestVersion: number }>>('/workflows', {
        project_id: String(projectId),
      }),
    listWorkflowTasks: (projectId, workflowId, workflowVersion) =>
      getJson<Array<{ taskCode: string; name: string }>>(
        `/workflows/${workflowId}/tasks`,
        workflowVersion !== undefined
          ? { project_id: String(projectId), workflow_version: String(workflowVersion) }
          : { project_id: String(projectId) },
      ),
    previewExpression: async (projectId, workflowId, workflowVersion, taskId, groups) =>
      sendJson<DependencyExpressionPreview>('/preview', {
        projectId,
        workflowId,
        workflowVersion,
        taskId,
        groups: groupsToWire(groups),
      }),
    saveDependency: async (input) =>
      sendJson<{ saved: true; version: number }>('/saves', {
        projectId: input.projectId,
        workflowId: input.workflowId,
        workflowVersion: input.workflowVersion,
        taskId: input.taskId,
        groups: groupsToWire(input.groups),
      }),
    evaluateDependency: async (request) =>
      sendJson<DependencyExpressionPreview & { evaluatedAt: string }>('/evaluate', {
        projectId: request.projectId,
        workflowId: request.workflowId,
        workflowVersion: request.workflowVersion,
        taskId: request.taskId,
        groups: groupsToWire(request.groups),
        ...(request.asOf !== undefined ? { asOf: request.asOf } : {}),
      }),
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
