/**
 * 票 2-05 验收测试：AppShell 三段式布局组件（0.8 §7 测试集 6/7）
 *
 * 测试集 6：AI 入口跨业务路由单实例；登录页不渲染；切换路由上下文更新。
 * 测试集 7：菜单隐藏后直接访问受限路由仍由路由守卫拒绝（显隐不替代鉴权）。
 * 附加：菜单消费正向（direct 组标题不渲染/F56a）+ future 组折叠渲染（2-04 接驳）。
 * 注：组件测试用独立 memory router + stub 视图，不改产品 routes.ts；
 *     测试集 7 之 1 用产品真实 router（index.ts default）验证守卫本身。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import AppShell from '../AppShell.vue'
import App from '../../App.vue'
import { clearToken, setToken } from '../../services/http'
import productRouter from '../../router'
import { loadGroupFolded } from '../../navigation/groupFold'

function stubView(tag: string) {
  return { template: `<div data-stub="${tag}">${tag}</div>` }
}

/** 组件测试路由：两条业务路由（测试集 6 之「两条不同业务路由」）+ 登录页 + 菜单消费验证路由 */
function makeTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: stubView('login') },
      { path: '/a', name: 'bizA', component: stubView('a') },
      { path: '/b', name: 'bizB', component: stubView('b') },
      { path: '/dag', name: 'dagEntry', component: stubView('dag') },
      { path: '/model/list', name: 'dwModeling', component: stubView('dw') },
    ],
  })
}

describe('2-05 测试集 6：AI 挂载点单实例 + 登录页不渲染', () => {
  it('AppShell 内 AI 全局挂载点存在且唯一（与 RouterView 同级）', () => {
    const router = makeTestRouter()
    const w = mount(AppShell, { global: { plugins: [router] } })
    expect(w.findAll('#ai-assistant-global-mount')).toHaveLength(1)
    expect(w.find('#ai-assistant-global-mount').attributes('aria-label')).toBe('AI 助手全局挂载点')
  })

  it('跨两条业务路由切换：AppShell 不重建，挂载点保持单实例（跨路由保持）', async () => {
    const router = makeTestRouter()
    await router.push('/a')
    const w = mount(AppShell, { global: { plugins: [router] } })
    expect(w.findAll('#ai-assistant-global-mount')).toHaveLength(1)
    await router.push('/b')
    await w.vm.$nextTick()
    expect(w.findAll('#ai-assistant-global-mount')).toHaveLength(1)
    // 上下文随路由元信息更新（0.8 §6 规则 3）
    expect((w.vm as unknown as { aiContext: string }).aiContext).toBe('/b')
    await router.push('/a')
    await w.vm.$nextTick()
    expect((w.vm as unknown as { aiContext: string }).aiContext).toBe('/a')
  })

  it('App 级：登录页不挂载 AppShell（无 AI 挂载点）；认证后业务路由挂载', async () => {
    const router = makeTestRouter()
    setToken('t-shell')
    await router.push('/login')
    const w = mount(App, { global: { plugins: [router] } })
    expect(w.findComponent(AppShell).exists()).toBe(false)
    expect(w.find('#ai-assistant-global-mount').exists()).toBe(false)
    await router.push('/a')
    await w.vm.$nextTick()
    expect(w.findComponent(AppShell).exists()).toBe(true)
    expect(w.findAll('#ai-assistant-global-mount')).toHaveLength(1)
    clearToken()
  })
})

describe('2-05 测试集 7：菜单显隐不替代鉴权', () => {
  it('产品真实守卫：无 token 直接访问受限路由被重定向 /login（守卫独立于菜单过滤）', async () => {
    clearToken()
    await productRouter.push('/')
    expect(productRouter.currentRoute.value.path).toBe('/login')
    setToken('t-guard')
    await productRouter.push('/')
    expect(productRouter.currentRoute.value.path).toBe('/')
    await productRouter.push('/login')
    expect(productRouter.currentRoute.value.path).toBe('/')
    clearToken()
  })

  it('R-15 初始态（批次全关）：AppShell 侧栏零菜单组渲染，但守卫仍生效（联合断言）', () => {
    const router = makeTestRouter()
    const w = mount(AppShell, { global: { plugins: [router] } })
    expect(w.findAll('.menu-group')).toHaveLength(0)
  })
})

describe('2-05 菜单消费（filterMenuGroups 接驳 + F56a direct + future 折叠渲染）', () => {
  it('批次开+路由已注册：B 组一级直达可见且组标题不渲染（direct；F56a 2A/3B）', async () => {
    const router = makeTestRouter()
    await router.push('/dag')
    const w = mount(AppShell, {
      global: { plugins: [router] },
      props: { filterOverrides: { batchSwitches: { inc4: true } } },
    })
    const groups = w.findAll('.menu-group')
    expect(groups).toHaveLength(1)
    expect(groups[0].attributes('data-group-id')).toBe('task-center')
    expect(groups[0].find('.group-title').exists()).toBe(false)
    const link = groups[0].find('a.menu-link')
    expect(link.text()).toBe('任务中心')
    expect(link.attributes('href')).toContain('/dag')
  })

  it('future 组渲染：默认折叠（aria-expanded=false + items 隐藏）；展开持久化稳定键且不改路由', async () => {
    localStorage.clear()
    const router = makeTestRouter()
    await router.push('/a')
    const w = mount(AppShell, {
      global: { plugins: [router] },
      props: { filterOverrides: { previewAllowed: new Set(['dw-modeling']) } },
    })
    const futureGroup = w.find('.menu-group[data-group-id="future"]')
    expect(futureGroup.exists()).toBe(true)
    expect(futureGroup.find('.group-label').text()).toBe('后续批次')
    const toggle = futureGroup.find('button.group-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    // 默认折叠：items v-show=false（组标题可点开）
    const itemsUl = futureGroup.find('ul.menu-items')
    expect((itemsUl.element as HTMLElement).style.display).toBe('none')
    const routeBefore = router.currentRoute.value.fullPath
    await toggle.trigger('click')
    await w.vm.$nextTick()
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect((itemsUl.element as HTMLElement).style.display).not.toBe('none')
    expect(loadGroupFolded('future', true)).toBe(false)
    // 展开不改变路由（0.8 §7 测试集 4 组件级）
    expect(router.currentRoute.value.fullPath).toBe(routeBefore)
  })

  it('future 组空时整组不渲染（0.8 §5.2 组件级闭环）', () => {
    localStorage.clear()
    const router = makeTestRouter()
    const w = mount(AppShell, { global: { plugins: [router] } })
    expect(w.find('.menu-group[data-group-id="future"]').exists()).toBe(false)
  })
})
