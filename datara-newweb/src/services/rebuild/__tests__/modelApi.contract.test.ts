import { afterEach, describe, expect, it, vi } from 'vitest'
import { modelApi } from '../modelApi'

afterEach(() => vi.unstubAllGlobals())
const envelope = (data: unknown) => new Response(JSON.stringify({ code: 0, msg: 'success', data }), {
  status: 200, headers: { 'Content-Type': 'application/json' },
})

describe('model API', () => {
  it('connects list, create, lifecycle, DDL, and delete operations', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(envelope({ total: 0, list: [], layers: [], domains: [] }))
      .mockResolvedValueOnce(envelope({ id: 8 }))
      .mockResolvedValueOnce(envelope({ status: 'published' }))
      .mockResolvedValueOnce(envelope({ engine: 'mysql', ddl: 'CREATE TABLE t()', notes: [] }))
      .mockResolvedValueOnce(envelope({ deleted: true }))
    vi.stubGlobal('fetch', fetchMock)

    await modelApi.list({ keyword: 'orders', status: 'draft', page: 1, size: 100 })
    await modelApi.create({ name: '订单', code: 'dwd_orders', layer: 'DWD', engine: 'mysql' })
    await modelApi.publish(8)
    await modelApi.ddl(8, 'mysql')
    await modelApi.remove(8)

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v1/rebuild/models?keyword=orders&status=draft&page=1&size=100')
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({ code: 'dwd_orders', layer: 'DWD' })
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/models/8/publish')
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain('/models/8/ddl?engine=mysql')
    expect(fetchMock.mock.calls[4]?.[1]?.method).toBe('DELETE')
  })
})
