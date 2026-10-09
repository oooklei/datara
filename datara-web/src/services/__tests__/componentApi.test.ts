/**
 * componentApi 契约测试（M0 组件目录）：
 * 以 datara-backend/api/component.py 为唯一权威，验证 URL/方法/查询串与
 * {code,msg,data} 解包、错误抛出语义（沿用 datasourceApi 的 stub fetch 方案）。
 *
 * 重点覆盖 qs() 的空值剔除与 paletteVisible=false 的保留 —— 后者是"仅看
 * 不可见组件"的唯一入口，若被当作空值丢掉，过滤会静默失效。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getComponent, getComponentCatalog, getComponentStats, listComponents,
  getComponentRegistry, offlineComponent, rollbackComponent,
  getImpactedWorkflows, publishComponentVersion, deleteComponent, upgradeComponentRefs,
} from '../componentApi'
import { TOKEN_KEY } from '../http'

const fetchMock = vi.fn()
function stubRes(data: unknown, code = 0, msg = '') {
  fetchMock.mockResolvedValueOnce({ json: async () => ({ code, msg, data }) })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok-m0', setItem: vi.fn(), removeItem: vi.fn() })
})

describe('组件目录契约（M0 只读）', () => {
  it('listComponents 无参 → GET /components（带 token header）', async () => {
    stubRes({ total: 74, catalogHash: 'h', schemaVersion: 1, items: [] })
    const r = await listComponents()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/components')
    expect(init.method).toBe('GET')
    expect(init.headers.token).toBe('tok-m0')
    expect(r.total).toBe(74)
  })

  it('listComponents 带 profile/route/q → 查询串正确', async () => {
    stubRes({ total: 0, catalogHash: 'h', schemaVersion: 1, items: [] })
    await listComponents({ profile: 'dag', route: 'master', q: 'sql' })
    const url: string = fetchMock.mock.calls[0][0]
    expect(url).toContain('profile=dag')
    expect(url).toContain('route=master')
    expect(url).toContain('q=sql')
  })

  it('paletteVisible=false 必须保留（否则"仅不可见"过滤静默失效）', async () => {
    stubRes({ total: 0, catalogHash: 'h', schemaVersion: 1, items: [] })
    await listComponents({ paletteVisible: false })
    expect(fetchMock.mock.calls[0][0]).toContain('paletteVisible=false')
  })

  it('paletteVisible=true 与未传值的区分', async () => {
    stubRes({ total: 0, catalogHash: 'h', schemaVersion: 1, items: [] })
    await listComponents({ paletteVisible: true })
    expect(fetchMock.mock.calls[0][0]).toContain('paletteVisible=true')

    fetchMock.mockReset()
    stubRes({ total: 0, catalogHash: 'h', schemaVersion: 1, items: [] })
    await listComponents()
    expect(fetchMock.mock.calls[0][0]).not.toContain('paletteVisible')
  })

  it('空字符串过滤项被剔除（不产生 ?profile=）', async () => {
    stubRes({ total: 0, catalogHash: 'h', schemaVersion: 1, items: [] })
    await listComponents({ profile: '', q: '' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components')
  })

  it('getComponentStats → GET /components/stats', async () => {
    stubRes({ catalogHash: 'h', generatedAt: 't', source: {}, stats: {}, profiles: [] })
    const s = await getComponentStats()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/stats')
    expect(s.catalogHash).toBe('h')
  })

  it('getComponent → GET /components/{type}，type 需转义', async () => {
    stubRes({ type: 'src_select' })
    await getComponent('src_select')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/src_select')

    fetchMock.mockReset()
    stubRes({ type: 'a/b' })
    await getComponent('a/b')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/a%2Fb')
  })

  it('getComponentCatalog → GET /components/catalog', async () => {
    stubRes({ schemaVersion: 1 })
    await getComponentCatalog()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/catalog')
  })

  it('后端 code!==0 → throw Error(msg)（含 409 仅后端类型）', async () => {
    fetchMock.mockResolvedValueOnce({
      json: async () => ({ code: 409, msg: 'smoke 为后端保留类型，无前端 NodeSchema（预期行为）', data: null }),
    })
    await expect(getComponent('smoke')).rejects.toThrow('无前端 NodeSchema')
  })

  it('TOKEN_KEY 沿用统一约定', () => {
    expect(TOKEN_KEY).toBe('datara_token')
  })
})

describe('D3 发布治理契约（offline/rollback/impacted/registry/publish）', () => {
  it('offlineComponent → POST /components/{type}/offline，body 带 remark', async () => {
    stubRes({ type: 'comp_demo', state: 'offline', publishedVersion: 2 })
    const r = await offlineComponent('comp_demo', '停用说明')
    /* signal 为 http 助手统一注入的超时中止守卫（既有行为），断言存在即可 */
    expect(fetchMock.mock.calls[0]).toEqual([
      '/api/v1/components/comp_demo/offline',
      { method: 'POST', headers: expect.any(Object), body: JSON.stringify({ remark: '停用说明' }), signal: expect.anything() },
    ])
    expect(r.state).toBe('offline')
    expect(r.publishedVersion).toBe(2) // D3 裁定：下线保留 published_version
  })

  it('rollbackComponent → POST /components/{type}/rollback，body 带 version', async () => {
    stubRes({ type: 'comp_demo', publishedVersion: 1, supersededVersion: 2 })
    const r = await rollbackComponent('comp_demo', 1, '回到 v1')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/comp_demo/rollback')
    expect(body).toEqual({ version: 1, remark: '回到 v1' })
    expect(r.supersededVersion).toBe(2)
  })

  it('getImpactedWorkflows → GET /components/{type}/impacted', async () => {
    stubRes({
      type: 'comp_demo', publishedVersion: 2, state: 'published',
      items: [{ id: 'wf_a', code: 11, name: '流A', version: 3, releaseState: 'online', refVersions: [1], behind: true, aligned: false }],
    })
    const r = await getImpactedWorkflows('comp_demo')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/comp_demo/impacted')
    expect(r.items[0].behind).toBe(true)
  })

  it('upgradeComponentRefs serializes targets with the API snake_case contract', async () => {
    stubRes({ type: 'comp_demo', publishedVersion: 3, results: [{ wfId: 'wf-a', ok: true, newVersion: 3 }] })
    const result = await upgradeComponentRefs('comp_demo', [{ wfId: 'wf-a', baseVersion: 2 }])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/comp_demo/upgrade-refs')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      targets: [{ wf_id: 'wf-a', strategy: 'auto', base_version: 2 }],
    })
    expect(result.results[0].ok).toBe(true)
  })

  it('upgradeComponentRefs sends an explicit mapping or skip only when chosen', async () => {
    stubRes({ type: 'comp_demo', publishedVersion: 3, results: [] })
    await upgradeComponentRefs('comp_demo', [
      { wfId: 'wf-map', fieldMapping: { old_table: 'source_table' } },
      { wfId: 'wf-skip', migration: 'skip' },
      { wfId: 'wf-default', fieldMapping: {} },
    ])

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      targets: [
        { wf_id: 'wf-map', strategy: 'auto', field_mapping: { old_table: 'source_table' } },
        { wf_id: 'wf-skip', strategy: 'auto', migration: 'skip' },
        { wf_id: 'wf-default', strategy: 'auto' },
      ],
    })
  })

  it('getComponentRegistry → GET /components/registry，返回 items 数组', async () => {
    stubRes({ items: [{ type: 'comp_demo', name: '演示', profile: 'dag', scope: 'user', state: 'published', publishedVersion: 2, executionModel: 'dag-engine', category: null }] })
    const rows = await getComponentRegistry()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/registry')
    expect(rows[0].publishedVersion).toBe(2)
  })

  it('publishComponentVersion 422/6003 → err.code 与 err.data.items 透传（闸门面板渲染源）', async () => {
    fetchMock.mockResolvedValueOnce({
      json: async () => ({
        code: 6003, msg: '发布闸门未通过',
        data: { items: [{ gate: 'pure_data', ok: false, msg: '图标含函数片段' }, { gate: 'contract', ok: true, msg: 'ok' }] },
      }),
    })
    const err = await publishComponentVersion('comp_demo', { version: 1, draftRev: 3 }).then(
      () => { throw new Error('应抛出闸门错误') },
      (e) => e as Error & { code?: number; data?: { items?: { gate: string; ok: boolean }[] } },
    )
    expect(err.code).toBe(6003)
    expect(err.data?.items?.[0].gate).toBe('pure_data')
  })
})

describe('删除组件契约（Task 15 CRUD 补齐 · 仅草稿可删）', () => {
  it('deleteComponent → DELETE /components/{type}，type 需转义', async () => {
    stubRes({ type: 'user/demo', deleted: true })
    const r = await deleteComponent('user/demo')
    expect(fetchMock.mock.calls[0]).toEqual([
      '/api/v1/components/user%2Fdemo',
      { method: 'DELETE', headers: expect.any(Object), signal: expect.anything() },
    ])
    expect(r.deleted).toBe(true)
  })
})

describe('组件初始化模板（页面设计器 §11 · Task 14）', () => {
  it('catalog: 全量系统组件携带初始化模板（initTemplate 纯数据）', async () => {
    /* 直读仓库内权威快照喂给 listComponents 消费链：断言 catalog 全量（75 组件）
       每条携带 initTemplate，且为纯数据（PageDSL 片段禁函数/表达式字符串，
       与后端 FORBIDDEN_SNIPPETS 红线同口径）。 */
    const { readFileSync } = await import('node:fs')
    const catPath = new URL('../../../../datara-backend/common/dag_catalog.json', import.meta.url)
    const cat = JSON.parse(readFileSync(catPath, 'utf-8')) as {
      components: Record<string, unknown>[]
      catalogHash: string
      schemaVersion: number
    }
    stubRes({
      total: cat.components.length, catalogHash: cat.catalogHash,
      schemaVersion: cat.schemaVersion, items: cat.components,
    })
    const { listComponents } = await import('../componentApi')
    const res = await listComponents()
    expect(res.items.length).toBeGreaterThan(0)
    res.items.forEach((it) => {
      const tpl = (it as unknown as { initTemplate?: unknown }).initTemplate
      expect(tpl, `${it.type} 缺 initTemplate`).toBeTruthy()
      expect(JSON.stringify(tpl)).not.toMatch(/=>|function|eval\(|\bimport\b|\$\{/)
    })
  })
})
