/**
 * mock 模式读路径回归（补 `/workflow-definitions`、`/sync-tasks`、`/datasources`、`/runtime-nodes` 四个缺口）。
 *
 * 背景缺陷：`VITE_API_MODE=mock` 时此前仅 `graphService` 对象被切换，
 * `graphApi.ts` / `syncApi.ts` / `datasourceApi.ts` 里的**独立函数**仍直连真实后端。
 * 无后端时这四个端点全 502 → 总览四卡空、任务中心组件池空、导航偶发失效。
 *
 * 核心断言（不许退化）：mock 模式下这些读函数**一次 fetch 都不能发**，
 * 且必须返回非空、契约自洽的数据（空数组会让人误以为"mock 没接上"）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mockLineageGraph, mockListCategories, mockListDataSources, mockListDefinitions, mockListRuntimeNodes, mockListSyncTasks } from '../mock/api'

describe('mock 读路径数据契约（mock/api.ts）', () => {
  it('listDefinitions 返回 seed 定义，含 id/name/updatedAt 且带业务标签', async () => {
    const rows = await mockListDefinitions()
    expect(rows.length).toBeGreaterThan(0)
    for (const r of rows) {
      expect(r.id).toBeTruthy()
      expect(r.name).toBeTruthy()
      expect(typeof r.updatedAt).toBe('string')
    }
    expect(rows.map((r) => r.id)).toContain('wf_pay_sync')
  })

  it('listDefinitions 支持 search / tag 过滤，且 pageSize 钳制 200（对齐后端 PageQuery）', async () => {
    const kw = await mockListDefinitions({ search: '支付' })
    expect(kw.length).toBeGreaterThan(0)
    expect(kw.every((r) => r.name.includes('支付') || r.id.includes('支付'))).toBe(true)

    const tagged = await mockListDefinitions({ tag: 'etl' })
    expect(tagged.every((r) => (r.tags ?? []).includes('etl'))).toBe(true)
  })

  it('listSyncTasks 返回 PageData 形状（total + list），只含同步类任务', async () => {
    const p = await mockListSyncTasks()
    expect(Array.isArray(p.list)).toBe(true)
    expect(p.total).toBe(p.list.length)
    for (const r of p.list) {
      expect(r.tags).toContain('同步')
      /* 无真实实例来源 → 统计置 0，不编造随机数 */
      expect(r.readRows).toBe(0)
      expect(r.lastInstanceId).toBeNull()
    }
  })

  it('listDataSources 返回内存库真实数据源（非空），keyword 过滤生效', async () => {
    const all = await mockListDataSources()
    expect(all.length).toBeGreaterThan(0)
    const kw = await mockListDataSources({ keyword: 'gdb' })
    expect(kw.every((r) => JSON.stringify(r).toLowerCase().includes('gdb'))).toBe(true)
  })

  it('listRuntimeNodes 把字符串 id 映射为 number（RuntimeNodeRow 契约）', async () => {
    const rows = await mockListRuntimeNodes()
    expect(rows.length).toBeGreaterThan(0)
    for (const r of rows) {
      expect(typeof r.id).toBe('number')
      expect(Number.isInteger(r.id)).toBe(true)
      expect(r.name).toBeTruthy()
      expect(r.host).toBeTruthy()
    }
  })

  it('listCategories 只返回内置分类（custom=builtin=false 由 dataStore 承载，mock 下为空）', async () => {
    const rows = await mockListCategories()
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.every((r) => r.builtin)).toBe(true)
  })
})

/* ---------- 模式路由：mock 下一个真实请求都不许发 ---------- */

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok', setItem: vi.fn(), removeItem: vi.fn() })
})

/** 在 mock 模式下重新加载模块图（isMock 在 apiMode.ts 模块作用域求值，需 resetModules） */
async function loadMockMode() {
  vi.stubEnv('VITE_API_MODE', 'mock')
  vi.resetModules()
  return {
    graphApi: await import('../graphApi'),
    syncApi: await import('../syncApi'),
    datasourceApi: await import('../datasourceApi'),
    lineageApi: await import('../lineageApi'),
  }
}

describe('mock 模式路由：独立函数不得直连真实后端', () => {
  it('listDefinitions / listCategories / listRuntimeNodes 全部不发 fetch', async () => {
    const { graphApi } = await loadMockMode()

    const defs = await graphApi.listDefinitions({ pageNo: 1, pageSize: 200 })
    const cats = await graphApi.listCategories()
    const nodes = await graphApi.listRuntimeNodes()

    expect(defs.length).toBeGreaterThan(0)
    expect(cats.length).toBeGreaterThan(0)
    expect(nodes.length).toBeGreaterThan(0)
    /* 核心断言：一次真实请求都没发出 */
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('listSyncTasks / listDataSources 全部不发 fetch', async () => {
    const { syncApi, datasourceApi } = await loadMockMode()

    const p = await syncApi.listSyncTasks()
    const ds = await datasourceApi.listDataSources()

    expect(Array.isArray(p.list)).toBe(true)
    expect(ds.length).toBeGreaterThan(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('getDataSourceTree（既有 mock 分支）在同模式下依旧不发 fetch', async () => {
    const { datasourceApi } = await loadMockMode()
    const ds = await datasourceApi.listDataSources()
    const first = ds[0]

    const tree = await datasourceApi.getDataSourceTree(first.id as number)
    expect(tree.kind).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetchLineageGraph（Task 5 graph 聚合）mock 分支不发 fetch', async () => {
    const { lineageApi } = await loadMockMode()
    const res = await lineageApi.fetchLineageGraph({ level: 'table', source: 'all' })
    expect(res.nodes.length).toBeGreaterThan(0)
    expect(res.edges.length).toBeGreaterThan(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

/* ---------- Task 5：mockLineageGraph 双源样例（三态样式数据源） ---------- */

describe('mockLineageGraph（design+runtime 双源样例）', () => {
  it('全量：三态边齐全（双源/纯运行/纯设计），节点 sources 与边一致', async () => {
    const res = await mockLineageGraph({ level: 'table' })
    const dual = res.edges.filter((e) => e.sources.includes('design') && e.sources.includes('runtime'))
    const rtOnly = res.edges.filter((e) => e.sources.join() === 'runtime')
    const dgOnly = res.edges.filter((e) => e.sources.join() === 'design')
    expect(dual.length).toBeGreaterThan(0)
    expect(rtOnly.length).toBeGreaterThan(0)
    expect(dgOnly.length).toBeGreaterThan(0)
    // 节点 sources 聚合正确（「未验证」标记输入：纯设计上游节点）
    const userInfo = res.nodes.find((n) => n.fq === 'ods_gdb_biz_user_info')
    expect(userInfo!.sources).toEqual(['design'])
  })

  it('source=design → 仅保留设计行（纯设计子图，节点去运行佐证）', async () => {
    const res = await mockLineageGraph({ level: 'table', source: 'design' })
    expect(res.edges.length).toBeGreaterThan(0)
    expect(res.edges.every((e) => e.sources.includes('design'))).toBe(true)
    expect(res.nodes.every((n) => n.sources.every((s) => s === 'design'))).toBe(true)
  })

  it('中心表下推（db 前缀 _bare 归一）→ 双向全连通域收窄', async () => {
    const res = await mockLineageGraph({ level: 'table', table: 'dw.dwd_order_pay_detail' })
    const names = res.nodes.map((n) => n.fq)
    // 上游（ods_gdb_biz_*、dim_user）与下游链（dws_pay_summary_daily → ads_kpi_report）都在域内
    expect(names).toContain('ads_kpi_report')
    expect(names).toContain('ods_gdb_biz_trade_order')
    // 孤立域（dwd_gl_voucher_detail）不入
    expect(names).not.toContain('dwd_gl_voucher_detail')
  })

  it('direction/depth 下推：downstream depth=1 只收直连下游', async () => {
    const res = await mockLineageGraph({
      level: 'table', table: 'dwd_order_pay_detail', direction: 'downstream', depth: 1,
    })
    const names = res.nodes.map((n) => n.fq)
    expect(names).toContain('dws_pay_summary_daily')
    expect(names).not.toContain('ads_kpi_report') // 两跳外
    expect(names).not.toContain('ods_gdb_biz_trade_order') // 上游不入
  })

  it('limit 截断置位 truncated', async () => {
    const res = await mockLineageGraph({ level: 'table', table: 'dwd_order_pay_detail', limit: 3 })
    expect(res.truncated).toBe(true)
    expect(res.nodes.length).toBeLessThanOrEqual(3)
  })
})
