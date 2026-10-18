import { beforeEach, describe, expect, it, vi } from 'vitest'
import { R5A_CONTRACT_METHODS, createSqlIdeContract } from '../../../../services/rebuild/sqlIdeApi'

const fetchMock = vi.fn()

describe('R5-A sqlIdeApi route contract', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => 'test-token' })
    vi.stubGlobal('EventSource', { CONNECTING: 0, OPEN: 1, CLOSED: 2 })
  })

  it('keeps the frozen readonly method list', () => {
    expect(R5A_CONTRACT_METHODS).toHaveLength(17)
  })

  it('calls the project scoped database, execution and result routes with the A5 envelope', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: [{ name: 'analytics' }] }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { taskId: 'task-1' } }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data: { stmtIndex: 0, columns: ['value'], rows: [[1]], rowsTotal: 1, offset: 0, limit: 50 } }) })
    const contract = createSqlIdeContract(23)

    await expect(contract.listDatabases(9)).resolves.toEqual([{ name: 'analytics' }])
    await expect(contract.executeSql({ datasourceId: 9, db: 'analytics', sql: 'select 1', mode: 'auto', sessionId: 'session-1', clientRequestId: 'request-1' })).resolves.toEqual({ taskId: 'task-1' })
    await expect(contract.fetchResultPage(81, 0, 0, 50)).resolves.toMatchObject({ rows: [[1]], rowsTotal: 1 })

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/projects/23/sql-ide/databases?datasourceId=9', 'GET'],
      ['/api/v1/projects/23/sql-ide/executions', 'POST'],
      ['/api/v1/projects/23/sql-ide/results/81?stmtIndex=0&offset=0&limit=50', 'GET'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ datasourceId: 9, db: 'analytics', sql: 'select 1', mode: 'auto', sessionId: 'session-1', clientRequestId: 'request-1' })
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ token: 'test-token' })
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
    stream.close()
  })

  it('surfaces error_catalog envelopes as typed API errors', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({ code: 403, msg: 'Operation is not permitted', data: { errorCode: 'PERMISSION_DENIED', details: {} } }) })
    await expect(createSqlIdeContract(23).listDatabases(9)).rejects.toMatchObject({
      message: 'Operation is not permitted', code: 403, errorCode: 'PERMISSION_DENIED',
    })
  })
})
