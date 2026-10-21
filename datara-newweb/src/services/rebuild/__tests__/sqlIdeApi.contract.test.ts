import { beforeEach, describe, expect, it, vi } from 'vitest'
import { R5A_CONTRACT_METHODS, createSqlIdeContract } from '../sqlIdeApi'

const fetchMock = vi.fn()

describe('R5-A sqlIdeApi route contract', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => 'test-token' })
    vi.stubGlobal('EventSource', { CONNECTING: 0, OPEN: 1, CLOSED: 2 })
  })

  it('keeps the frozen readonly method list', () => {
    expect(R5A_CONTRACT_METHODS).toHaveLength(23)
    expect(new Set(R5A_CONTRACT_METHODS).size).toBe(23)
    expect(R5A_CONTRACT_METHODS).toEqual([
      'listDatabases', 'listSchemas', 'listRelations', 'listColumns', 'listRoutines',
      'listIndexes', 'searchObjects', 'lintSql', 'executeSql', 'cancelExecution',
      'openEventStream', 'fetchResultPage', 'listHistory', 'deleteHistory', 'listScripts',
      'saveScript', 'deleteScript', 'getDefinition', 'exportResult', 'exportTable',
      'getExport', 'getExportDownloadUrl', 'cancelExport',
    ])
  })

  it('calls the project scoped database, execution and result routes with the A5 envelope', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { items: [{ name: 'analytics' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false, pageSize: 100 } } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { taskId: 'task-1' } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { stmtIndex: 0, resultSetId: 'rs-9', columns: ['value'], rows: [[1]], row_count: { kind: 'exact', value: 1 }, page: { offset: 0, limit: 50, has_more: false } } }) })
    const contract = createSqlIdeContract(23)

    await expect(contract.listDatabases(9)).resolves.toMatchObject({ items: [{ name: 'analytics' }], capability: 'supported', page: { hasMore: false } })
    await expect(contract.executeSql({ datasourceId: 9, db: 'analytics', sql: 'select 1', mode: 'auto', sessionId: 'session-1', clientRequestId: 'request-1' })).resolves.toEqual({ taskId: 'task-1' })
    await expect(contract.fetchResultPage(81, 'rs-9', 0, 50)).resolves.toMatchObject({ resultSetId: 'rs-9', rows: [[1]], rowsTotal: 1, offset: 0, limit: 50 })

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/projects/23/sql-ide/databases?datasourceId=9', 'GET'],
      ['/api/v1/projects/23/sql-ide/executions', 'POST'],
      ['/api/v1/projects/23/sql-ide/results/81?resultSetId=rs-9&offset=0&limit=50', 'GET'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ datasourceId: 9, db: 'analytics', sql: 'select 1', mode: 'auto', sessionId: 'session-1', clientRequestId: 'request-1' })
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ token: 'test-token' })
  })

  it('enforces the frozen 1..500 result-page limit and requires resultSetId', async () => {
    const contract = createSqlIdeContract(23)
    await expect(contract.fetchResultPage(81, '', 0, 50)).rejects.toThrow('resultSetId is required')
    await expect(contract.fetchResultPage(81, 'rs-9', 0, 501)).rejects.toThrow('1 to 500')
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { result_set_id: 'rs-9', row_count: { kind: 'exact', value: 1 }, rows: [[1]], page: { offset: 0, limit: 500 } } }) })
    await expect(contract.fetchResultPage(81, 'rs-9', 0, 500)).resolves.toMatchObject({ resultSetId: 'rs-9', rowsTotal: 1, limit: 500 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/projects/23/sql-ide/results/81?resultSetId=rs-9&offset=0&limit=500')
  })

  it('adapts the backend cancellation response to the readonly UI contract', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { accepted: true, status: 'canceling' } }) })

    await expect(createSqlIdeContract(23).cancelExecution('task-1')).resolves.toEqual({ canceled: true })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/projects/23/sql-ide/executions/task-1/cancel')
  })

  it('reconnects SSE with Last-Event-ID and clears the cursor after reset-required', async () => {
    const sseResponse = (frame: string) => ({
      ok: true,
      status: 200,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(frame))
          controller.close()
        },
      }),
    })
    fetchMock
      .mockResolvedValueOnce(sseResponse('id: 41\nevent: log\ndata: {"message":"ok"}\n\n'))
      .mockResolvedValueOnce(sseResponse('id: 42\nevent: reset-required\ndata: {}\n\n'))
      .mockImplementation(() => new Promise(() => undefined))

    const stream = createSqlIdeContract(23).openEventStream('task-1')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(fetchMock.mock.calls[1][1].headers).toMatchObject({ 'Last-Event-ID': '41' })
    expect(fetchMock.mock.calls[2][1].headers).not.toHaveProperty('Last-Event-ID')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin' })
    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty('token')
    stream.close()
  })

  it('passes metadata cursors explicitly and preserves the A5 capability envelope', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { items: [{ name: 'analytics' }], capability: 'conditional', constraints: ['requires read access'], page: { nextCursor: 'next-2', hasMore: true } } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { items: [{ kind: 'table', name: 'events', parent: 'public' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } } }) })
    const contract = createSqlIdeContract(23)

    await expect(contract.listDatabases(9)).resolves.toMatchObject({ capability: 'conditional', constraints: ['requires read access'], page: { nextCursor: 'next-2', hasMore: true } })
    await expect(contract.searchObjects(9, 'event', 'cursor-1')).resolves.toMatchObject({ items: [{ kind: 'table', name: 'events' }], page: { hasMore: false } })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/projects/23/sql-ide/databases?datasourceId=9',
      '/api/v1/projects/23/sql-ide/objects/search?datasourceId=9&keyword=event&cursor=cursor-1',
    ])
  })

  it('surfaces error_catalog envelopes as typed API errors', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({ code: 403, msg: 'Operation is not permitted', data: { errorCode: 'PERMISSION_DENIED', details: {} } }) })
    await expect(createSqlIdeContract(23).listDatabases(9)).rejects.toMatchObject({
      message: 'Operation is not permitted', code: 403, errorCode: 'PERMISSION_DENIED',
    })
  })

  it('uses the frozen read-only definition and export routes and keeps export TTL', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { definition: 'CREATE TABLE t (id INT)', capability: 'supported', constraints: ['read-only'] } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { exportId: 'exp-1', status: 'completed', expiresAt: '2026-10-19T10:00:00Z' } }) })
    const contract = createSqlIdeContract(23)

    await expect(contract.getDefinition({ datasourceId: 9, database: 'analytics', objectKind: 'table', objectRef: { schema: 'public', name: 'events' } })).resolves.toMatchObject({ definition: expect.stringContaining('CREATE TABLE'), capability: 'supported' })
    await expect(contract.exportResult({ historyId: 81, resultSetId: 'rs-9', format: 'xlsx' })).resolves.toMatchObject({ exportId: 'exp-1', status: 'completed', expiresAt: expect.any(String) })
    expect(contract.getExportDownloadUrl('exp-1')).toBe('/api/v1/projects/23/sql-ide/exports/exp-1/download')
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/projects/23/sql-ide/definitions', 'POST'],
      ['/api/v1/projects/23/sql-ide/exports', 'POST'],
    ])
  })

  it('normalizes lint DTO columns and sends saved script revisions as CAS expectations', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { valid: false, diagnostics: [{ stmtIndex: 2, line: 4, column: 7, severity: 'warning', code: 'W001', message: 'check' }] } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { script_id: 8, name: 'daily', sql_text: 'select 1', revision: 4, updated_at: '2026-10-19T00:00:00Z' } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: null }) })
    const contract = createSqlIdeContract(23)

    await expect(contract.lintSql(9, 'select 1')).resolves.toMatchObject([{ stmtIndex: 2, line: 4, col: 7, severity: 'warning', code: 'W001' }])
    await expect(contract.saveScript({ id: 8, name: 'daily', sqlText: 'select 1', revision: 3 })).resolves.toMatchObject({ id: 8, revision: 4 })
    await expect(contract.deleteScript(8, 4)).resolves.toBeUndefined()
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ id: 8, name: 'daily', sqlText: 'select 1', expectedRevision: 3 })
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/projects/23/sql-ide/scripts/8?expectedRevision=4')
    expect(fetchMock.mock.calls[2][1].method).toBe('DELETE')
  })
})
