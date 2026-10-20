/**
 * L3-06 组件测试：ProjectWorkbenchView 项目工作台页（A 组工作台承载）。
 * 覆盖：metrics 查询→展示闭环（workflow-result-stats 四计数表格）、加载/错误/空三态、
 * 快捷导航七段渲染与点击 push、导航区独立于 metrics 加载先渲染。
 * 依赖 mock：vue-router.useRouter（/p/:projectId/* 路由注册归 L3-03）、
 * metricsApi.createMetricsContract（R7 GREEN 收编件；契约层 13 例由
 * services/rebuild/__tests__/metricsApi.contract.test.ts 锁定，本文件不重复）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { pushSpy, statsSpy } = vi.hoisted(() => ({
  pushSpy: vi.fn(),
  statsSpy: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushSpy }),
}))

vi.mock('../../services/rebuild/metricsApi', () => ({
  createMetricsContract: () => ({ queryWorkflowResultStats: statsSpy }),
}))

import ProjectWorkbenchView from '../ProjectWorkbenchView.vue'

function mountView(props: { projectId: number } = { projectId: 9 }) {
  return mount(ProjectWorkbenchView, { props })
}

beforeEach(() => {
  pushSpy.mockClear()
  statsSpy.mockReset()
})

describe('L3-06 ProjectWorkbenchView 项目工作台页', () => {
  it('加载态：metrics 查询 pending 时渲染 role=status，且快捷导航已先渲染可交互', async () => {
    statsSpy.mockReturnValue(new Promise(() => {}))
    const w = mountView()
    expect(w.find('[role="status"]').exists()).toBe(true)
    expect(w.find('[data-loading]').exists()).toBe(true)
    const nav = w.find('[data-workbench-nav]')
    expect(nav.exists()).toBe(true)
    expect(nav.findAll('.nav-item')).toHaveLength(7)
  })

  it('metrics 查询→展示闭环：queryWorkflowResultStats(projectId, window) → 四计数表格逐行呈现', async () => {
    statsSpy.mockResolvedValue([
      { workflowId: 7, runDate: '2026-10-20', successCount: 5, failureCount: 1, skippedCount: 2, retryCount: 3 },
      { workflowId: 7, runDate: '2026-10-21', successCount: 8, failureCount: 0, skippedCount: 0, retryCount: 1 },
    ])
    const w = mountView()
    await flushPromises()
    expect(statsSpy).toHaveBeenCalledTimes(1)
    const [calledProjectId, calledWindow] = statsSpy.mock.calls[0] as unknown as [
      number,
      { from: string; to: string; offset: number; limit: number },
    ]
    expect(calledProjectId).toBe(9)
    expect(typeof calledWindow.from).toBe('string')
    expect(typeof calledWindow.to).toBe('string')
    expect(calledWindow.offset).toBe(0)
    expect(calledWindow.limit).toBe(50)
    expect(w.find('[data-metrics-table]').exists()).toBe(true)
    const rows = w.findAll('[data-metric-row]')
    expect(rows).toHaveLength(2)
    expect(rows[0].attributes('data-metric-row')).toBe('2026-10-20')
    expect(rows[0].text()).toContain('5')
    expect(rows[0].text()).toContain('1')
    expect(rows[0].text()).toContain('2')
    expect(rows[0].text()).toContain('3')
    expect(rows[1].attributes('data-metric-row')).toBe('2026-10-21')
  })

  it('metrics 空态：查询结果为空渲染 data-empty，不渲染表格', async () => {
    statsSpy.mockResolvedValue([])
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-metrics-table]').exists()).toBe(false)
    expect(w.find('[role="status"]').exists()).toBe(false)
  })

  it('metrics 错误态：查询 reject → role=alert 呈现错误信息，不渲染表格', async () => {
    statsSpy.mockRejectedValue(new Error('HTTP 500 /rebuild/metrics/workflow-result-stats'))
    const w = mountView()
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.find('[data-metrics-error]').text()).toContain('HTTP 500')
    expect(w.find('[data-metrics-table]').exists()).toBe(false)
  })

  it('快捷导航渲染：PRE §3.2 七段锚点齐全（dag/datasource/resources/ide/meta/dep/system）', () => {
    statsSpy.mockResolvedValue([])
    const w = mountView()
    for (const key of ['dag', 'datasource', 'resources', 'ide', 'meta', 'dep', 'system']) {
      expect(w.find(`[data-nav="${key}"]`).exists()).toBe(true)
    }
  })

  it('快捷导航点击 → router.push(/p/:projectId/<seg>)', async () => {
    statsSpy.mockResolvedValue([])
    const w = mountView()
    await w.find('[data-nav="dag"]').trigger('click')
    await w.find('[data-nav="system"]').trigger('click')
    expect(pushSpy).toHaveBeenCalledTimes(2)
    expect(pushSpy).toHaveBeenNthCalledWith(1, '/p/9/dag')
    expect(pushSpy).toHaveBeenNthCalledWith(2, '/p/9/system')
  })

  it('projectId 透传：不同 props 下查询与导航均携带该项目 id', async () => {
    statsSpy.mockResolvedValue([])
    const w = mountView({ projectId: 42 })
    await flushPromises()
    expect(statsSpy.mock.calls[0][0]).toBe(42)
    await w.find('[data-nav="meta"]').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/p/42/meta')
  })
})
