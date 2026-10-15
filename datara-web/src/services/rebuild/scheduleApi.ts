/**
 * I7（调度运行时）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/schedule/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/I7-I9-前端消费面分析.md §3（契约期待草案）。
 * 事件契约模式参照 legacy views/dag/InstanceRunsView.vue 的 InstanceRow/TaskStateEvent。
 * RED 约定：所有 I/O 方法在后端接入前抛 I7_SCHEDULER_NOT_WIRED，不发出任何真实请求。
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

/* ---------- RED 哨兵 ---------- */

export const I7_SCHEDULER_NOT_WIRED = 'I7_SCHEDULER_NOT_WIRED: rebuild/schedule contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const I7_CONTRACT_METHODS = [
  'listTriggers',
  'registerTrigger',
  'listQueue',
  'listRuntimeEvents',
  'listAlerts',
] as const

export type I7ContractMethod = (typeof I7_CONTRACT_METHODS)[number]

export interface ScheduleContract {
  listTriggers: () => Promise<TriggerRegistration[]>
  registerTrigger: (input: TriggerRegistrationInput) => Promise<TriggerRegistration>
  listQueue: () => Promise<ScheduleQueueEntry[]>
  listRuntimeEvents: (instanceId?: number | null) => Promise<ScheduleRuntimeEvent[]>
  listAlerts: () => Promise<ScheduleAlert[]>
}

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 I7_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(I7_SCHEDULER_NOT_WIRED)
}

/**
 * I7 契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（ScheduleValidationView）不感知切换。
 */
export function createScheduleContract(): ScheduleContract {
  return {
    listTriggers: notWired,
    registerTrigger: notWired,
    listQueue: notWired,
    listRuntimeEvents: notWired,
    listAlerts: notWired,
  }
}
