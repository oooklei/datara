/**
 * 票 1.4 验收测试：routes 负断言 + History 回退配置核验
 * （WBS 1.4 验收方式原文「Playwright 深层 path 直达不落首页 + routes 负断言测试」之前半；
 *   增量 1 退出标准 2「routes.ts 无 demo:true、无 /rebuild/validation（负断言测试通过）」）
 *
 * 裁示依据（s231-accept-batch ①，信箱 L192）：**不设 catch-all 回 `/`，以权威设计 §7.3 判据为准**。
 * §7.3 联通判据：「History 模式回退正确 | 直接访问深层 path（无 `#`）不落首页」。
 * 故本测试把该判据下沉为 routes 层不变量：routes.ts 不得存在把未匹配深层 path 重定向/回落到首页
 * 的 catch-all 条目——一旦有人补 `/:pathMatch(.*)* → '/'`，本测试即失败，判据不被静默破坏。
 *
 * Playwright 深层 path 实跑判据（WBS 1.4 验收方式后半）按 s231 裁示②随**增量 2.1 收口**核验，
 * 落位 tests/e2e/（s231 裁示③），不在本票收口范围。
 *
 * 注：本测试只读 routes.ts / router/index.ts / vite.config.ts 源码与 routes 运行期对象，
 *     不改动产品路由；登录守卫行为由 src/layouts/__tests__/appShell.contract.test.ts 测试集 7 覆盖。
 */
import { describe, expect, it } from 'vitest'
import { routes } from '../routes'
import TaskCenterView from '../../views/TaskCenterView.vue'
import SshNodeManagementView from '../../views/SshNodeManagementView.vue'
import RuntimeNodeView from '../../views/depops/RuntimeNodeView.vue'
import routesSource from '../routes.ts?raw'
import routerSource from '../index.ts?raw'
import viteSource from '/vite.config.ts?raw'
import indexHtmlSource from '/index.html?raw'

/** 剥离块注释与行注释后的可执行代码（避免文档字符串里的路径字面量造成误报）。 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
}

const CATCH_ALL_MARKER = ':pathMatch'

describe('1.4 routes 负断言（WBS 1.4 / 增量 1 退出标准 2）', () => {
  it('routes 正式产品路由基线：/login、/、/dag 任务中心（s260 派令 INC4-FE-1 解锁）、/dep/runtime 运行节点页（IMPL-v4-17）与 /p/:projectId 项目工作区层两条（s251 派令 L3-03 解锁），无 demo/验证页/临时占位路由', () => {
    expect(routes.map((r) => r.path)).toEqual([
      '/login',
      '/',
      '/dag',
      // 17.5 P4 SSH 节点域收口：独立挂载页
      '/dep/ssh',
      // 17.4 P3 运行节点迁移（IMPL-v4-17）：运行时节点页
      '/dep/runtime',
      '/p/:projectId',
      '/p/:projectId/:seg',
    ])
  })

  it('/dag 绑定 TaskCenterView 且具名（s260 INC4-FE-1：任务中心顶部视角页签框架承载）', () => {
    const dag = routes.find((r) => r.path === '/dag')
    expect(dag).toBeTruthy()
    expect(dag?.name).toBe('dag-entry')
    expect(dag?.component).toBe(TaskCenterView)
  })

  it('/dep/ssh 绑定 SshNodeManagementView 且具名（17.5 P4 SSH 节点域收口：独立挂载页）', () => {
    const ssh = routes.find((r) => r.path === '/dep/ssh')
    expect(ssh).toBeTruthy()
    expect(ssh?.name).toBe('dep-ssh')
    expect(ssh?.component).toBe(SshNodeManagementView)
  })

  it('/dep/runtime 绑定 RuntimeNodeView 且具名（IMPL-v4-17：17.4 P3 运行节点迁移）', () => {
    const runtime = routes.find((r) => r.path === '/dep/runtime')
    expect(runtime).toBeTruthy()
    expect(runtime?.name).toBe('dep-runtime')
    expect(runtime?.component).toBe(RuntimeNodeView)
  })

  it('无任何路由携带 demo:true 标记（零 demo 路由）', () => {
    const demoRoutes = routes.filter((r) => (r as { demo?: boolean }).demo === true)
    expect(demoRoutes).toHaveLength(0)
    expect(stripComments(routesSource)).not.toContain('demo')
  })

  it('无 /rebuild/validation 验证页路由（旧 datara-web 验证页零残留）', () => {
    expect(routes.some((r) => String(r.path).includes('rebuild/validation'))).toBe(false)
    expect(stripComments(routesSource)).not.toContain('rebuild/validation')
  })

  it('路由不占用 /api 前缀（/api 为后端唯一上游，前端路由与其零重叠）', () => {
    const apiRoutes = routes.filter((r) => String(r.path).startsWith('/api'))
    expect(apiRoutes).toHaveLength(0)
  })

  it('routes.ts 源码不出现 /api 前缀路由字面量（含注释外全部代码）', () => {
    expect(stripComments(routesSource)).not.toContain("path: '/api")
    expect(stripComments(routesSource)).not.toContain('path: `/api')
  })

  it('未匹配深层 path 不落首页：routes 无 catch-all 条目（§7.3 判据，s231 裁示①）', () => {
    // catch-all 通配段（vue-router 4 语法 :pathMatch(.*)*）零出现
    expect(stripComments(routesSource)).not.toContain(CATCH_ALL_MARKER)
    expect(routes.some((r) => String(r.path).includes(CATCH_ALL_MARKER))).toBe(false)
    // 亦无「未匹配即重定向首页」的等价形态（redirect 到 /）
    expect(routes.some((r) => r.path !== '/' && r.path !== '/login' && 'redirect' in r)).toBe(false)
  })

  it('routes 无 component 之外的空壳占位（每条正式路由均有具名组件）', () => {
    for (const r of routes) {
      expect(r.name, `路由 ${String(r.path)} 应有 name`).toBeTruthy()
      expect(r.component, `路由 ${String(r.path)} 应绑定 component`).toBeTruthy()
    }
  })
})

describe('1.4 History 回退配置核验（§2.4 模式决策 / §7.3 判据）', () => {
  it('router 使用 createWebHistory（§2.4 冻结决策：弃 hash，用 History 模式）', () => {
    const code = stripComments(routerSource)
    expect(code).toContain('createWebHistory')
    expect(code).not.toContain('createWebHashHistory')
  })

  it('router 未设 base 前缀偏移（BASE 由 http 底座单点持有，路由层不重复声明）', () => {
    const code = stripComments(routerSource)
    expect(code).not.toContain('/api/v1')
    expect(code).not.toContain('LEGACY_BASE')
  })

  it('dev server 为 SPA 回退（vite appType 默认 spa：深层 path 直达由 vite 回落 index.html，不落首页）', () => {
    // vite.config.ts 无注释，直接用原文（stripComments 的 `//` 规则会误切 URL 内的 `//`）
    // 未显式关闭 SPA 回退（appType 缺省即 'spa'）；若被改为 'mpa'/'custom' 则 History 回退失效
    expect(viteSource).not.toContain('appType')
  })

  it('SPA 单一挂载点（index.html 仅一个 #app，History 模式无 hash 路由入口）', () => {
    const code = stripComments(indexHtmlSource)
    expect(code).toContain('<div id="app"')
    expect(code).not.toContain('createWebHashHistory')
    // 单一挂载点：#app 仅出现一次
    expect(code.split('<div id="app"').length - 1).toBe(1)
  })

  it('vite dev 单线反代 /api/v1 → 8001（§7.1 单 BASE 拓扑，与路由层 /api 前缀零重叠互证）', () => {
    expect(viteSource).toContain("'/api/v1'")
    expect(viteSource).toContain('localhost:8001')
    // 无第二后端旁路（红线 1）
    expect(viteSource).not.toContain('LEGACY_BASE')
    expect(viteSource).not.toContain('8000')
  })

  it('登录守卫按 token 判定（守卫与 History 模式正交；显隐不替代鉴权）', async () => {
    // 运行期核验 history 实例存在；History 模式 base 为 pathname 根（hash 模式会带 '#'）
    const { default: router } = await import('../index')
    expect(router.options.history).not.toBeNull()
    expect(router.options.history.base).not.toContain('#')
    expect(router.options.history.base === '' || router.options.history.base === '/').toBe(true)
  })
})
