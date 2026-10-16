/**
 * I8 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 I8_STREAM_NOT_WIRED（即后端接入前不存在半连通状态）。
 * 组件可编译性由 `pnpm build` 门禁保证。
 */
import { describe, expect, it } from 'vitest'
import {
  I8_CONTRACT_METHODS,
  I8_STREAM_NOT_WIRED,
  createStreamContract,
} from '../../../../services/rebuild/streamApi'

const window = { from: '2026-01-01T00:00:00Z', to: '2026-01-02T00:00:00Z', offset: 0, limit: 50 }

describe('I8 streamApi contract (RED)', () => {
  it('contract method list is frozen to the stream job/attempt/checkpoint/metric/observation/recovery subset', () => {
    expect(I8_CONTRACT_METHODS).toHaveLength(6)
    expect(I8_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listStreamJobs',
        'listStreamAttempts',
        'listStreamCheckpoints',
        'listStreamMetrics',
        'queryStreamObservation',
        'listStreamRecoveryEvents',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createStreamContract()
    for (const method of I8_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until stream backend is wired', async () => {
    const contract = createStreamContract()
    const cases: Promise<unknown>[] = [
      contract.listStreamJobs(window),
      contract.listStreamAttempts(window),
      contract.listStreamAttempts(window, 'job-1'),
      contract.listStreamCheckpoints(window),
      contract.listStreamMetrics(window),
      contract.queryStreamObservation(window),
      contract.listStreamRecoveryEvents(window, 'job-1'),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(I8_STREAM_NOT_WIRED)
    }
  })
})
