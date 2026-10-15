/**
 * I9 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 I9_METRICS_NOT_WIRED（即后端接入前不存在半连通状态）。
 * 组件可编译性由 `pnpm build` 门禁保证。
 */
import { describe, expect, it } from 'vitest'
import {
  I9_CONTRACT_METHODS,
  I9_METRICS_NOT_WIRED,
  createMetricsContract,
} from '../../../../services/rebuild/metricsApi'

const window = { from: '2026-01-01T00:00:00Z', to: '2026-01-02T00:00:00Z', offset: 0, limit: 50 }

describe('I9 metricsApi contract (RED)', () => {
  it('contract method list is frozen to the metrics/quality/lineage subset', () => {
    expect(I9_CONTRACT_METHODS).toHaveLength(6)
    expect(I9_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'queryWorkflowResultStats',
        'queryTaskInstanceDataStats',
        'queryTaskDataStatSegments',
        'queryTaskDataErrorSamples',
        'listQualityRuleLinks',
        'listLineageWritebacks',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createMetricsContract()
    for (const method of I9_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until metrics backend is wired', async () => {
    const contract = createMetricsContract()
    const cases: Promise<unknown>[] = [
      contract.queryWorkflowResultStats(window),
      contract.queryTaskInstanceDataStats(window),
      contract.queryTaskDataStatSegments(window),
      contract.queryTaskDataErrorSamples(window),
      contract.listQualityRuleLinks(window),
      contract.listLineageWritebacks(window, 'all'),
      contract.listLineageWritebacks(window, 'sql'),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(I9_METRICS_NOT_WIRED)
    }
  })
})
