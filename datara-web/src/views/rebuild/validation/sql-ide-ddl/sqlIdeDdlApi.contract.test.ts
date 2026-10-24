/**
 * R5-B DDL 契约 GREEN 测试（node 环境，HTTP 适配层）。
 * 断言：五个方法均发出冻结端点请求；确认闸语义由 UI+服务端双闸。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { R5B_CONTRACT_METHODS, createSqlIdeDdlContract } from '../../../../services/rebuild/sqlIdeDdlApi'

describe('R5-B sqlIdeDdlApi contract (GREEN)', () => {
  afterEach(() => vi.restoreAllMocks())
  it('contract method list is frozen', () => {
    expect(R5B_CONTRACT_METHODS).toEqual([
      'getDefinition',
      'validatePolicy',
      'previewImpact',
      'submitConfirm',
      'listExecutionRecords',
    ])
  })

  it('every I/O method uses the wired backend contract', async () => {
    const calls: Array<{ url: string; body?: unknown }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      const payload = url.includes('validate-policy')
        ? { snapshotId: 'p-1', findings: [], blocked: false }
        : url.includes('preview-impact')
          ? { snapshotId: 'i-1', impacts: [], unknownReasons: [] }
          : url.includes('execution-records')
            ? { items: [] }
            : url.includes('/confirm')
              ? { recordId: 1, status: 'success' }
              : { definitionText: 'CREATE TABLE t (id INT)', sourceVersion: 'v1', capability: 'read', constraints: [] }
      return new Response(JSON.stringify({ code: 0, msg: 'success', data: payload }), { status: 200, headers: { 'content-type': 'application/json' } })
    })
    const contract = createSqlIdeDdlContract()
    await expect(contract.getDefinition(0, 'table', null, 't')).resolves.toMatchObject({ ddlText: expect.stringContaining('CREATE TABLE') })
    await expect(contract.validatePolicy(0, 'ALTER TABLE t ADD COLUMN c INT')).resolves.toMatchObject({ snapshotId: 'p-1' })
    await expect(contract.previewImpact(0, 'ALTER TABLE t ADD COLUMN c INT')).resolves.toEqual([])
    await expect(contract.submitConfirm({ datasourceId: 0, definition: { objectKind: 'table', schema: null, name: 't', ddlText: 'CREATE TABLE t (id INT)' }, nextDdlText: 'ALTER TABLE t ADD COLUMN c INT', policyReport: { findings: [], snapshotId: 'p-1', blocked: false }, confirmPhrase: 'user-provided-phrase' })).resolves.toMatchObject({ recordId: 1 })
    await expect(contract.listExecutionRecords(0)).resolves.toEqual([])
    expect(calls.map((item) => item.url)).toEqual(expect.arrayContaining([
      '/api/v1/projects/1/sql-ide/definitions', '/api/v1/rebuild/sql-ide-ddl/validate-policy', '/api/v1/rebuild/sql-ide-ddl/preview-impact', '/api/v1/rebuild/sql-ide-ddl/confirm', '/api/v1/rebuild/sql-ide-ddl/execution-records',
    ]))
  })
})
