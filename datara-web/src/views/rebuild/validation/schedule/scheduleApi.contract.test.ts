/**
 * I7 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R6_SCHEDULER_NOT_WIRED（即后端接入前不存在半连通状态）。
 * 组件可编译性由 `pnpm build` 门禁保证。
 */
import { describe, expect, it } from 'vitest'
import {
  R6_CONTRACT_METHODS,
  R6_SCHEDULER_NOT_WIRED,
  createScheduleContract,
} from '../../../../services/rebuild/scheduleApi'

describe('I7 scheduleApi contract (RED)', () => {
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

  it('every I/O method refuses until schedule backend is wired', async () => {
    const contract = createScheduleContract()
    const cases: Promise<unknown>[] = [
      contract.listTriggers(),
      contract.registerTrigger({ name: 't', kind: 'CRON', cron: '0 0 * * *' }),
      contract.listQueue(),
      contract.listRuntimeEvents(null),
      contract.listRuntimeEvents(42),
      contract.listAlerts(),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(R6_SCHEDULER_NOT_WIRED)
    }
  })
})
