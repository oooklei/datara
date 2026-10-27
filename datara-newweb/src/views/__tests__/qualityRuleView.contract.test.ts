import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../qc/QualityRuleView.vue'

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

const rule = {
  id: 1,
  assetId: 9,
  name: '主键非空',
  expression: 'id IS NOT NULL',
  severity: 'error' as const,
  enabled: true,
  createdAt: '2026-10-22T10:00:00Z',
  updatedAt: null,
}

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
    issues: [],
  },
  generatedAt: '2026-10-22T10:05:00Z',
}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/qc/rule 质量规则页（IMPL-v4-07）', () => {
  it('renders project picker and skips the rule query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-rule-list]').exists()).toBe(false)
    expect(governanceApi.listRules).not.toHaveBeenCalled()
  })

  it('lists rules for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listRules).mockResolvedValue({ total: 1, list: [rule] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listRules).toHaveBeenCalledWith(1)
    expect(w.find('[data-rule-list]').exists()).toBe(true)
    expect(w.find('[data-rule-id="1"]').text()).toContain('主键非空')
    expect(w.find('[data-severity]').attributes('data-severity')).toBe('error')
  })

  it('creates a rule through the dialog and reloads the list', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listRules).mockResolvedValue({ total: 0, list: [] })
    vi.mocked(governanceApi.createRule).mockResolvedValue({ ...rule, projectId: 1 })
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-create]').attributes('disabled')).toBeUndefined()

    await w.find('[data-create]').trigger('click')
    await w.find('[data-name]').setValue('主键非空')
    await w.find('[data-asset-input]').setValue('9')
    await w.find('[data-expr-input]').setValue('id IS NOT NULL')
    await w.find('[data-severity-select]').setValue('error')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(governanceApi.createRule).toHaveBeenCalledWith(1, {
      assetId: 9,
      name: '主键非空',
      expression: 'id IS NOT NULL',
      severity: 'error',
      enabled: true,
    })
    expect(w.find('[role=dialog]').exists()).toBe(false)
  })

  it('runs a rule and reports structural semantics without fabricating row-level counts', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listRules).mockResolvedValue({ total: 1, list: [rule] })
    vi.mocked(governanceApi.runRule).mockResolvedValue(run)
    const w = mount(View)
    await flushPromises()

    await w.find('[data-run]').trigger('click')
    await flushPromises()

    expect(governanceApi.runRule).toHaveBeenCalledWith(1, 1)
    // 执行后须刷新列表（reload → listRules 二次调用），避免展示陈旧状态
    expect(governanceApi.listRules).toHaveBeenCalledTimes(2)
    const text = w.find('[data-run-result]').text()
    expect(text).toContain('succeeded')
    expect(text).toContain('structural')
    // structural 红线：不得出现行级四字段计数（后端恒 0，前端不得虚构）
    expect(text).not.toMatch(/ checked| success| failed| skipped/)
    expect(w.find('[data-structural-note]').text()).toContain('行级四字段恒 0')
  })

  it('surfaces backend errors without dropping the list', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listRules).mockResolvedValue({ total: 1, list: [rule] })
    vi.mocked(governanceApi.runRule).mockRejectedValue(Object.assign(new Error('permission denied'), { code: 1003 }))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-run]').trigger('click')
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('permission denied')
    expect(w.find('[data-rule-list]').exists()).toBe(true)
  })
})
