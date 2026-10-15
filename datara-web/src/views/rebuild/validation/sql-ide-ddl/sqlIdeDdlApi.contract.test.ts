/**
 * R5-B DDL 契约 RED 测试（node 环境，纯契约层）。
 * 断言：4 方法统一抛 R5B_BACKEND_NOT_WIRED；确认闸语义由 UI+服务端双闸（契约层不提供绕过）。
 */
import { describe, expect, it } from 'vitest'
import { R5B_BACKEND_NOT_WIRED, R5B_CONTRACT_METHODS, createSqlIdeDdlContract } from '../../../../services/rebuild/sqlIdeDdlApi'

describe('R5-B sqlIdeDdlApi contract (RED)', () => {
  it('contract method list is frozen', () => {
    expect(R5B_CONTRACT_METHODS).toEqual(['getDefinition', 'validatePolicy', 'submitConfirm', 'listExecutionRecords'])
  })

  it('every I/O method refuses until A5 ddl wiring', async () => {
    const contract = createSqlIdeDdlContract()
    await expect(contract.getDefinition(0, 'table', null, 't')).rejects.toThrow(R5B_BACKEND_NOT_WIRED)
    await expect(contract.validatePolicy(0, 'ALTER TABLE t ADD COLUMN c INT')).rejects.toThrow(R5B_BACKEND_NOT_WIRED)
    await expect(
      contract.submitConfirm({
        datasourceId: 0,
        definition: { objectKind: 'table', schema: null, name: 't', ddlText: 'CREATE TABLE t (id INT)' },
        nextDdlText: 'ALTER TABLE t ADD COLUMN c INT',
        policyReport: { findings: [], snapshotId: null, blocked: false },
        confirmPhrase: 'user-provided-phrase',
      }),
    ).rejects.toThrow(R5B_BACKEND_NOT_WIRED)
    await expect(contract.listExecutionRecords(0)).rejects.toThrow(R5B_BACKEND_NOT_WIRED)
  })
})
