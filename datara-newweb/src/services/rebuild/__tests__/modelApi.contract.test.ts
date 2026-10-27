/**
 * I18 数仓建模 API 契约测试（A6 分片 22 端点）。
 * 以 `datara-backend/rebuild/model/api.py` 为真源，逐方法断言 URL + HTTP method + 关键参数。
 * 传输底座 `../../http` 被整体 mock，故断言落在 modelApi 的路径/动词/入参映射上。
 */
import { describe, expect, it, vi } from 'vitest'

/** 传输底座 mock：参数形态显式声明，保证 `mock.calls` 元组可按位索引（放行门③ vue-tsc）。 */
const http = vi.hoisted(() => ({
  getJson: vi.fn(async (path: string, query?: unknown) => ({})),
  postJson: vi.fn(async (path: string, body?: unknown) => ({})),
  putJson: vi.fn(async (path: string, body?: unknown) => ({})),
  patchJson: vi.fn(async (path: string, body?: unknown) => ({})),
  deleteJson: vi.fn(async (path: string, options?: unknown) => ({})),
  request: vi.fn(async (path: string, options?: { method?: string; body?: BodyInit | null; query?: unknown }) => ({})),
}))
vi.mock('../../http', () => http)

import { modelApi } from '../modelApi'

const methodOf = (call: unknown[]) => (call[1] as { method?: string } | undefined)?.method

/** `ModelFieldRow` 全字段行（A6-9 全量保存；vue-tsc 要求类型完整）。 */
const fieldRow = {
  name: 'id', dataType: 'bigint', length: null, precision: null,
  nullable: false, defaultValue: null, comment: '主键', isPk: true, isPartition: false, dictRef: null,
}

describe('I18 modelApi contract (A6-1~A6-22)', () => {
  it('maps all 22 methods to the rebuild model routes', async () => {
    const file = new File(['CREATE TABLE t();'], 'schema.sql', { type: 'text/sql' })

    await modelApi.list({ keyword: 'orders', status: 'draft', page: 1, size: 100 })
    await modelApi.dicts()
    await modelApi.create({ name: '订单', code: 'dwd_orders', layer: 'DWD', engine: 'mysql' })
    await modelApi.update(8, { name: '订单V2' })
    await modelApi.remove(8)
    await modelApi.publish(8)
    await modelApi.redraft(8)
    await modelApi.ddl(8, 'mysql')
    await modelApi.detail(8)
    await modelApi.updateFields(8, { rev: 1, fields: [] })
    await modelApi.listVersions(8)
    await modelApi.createVersion(8, { changeNote: 'v2' })
    await modelApi.diffVersion(8, 3, 2)
    await modelApi.rollbackVersion(8, 3)
    await modelApi.getEr({ layer: 'DWD', domain: '交易域' })
    await modelApi.putEr({ positions: { '1': { x: 10, y: 20 } }, relations: { removed: [], added: [], updated: [] } })
    await modelApi.lineage(8)
    await modelApi.impact(8)
    await modelApi.physicalize(8, { engine: 'mysql', mode: 'script' })
    await modelApi.reverseScan({ dsId: 5 })
    await modelApi.reverseImport({ dsId: 5, tables: [{ tb: 't_order' }] })
    await modelApi.reverseImportDdl(file)

    expect(http.getJson.mock.calls.map(([path]) => path)).toEqual([
      '/rebuild/models', '/rebuild/model-dicts', '/rebuild/models/8/ddl',
      '/rebuild/models/8', '/rebuild/models/8/versions',
      '/rebuild/models/8/versions/3/diff', '/rebuild/models/er',
      '/rebuild/models/8/lineage', '/rebuild/models/8/impact',
    ])
    expect(http.postJson.mock.calls.map(([path]) => path)).toEqual([
      '/rebuild/models', '/rebuild/models/8/publish', '/rebuild/models/8/redraft',
      '/rebuild/models/8/versions', '/rebuild/models/8/versions/3/rollback',
      '/rebuild/models/8/physicalize', '/rebuild/models/reverse/scan', '/rebuild/models/reverse/import',
    ])
    expect(http.putJson.mock.calls.map(([path]) => path)).toEqual([
      '/rebuild/models/8', '/rebuild/models/8/fields', '/rebuild/models/er',
    ])
    expect(http.deleteJson.mock.calls.map(([path]) => path)).toEqual(['/rebuild/models/8'])
    expect(http.patchJson).not.toHaveBeenCalled()
    expect(http.request.mock.calls.map(([path]) => path)).toEqual(['/rebuild/models/reverse/import-ddl'])
  })

  it('forwards query, optimistic-lock rev, and payloads unchanged', async () => {
    await modelApi.list({ keyword: 'orders', status: 'draft', page: 1, size: 100 })
    expect(http.getJson.mock.calls[0][1]).toEqual({ keyword: 'orders', status: 'draft', page: 1, size: 100 })

    await modelApi.ddl(8, 'mysql')
    expect(http.getJson.mock.calls[1][1]).toEqual({ engine: 'mysql' })

    await modelApi.diffVersion(8, 3, 2)
    expect(http.getJson.mock.calls.at(-1)?.[1]).toEqual({ base: 2 })

    await modelApi.updateFields(8, { rev: 7, fields: [fieldRow] })
    expect(http.putJson.mock.calls[0][1]).toEqual({ rev: 7, fields: [fieldRow] })

    await modelApi.getEr({ layer: 'DWD', domain: '交易域' })
    expect(http.getJson.mock.calls.at(-1)?.[1]).toEqual({ layer: 'DWD', domain: '交易域' })

    await modelApi.physicalize(8, { engine: 'doris', mode: 'exec', dsId: 5, dbName: 'dw' })
    expect(http.postJson.mock.calls.at(-1)?.[1]).toEqual({ engine: 'doris', mode: 'exec', dsId: 5, dbName: 'dw' })
  })

  it('sends the DDL file as multipart body via the raw request channel', async () => {
    const file = new File(['CREATE TABLE t();'], 'schema.sql', { type: 'text/sql' })
    await modelApi.reverseImportDdl(file)
    const [path, options] = http.request.mock.calls[0]
    expect(path).toBe('/rebuild/models/reverse/import-ddl')
    expect(methodOf(http.request.mock.calls[0])).toBe('POST')
    expect(options?.body).toBeInstanceOf(FormData)
    expect((options?.body as FormData).get('file')).toBe(file)
  })
})
