import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ind/ConsistencyCheckView.vue'

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
  return { ...actual, governanceApi: { listStandards: vi.fn(), checkStandard: vi.fn() } }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { governanceApi } from '../../services/rebuild/governanceApi'
import { listProjects } from '../../services/rebuild/projectApi'

const standard = {
  id: 9,
  projectId: 1,
  code: 'STD001',
  name: '金额非空',
  dataType: 'decimal',
  expression: 'not_null',
  description: '',
  status: 'draft' as const,
  createdAt: null,
  updatedAt: null,
}

const checkResult = {
  standardId: 9,
  code: 'STD001',
  passed: true,
  engine: 'structural',
  findings: [],
  checkedAt: null,
}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/ind/consistency 一致性检查页（增量 14）', () => {
  it('renders project picker and skips the standard query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-consistency-result]').exists()).toBe(false)
    expect(governanceApi.listStandards).not.toHaveBeenCalled()
  })

  it('loads standards for the route project and enables the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listStandards).toHaveBeenCalledWith(1)
    expect(w.find('[data-standard-select]').exists()).toBe(true)
    expect(w.find('[data-standard-select]').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-pending]').exists()).toBe(true)
  })

  it('runs the check for the selected standard and renders the result table', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    vi.mocked(governanceApi.checkStandard).mockResolvedValue([checkResult])
    const w = mount(View)
    await flushPromises()
    await w.find('[data-standard-select]').setValue('9')
    await w.find('button[type="button"]').trigger('click')
    await flushPromises()
    expect(governanceApi.checkStandard).toHaveBeenCalledWith(1, { standardId: 9 })
    expect(w.find('[data-consistency-result]').exists()).toBe(true)
    expect(w.find('[data-consistency-result]').text()).toContain('通过')
  })

  it('opens the result detail drawer and navigates to the indicator list', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    vi.mocked(governanceApi.checkStandard).mockResolvedValue([checkResult])
    const w = mount(View)
    await flushPromises()
    await w.find('[data-standard-select]').setValue('9')
    await w.find('button[type="button"]').trigger('click')
    await flushPromises()
    await w.find('[data-consistency-result] tbody button').trigger('click')
    expect(w.find('[role=dialog]').exists()).toBe(true)
    await w.find('[data-goto-list]').trigger('click')
    expect(router.push).toHaveBeenCalledWith('/ind/list')
  })

  it('surfaces backend errors without dropping the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockRejectedValue(
      Object.assign(new Error('standard list failed'), { code: 4041 }),
    )
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('standard list failed')
    expect(w.find('[data-project-select]').exists()).toBe(true)
  })
})
