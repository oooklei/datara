import { describe, it, expect } from 'vitest'
import { routes } from '../routes'

// todo 5 (W0-5) 应用外壳：43 条新增路由 + 8 条现有路由 + 兜底 catch-all（qc/bind、meta/collect、ind/approval 已下线；/dag/depend 跨流依赖删除，/dep/runtime 运行时节点新增；I1：/sync/wizard 与 /etl/design/:id 移除，/login 新增；I6：/batch/board 同步进度看板删除，监控统一走 /sync/list 与 /sync/detail/:id）
describe('router shell (todo 5)', () => {
  const newPaths = [
    '/login',
    '/ds/list', '/ds/detail/:id', '/sync/list', '/sync/detail/:id',
    '/etl/list', '/stream/list', '/stream/detail/:id',
    '/model/list', '/model/design/:id', '/ide', '/dag/runs', '/dag/alarm',
    '/script/list', '/script/env', '/script/remote', '/param/global', '/param/builtin',
    '/param/env', '/param/tools',
    '/qc/score', '/qc/rule', '/qc/task', '/qc/exception', '/qc/report', '/qc/alarm',
    '/meta/catalog', '/meta/tag', '/std/element', '/std/code', '/std/naming',
    '/std/mapping', '/std/approval', '/ind/list', '/ind/board', '/ind/consistency',
    '/dep/center', '/dep/monitor', '/dep/log', '/dep/alarm', '/dep/ops', '/dep/runtime',
    '/dag/instances', // I3：调度执行引擎真实运行实例视图
  ]
  const existingPaths = ['/', '/dag', '/dag/design/:id', '/deploy', '/stream/design/:id', '/model/er', '/meta/lineage', '/meta/map']

  it('registers all 43 new module routes', () => {
    const registered = new Set(routes.map((r) => r.path))
    for (const p of newPaths) {
      expect(registered.has(p), `route ${p} should be registered`).toBe(true)
    }
    expect(newPaths.length).toBe(43)
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
})
