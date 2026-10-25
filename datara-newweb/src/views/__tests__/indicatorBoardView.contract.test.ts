import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ind/IndicatorBoardView.vue'

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
  return { ...actual, governanceApi: { listMetrics: vi.fn() } }
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

describe('/ind/board 指标看板页（增量 14）', () => {
  it('renders project picker and skips the metric query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-ind-board]').exists()).toBe(false)
    expect(governanceApi.listMetrics).not.toHaveBeenCalled()
  })

  it('renders definition cards with status anchors for the route project', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 1, list: [metric] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listMetrics).toHaveBeenCalledWith(1)
    expect(w.find('[data-ind-board]').exists()).toBe(true)
    expect(w.find('[data-ind-board]').text()).toContain('成交总额')
    expect(w.find('[data-status]').attributes('data-status')).toBe('active')
  })

  it('renders the empty state when the project has no metrics', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 0, list: [] })
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-ind-board]').exists()).toBe(false)
  })

  it('navigates to indicator list and consistency check from the toolbar links', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 1, list: [metric] })
    const w = mount(View)
    await flushPromises()
    await w.find('[data-goto-list]').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ path: '/ind/list', query: { projectId: '1' } })
    await w.find('[data-goto-consistency]').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ path: '/ind/consistency', query: { projectId: '1' } })
  })

  it('surfaces backend errors without dropping the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listMetrics).mockRejectedValue(
      Object.assign(new Error('metric board failed'), { code: 4041 }),
    )
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('metric board failed')
    expect(w.find('[data-project-select]').exists()).toBe(true)
  })
})
