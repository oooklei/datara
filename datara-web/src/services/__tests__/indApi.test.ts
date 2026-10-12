import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('indApi', () => {
  const fetchMock = vi.fn()
  beforeEach(() => { vi.stubEnv('VITE_API_MODE', 'real'); vi.resetModules(); fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('localStorage', { getItem: () => 'tok-ind', setItem: vi.fn(), removeItem: vi.fn() }) })
  it('列表筛选和一致性接口契约', async () => {
    const api = await import('../indApi')
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: '', data: { list: [], total: 0 } }) })
    await api.listIndicators({ status: 'published', keyword: 'pay' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/indicators?status=published&keyword=pay')
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: '', data: { checked: 0, pass: 0, fail: 0, items: [] } }) })
    await api.getIndicatorConsistency()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/indicators/consistency')
  })
})
