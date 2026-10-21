import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  R5B_CONTRACT_METHODS,
  R5B_PERMISSION_MATRIX,
  createSqlIdeDdlContract,
} from '../sqlIdeDdlApi'

const fetchMock = vi.fn()

const OBJECT_REF = { datasourceId: 9, database: 'analytics', kind: 'table' as const, name: 'users' }

const VALIDATION_REQUEST = {
  datasourceId: 9,
  objectRef: OBJECT_REF,
  sourceVersion: 'v-20261021-01',
  nextDdlText: 'ALTER TABLE users ADD COLUMN nickname varchar(64)',
}

const CONFIRM_REQUEST = {
  ...VALIDATION_REQUEST,
  policySnapshotId: 'snap-policy-1',
  impactSnapshotId: 'snap-impact-1',
  confirmPhrase: 'CONFIRM-ALTER-TABLE-users-20261021',
}

function okEnvelope(data: unknown) {
  return { ok: true, status: 200, json: async () => ({ code: 0, msg: 'success', data }) }
}

function errorEnvelope(status: number, code: number, msg: string, errorCode: string) {
  return { ok: false, status, json: async () => ({ code, msg, data: { errorCode, details: {} } }) }
}

describe('R5-B sqlIdeDdlApi route contract', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => 'test-token' })
  })

  it('contract method list and permission matrix are frozen', () => {
    expect(R5B_CONTRACT_METHODS).toEqual(['getDefinition', 'validatePolicy', 'previewImpact', 'submitConfirm', 'listExecutionRecords'])
    expect(Object.keys(R5B_PERMISSION_MATRIX)).toEqual(['getDefinition', 'validatePolicy', 'previewImpact', 'submitConfirm', 'listExecutionRecords'])
    expect(R5B_PERMISSION_MATRIX).toMatchObject({
      getDefinition: 'VIEW_ALL',
      validatePolicy: 'EDIT_DEFINITION',
      previewImpact: 'VIEW_ALL',
      submitConfirm: 'EDIT_DEFINITION',
      listExecutionRecords: 'VIEW_ALL',
    })
  })

  it('getDefinition posts to R5-A definitions route and normalizes snake keys', async () => {
    fetchMock.mockResolvedValueOnce(okEnvelope({
      object_ref: { datasource_id: 9, database: 'analytics', kind: 'table', name: 'users' },
      definition_text: 'CREATE TABLE users (id bigint)',
      sourceVersion: 'v-20261021-01',
      capability: 'ddl',
      constraints: ['forbid-drop'],
    }))

    const snapshot = await createSqlIdeDdlContract(7).getDefinition(9, OBJECT_REF)

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/projects/7/sql-ide/definitions', 'POST'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      datasourceId: 9,
      database: 'analytics',
      objectKind: 'table',
      objectRef: OBJECT_REF,
    })
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ token: 'test-token' })
    expect(snapshot).toMatchObject({
      objectRef: { datasourceId: 9, database: 'analytics', kind: 'table', name: 'users' },
      definition: 'CREATE TABLE users (id bigint)',
      sourceVersion: 'v-20261021-01',
      capability: 'ddl',
      constraints: ['forbid-drop'],
    })
  })

  it('getDefinition fails closed when sourceVersion is missing', async () => {
    fetchMock.mockResolvedValueOnce(okEnvelope({
      definition_text: 'CREATE TABLE users (id bigint)',
      capability: 'ddl',
      constraints: [],
    }))

    await expect(createSqlIdeDdlContract(7).getDefinition(9, OBJECT_REF)).rejects.toMatchObject({
      code: 502,
      errorCode: 'SOURCE_VERSION_UNAVAILABLE',
    })
  })

  it('validatePolicy posts camel body and normalizes snapshot_id', async () => {
    fetchMock.mockResolvedValueOnce(okEnvelope({
      snapshot_id: 'snap-policy-1',
      findings: [{ level: 'block', code: 'RB-DROP-TABLE', message: 'drop table is blocked', impacts: ['view v_user'] }],
      blocked: true,
    }))

    const report = await createSqlIdeDdlContract(7).validatePolicy(VALIDATION_REQUEST)

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/rebuild/sql-ide-ddl/validate-policy', 'POST'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(VALIDATION_REQUEST)
    expect(report).toMatchObject({
      snapshotId: 'snap-policy-1',
      blocked: true,
      findings: [{ level: 'block', code: 'RB-DROP-TABLE', message: 'drop table is blocked', impacts: ['view v_user'] }],
    })
  })

  it('previewImpact normalizes nested objectRef.datasource_id and unknown_reasons', async () => {
    fetchMock.mockResolvedValueOnce(okEnvelope({
      snapshot_id: 'snap-impact-1',
      impacts: [
        { objectRef: { datasource_id: 9, database: 'analytics', kind: 'view', name: 'v_user' }, relation_type: 'dependent', detail: 'view v_user depends on users' },
      ],
      unknown_reasons: ['lineage missing for db2'],
    }))

    const report = await createSqlIdeDdlContract(7).previewImpact(VALIDATION_REQUEST)

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/rebuild/sql-ide-ddl/preview-impact', 'POST'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(VALIDATION_REQUEST)
    expect(report.impacts).toHaveLength(1)
    expect(report.impacts[0]).toMatchObject({
      objectRef: { datasourceId: 9, database: 'analytics', kind: 'view', name: 'v_user' },
      relationType: 'dependent',
      detail: 'view v_user depends on users',
    })
    expect(report.unknownReasons).toEqual(['lineage missing for db2'])
  })

  it('submitConfirm refuses blank confirm phrase without any request (A7)', async () => {
    await expect(createSqlIdeDdlContract(7).submitConfirm({ ...CONFIRM_REQUEST, confirmPhrase: '   ' })).rejects.toMatchObject({
      code: 400,
      errorCode: 'CONFIRM_PHRASE_INVALID',
    })
    await expect(createSqlIdeDdlContract(7).submitConfirm({ ...CONFIRM_REQUEST, confirmPhrase: '' })).rejects.toMatchObject({
      code: 400,
      errorCode: 'CONFIRM_PHRASE_INVALID',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submitConfirm posts confirm phrase verbatim and returns outcome', async () => {
    fetchMock.mockResolvedValueOnce(okEnvelope({ recordId: 'rec-1', status: 'success' }))

    const outcome = await createSqlIdeDdlContract(7).submitConfirm(CONFIRM_REQUEST)

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/rebuild/sql-ide-ddl/confirm', 'POST'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(CONFIRM_REQUEST)
    expect(outcome).toEqual({ recordId: 'rec-1', status: 'success' })
  })

  it('listExecutionRecords defaults page/pageSize and normalizes record keys', async () => {
    fetchMock.mockResolvedValueOnce(okEnvelope({
      items: [
        { record_id: 'rec-1', actor_id: 3, action: 'APPLY', script_hash: 'sha256:abc', executed_at: '2026-10-21T10:00:00+08:00', status: 'success', failure_summary: null },
      ],
      page: { next_cursor: 'cur-2', has_more: true },
    }))

    const result = await createSqlIdeDdlContract(7).listExecutionRecords({ datasourceId: 9 })

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/rebuild/sql-ide-ddl/execution-records', 'POST'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ datasourceId: 9, page: 1, pageSize: 50 })
    expect(result.items).toHaveLength(1)
    expect(result.items[0]).toMatchObject({
      recordId: 'rec-1',
      actorId: 3,
      action: 'APPLY',
      scriptHash: 'sha256:abc',
      executedAt: '2026-10-21T10:00:00+08:00',
      status: 'success',
      failureSummary: null,
    })
    expect(result.page).toEqual({ nextCursor: 'cur-2', hasMore: true })
  })

  it('listExecutionRecords forwards 502 CAPABILITY_UNSUPPORTED as typed error', async () => {
    fetchMock.mockResolvedValueOnce(errorEnvelope(502, 502, 'capability unsupported', 'CAPABILITY_UNSUPPORTED'))

    await expect(createSqlIdeDdlContract(7).listExecutionRecords({ datasourceId: 9 })).rejects.toMatchObject({
      code: 502,
      errorCode: 'CAPABILITY_UNSUPPORTED',
    })
  })

  it('listExecutionRecords guards pagination bounds before any request', async () => {
    await expect(createSqlIdeDdlContract(7).listExecutionRecords({ datasourceId: 9, page: 0 })).rejects.toThrow(RangeError)
    await expect(createSqlIdeDdlContract(7).listExecutionRecords({ datasourceId: 9, page: 1.5 })).rejects.toThrow(RangeError)
    await expect(createSqlIdeDdlContract(7).listExecutionRecords({ datasourceId: 9, pageSize: 201 })).rejects.toThrow(RangeError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('maps 409 POLICY_BLOCKED and 422 LINEAGE_UNKNOWN envelopes to typed errors', async () => {
    fetchMock
      .mockResolvedValueOnce(errorEnvelope(409, 409, 'policy blocked the ddl', 'POLICY_BLOCKED'))
      .mockResolvedValueOnce(errorEnvelope(422, 422, 'lineage unknown', 'LINEAGE_UNKNOWN'))

    await expect(createSqlIdeDdlContract(7).validatePolicy(VALIDATION_REQUEST)).rejects.toMatchObject({
      code: 409,
      errorCode: 'POLICY_BLOCKED',
    })
    await expect(createSqlIdeDdlContract(7).previewImpact(VALIDATION_REQUEST)).rejects.toMatchObject({
      code: 422,
      errorCode: 'LINEAGE_UNKNOWN',
    })
  })
})
