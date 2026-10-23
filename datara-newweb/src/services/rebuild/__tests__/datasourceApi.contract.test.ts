import { describe, expect, it, vi } from 'vitest'

import { ContractApiError } from '../adapterKit'
import {
  DATASOURCE_CONTRACT_METHODS,
  DATASOURCE_ERROR_CODES,
  DATASOURCE_PERMISSION_MATRIX,
  createDatasourceContract,
  type DatasourceDraft,
  type DatasourceRecord,
} from '../datasourceApi'

type RecordedCall = { url: string; init?: RequestInit }

const draft: DatasourceDraft = {
  name: 'orders', kind: 'mysql', host: 'mysql', port: 3306,
  database: 'warehouse', username: 'reader', password: 'secret',
}

const recordWire = {
  id: 9, project_id: 7, name: 'orders', kind: 'mysql', host: 'mysql', port: 3306,
  database: 'warehouse', username: 'reader', created_at: '2026-10-21T12:00:00', updated_at: '2026-10-21T12:01:00',
}

function installFetch(dataFor: (url: string, init?: RequestInit) => unknown): RecordedCall[] {
  const calls: RecordedCall[] = []
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    return new Response(JSON.stringify({ code: 0, msg: 'success', data: dataFor(url, init) }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch
  return calls
}

describe('10A rebuild datasource contract registry (R-47)', () => {
  it('freezes all 11 methods and their permission matrix', () => {
    expect(DATASOURCE_CONTRACT_METHODS).toHaveLength(11)
    expect(Object.keys(createDatasourceContract(7))).toEqual([...DATASOURCE_CONTRACT_METHODS])
    expect(DATASOURCE_PERMISSION_MATRIX).toEqual({
      validateDraft: 'authenticated', probeProfile: 'admin', listDatasources: 'VIEW_ALL',
      createDatasource: 'EDIT_DEFINITION', getDatasource: 'VIEW_ALL', updateDatasource: 'EDIT_DEFINITION',
      deleteDatasource: 'EDIT_DEFINITION', testDatasource: 'EDIT_DEFINITION', listSchemas: 'VIEW_ALL',
      listObjects: 'VIEW_ALL', listColumns: 'VIEW_ALL',
    })
  })

  it('maps all 11 methods to the rebuild routes with project-scoped CRUD and metadata paths', async () => {
    const calls = installFetch((url) => {
      if (url.endsWith('/validate')) return { name: 'orders', kind: 'mysql', capabilities: ['metadata'] }
      if (url.endsWith('/probe') || url.endsWith('/test')) return { connected: true, database: 'warehouse', server_version: '8', capabilities: ['metadata'] }
      if (url.endsWith('/schemas')) return { items: ['warehouse'], next_after: null, limit: 100 }
      if (url.includes('/objects?')) return { items: [{ schema: 'warehouse', name: 'orders', type: 'table' }], next_after: null, limit: 100 }
      if (url.includes('/columns?')) return { items: [{ schema: 'warehouse', object: 'orders', name: 'id', data_type: 'int', database_type: 'int', nullable: false, primary_key: true, comment: '' }], next_after: null, limit: 200 }
      if (url.endsWith('/datasources')) return { items: [recordWire] }
      if ((url.endsWith('/9') && calls.length === 7)) return { deleted: true, id: 9 }
      return recordWire
    })
    const api = createDatasourceContract(7)
    await api.validateDraft(draft)
    await api.probeProfile('mysql-src')
    await api.listDatasources()
    await api.createDatasource(draft)
    await api.getDatasource(9)
    await api.updateDatasource(9, draft)
    await api.deleteDatasource(9)
    await api.testDatasource(9)
    await api.listSchemas(9)
    await api.listObjects(9, 'warehouse')
    await api.listColumns(9, 'warehouse', 'orders')

    expect(calls.map(({ url, init }) => [url, init?.method])).toEqual([
      ['/api/v1/rebuild/datasources/validate', 'POST'],
      ['/api/v1/rebuild/datasources/profiles/mysql-src/probe', 'POST'],
      ['/api/v1/rebuild/projects/7/datasources', 'GET'],
      ['/api/v1/rebuild/projects/7/datasources', 'POST'],
      ['/api/v1/rebuild/projects/7/datasources/9', 'GET'],
      ['/api/v1/rebuild/projects/7/datasources/9', 'PUT'],
      ['/api/v1/rebuild/projects/7/datasources/9', 'DELETE'],
      ['/api/v1/rebuild/projects/7/datasources/9/test', 'POST'],
      ['/api/v1/rebuild/projects/7/datasources/9/schemas?limit=100', 'GET'],
      ['/api/v1/rebuild/projects/7/datasources/9/objects?schema=warehouse&limit=100', 'GET'],
      ['/api/v1/rebuild/projects/7/datasources/9/columns?schema=warehouse&object_name=orders&limit=200', 'GET'],
    ])
    expect(calls.every(({ url }) => !url.startsWith('/api/v1/datasources'))).toBe(true)
  })

  it('sends credentials only in write bodies and never exposes password on response records', async () => {
    const calls = installFetch(() => recordWire)
    const result = await createDatasourceContract(7).createDatasource(draft)
    expect(JSON.parse(String(calls[0].init?.body))).toEqual(draft)
    expect(result).toEqual({
      id: 9, projectId: 7, name: 'orders', kind: 'mysql', host: 'mysql', port: 3306,
      database: 'warehouse', username: 'reader', createdAt: recordWire.created_at, updatedAt: recordWire.updated_at,
    })
    expect('password' in result).toBe(false)
    const keys = ['id', 'projectId', 'name', 'kind', 'host', 'port', 'database', 'username', 'createdAt', 'updatedAt'] as const satisfies readonly (keyof DatasourceRecord)[]
    expect(Object.keys(result).sort()).toEqual([...keys].sort())
  })

  it('preserves stable backend error codes for UI handling', async () => {
    globalThis.fetch = vi.fn(async () => new Response(
      JSON.stringify({ code: 4042, msg: 'datasource not found', data: null }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    )) as typeof fetch
    const error = await createDatasourceContract(7).getDatasource(404).catch((caught) => caught)
    expect(error).toBeInstanceOf(ContractApiError)
    expect(error).toMatchObject({ httpStatus: 404, code: DATASOURCE_ERROR_CODES.datasourceNotFound })
    expect(DATASOURCE_ERROR_CODES).toEqual({
      invalidToken: 1001, permissionDenied: 1003, invalidInput: 4001, registerBeforeTest: 4002,
      projectNotFound: 4041, datasourceNotFound: 4042, duplicateName: 4091,
      connectionFailed: 5021, metadataBrowseFailed: 5022, profileUnavailable: 5031,
    })
  })
})
