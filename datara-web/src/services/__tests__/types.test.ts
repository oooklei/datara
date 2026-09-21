/**
 * 服务契约层类型断言（Wave 0 todo 2）
 * 验证：嵌套形状可寻址（datasources[].pool.max / qcRules[].linkTask / streamJobs[].checkpoint.mode）、
 * CollectionKey 覆盖核心集合、IDataStore 签名可用。
 */
import { describe, it, expect, expectTypeOf } from 'vitest'
import type {
  DataSource,
  QcRule,
  StreamJob,
  CollectionKey,
  IDataStore,
  SyncBatch,
  Indicator,
  WorkflowMeta,
  Component,
} from '../types'

describe('types contract (todo 2)', () => {
  it('datasources[].pool.max 可寻址且为 number', () => {
    expectTypeOf<DataSource['pool']['max']>().toBeNumber()
  })

  it('qcRules[].linkTask 可寻址且为 string', () => {
    expectTypeOf<QcRule['linkTask']>().toBeString()
  })

  it('streamJobs[].checkpoint.mode 可寻址且为 string', () => {
    expectTypeOf<StreamJob['checkpoint']['mode']>().toBeString()
  })

  it('核心集合类型可寻址（syncBatches[].logs / indicators[].versions / workflows[].nodesDetail / components[].nodes）', () => {
    expectTypeOf<SyncBatch['logs'][number]['status']>().toBeString()
    expectTypeOf<Indicator['versions'][number]['v']>().toBeNumber()
    expectTypeOf<WorkflowMeta['nodesDetail'][number]['dep']>().toEqualTypeOf<string[]>()
    expectTypeOf<Component['nodes']>().toEqualTypeOf<string[]>()
  })

  it('CollectionKey 覆盖核心集合名', () => {
    const keys: CollectionKey[] = [
      'datasources', 'syncBatches', 'qcRules', 'workflows', 'indicators', 'components',
    ]
    expect(keys).toHaveLength(6)
  })

  it('IDataStore 签名可用（get/list/save/remove 全部 async）', async () => {
    const store: IDataStore = {
      async get(col) {
        void col
        return null
      },
      async list(col) {
        void col
        return []
      },
      async save(col, row) {
        void col
        void row
      },
      async remove(col, id) {
        void col
        void id
      },
    }
    const r = await store.get<DataSource>('datasources')
    expect(r).toBeNull()
  })
})