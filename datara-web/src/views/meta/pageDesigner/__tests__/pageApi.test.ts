/**
 * pageApi 契约测试（Task 9 · mock 模式）：
 * isMock 在 apiMode.ts 模块作用域求值 → 沿用 mockApi.test.ts 的
 * stubEnv + resetModules + 动态 import 方案，让三个方法真实走 mock 分支。
 * 守护断言：mock 模式下一次 fetch 都不能发（防止 mock 失效直连真实后端）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok', setItem: vi.fn(), removeItem: vi.fn() })
})

/** 在 mock 模式下重新加载模块图（isMock 随模块求值，需 resetModules） */
async function loadMockMode() {
  vi.stubEnv('VITE_API_MODE', 'mock')
  vi.resetModules()
  return (await import('../pageApi')).pageApi
}

describe('pageApi (mock 模式)', () => {
  it('getResources 返回五键且不发真实请求', async () => {
    const pageApi = await loadMockMode()
    const r = await pageApi.getResources()
    expect(Object.keys(r).sort()).toEqual(['components', 'datasources', 'globalParams', 'timeParams', 'workflows'])
    expect(r.datasources.length).toBe(2)
    expect(r.timeParams.map((t) => t.path)).toEqual(['$system.date', '$system.datetime', '$system.month'])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('preview 返回 rowCap=100 且逐查询给出空结果项', async () => {
    const pageApi = await loadMockMode()
    const r = await pageApi.preview([{ id: 'q1', datasourceId: 1, sql: 'SELECT 1' }])
    expect(r.rowCap).toBe(100)
    expect(r.results.q1).toEqual({ columns: [], rows: [], truncated: false, error: '' })
    expect(r.widgetErrors).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refreshRefs 返回 refreshed 数字（三字段形状）', async () => {
    const pageApi = await loadMockMode()
    const r = await pageApi.refreshRefs('page_x')
    expect(typeof r.refreshed).toBe('number')
    expect(typeof r.publishedVersion).toBe('number')
    expect(Array.isArray(r.items)).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('pdDatabases/pdTables/pdColumns 返回样例且不发请求（D3 库表钻取）', async () => {
    vi.stubEnv('VITE_API_MODE', 'mock')
    vi.resetModules()
    const mod = await import('../pageApi')
    expect(await mod.pdDatabases(1)).toEqual(['datara_dw', 'ods'])
    expect((await mod.pdTables(1, 'datara_dw')).map((t) => `${t.name}:${t.kind}`)).toEqual(['t1:table', 'v_dim_user:view'])
    const cols = await mod.pdColumns(1, 'datara_dw', 't1')
    expect(cols).toHaveLength(3)
    expect(cols[0]).toMatchObject({ name: 'id', dataType: 'bigint' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('pageApi (real 模式：pd* 委托 ideApi 端点，D3)', () => {
  async function loadRealMode() {
    vi.stubEnv('VITE_API_MODE', 'real')
    vi.resetModules()
    return import('../pageApi')
  }

  it('pdDatabases → GET /datasources/{id}/databases', async () => {
    const mod = await loadRealMode()
    fetchMock.mockResolvedValue({ json: async () => ({ code: 0, msg: '', data: ['datara_dw', 'ods'] }) })
    expect(await mod.pdDatabases(7)).toEqual(['datara_dw', 'ods'])
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/datasources/7/databases')
  })

  it('pdTables → GET /datasources/{id}/databases/{db}/tables?limit=200', async () => {
    const mod = await loadRealMode()
    fetchMock.mockResolvedValue({
      json: async () => ({ code: 0, msg: '', data: [{ name: 't1', kind: 'table', rows: 128, comment: '' }] }),
    })
    const r = await mod.pdTables(7, 'datara_dw')
    expect(r[0]).toMatchObject({ name: 't1', kind: 'table', rows: 128 })
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/datasources/7/databases/datara_dw/tables?limit=200')
  })

  it('pdColumns → GET /datasources/{id}/databases/{db}/tables/{table}/columns', async () => {
    const mod = await loadRealMode()
    fetchMock.mockResolvedValue({
      json: async () => ({
        code: 0, msg: '',
        data: [{ name: 'id', dataType: 'bigint', columnType: 'bigint', length: null, nullable: false, key: 'PRI', comment: '', extra: '', defaultValue: null }],
      }),
    })
    const r = await mod.pdColumns(7, 'datara_dw', 't1')
    expect(r[0]).toMatchObject({ name: 'id', dataType: 'bigint' })
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/datasources/7/databases/datara_dw/tables/t1/columns')
  })
})
