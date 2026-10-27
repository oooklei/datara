import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppShell from '../AppShell.vue'
import * as authApi from '../../services/rebuild/authApi'

const { listProjectsSpy } = vi.hoisted(() => ({ listProjectsSpy: vi.fn() }))

vi.mock('../../services/rebuild/projectApi', () => ({ listProjects: listProjectsSpy }))

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div>home</div>' } },
      { path: '/p/:projectId', component: { template: '<div>project</div>' } },
      { path: '/p/:projectId/:pathMatch(.*)*', component: { template: '<div>segment</div>' } },
      { path: '/dep/runtime', component: { template: '<div>runtime</div>' } },
      { path: '/sys', component: { template: '<div>system</div>' } },
    ],
  })
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  listProjectsSpy.mockReset()
  listProjectsSpy.mockResolvedValue({ total: 2, list: [
    { id: 33, name: '电商全域数据治理项目' },
    { id: 34, name: '客户数据治理项目' },
  ] })
  const account = (authApi as unknown as { authAccount?: { value: unknown } }).authAccount
  if (account) account.value = { id: 7, username: 'analyst', role: 'operator' }
})

describe('UX v3：AppShell 顶层能力', () => {
  it('顶栏展示真实登录账号和角色而非固定验证文案', async () => {
    const router = makeRouter()
    await router.push('/p/33')
    const wrapper = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.get('[data-current-user]').text()).toContain('analyst')
    expect(wrapper.get('[data-current-user]').text()).toContain('分析师')
  })

  it('项目切换器展示可见项目并切换到目标项目工作台', async () => {
    const router = makeRouter()
    await router.push('/p/33')
    const wrapper = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('[data-project-switcher]').trigger('click')
    expect(wrapper.findAll('[data-project-option]')).toHaveLength(2)
    await wrapper.findAll('[data-project-option]')[1].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/p/34')
  })

  it('主题按钮切换 dark/light 并持久化', async () => {
    const router = makeRouter()
    await router.push('/p/33')
    const wrapper = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('[data-theme-toggle]').trigger('click')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('datara.theme')).toBe('dark')
    await wrapper.get('[data-theme-toggle]').trigger('click')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('窄屏导航按钮可展开与收起项目侧栏', async () => {
    const router = makeRouter()
    await router.push('/p/33')
    const wrapper = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    const toggle = wrapper.get('[data-sidebar-toggle]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.app-shell').classes()).toContain('sidebar-open')
  })
})
