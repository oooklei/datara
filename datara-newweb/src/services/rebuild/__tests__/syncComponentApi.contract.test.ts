import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSyncComponentContract, SyncApiError, suggestInitialMapping, type SyncColumn } from '../syncComponentApi'

const source = { datasource_id: 7, schema: 'sales', object: 'orders' }
const target = { datasource_id: 8, schema: 'dw', object: 'orders_v2' }

function ok(data: unknown): Response {
  return new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => vi.unstubAllGlobals())

describe('R4 SYNC API adapter', () => {
  it('gets capabilities and explores both the schema and wire fields', async () => {
    vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'datara_token' ? 'validation-token' : null })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok({ form_fields: ['source_datasource'], mapping_fields: [], mapping_status: [] }))
      .mockResolvedValueOnce(ok({ items: [{ column_name: 'id', data_type: 'int' }], truncated: false, limit: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = createSyncComponentContract()
    expect((await api.getCapabilities()).form_fields).toEqual(['source_datasource'])
    const result = await api.explore(4, source)
    expect(result.items[0]?.column_name).toBe('id')
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/api/v1/rebuild/sync/capabilities')
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/explore?project_id=4&datasource_id=7&schema=sales&object_name=orders&limit=200')
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>).token).toBe('validation-token')
  })

  it('sends auto mapping and version plan requests using the backend contract', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(ok({ mappings: [{ source_column: 'id', target_column: 'id' }] }))
      .mockResolvedValueOnce(ok({ saved: true, workflow_version: 2, task_id: 'sync-orders' }))
      .mockResolvedValueOnce(ok({ items: [{ task_id: 'sync-orders', workflow_version: 2 }] }))
    vi.stubGlobal('fetch', fetchMock)
    const api = createSyncComponentContract()
    expect(await api.autoMap(4, source, target)).toEqual([{ source_column: 'id', target_column: 'id' }])
    const plan = {
      project_id: 4,
      workflow_id: 12,
      workflow_version: 2,
      task_id: 'sync-orders',
      source,
      target,
      mappings: [],
      transform_config: { filter_condition: '' },
      target_properties: { batch_concurrency: { batch_size: 500, concurrency: 2 } },
    }
    expect(await api.savePlan(plan)).toMatchObject({ saved: true, workflow_version: 2 })
    expect(await api.listPlans(4, 12, 2)).toHaveLength(1)
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual([
      '/api/v1/rebuild/sync/mappings/auto',
      '/api/v1/rebuild/sync/plans',
      '/api/v1/rebuild/sync/plans?project_id=4&workflow_id=12&workflow_version=2',
    ])
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ project_id: 4, source, target })
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual(plan)
  })

  it('surfaces backend diagnostics as a typed error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'SYNC_INVALID_TRANSFORM', msg: 'transform_config violates its schema', data: { diagnostics: [{ field: 'transform_config.filter_condition' }] },
    }), { status: 400, headers: { 'Content-Type': 'application/json' } })))
    await expect(createSyncComponentContract().getCapabilities()).rejects.toMatchObject({
      name: 'SyncApiError', status: 400, code: 'SYNC_INVALID_TRANSFORM',
      diagnostics: [{ field: 'transform_config.filter_condition' }],
    } satisfies Partial<SyncApiError>)
  })

  it('suggests mappings by case-insensitive column name', () => {
    const sourceColumns: SyncColumn[] = [{ column_name: 'Name', data_type: 'varchar' }]
    const targetColumns: SyncColumn[] = [
      { column_name: 'NAME', data_type: 'text' },
      { column_name: 'missing', data_type: 'int' },
    ]
    expect(suggestInitialMapping(sourceColumns, targetColumns)).toMatchObject([
      { source_column: 'Name', target_column: 'NAME', mapping_status: 'AUTO' },
      { source_column: '', target_column: 'missing', mapping_status: 'UNMATCHED' },
    ])
  })
})
