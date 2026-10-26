import { afterEach, describe, expect, it, vi } from 'vitest'
import { modelApi } from '../modelApi'

afterEach(() => vi.unstubAllGlobals())
const envelope = (data: unknown) => new Response(JSON.stringify({ code: 0, msg: 'success', data }), {
  status: 200, headers: { 'Content-Type': 'application/json' },
})

describe('model API', () => {
  it('normalizes the field-save revision envelope to a number', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(envelope({ rev: 3 })))

    await expect(modelApi.updateFields(8, { rev: 2, fields: [] })).resolves.toBe(3)
  })

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

  it('connects design, versions, lineage, ER, and physicalization operations', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(envelope({})))
    vi.stubGlobal('fetch', fetchMock)

    await modelApi.detail(8)
    await modelApi.updateFields(8, { rev: 2, fields: [] })
    await modelApi.listVersions(8)
    await modelApi.createVersion(8, { changeNote: '字段调整' })
    await modelApi.diffVersion(8, 3, 2)
    await modelApi.rollbackVersion(8, 3)
    await modelApi.getEr({ layer: 'DWD', domain: '交易域' })
    await modelApi.putEr({ positions: {}, relations: { removed: [], added: [], updated: [] } })
    await modelApi.lineage(8)
    await modelApi.impact(8)
    await modelApi.physicalize(8, { engine: 'mysql', mode: 'script' })

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/models/8')
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('PUT')
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain('/versions/3/diff?base=2')
    expect(String(fetchMock.mock.calls[6]?.[0])).toContain('/models/er?layer=DWD&domain=')
    expect(fetchMock.mock.calls[7]?.[1]?.method).toBe('PUT')
    expect(String(fetchMock.mock.calls[8]?.[0])).toContain('/models/8/lineage')
    expect(String(fetchMock.mock.calls[9]?.[0])).toContain('/models/8/impact')
    expect(String(fetchMock.mock.calls[10]?.[0])).toContain('/models/8/physicalize')
  })
})
