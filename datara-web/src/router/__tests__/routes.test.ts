import { describe, it, expect } from 'vitest'
import { routes } from '../routes'

// todo 5 (W0-5) 应用外壳：47 条新增路由 + 8 条现有路由 + 兜底 catch-all（qc/bind、meta/collect、ind/approval 已下线；/dag/depend 跨流依赖删除，/dep/runtime 运行时节点新增；I1：/sync/wizard 与 /etl/design/:id 移除，/login 新增；I6：/batch/board 同步进度看板删除，监控统一走 /sync/list 与 /sync/detail/:id；M-B0：/meta/baseline 组件基线化工作台新增；I13：组件治理页路由暴露）
describe('router shell (todo 5)', () => {
  const newPaths = [
    '/login',
    '/ds/list', '/ds/detail/:id', '/sync/list', '/sync/detail/:id',
    '/etl/list', '/stream/list', '/stream/detail/:id',
    '/model/list', '/model/design/:id', '/ide', '/dag/runs', '/dag/alarm',
    '/script/list', '/script/env', '/script/remote', '/param/global', '/param/builtin',
    '/param/env', '/param/tools',
    '/qc/score', '/qc/rule', '/qc/task', '/qc/exception', '/qc/report', '/qc/alarm',
    '/meta/components', '/meta/components/baseline', '/meta/components/design/:type?',
    '/meta/catalog', '/meta/tag', '/std/element', '/std/code', '/std/naming',
    '/std/mapping', '/std/approval', '/ind/list', '/ind/board', '/ind/consistency',
    '/dep/center', '/dep/monitor', '/dep/log', '/dep/alarm', '/dep/ops', '/dep/runtime',
    '/dag/instances', // I3：调度执行引擎真实运行实例视图
    '/meta/baseline', // M-B0：组件基线化工作台（八段 DSL 底稿/体检/认可发 v1）
  ]
  const existingPaths = ['/', '/dag', '/dag/design/:id', '/deploy', '/stream/design/:id', '/model/er', '/meta/lineage', '/meta/map']

  it('registers all 47 new module routes', () => {
    const registered = new Set(routes.map((r) => r.path))
    for (const p of newPaths) {
      expect(registered.has(p), `route ${p} should be registered`).toBe(true)
    }
    expect(newPaths.length).toBe(47)
  })

  it('keeps the 8 existing routes unchanged', () => {
    const registered = new Set(routes.map((r) => r.path))
    for (const p of existingPaths) {
      expect(registered.has(p), `route ${p} should be registered`).toBe(true)
    }
  })

  it('has a catch-all fallback so unregistered paths land on placeholder (no 404)', () => {
    expect(routes.some((r) => r.path === '/:pathMatch(.*)*')).toBe(true)
  })

  /* F56a 同壳单入口：旧同壳路径 redirect 到权威路由（query.tab 承载页签，原 query 透传保书签） */
  it('redirects legacy same-shell paths to the canonical hub route', () => {
    const byPath = new Map(routes.map((r) => [r.path, r]))
    const cases: [string, string][] = [
      ['/script/env', '/script/list'],
      ['/script/remote', '/script/list'],
      ['/param/builtin', '/param/global'],
      ['/param/env', '/param/global'],
      ['/param/tools', '/param/global'],
      ['/qc/report-dag', '/qc/report'],
      ['/qc/report-table', '/qc/report'],
      ['/std/code', '/std/element'],
      ['/std/naming', '/std/element'],
      ['/std/mapping', '/std/element'],
      ['/std/approval', '/std/element'],
    ]
    for (const [from, to] of cases) {
      const rec = byPath.get(from)
      expect(rec, `route ${from} should be registered`).toBeTruthy()
      expect(rec!.redirect, `route ${from} should redirect`).toBeTruthy()
      const target = (rec!.redirect as (t: { query: Record<string, unknown> }) => { path: string })({ query: {} })
      expect(target.path, `route ${from} should redirect to ${to}`).toBe(to)
    }
    /* 权威路由本体不 redirect */
    for (const keep of ['/script/list', '/param/global', '/qc/report', '/std/element']) {
      expect(byPath.get(keep)!.redirect, `${keep} should be canonical (no redirect)`).toBeFalsy()
    }
  })

  /* M-B0：基线化工作台路由元信息（标题 + 独立 name，挂在 meta 组件族） */
  it('registers the M-B0 baseline workbench route with meta title', () => {
    const rec = routes.find((r) => r.path === '/meta/baseline')
    expect(rec, 'route /meta/baseline should be registered').toBeTruthy()
    expect(rec!.name).toBe('meta-baseline')
    expect((rec!.meta as { title?: string }).title).toBe('基线化工作台')
  })

  /* 组件设计器统一入口：旧 B4 声明编辑器下线，design 路径 redirect 到 page-designer（保书签，:type 透传） */
  it('redirects the legacy component design route to the unified page-designer', () => {
    const rec = routes.find((r) => r.path === '/meta/components/design/:type?')
    expect(rec, 'legacy design route should be registered').toBeTruthy()
    expect(rec!.redirect, 'legacy design route should redirect').toBeTruthy()
    const fn = rec!.redirect as (t: { params: Record<string, string> }) => { path: string }
    expect(fn({ params: { type: 'op_filter' } }).path).toBe('/meta/components/page-designer/op_filter')
    expect(fn({ params: {} }).path).toBe('/meta/components/page-designer')
  })

  /* 组件设计器：page-designer 为设计器唯一权威路由，标题统一为「组件设计器」 */
  it('registers the page-designer as the canonical component designer route', () => {
    const rec = routes.find((r) => r.path === '/meta/components/page-designer/:type?')
    expect(rec, 'page-designer route should be registered').toBeTruthy()
    expect(rec!.redirect, 'page-designer should be canonical (no redirect)').toBeFalsy()
    expect((rec!.meta as { title?: string }).title).toBe('组件设计器')
  })
})
