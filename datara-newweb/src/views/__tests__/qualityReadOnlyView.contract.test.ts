import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../qc/QualityReadOnlyView.vue'

const listProjects = vi.hoisted(() => vi.fn())
const listExceptions = vi.hoisted(() => vi.fn())
const listReports = vi.hoisted(() => vi.fn())
const listAlarmPolicies = vi.hoisted(() => vi.fn())

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

vi.mock('../../services/rebuild/projectApi', () => ({ listProjects }))
vi.mock('../../services/rebuild/governanceApi', () => ({
  governanceApi: { listExceptions, listReports, listAlarmPolicies },
}))

describe('quality read-only views', () => {
  beforeEach(() => {
    listProjects.mockReset()
    listExceptions.mockReset()
    listReports.mockReset()
    listAlarmPolicies.mockReset()
    listProjects.mockResolvedValue({ total: 2, list: [{ id: 7, name: '质量项目' }, { id: 11, name: '项目工作区' }] })
    listExceptions.mockResolvedValue({ total: 1, list: [{ id: 1, target: 'orders', status: 'open', hitCount: 2, sampleSql: 'select 1' }] })
    listReports.mockResolvedValue({ total: 0, list: [] })
    listAlarmPolicies.mockResolvedValue({ total: 0, list: [] })
  })

  it('selects the first authorized project and renders exception data', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(View, { props: { kind: 'exceptions' }, global: { plugins: [router] } })
    await flushPromises()

    expect(listExceptions).toHaveBeenCalledWith(7, 1, 50, undefined)
    expect(wrapper.find('[data-quality-view="exceptions"]').exists()).toBe(true)
    expect(wrapper.find('[data-quality-table]').text()).toContain('orders')
  })

  it('prefers the project route param over a conflicting query project', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/p/:projectId/meta', component: { template: '<div />' } }],
    })
    await router.push('/p/11/meta?projectId=7')
    await router.isReady()
    mount(View, { props: { kind: 'exceptions' }, global: { plugins: [router] } })
    await flushPromises()

    expect(listExceptions).toHaveBeenCalledWith(11, 1, 50, undefined)
  })

  it('uses the query project when no route param is present', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/?projectId=11')
    await router.isReady()
    mount(View, { props: { kind: 'exceptions' }, global: { plugins: [router] } })
    await flushPromises()

    expect(listExceptions).toHaveBeenCalledWith(11, 1, 50, undefined)
  })

  it('keeps the latest project request loading and ignores an older successful response', async () => {
    const oldRequest = deferred<{ total: number; list: Array<Record<string, unknown>> }>()
    const latestRequest = deferred<{ total: number; list: Array<Record<string, unknown>> }>()
    listExceptions.mockImplementationOnce(() => oldRequest.promise).mockImplementationOnce(() => latestRequest.promise)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(View, { props: { kind: 'exceptions' }, global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('[data-project-select]').setValue('11')
    oldRequest.resolve({ total: 99, list: [{ id: 70, target: 'stale-project' }] })
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('stale-project')

    latestRequest.resolve({ total: 1, list: [{ id: 110, target: 'latest-project' }] })
    await flushPromises()
    expect(wrapper.text()).toContain('latest-project')
    expect(wrapper.find('footer').exists()).toBe(false)
  })

  it('ignores an older kind request error after the latest kind succeeds', async () => {
    const oldRequest = deferred<{ total: number; list: Array<Record<string, unknown>> }>()
    const latestRequest = deferred<{ total: number; list: Array<Record<string, unknown>> }>()
    listExceptions.mockImplementationOnce(() => oldRequest.promise)
    listReports.mockImplementationOnce(() => latestRequest.promise)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(View, { props: { kind: 'exceptions' }, global: { plugins: [router] } })
    await flushPromises()

    await wrapper.setProps({ kind: 'reports' })
    latestRequest.resolve({ total: 1, list: [{ id: 9, title: 'latest-report', content: {} }] })
    await flushPromises()
    oldRequest.reject(new Error('stale exception failure'))
    await flushPromises()

    expect(wrapper.find('[data-quality-view="reports"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('latest-report')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('ignores a late page-two response after returning to page one', async () => {
    const stalePageTwo = deferred<{ total: number; list: Array<Record<string, unknown>> }>()
    const latestPageOne = deferred<{ total: number; list: Array<Record<string, unknown>> }>()
    listExceptions
      .mockResolvedValueOnce({ total: 100, list: [{ id: 1, target: 'initial-page-one' }] })
      .mockImplementationOnce(() => stalePageTwo.promise)
      .mockImplementationOnce(() => latestPageOne.promise)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(View, { props: { kind: 'exceptions' }, global: { plugins: [router] } })
    await flushPromises()

    await wrapper.findAll('footer button')[1].trigger('click')
    await wrapper.findAll('footer button')[0].trigger('click')
    latestPageOne.resolve({ total: 1, list: [{ id: 2, target: 'latest-page-one' }] })
    await flushPromises()
    stalePageTwo.resolve({ total: 100, list: [{ id: 3, target: 'stale-page-two' }] })
    await flushPromises()

    expect(wrapper.text()).toContain('latest-page-one')
    expect(wrapper.text()).not.toContain('stale-page-two')
    expect(wrapper.find('footer').exists()).toBe(false)
  })
})
