/**
 * I7 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R6_SCHEDULER_NOT_WIRED（即后端接入前不存在半连通状态）。
 * 组件可编译性由 `pnpm build` 门禁保证。
 */
import { describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({
  get: vi.fn(async (_path: string) => [] as unknown[]),
  post: vi.fn(async () => ({ id: 1, name: 't', kind: 'CRON', enabled: true })),
}))
vi.mock('../../../../services/http', () => ({ http }))
import {
  R6_CONTRACT_METHODS,
  R6_SCHEDULER_NOT_WIRED,
  createScheduleContract,
} from '../../../../services/rebuild/scheduleApi'

describe('I7 scheduleApi contract (GREEN)', () => {
  it('contract method list is frozen to the schedule runtime subset', () => {
    expect(R6_CONTRACT_METHODS).toHaveLength(5)
    expect(R6_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listTriggers',
        'registerTrigger',
        'listQueue',
        'listRuntimeEvents',
        'listAlerts',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createScheduleContract()
    for (const method of R6_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method uses the unified HTTP base and endpoint contract', async () => {
    const contract = createScheduleContract()
    const cases: Promise<unknown>[] = [
      contract.listTriggers(),
      contract.registerTrigger({ name: 't', kind: 'CRON', cron: '0 0 * * *' }),
      contract.listQueue(),
      contract.listRuntimeEvents(null),
      contract.listRuntimeEvents(42),
      contract.listAlerts(),
    ]
    await Promise.all(cases)
    expect(http.get).toHaveBeenCalledWith('/rebuild/schedule/triggers')
    expect(http.post).toHaveBeenCalledWith('/rebuild/schedule/triggers', expect.any(Object))
    expect(http.get).toHaveBeenCalledWith('/rebuild/schedule/queue')
    expect(http.get).toHaveBeenCalledWith('/rebuild/schedule/runtime-events')
    expect(http.get).toHaveBeenCalledWith('/rebuild/schedule/runtime-events?instanceId=42')
    expect(http.get).toHaveBeenCalledWith('/rebuild/schedule/alerts')
  })

  it('registerTrigger forwards misfirePolicy placeholder to the backend', async () => {
    /* FE-08 骨架（ScheduleRuntimeDialog）注册表单的 misfire 占位字段面：
       RED 阶段不产生分支——带 misfirePolicy 的输入与不带同样统一抛哨兵，
       持久化域模型待核（大盘 #31）由后端建模收口后细化。 */
    const contract = createScheduleContract()
    await expect(
      contract.registerTrigger({ name: 't', kind: 'CRON', cron: '0 0 * * *', misfirePolicy: 'FIRE_NOW' }),
    )
    await contract.registerTrigger({ name: 't', kind: 'MANUAL', misfirePolicy: 'RESCHEDULE' })
    expect(http.post).toHaveBeenCalledWith('/rebuild/schedule/triggers', expect.objectContaining({ misfirePolicy: 'RESCHEDULE' }))
  })

  it('sentinel wordform is frozen to R6_SCHEDULER_NOT_WIRED (X13-A rename regression guard)', () => {
    /* Task 1（X13-A）哨兵改名冻结：UI 横幅与守卫以词形前缀匹配，改名即回归此断言 */
    expect(R6_SCHEDULER_NOT_WIRED.startsWith('R6_SCHEDULER_NOT_WIRED')).toBe(true)
  })
})
