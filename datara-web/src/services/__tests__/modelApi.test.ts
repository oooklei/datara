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

describe('modelApi 真实分支（stub fetch 契约，datasourceApi.test 先例）', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubEnv('VITE_API_MODE', 'real')
    vi.resetModules()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => 'tok-i4', setItem: vi.fn(), removeItem: vi.fn() })
  })

  it('listModels → GET /models，查询串按需拼接（无参时无 ?）', async () => {
    const api = await import('../modelApi')
    const resp = { code: 0, msg: '', data: { list: [], total: 0, layers: [], domains: [] } }
    fetchMock.mockResolvedValueOnce({ json: async () => resp })
    await api.listModels({ layer: 'DWD', status: 'published', keyword: 'pay', page: 1, size: 20 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/models?layer=DWD&status=published&keyword=pay&page=1&size=20')
    expect(init.method).toBe('GET')
    expect(init.headers.token).toBe('tok-i4')

    fetchMock.mockResolvedValueOnce({ json: async () => resp })
    await api.listModels()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/models')
  })

  it('reverseImportDdl → POST multipart（URL/FormData file 字段/token header），code=0 返回 data', async () => {
    const api = await import('../modelApi')
    fetchMock.mockResolvedValueOnce({ status: 200, text: async () => JSON.stringify({ code: 0, msg: '', data: { imported: 2, skipped: [] } }) })
    const file = new File(['CREATE TABLE t(id INT);'], 'model.sql', { type: 'text/plain' })
    const r = await api.reverseImportDdl(file)
    expect(r).toEqual({ imported: 2, skipped: [] })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/models/reverse/import-ddl')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file')).toBe(file)
    expect(init.headers.token).toBe('tok-i4')
  })

  it('reverseImportDdl：code≠0 → throw Error(msg)', async () => {
    const api = await import('../modelApi')
    fetchMock.mockResolvedValueOnce({ status: 400, text: async () => JSON.stringify({ code: 1, msg: 'DDL 解析失败', data: null }) })
    await expect(api.reverseImportDdl(new File(['bad'], 'bad.sql'))).rejects.toThrow('DDL 解析失败')
  })

  it('reverseImportDdl：非 JSON 响应（代理 502 HTML）→ 可读 HTTP 错误', async () => {
    const api = await import('../modelApi')
    fetchMock.mockResolvedValueOnce({ status: 502, text: async () => '<html>502 Bad Gateway</html>' })
    await expect(api.reverseImportDdl(new File(['x'], 'x.sql'))).rejects.toThrow('HTTP 502')
  })
})
