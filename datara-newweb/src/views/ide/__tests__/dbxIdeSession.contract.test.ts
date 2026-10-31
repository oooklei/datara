import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DbxIdeView from '../DbxIdeView.vue'
import { authAccount } from '../../../services/rebuild/authApi'

const mocks = vi.hoisted(() => ({
  issue: vi.fn(),
  projects: vi.fn(),
  complete: vi.fn(),
  send: vi.fn(),
  environments: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('../../../services/rebuild/authApi', async () => {
  const { shallowRef } = await import('vue')
  return { authAccount: shallowRef(null) }
})
vi.mock('../../../services/rebuild/dbxIdeApi', () => ({ issueDbxIdeSession: mocks.issue }))
vi.mock('../../../services/rebuild/orchestrationApi', () => ({ orchestrationApi: { listEnvironments: mocks.environments } }))
vi.mock('../../../services/rebuild/projectApi', () => ({ listProjects: mocks.projects }))
vi.mock('../../../services/rebuild/variableApi', () => ({ createVariableContract: () => ({ completeVariables: mocks.complete }) }))
vi.mock('../../../services/rebuild/dbxVariableBridge', () => ({
  buildVariableEntries: (items: unknown[]) => items,
  sendVariablesToDbx: mocks.send,
}))
vi.mock('../../variables/VariableManagerDrawer.vue', () => ({ default: { template: '<div />' } }))

describe('DBX IDE session gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authAccount.value = null
    mocks.projects.mockResolvedValue({ list: [] })
    mocks.complete.mockResolvedValue([])
    mocks.environments.mockResolvedValue([])
  })

  it('loads the iframe only after the current project receives an IDE session', async () => {
    let complete!: () => void
    mocks.issue.mockImplementationOnce(() => new Promise<void>((resolve) => { complete = resolve }))
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    const wrapper = mount(DbxIdeView, { props: { projectId: 33 } })
    await flushPromises()
    expect(mocks.issue).toHaveBeenCalledWith(33)
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(false)
    complete()
    await flushPromises()
    expect(wrapper.find('[data-dbx-frame]').attributes('src')).toBe('/ide/')
    wrapper.unmount()
  })

  it('drops a stale iframe and ignores an old session response after account and project switch', async () => {
    let finishOld!: () => void
    mocks.projects.mockResolvedValueOnce({ list: [{ id: 33, name: '旧项目' }] })
      .mockResolvedValueOnce({ list: [{ id: 34, name: '新项目' }] })
    mocks.issue.mockResolvedValueOnce(undefined)
      .mockImplementationOnce(() => new Promise<void>((resolve) => { finishOld = resolve }))
      .mockResolvedValueOnce(undefined)
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    const wrapper = mount(DbxIdeView, { props: { projectId: 33 } })
    await flushPromises()
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(true)
    await wrapper.setProps({ projectId: 34 })
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(false)
    authAccount.value = { id: 2, username: 'zhangsan', role: 'developer' }
    await flushPromises()
    expect(wrapper.find('[data-dbx-project]').text()).toBe('新项目')
    expect(mocks.issue).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(false)
    finishOld()
    await flushPromises()
    expect(mocks.issue).toHaveBeenLastCalledWith(34)
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps the iframe closed when access is denied', async () => {
    mocks.issue.mockRejectedValueOnce(new Error('无数据源权限'))
    authAccount.value = { id: 2, username: 'zhangsan', role: 'developer' }
    const wrapper = mount(DbxIdeView, { props: { projectId: 33 } })
    await flushPromises()
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(false)
    expect(wrapper.find('[data-ide-session-error]').text()).toContain('无数据源权限')
    wrapper.unmount()
  })

  it('shows a retry action after a session failure and opens the frame after retry', async () => {
    mocks.issue.mockRejectedValueOnce(new Error('连接暂不可用')).mockResolvedValueOnce(undefined)
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    const wrapper = mount(DbxIdeView, { props: { projectId: 33 } })
    await flushPromises()
    expect(wrapper.find('[data-ide-session-error]').text()).toContain('连接暂不可用')
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(false)
    await wrapper.find('[data-ide-retry]').trigger('click')
    await flushPromises()
    expect(mocks.issue).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-ide-frame-loading]').exists()).toBe(true)
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(true)
    await wrapper.find('[data-dbx-frame]').trigger('load')
    expect(wrapper.find('[data-ide-frame-loading]').exists()).toBe(false)
    expect(wrapper.find('[data-ide-reload]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows frame failure and restarts the session when loading is retried', async () => {
    mocks.issue.mockResolvedValue(undefined)
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    const wrapper = mount(DbxIdeView, { props: { projectId: 33 } })
    await flushPromises()
    await wrapper.find('[data-dbx-frame]').trigger('error')
    expect(wrapper.find('[data-ide-session-error]').text()).toContain('页面请求失败')
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(false)
    await wrapper.find('[data-ide-retry]').trigger('click')
    await flushPromises()
    expect(mocks.issue).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-dbx-frame]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('uses a named environment choice for DBX variable resolution', async () => {
    mocks.issue.mockResolvedValue(undefined)
    mocks.environments.mockResolvedValue([{ id: 2, code: '188356094854656', name: 'default-env' }])
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
    const wrapper = mount(DbxIdeView, { props: { projectId: 33 } })
    await flushPromises()
    expect(wrapper.find('[data-dbx-environment]').text()).toBe('default-env')
    await wrapper.find('[data-environment-group]').setValue('2')
    await flushPromises()
    expect(wrapper.find('[data-dbx-environment]').text()).toBe('default-env')
    expect(mocks.complete).toHaveBeenLastCalledWith('', { projectId: 33, environmentGroupId: 2 })
    wrapper.unmount()
  })
})
