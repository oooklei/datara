/**
 * I7（调度运行时）契约层 — GREEN 阶段（2026-10-25 更正）。
 * 端点前缀 /api/v1/rebuild/schedule/*，经 http 底座统一信封接线；
 * 本文件语义源自 docs/increments/I7-I9-前端消费面分析.md §3（契约期待草案）。
 * 事件契约模式参照 legacy views/dag/InstanceRunsView.vue 的 InstanceRow/TaskStateEvent。
 *
 * FE-08 补登（2026-10-19）：Alert 记录面板（listAlerts）落位 alarm 页签（/dag/alarm），
 * 与「调度弹窗（ScheduleDialog）+ 实例页（InstanceRunsView）」两处职责边界：
 * - 弹窗/实例页：调度配置与运行时状态（TRIAL/FORMAL/STREAM 三态）；
 * - alarm 页签：告警记录只读列表（级别/通道/时间），不承载调度配置编辑。
 *
 * 更正（2026-10-25）：旧 RED 注释已过时——createScheduleContract() 五方法经 request()
 * 真实接线后端 rebuild/schedule；R6_SCHEDULER_NOT_WIRED 常量仅保留作 View 横幅兼容引用，
 * 不再是活哨兵（原 L6/L109 RED 约定注释与实现体不一致已修正）。
 */

/* ---------- 触发注册（MANUAL/CRON/DEPENDENCY/EVENT/TRIAL，plan I7 Step） ---------- */

export type TriggerKind = 'MANUAL' | 'CRON' | 'DEPENDENCY' | 'EVENT' | 'TRIAL'

export interface TriggerRegistration {
  id: number
  name: string
  kind: TriggerKind
  /** CRON 表达式（仅 CRON 触发） */
  cron?: string | null
  /** 依赖工作流 ID（DEPENDENCY）或事件源标识（EVENT） */
  source?: string | null
  enabled: boolean
  /** 下次/最近触发时间（列表期待字段） */
  nextFireAt?: string | null
  lastFireAt?: string | null
  /** misfire 策略标识（如 FIRE_NOW/RESCHEDULE） */
  misfirePolicy?: string | null
}

export interface TriggerRegistrationInput {
  name: string
  kind: TriggerKind
  cron?: string | null
  source?: string | null
  enabled?: boolean
  misfirePolicy?: string | null
}

/* ---------- 实例队列视图（并发/优先级/misfire 状态） ---------- */

export interface ScheduleQueueEntry {
  instanceId: number
  workflowId: number
  triggerKind: TriggerKind
  priority: number
  state: 'queued' | 'dispatched' | 'running' | 'finished' | 'canceled' | 'misfired'
  /** 并发槽位（并发控制观测面） */
  concurrencySlot?: number | null
  enqueuedAt: string
  startedAt?: string | null
  finishedAt?: string | null
}

/* ---------- 运行时事件流（超时/重试/Master 分派/Logger 事件链） ---------- */

export interface ScheduleRuntimeEvent {
  /** 事件序号（单调递增，事件链排序键） */
  seq: number
  instanceId: number
  type: 'dispatch' | 'master-assign' | 'timeout' | 'retry' | 'log' | 'alert'
  /** 重试尝试序号（retry 事件） */
  attempt?: number | null
  timeoutSec?: number | null
  message?: string | null
  occurredAt: string
}

/* ---------- Alert 记录 ---------- */

export interface ScheduleAlert {
  id: number
  instanceId: number | null
  level: 'info' | 'warn' | 'error'
  channel: string
  message: string
  createdAt: string
}

/* ---------- 兼容常量（GREEN 接线后保留，供旧 View 横幅引用；非活哨兵） ---------- */

/** @deprecated VIEW 横幅兼容引用；契约已 GREEN，不再作哨兵抛出 */
export const R6_SCHEDULER_NOT_WIRED = 'R6_SCHEDULER_NOT_WIRED: rebuild/schedule contract not connected yet'

import { request } from '../http'

const BASE = '/rebuild/schedule'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R6_CONTRACT_METHODS = [
  'listTriggers',
  'registerTrigger',
  'listQueue',
  'listRuntimeEvents',
  'listAlerts',
] as const

export type R6ContractMethod = (typeof R6_CONTRACT_METHODS)[number]

export interface ScheduleContract {
  listTriggers: () => Promise<TriggerRegistration[]>
  registerTrigger: (input: TriggerRegistrationInput) => Promise<TriggerRegistration>
  listQueue: () => Promise<ScheduleQueueEntry[]>
  listRuntimeEvents: (instanceId?: number | null) => Promise<ScheduleRuntimeEvent[]>
  listAlerts: () => Promise<ScheduleAlert[]>
}

/* ---------- GREEN 实现（经 http 底座统一信封接线后端 rebuild/schedule） ---------- */

/**
 * I7 契约工厂（已活态）：签名与类型已冻结，五方法经 request() 真实接线；
 * UI 层（ScheduleValidationView）不感知切换。R6_SCHEDULER_NOT_WIRED 保留仅作兼容引用。
 */
export function createScheduleContract(): ScheduleContract {
  return {
    listTriggers: () => request<TriggerRegistration[]>(`${BASE}/triggers`),
    registerTrigger: (input) => request<TriggerRegistration>(`${BASE}/triggers`, { method: 'POST', json: input }),
    listQueue: () => request<ScheduleQueueEntry[]>(`${BASE}/queue`),
    listRuntimeEvents: (instanceId = null) => request<ScheduleRuntimeEvent[]>(`${BASE}/runtime-events`, { query: { instanceId } }),
    listAlerts: () => request<ScheduleAlert[]>(`${BASE}/alerts`),
  }
}
