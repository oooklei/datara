import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authAccount } from '../../services/rebuild/authApi'
import HomeView from '../HomeView.vue'
import AppShell from '../../layouts/AppShell.vue'

const listProjects = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/projectApi', () => ({ listProjects }))

beforeEach(() => {
  listProjects.mockReset()
  authAccount.value = null
})

describe('account switch project isolation', () => {
  it('replaces prior home projects after admin signs in', async () => {
    let finishOld!: (page: unknown) => void
    listProjects.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve }))
      .mockResolvedValueOnce({ list: [{ id: 33, name: '管理员项目' }], total: 1 })
    authAccount.value = { id: 2, username: 'zhangsan', role: 'developer' }
    const wrapper = mount(HomeView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    await flushPromises()
    expect(wrapper.find('[data-project-id="33"]').exists()).toBe(true)
    finishOld({ list: [{ id: 22, name: '旧账号项目' }], total: 1 })
    await flushPromises()
    expect(wrapper.find('[data-project-id="22"]').exists()).toBe(false)
    expect(wrapper.find('[data-project-id="33"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('refreshes the shell project switcher when the account changes on the same route', async () => {
    let finishOld!: (page: unknown) => void
    listProjects.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve }))
      .mockResolvedValueOnce({ list: [{ id: 33, name: '管理员项目' }], total: 1 })
    authAccount.value = { id: 2, username: 'zhangsan', role: 'developer' }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/p/:projectId', component: { template: '<div />' } }],
    })
    await router.push('/p/33')
    const wrapper = mount(AppShell, { global: { plugins: [router] } })
    await flushPromises()
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    await flushPromises()
    expect(wrapper.find('[data-project-name="33"]').text()).toBe('管理员项目')
    finishOld({ list: [{ id: 33, name: '旧账号项目' }], total: 1 })
    await flushPromises()
    expect(wrapper.find('[data-project-name="33"]').text()).toBe('管理员项目')
    wrapper.unmount()
  })
})
