/**
 * scheduleCrudApi 契约测试（9-02 GREEN 段，R-22 拆分兑现）：
 * - CRUD 七端点全对拍（动词 / URL / 载荷），8001 rebuild 域为唯一事实源；
 * - 类型面冻结：ScheduleRow 17 键（后端 payload 对拍）+ 策略枚举值集（validate_policies）；
 * - misfirePolicy 校正锁定：FIRE_ONCE 在位，旧值 FIRE_NOW 回潮即编译红（@ts-expect-error 收窄锁）；
 * - nextFireTimes 响应面：create/update 返回 ScheduleMutationResult（S254⑤/S256⑤ 注记销项）；
 * - R6 unchanged subset：拆分后 scheduleApi.ts 观测面保持 RED 哨兵，五方法清单冻结。
 */
import { describe, expect, it } from 'vitest'

import {
  createScheduleCrudContract,
  type ScheduleConcurrencyPolicy,
  type ScheduleInput,
  type ScheduleMisfirePolicy,
  type ScheduleMutationResult,
  type ScheduleRow,
} from '../scheduleCrudApi'
import { R6_CONTRACT_METHODS, R6_SCHEDULER_NOT_WIRED, createScheduleContract } from '../scheduleApi'

/* ---------- 测试底座：mock 全局 fetch，记录调用并回 {code,msg,data} 包络 ---------- */

type RecordedCall = { url: string; init?: RequestInit }

function installFetch(data: () => unknown): RecordedCall[] {
  const calls: RecordedCall[] = []
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init })
    return new Response(JSON.stringify({ code: 0, msg: 'success', data: data() }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch
  return calls
}

/* ---------- 类型面冻结底稿 ---------- */

const SCHEDULE_ROW_KEYS = [
  'id', 'wfCode', 'name', 'crontab', 'startTime', 'endTime', 'state', 'priority',
  'workerGroup', 'failRetryTimes', 'failRetryInterval', 'misfirePolicy',
  'concurrencyPolicy', 'maxRunningInstances', 'timezone', 'createTime', 'updateTime',
] as const satisfies readonly (keyof ScheduleRow)[]

/** 反向覆盖锁：ScheduleRow 增删键而冻结清单未同步时此类型退化为 never，断言行即编译报错 */
type RowKeysCovered = Exclude<keyof ScheduleRow, (typeof SCHEDULE_ROW_KEYS)[number]> extends never ? true : never

const DUMMY_ROW: ScheduleRow = {
  id: 1, wfCode: 2, name: 'n', crontab: '0 0 1 * * *', startTime: null, endTime: null,
  state: 'offline', priority: 3, workerGroup: null, failRetryTimes: 0, failRetryInterval: 0,
  misfirePolicy: 'FIRE_ONCE', concurrencyPolicy: 'ALLOW', maxRunningInstances: 1,
  timezone: 'Asia/Shanghai', createTime: null, updateTime: null,
}

const MISFIRE_POLICIES: readonly ScheduleMisfirePolicy[] = ['FIRE_ONCE', 'SKIP', 'FIRE_ALL_LIMITED']
const CONCURRENCY_POLICIES: readonly ScheduleConcurrencyPolicy[] = ['ALLOW', 'FORBID', 'QUEUE']

const INPUT: ScheduleInput = {
  name: 'nightly', crontab: '0 0 1 * * *', startTime: null, endTime: null,
  priority: 3, workerGroup: null, failRetryTimes: 3, failRetryInterval: 10,
  misfirePolicy: 'FIRE_ONCE', concurrencyPolicy: 'ALLOW', maxRunningInstances: 1,
  timezone: 'Asia/Shanghai',
}

describe('scheduleCrudApi split contract', () => {
  it('uses the rebuild 8001 seven-endpoint surface and keeps policy fields camelCase', async () => {
    const calls = installFetch(() => ({ valid: true, nextFireTimes: [] }))
    const api = createScheduleCrudContract(7)
    await api.previewCrontab('0 0 1 * * *', 'UTC')

    expect(calls[0].url).toBe('/api/v1/rebuild/crontab-preview')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ projectId: 7, crontab: '0 0 1 * * *', timezone: 'UTC' })
    expect(Object.keys(api).sort()).toEqual([
      'createSchedule', 'deleteSchedule', 'listSchedules', 'offlineSchedule',
      'onlineSchedule', 'previewCrontab', 'updateSchedule',
    ].sort())
  })
})

describe('schedule row and policy type face (backend 17-key payload)', () => {
  it('freezes the 17-key ScheduleRow shape against the backend payload', () => {
    const covered: RowKeysCovered = true
    expect(covered).toBe(true)
    expect(SCHEDULE_ROW_KEYS).toEqual(Object.keys(DUMMY_ROW))
    expect(SCHEDULE_ROW_KEYS).toHaveLength(17)
  })

  it('keeps policy enums aligned with backend validate_policies and locks misfire FIRE_ONCE', () => {
    expect([...MISFIRE_POLICIES]).toEqual(['FIRE_ONCE', 'SKIP', 'FIRE_ALL_LIMITED'])
    expect([...CONCURRENCY_POLICIES]).toEqual(['ALLOW', 'FORBID', 'QUEUE'])

    // @ts-expect-error R6：misfire 旧值 FIRE_NOW 已校正为 FIRE_ONCE，回潮则此行编译报错
    const stale: ScheduleMisfirePolicy = 'FIRE_NOW'
    expect(stale).toBe('FIRE_NOW')
  })
})

describe('seven-endpoint wire surface', () => {
  it('covers all seven endpoints with correct verbs and urls', async () => {
    const calls = installFetch(() => DUMMY_ROW)
    const api = createScheduleCrudContract(7)

    await api.listSchedules(3)
    await api.createSchedule(3, INPUT)
    await api.updateSchedule(5, INPUT)
    await api.deleteSchedule(5)
    await api.onlineSchedule(5)
    await api.offlineSchedule(5)
    await api.previewCrontab('0 0 1 * * *')

    expect(calls.map((c) => `${c.init?.method ?? 'GET'} ${c.url}`)).toEqual([
      'GET /api/v1/rebuild/workflow-definitions/3/schedules',
      'POST /api/v1/rebuild/workflow-definitions/3/schedules',
      'PUT /api/v1/rebuild/schedules/5',
      'DELETE /api/v1/rebuild/schedules/5',
      'POST /api/v1/rebuild/schedules/5/online',
      'POST /api/v1/rebuild/schedules/5/offline',
      'POST /api/v1/rebuild/crontab-preview',
    ])
  })

  it('passes the camelCase input through verbatim and defaults preview timezone to Asia/Shanghai', async () => {
    const calls = installFetch(() => DUMMY_ROW)
    const api = createScheduleCrudContract(7)

    await api.createSchedule(3, INPUT)
    await api.updateSchedule(5, INPUT)
    await api.previewCrontab('0 0 1 * * *')

    // 后端 normalized() 拥有默认权：前端零注入，载荷与 input 逐键一致
    expect(JSON.parse(String(calls[0].init?.body))).toEqual(INPUT)
    expect(JSON.parse(String(calls[1].init?.body))).toEqual(INPUT)
    expect(JSON.parse(String(calls[2].init?.body))).toEqual({ projectId: 7, crontab: '0 0 1 * * *', timezone: 'Asia/Shanghai' })
  })

  it('deleteSchedule resolves void without echoing row data', async () => {
    const calls = installFetch(() => DUMMY_ROW)
    const api = createScheduleCrudContract(7)

    await expect(api.deleteSchedule(5)).resolves.toBeUndefined()
    expect(calls[0].init?.method).toBe('DELETE')
    expect(calls[0].url).toBe('/api/v1/rebuild/schedules/5')
  })

  it('exposes nextFireTimes on mutation results and preview per the backend contract', async () => {
    const row: ScheduleMutationResult = { ...DUMMY_ROW, id: 5, nextFireTimes: ['2026-11-01 00:00:00'] }
    let data: unknown = row
    const calls = installFetch(() => data)
    const api = createScheduleCrudContract(7)

    // create/update：ScheduleMutationResult = 17 键行 + nextFireTimes（源文件回潮裸 ScheduleRow 则此行编译红）
    const created = await api.createSchedule(3, INPUT)
    expect(created.nextFireTimes).toEqual(['2026-11-01 00:00:00'])
    expect(created.id).toBe(5)
    const updated = await api.updateSchedule(5, INPUT)
    expect(updated.nextFireTimes).toEqual(['2026-11-01 00:00:00'])

    // preview：{valid, nextFireTimes}
    data = { valid: true, nextFireTimes: ['2026-11-01 00:00:00', '2026-12-01 00:00:00'] }
    const preview = await api.previewCrontab('0 0 1 * * *')
    expect(preview.valid).toBe(true)
    expect(preview.nextFireTimes).toHaveLength(2)
    expect(calls[2].url).toBe('/api/v1/rebuild/crontab-preview')
  })
})

describe('R6 unchanged subset (scheduleApi.ts stays RED after the split)', () => {
  it('keeps the frozen five-method observation list', () => {
    expect([...R6_CONTRACT_METHODS]).toEqual(['listTriggers', 'registerTrigger', 'listQueue', 'listRuntimeEvents', 'listAlerts'])
  })

  it('keeps the three observation methods as RED sentinels', async () => {
    const obs = createScheduleContract()
    await expect(obs.listQueue()).rejects.toThrow(R6_SCHEDULER_NOT_WIRED)
    await expect(obs.listRuntimeEvents()).rejects.toThrow(R6_SCHEDULER_NOT_WIRED)
    await expect(obs.listAlerts()).rejects.toThrow(R6_SCHEDULER_NOT_WIRED)
  })
})
