import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ind/IndicatorListView.vue'

const router = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => router.route, useRouter: () => ({ push: router.push }) }))

vi.mock('../../services/rebuild/governanceApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/governanceApi')>(
      '../../services/rebuild/governanceApi',
    )
  return { ...actual, governanceApi: { listMetrics: vi.fn(), createMetric: vi.fn() } }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { governanceApi } from '../../services/rebuild/governanceApi'
import { listProjects } from '../../services/rebuild/projectApi'

const metric = {
  id: 5,
  projectId: 1,
  code: 'GMV',
  name: '成交总额',
  formula: 'sum(amount)',
  description: '',
  status: 'active' as const,
  createdAt: null,
  updatedAt: null,
}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/ind/list 指标目录页（增量 14）', () => {
  it('renders project picker and skips the metric query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-ind-list]').exists()).toBe(false)
    expect(governanceApi.listMetrics).not.toHaveBeenCalled()
  })

  it('lists metrics for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 1, list: [metric] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listMetrics).toHaveBeenCalledWith(1)
    expect(w.find('[data-ind-list]').exists()).toBe(true)
    expect(w.find('[data-ind-list]').text()).toContain('GMV')
  })

  it('creates a metric through the dialog and reloads the list', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 1, list: [metric] })
    vi.mocked(governanceApi.createMetric).mockResolvedValue(metric)
    const w = mount(View)
    await flushPromises()
    await w.find('.ind-actions button').trigger('click')
    const inputs = w.findAll('form[role=dialog] input')
    await inputs[0]!.setValue('GMV')
    await inputs[1]!.setValue('成交总额')
    await w.find('form[role=dialog] textarea').setValue('sum(amount)')
    await inputs[2]!.setValue('成交额口径')
    await w.find('form[role=dialog]').trigger('submit')
    await flushPromises()
    expect(governanceApi.createMetric).toHaveBeenCalledWith(1, {
      code: 'GMV',
      name: '成交总额',
      formula: 'sum(amount)',
      description: '成交额口径',
      status: 'draft',
    })
    expect(governanceApi.listMetrics).toHaveBeenCalledTimes(2)
  })

  it('surfaces backend errors without dropping the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockRejectedValue(
      Object.assign(new Error('metric list failed'), { code: 4041 }),
    )
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('metric list failed')
    expect(w.find('[data-project-select]').exists()).toBe(true)
  })

  it('preserves project context in consistency and board navigation', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 1, list: [metric] })
    const w = mount(View)
    await flushPromises()
    await w.find('.tbl-toolbar button').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ path: '/ind/consistency', query: { projectId: '1' } })
    await w.find('[data-ind-list] tbody tr button:last-child').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ path: '/ind/board', query: { projectId: '1' } })
  })
})
