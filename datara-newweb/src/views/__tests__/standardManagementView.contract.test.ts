import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../std/StandardManagementView.vue'

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
  return {
    ...actual,
    governanceApi: { listStandards: vi.fn(), createStandard: vi.fn(), checkStandard: vi.fn() },
  }
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
  description: '金额字段非空',
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

describe('/std/element 标准管理页（增量 14）', () => {
  it('renders project picker and skips the standard query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-std-list]').exists()).toBe(false)
    expect(governanceApi.listStandards).not.toHaveBeenCalled()
  })

  it('lists standards for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listStandards).toHaveBeenCalledWith(1)
    expect(w.find('[data-std-list]').exists()).toBe(true)
    expect(w.find('[data-std-list]').text()).toContain('STD001')
  })

  it('creates a standard through the dialog and reloads the list', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    vi.mocked(governanceApi.createStandard).mockResolvedValue(standard)
    const w = mount(View)
    await flushPromises()
    await w.find('.std-actions button').trigger('click')
    const inputs = w.findAll('form[role=dialog] input')
    await inputs[0]!.setValue('STD001')
    await inputs[1]!.setValue('金额非空')
    await inputs[2]!.setValue('decimal')
    await inputs[3]!.setValue('not_null')
    await inputs[4]!.setValue('金额字段非空')
    await w.find('form[role=dialog]').trigger('submit')
    await flushPromises()
    expect(governanceApi.createStandard).toHaveBeenCalledWith(1, {
      code: 'STD001',
      name: '金额非空',
      dataType: 'decimal',
      expression: 'not_null',
      description: '金额字段非空',
      status: 'draft',
    })
    expect(governanceApi.listStandards).toHaveBeenCalledTimes(2)
  })

  it('runs the structural check for the clicked standard', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    vi.mocked(governanceApi.checkStandard).mockResolvedValue([checkResult])
    const w = mount(View)
    await flushPromises()
    await w.find('[data-std-list] button').trigger('click')
    await flushPromises()
    expect(governanceApi.checkStandard).toHaveBeenCalledWith(1, { standardId: 9 })
    expect(w.find('[data-check-result]').text()).toContain('structural')
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

  it('invalidates an in-flight check when the project changes', async () => {
    let resolveCheck!: (value: typeof checkResult[]) => void
    vi.mocked(listProjects).mockResolvedValue({ total: 2, list: [{ id: 1, name: 'P1' }, { id: 2, name: 'P2' }] })
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 1, list: [standard] })
    vi.mocked(governanceApi.checkStandard).mockImplementation(() => new Promise((resolve) => { resolveCheck = resolve }))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-project-select]').setValue('1')
    await flushPromises()
    await w.find('[data-std-list] button').trigger('click')
    await w.find('[data-project-select]').setValue('2')
    await flushPromises()
    resolveCheck([checkResult])
    await flushPromises()
    expect(w.find('[data-check-result]').exists()).toBe(false)
  })
})
