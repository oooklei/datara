/**
 * R4-SYNC 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R4_SYNC_NOT_WIRED（后端接入前不存在半连通状态）、
 * 本地初始映射建议纯函数行为。组件可编译性由 `pnpm build` 门禁保证。
 * 语义源：docs/increments/R4-SYNC-API-contract-pending.md（Codex 草案）。
 */
import { describe, expect, it } from 'vitest'
import {
  R4_SYNC_CONTRACT_METHODS,
  R4_SYNC_NOT_WIRED,
  createSyncComponentContract,
  suggestInitialMapping,
  type SyncColumn,
} from '../../../../services/rebuild/syncComponentApi'

const probeRequest = {
  projectId: 1,
  mode: 'source_table' as const,
  source: { datasourceId: 1, schema: 'public', table: 'orders' },
}

const columns: SyncColumn[] = [
  { ordinal: 1, name: 'id', type: 'bigint', nullable: false },
  { ordinal: 2, name: 'Name', type: 'varchar', nullable: true, precision: 64 },
]

describe('R4 syncComponentApi contract (RED)', () => {
  it('contract method list is frozen to the sync plan/run subset', () => {
    expect(R4_SYNC_CONTRACT_METHODS).toHaveLength(11)
    expect(R4_SYNC_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'getCapabilities',
        'probe',
        'savePlan',
        'getPlan',
        'previewPlan',
        'runPlan',
        'getRun',
        'getAttempt',
        'cancelRun',
        'getCheckpoint',
        'resumeRun',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createSyncComponentContract()
    for (const method of R4_SYNC_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until sync backend is wired', async () => {
    const contract = createSyncComponentContract()
    const cases: Promise<unknown>[] = [
      contract.getCapabilities(1),
      contract.probe(probeRequest),
      contract.savePlan({
        projectId: 1,
        mode: 'source_table',
        source: probeRequest.source,
        target: probeRequest.source,
        strategy: 'full',
        writeMode: 'append',
        targetPolicy: 'existing_only',
        mapping: [],
      }),
      contract.getPlan(1, 1),
      contract.previewPlan(1, 1, 'digest', 1),
      contract.runPlan({ projectId: 1, planId: 1, planVersion: 1, planDigest: 'digest', idempotencyKey: 'k1' }),
      contract.getRun(1, 1),
      contract.getAttempt(1, 1, 1),
      contract.cancelRun(1, 1),
      contract.getCheckpoint(1, 1),
      contract.resumeRun(1, 1, { idempotencyKey: 'k2', checkpointRef: 'ck' }),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(R4_SYNC_NOT_WIRED)
    }
  })

  it('suggestInitialMapping matches source columns case-insensitively by name', () => {
    const target: SyncColumn[] = [
      { ordinal: 1, name: 'ID', type: 'bigint', nullable: false },
      { ordinal: 2, name: 'name', type: 'varchar', nullable: true },
      { ordinal: 3, name: 'extra', type: 'int', nullable: true },
    ]
    const mapping = suggestInitialMapping(columns, target)
    expect(mapping).toHaveLength(3)
    expect(mapping[0]).toMatchObject({ targetOrdinal: 1, operation: 'map', sourceColumn: 'id', targetColumn: 'ID' })
    expect(mapping[1]).toMatchObject({ targetOrdinal: 2, operation: 'map', sourceColumn: 'Name', targetColumn: 'name' })
    // 无同名源列时建议仍生成（sourceColumn 为空），由用户调整
    expect(mapping[2]).toMatchObject({ targetOrdinal: 3, operation: 'map', sourceColumn: undefined, targetColumn: 'extra' })
  })
})
