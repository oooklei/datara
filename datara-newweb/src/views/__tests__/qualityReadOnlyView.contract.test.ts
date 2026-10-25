import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../qc/QualityReadOnlyView.vue'

const listProjects = vi.hoisted(() => vi.fn())
const listExceptions = vi.hoisted(() => vi.fn())
const listReports = vi.hoisted(() => vi.fn())
const listAlarmPolicies = vi.hoisted(() => vi.fn())

vi.mock('../../services/rebuild/projectApi', () => ({ listProjects }))
vi.mock('../../services/rebuild/governanceApi', () => ({
  governanceApi: { listExceptions, listReports, listAlarmPolicies },
}))

describe('quality read-only views', () => {
  beforeEach(() => {
    listProjects.mockResolvedValue({ total: 1, list: [{ id: 7, name: '质量项目' }] })
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
})
