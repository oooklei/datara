/**
 * dataStore 种子完整性断言（Wave 0 todo 3）
 * 验证：导出集合数 >= 40 且含核心集合、ST 字典、MENUS 五组、list/save/remove 生效。
 */
import { describe, it, expect } from 'vitest'
import { ST, MENUS, DB, dataStore } from '../mock/dataStore'
import type { DataSource } from '../types'

describe('dataStore seed (todo 3)', () => {
  it('导出集合数 >= 40 且含核心集合', () => {
    const keys = Object.keys(DB)
    expect(keys.length).toBeGreaterThanOrEqual(40)
    for (const k of ['datasources', 'syncBatches', 'qcRules', 'workflows', 'indicators', 'components']) {
      expect(keys).toContain(k)
    }
  })

  it('ST 状态字典完整', () => {
    expect(ST.draft.label).toBe('草稿')
    expect(ST.success.cls).toBe('st-green')
    expect(Object.keys(ST).length).toBeGreaterThanOrEqual(20)
  })

  it('MENUS 五组导航', () => {
    const groups = MENUS.map((m) => m.group)
    expect(groups).toContain('总览')
    expect(groups).toContain('数据集成')
    expect(groups).toContain('数据开发')
    expect(groups).toContain('数据治理')
    expect(groups).toContain('部署运维')
  })

  it('dataStore.list 返回种子行', async () => {
    const ds = await dataStore.list<DataSource>('datasources')
    expect(ds.length).toBeGreaterThanOrEqual(4)
    const wf = await dataStore.list('workflows')
    expect(wf.length).toBeGreaterThanOrEqual(1)
  })

  it('dataStore.save/remove 生效', async () => {
    const row = { id: 'T1', name: '测试源' } as unknown as DataSource
    await dataStore.save<DataSource>('datasources', row)
    const rows = await dataStore.list<DataSource>('datasources')
    expect(rows.some((r) => r.id === 'T1')).toBe(true)
    await dataStore.remove('datasources', 'T1')
    const rows2 = await dataStore.list<DataSource>('datasources')
    expect(rows2.some((r) => r.id === 'T1')).toBe(false)
  })
})