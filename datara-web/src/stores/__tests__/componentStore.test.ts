/**
 * componentStore 单测（工作台优化 Task 4，方案 §2.3）。
 *
 * 被测契约：
 * - ensureSpecs：规格骨架拉取 → 8 要素骨架展平 → normalizeSpec 归一化入 specMap；
 *   ETag 304 沿用缓存；服务异常 degraded=true 走 profile 兜底，loaded=false 时下次自动重试；
 *   loading 并发去重。
 * - setupComponentStoreBus：component:published / rolled-back / offline 三事件 → force 重拉。
 * - fetchComponentSpec 以 vi.mock 替身注入（真实实现为独立 fetch，不落 http 统一包解包）。
 *
 * mock 返回的 item 采用后端 _spec_item 的**真实骨架形态**
 * （权威源 datara-backend/api/component_spec.py：缺失要素显式 null 而非缺键）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { useComponentStore, setupComponentStoreBus } from '../componentStore'
import { fetchComponentSpec, type ComponentSpecResult } from '../../services/componentApi'
import { bus } from '../../services/eventBus'

vi.mock('../../services/componentApi', () => ({
  fetchComponentSpec: vi.fn(),
}))

const mockedFetch = vi.mocked(fetchComponentSpec)

/** 后端 8 要素骨架样例（与 _spec_item 逐键对齐；None 显式携带） */
function specItem(type: string, name: string) {
  return {
    type,
    identity: { type, displayName: name, aliases: [`${type}-alias`] },
    description: { summary: `${name}摘要`, description: null, category: '数据同步', docUrl: null },
    inputs: [
      { key: 'sql', label: 'SQL 语句', uiType: 'text', required: true, default: '', desc: '待执行 SQL' },
    ],
    outputs: [{ name: 'rows', type: 'any', desc: '结果集' }],
    visual: { icon: '🗄️', color: '#409eff', shape: 'default', badge: null },
    behaviors: null,
    dropPolicy: {
      snapToGrid: true,
      autoName: '{type}-{n}',
      prefillFromUpstream: [],
      autoConnect: { upstream: 'nearest', downstream: 'nearest' },
      maxInstances: 0,
    },
    extensions: null,
    specVersion: '2.0',
    ports: { inputs: [{ name: 'in', type: 'any' }], outputs: [{ name: 'out', type: 'any' }] },
  }
}

const ETAG = '"a1b2c3d4"'

beforeEach(() => {
  setActivePinia(createPinia())
  mockedFetch.mockReset()
})

describe('ensureSpecs 拉取与缓存', () => {
  it('首次拉取：骨架展平归一化入 specMap，loaded=true、degraded=false、记录 etag', async () => {
    mockedFetch.mockResolvedValue({ etag: ETAG, items: [specItem('sql_exec', 'SQL 执行')] })
    const s = useComponentStore()
    await s.ensureSpecs()
    const spec = s.specMap.get('sql_exec')
    expect(spec).toBeDefined()
    expect(spec?.summary).toBe('SQL 执行摘要')       // description.summary → summary
    expect(spec?.icon).toBe('🗄️')                   // visual.icon → icon
    expect(spec?.displayName).toBe('SQL 执行')       // identity.displayName → displayName
    expect(spec?.aliases).toEqual(['sql_exec-alias']) // identity.aliases → aliases
    expect(spec?.fields).toHaveLength(1)              // inputs → fields
    expect(spec?.fields[0]?.key).toBe('sql')
    expect(spec?.outputs).toEqual([{ name: 'rows', type: 'any', desc: '结果集' }])
    expect(spec?.specVersion).toBe('2.0')
    expect(s.etag).toBe(ETAG)
    expect(s.loaded).toBe(true)
    expect(s.degraded).toBe(false)
    expect(mockedFetch).toHaveBeenCalledWith(undefined) // 无 etag → 不带 If-None-Match
  })

  it('304：沿用现有缓存（specMap 不清空、etag 不变），loaded/degraded 正常', async () => {
    mockedFetch
      .mockResolvedValueOnce({ etag: ETAG, items: [specItem('sql_exec', 'SQL 执行')] })
      .mockResolvedValueOnce(null) // 304 无 body
    const s = useComponentStore()
    await s.ensureSpecs()
    await s.ensureSpecs(true) // loaded 后须 force 才会真正重拉（模拟失效广播）
    expect(mockedFetch).toHaveBeenCalledTimes(2)
    expect(mockedFetch).toHaveBeenLastCalledWith(ETAG) // 条件请求携带已存 etag
    expect(s.specMap.get('sql_exec')).toBeDefined()    // 304 → 缓存沿用，未重建
    expect(s.etag).toBe(ETAG)
    expect(s.loaded).toBe(true)
    expect(s.degraded).toBe(false)
  })

  it('loading 并发去重：进行中重复调用不再发请求', async () => {
    let resolveFetch!: (v: ComponentSpecResult | null) => void
    mockedFetch.mockImplementation(() => new Promise<ComponentSpecResult | null>((resolve) => { resolveFetch = resolve }))
    const s = useComponentStore()
    const p1 = s.ensureSpecs()
    const p2 = s.ensureSpecs()
    resolveFetch({ etag: ETAG, items: [] })
    await Promise.all([p1, p2])
    expect(mockedFetch).toHaveBeenCalledTimes(1)
  })
})

describe('异常降级（profile 兜底路径）', () => {
  it('服务异常 → degraded=true、loaded 保持 false；恢复后下次调用自动重试', async () => {
    mockedFetch
      .mockRejectedValueOnce(new Error('网络不可达'))
      .mockResolvedValueOnce({ etag: ETAG, items: [specItem('sql_exec', 'SQL 执行')] })
    const s = useComponentStore()
    await s.ensureSpecs()
    expect(s.degraded).toBe(true)
    expect(s.loaded).toBe(false) // 失败不计入 loaded → 下次不短路
    expect(s.specMap.size).toBe(0)
    await s.ensureSpecs()
    expect(s.degraded).toBe(false)
    expect(s.loaded).toBe(true)
    expect(s.specMap.get('sql_exec')).toBeDefined()
  })
})

describe('审查修复回归（失败保留缓存 / pendingForce 补拉）', () => {
  it('已加载后 force 重拉失败 → degraded=true，旧缓存沿用、loaded 仍 true', async () => {
    mockedFetch
      .mockResolvedValueOnce({ etag: ETAG, items: [specItem('sql_exec', 'SQL 执行')] })
      .mockRejectedValueOnce(new Error('网络不可达'))
    const s = useComponentStore()
    await s.ensureSpecs()
    await s.ensureSpecs(true)
    expect(s.degraded).toBe(true)
    expect(s.loaded).toBe(true)                     // 失败不清 loaded → 旧缓存继续可用
    expect(s.specMap.get('sql_exec')).toBeDefined() // 旧规格沿用
    expect(s.etag).toBe(ETAG)
  })

  it('loading 中的 invalidate 不被吞：pendingForce 记账，首请求落地后自动补拉最新清单', async () => {
    let resolveFetch!: (v: ComponentSpecResult | null) => void
    mockedFetch
      .mockImplementationOnce(() => new Promise<ComponentSpecResult | null>((resolve) => { resolveFetch = resolve }))
      .mockResolvedValueOnce({ etag: '"ef01"', items: [specItem('sql_exec2', 'SQL 执行 V2')] })
    const s = useComponentStore()
    const p1 = s.ensureSpecs() // 请求 #1 在飞（不 await）
    await s.invalidate()       // 被 loading 拦截 → pendingForce 记账，立即返回
    expect(mockedFetch).toHaveBeenCalledTimes(1) // 补拉未提前发出
    resolveFetch({ etag: ETAG, items: [specItem('sql_exec', 'SQL 执行')] })
    await p1                   // 实现：finally 内联补拉 → p1 在补拉完成后才 resolve
    expect(mockedFetch).toHaveBeenCalledTimes(2)
    expect(mockedFetch).toHaveBeenLastCalledWith(ETAG) // 补拉条件请求携带首请求落地的 etag
    expect(s.specMap.get('sql_exec2')).toBeDefined()   // 补拉以最新清单覆盖缓存
    expect(s.etag).toBe('"ef01"')
    expect(s.loaded).toBe(true)
    expect(s.degraded).toBe(false)
  })
})

describe('失效广播（setupComponentStoreBus）', () => {
  it('published / rolled-back / offline 三事件均触发 force 重拉', async () => {
    mockedFetch.mockResolvedValue({ etag: ETAG, items: [specItem('sql_exec', 'SQL 执行')] })
    const s = useComponentStore()
    await s.ensureSpecs()
    expect(mockedFetch).toHaveBeenCalledTimes(1)
    setupComponentStoreBus()
    bus.emit('component:published')
    await flushPromises()
    expect(mockedFetch).toHaveBeenCalledTimes(2)
    bus.emit('component:rolled-back')
    await flushPromises()
    expect(mockedFetch).toHaveBeenCalledTimes(3)
    bus.emit('component:offline')
    await flushPromises()
    expect(mockedFetch).toHaveBeenCalledTimes(4)
    // 广播重拉为条件请求（携带已存 etag）
    expect(mockedFetch).toHaveBeenLastCalledWith(ETAG)
  })
})
