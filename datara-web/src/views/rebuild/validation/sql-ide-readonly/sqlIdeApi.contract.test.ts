/**
 * R5-A 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R5A_BACKEND_NOT_WIRED（即 A5 接入前不存在半连通状态）。
 * 组件可编译性由 `pnpm build`（vue-tsc -b）门禁保证。
 */
import { describe, expect, it } from 'vitest'
import {
  R5A_BACKEND_NOT_WIRED,
  R5A_CONTRACT_METHODS,
  createSqlIdeContract,
} from '../../../../services/rebuild/sqlIdeApi'

describe('R5-A sqlIdeApi contract (RED)', () => {
  it('contract method list is frozen to the readonly subset', () => {
    expect(R5A_CONTRACT_METHODS).toHaveLength(17)
    expect(R5A_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listDatabases',
        'listRoutines',
        'listIndexes',
        'lintSql',
        'executeSql',
        'cancelExecution',
        'openEventStream',
        'fetchResultPage',
        'listHistory',
        'listScripts',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createSqlIdeContract()
    for (const method of R5A_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until A5 backend is wired', async () => {
    const contract = createSqlIdeContract()
    const cases: Promise<unknown>[] = [
      contract.listDatabases(0),
      contract.listSchemas(0, 'db'),
      contract.listRelations(0, 'db', null, 'table'),
      contract.listColumns(0, 'db', 't', null),
      contract.listRoutines(0, 'db', null, 'procedure'),
      contract.listIndexes(0, 'db', 't'),
      contract.searchObjects(0, 'kw'),
      contract.lintSql(0, 'SELECT 1'),
      contract.executeSql({ datasourceId: 0, db: null, sql: 'SELECT 1', mode: 'auto' }),
      contract.cancelExecution('task'),
      contract.fetchResultPage(1, 0, 0, 50),
      contract.listHistory(0),
      contract.deleteHistory(1),
      contract.listScripts(),
      contract.saveScript({ name: 's', sqlText: 'SELECT 1' }),
      contract.deleteScript(1),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(R5A_BACKEND_NOT_WIRED)
    }
  })

  it('openEventStream (sync factory) refuses before A5 wiring', () => {
    const contract = createSqlIdeContract()
    expect(() => contract.openEventStream('task')).toThrow(R5A_BACKEND_NOT_WIRED)
  })
})
