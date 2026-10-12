import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('metaApi 真实契约', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubEnv('VITE_API_MODE', 'real'); vi.resetModules(); fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => 'tok-meta', setItem: vi.fn(), removeItem: vi.fn() })
  })
  it('目录查询拼接筛选条件', async () => {
    const api = await import('../metaApi')
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: '', data: { list: [], total: 0 } }) })
    await api.listMetaCatalog({ keyword: 'order', layer: 'DWD', domain: '交易域' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/meta/catalog/tables?keyword=order&layer=DWD&domain=%E4%BA%A4%E6%98%93%E5%9F%9F')
  })
  it('资产地图使用 GET /meta/map 并透传 view/limit', async () => {
    const api = await import('../metaApi')
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: '', data: { stats: {}, nodes: [], edges: [], truncated: false } }) })
    await api.getMetaMap({ view: 'domain', limit: 50 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/meta/map?view=domain&limit=50')
  })
})
