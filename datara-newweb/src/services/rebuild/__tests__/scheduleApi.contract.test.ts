/**
 * I7 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R6_SCHEDULER_NOT_WIRED（即后端接入前不存在半连通状态）。
 * 组件可编译性由 `pnpm build` 门禁保证。
 */
import { describe, expect, it, vi } from 'vitest'
const { request } = vi.hoisted(() => ({ request: vi.fn(async (path: string, options?: { method?: string; json?: unknown; query?: unknown }) => {
  if (path.endsWith('/triggers') && options?.method === 'POST') return { id: 1, name: 't', kind: 'CRON', enabled: false }
  return []
}) }))
vi.mock('../../http', () => ({ request }))
import {
  R6_CONTRACT_METHODS,
  R6_SCHEDULER_NOT_WIRED,
  createScheduleContract,
} from '../scheduleApi'

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

  it('every observation method is wired to the rebuild scheduling endpoints', async () => {
    const contract = createScheduleContract()
    await contract.listTriggers()
    await contract.registerTrigger({ name: 't', kind: 'CRON', cron: '0 0 * * *' })
    await contract.listQueue()
    await contract.listRuntimeEvents(42)
    await contract.listAlerts()
    expect(request.mock.calls.map(([path]) => path)).toEqual([
      '/rebuild/schedule/triggers', '/rebuild/schedule/triggers',
      '/rebuild/schedule/queue', '/rebuild/schedule/runtime-events',
      '/rebuild/schedule/alerts',
    ])
  })

  it('registerTrigger forwards misfirePolicy to the backend unchanged', async () => {
    /* FE-08 骨架（ScheduleRuntimeDialog）注册表单的 misfire 占位字段面：
       RED 阶段不产生分支——带 misfirePolicy 的输入与不带同样统一抛哨兵，
       持久化域模型待核（大盘 #31）由后端建模收口后细化。 */
    const contract = createScheduleContract()
    await contract.registerTrigger({ name: 't', kind: 'CRON', cron: '0 0 * * *', misfirePolicy: 'FIRE_NOW' })
    expect(request.mock.calls.at(-1)?.[1]).toEqual(expect.objectContaining({ json: expect.objectContaining({ misfirePolicy: 'FIRE_NOW' }) }))
  })

  it('sentinel wordform is frozen to R6_SCHEDULER_NOT_WIRED (X13-A rename regression guard)', () => {
    /* Task 1（X13-A）哨兵改名冻结：UI 横幅与守卫以词形前缀匹配，改名即回归此断言 */
    expect(R6_SCHEDULER_NOT_WIRED.startsWith('R6_SCHEDULER_NOT_WIRED')).toBe(true)
  })
})
