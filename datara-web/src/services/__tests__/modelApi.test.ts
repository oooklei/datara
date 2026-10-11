/**
 * modelApi 单测（isMock 分支）：apiMode 模块在 import 时读 env，故用 stubEnv + 动态 import。
 * mock 分支走 dataStore 演示文档（demo 形状适配断言）。
 * 注：dataStore 预置 seed 且无 clear API → models 集合先按 id remove 清空再写入；
 * dwLayers seed 行无 id 字段无法按 id 清空 → 字典断言用 find 定位 DWD 层。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.stubEnv('VITE_API_MODE', 'mock')

describe('modelApi mock 分支', () => {
  beforeEach(async () => {
    vi.resetModules()
    const { dataStore } = await import('../mock/dataStore')
    for (const row of await dataStore.list<{ id?: string | number }>('models')) {
      await dataStore.remove('models', String(row.id))
    }
    await dataStore.save('dwLayers', { code: 'DWD', name: '明细数据层', rule: 'dwd_业务_过程，一个过程一张表', color: '#1668dc', seq: 2 })
    await dataStore.save('models', {
      id: 'MD001', name: '订单支付明细表', code: 'dwd_order_pay', layer: 'DWD',
      engine: 'Apache Doris', type: '事实表', status: 'published', version: 3,
      owner: '王工', bizDomain: '交易域', updatedAt: '2026-09-10 15:20',
      fields: [{ n: 'user_id', t: 'BIGINT', len: '', pk: true, pkPart: false, cmt: '用户ID', def: '' }],
    })
  })

  it('listModels 返回适配后的契约形状', async () => {
    const api = await import('../modelApi')
    const r = await api.listModels()
    expect(r.total).toBe(1)
    expect(r.list[0]).toMatchObject({ id: 1, code: 'dwd_order_pay', status: 'published', version: 3 })
    expect(r.layers).toContainEqual({ code: 'DWD', count: 1 })
  })

  it('getModelDicts 返回字典三元组', async () => {
    const api = await import('../modelApi')
    const d = await api.getModelDicts()
    const dwd = d.layers.find((l) => l.code === 'DWD')
    expect(dwd).toMatchObject({ code: 'DWD', rule: expect.stringContaining('dwd_') })
    expect(d.domains.length).toBeGreaterThan(0)
    expect(d.engines.length).toBeGreaterThan(0)
  })
})
