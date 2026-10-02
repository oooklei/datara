import { describe, expect, it } from 'vitest'
import { candidatesFor, resolveFallback } from '../bindingCatalog'
import type { ResourceCatalog } from '../bindingCatalog'

const cat: ResourceCatalog = {
  datasources: [{ id: 1, name: '主库', type: 'mysql', db: 'sales' }],
  workflows: [{ code: 100, name: '日批', vars: [{ path: '$wf.batch', label: 'batch', type: '文本' }] }],
  globalParams: [{ path: '$param.env', label: 'env' }],
  timeParams: [{ path: '$system.date', label: '当前日期', sample: '2026-10-03' }],
  components: [],
}

describe('bindingCatalog', () => {
  it('标量槽候选 = 变量+参数+时间参数（+组件可忽略）', () => {
    const c = candidatesFor('scalar', cat)
    expect(c.some((x) => x.value === '$wf.batch')).toBe(true)
    expect(c.some((x) => x.value === '$system.date')).toBe(true)
  })
  it('dataset 槽候选 = 数据源表入口', () => {
    expect(candidatesFor('dataset', cat)[0].value).toBe('ds:1')
  })
  it('resolveFallback：空输入落 placeholder 默认值', () => {
    expect(resolveFallback('请输入名称', '')).toBe('请输入名称')
    expect(resolveFallback('请输入名称', '实际值')).toBe('实际值')
  })
})
