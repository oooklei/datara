import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../qc/QualityTaskView.vue'

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
    governanceApi: { listRules: vi.fn(), createRule: vi.fn(), runRule: vi.fn(), listRuns: vi.fn() },
  }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { governanceApi } from '../../services/rebuild/governanceApi'
import { listProjects } from '../../services/rebuild/projectApi'

const run = {
  id: 3,
  assetId: 9,
  ruleId: 1,
  status: 'succeeded' as const,
  checkedRows: 0,
  successRows: 0,
  failedRows: 0,
  skippedRows: 0,
  summary: {
    engine: 'structural' as const,
    message: 'structural predicate validation only; row-level sampling requires a bound datasource',
    issues: ['expression contains forbidden token: drop'],
  },
  generatedAt: '2026-10-22T10:05:00Z',
}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/qc/task 检查任务页（IMPL-v4-07）', () => {
  it('renders project picker and skips the run query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(false)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-run-list]').exists()).toBe(false)
    expect(governanceApi.listRuns).not.toHaveBeenCalled()
  })

  it('lists runs for the project carried by route query', async () => {
    router.route.query.projectId = '1'
    vi.mocked(governanceApi.listRuns).mockResolvedValue({ total: 1, list: [run] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listRuns).toHaveBeenCalledWith(1)
    expect(w.find('[data-run-list]').exists()).toBe(true)
    expect(w.find('[data-run-id="3"]').text()).toContain('#1')
    expect(w.find('[data-status]').attributes('data-status')).toBe('succeeded')
    expect(w.find('[data-summary]').text()).toContain('structural')
    expect(w.find('[data-summary]').text()).toContain('drop')
  })

  it('reports structural semantics and never fabricates row-level counts', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listRuns).mockResolvedValue({ total: 1, list: [run] })
    const w = mount(View)
    await flushPromises()
    const text = w.text()
    expect(text).toContain('结构校验记录的计数为 0')
    // structural 红线：页面不得出现行级四字段计数
    expect(text).not.toMatch(/检查行数|成功行|失败行|跳过行/)
    expect(w.find('[data-run-list]').text()).not.toMatch(/ checked| success| failed| skipped/)
  })

  it('surfaces backend errors without rendering an empty-shell table', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listRuns).mockRejectedValue(Object.assign(new Error('permission denied'), { code: 1003 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('permission denied')
    expect(w.find('[data-run-list]').exists()).toBe(false)
    expect(w.find('[data-empty]').exists()).toBe(false)
  })
})
