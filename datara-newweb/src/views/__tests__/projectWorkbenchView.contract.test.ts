import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { pushSpy, loadDashboardSpy, setOptionSpy, disposeSpy } = vi.hoisted(() => ({
  pushSpy: vi.fn(),
  loadDashboardSpy: vi.fn(),
  setOptionSpy: vi.fn(),
  disposeSpy: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushSpy }) }))
vi.mock('../../services/rebuild/projectDashboard', () => ({ loadProjectDashboard: loadDashboardSpy }))
vi.mock('echarts', () => ({ init: () => ({ setOption: setOptionSpy, dispose: disposeSpy, resize: vi.fn() }) }))

import ProjectWorkbenchView from '../ProjectWorkbenchView.vue'

const dashboard = {
  workflowTypes: { normal: 1, sync: 1, stream: 1 },
  runTotals: { success: 13, failure: 1, skipped: 2, retry: 1, running: 1 },
  governance: { datasources: 4, resources: 7, assets: 20, standards: 6, metrics: 9, qualityRules: 5, openExceptions: 2 },
  dailyStats: [
    { workflowId: 1, runDate: '2026-10-26', successCount: 8, failureCount: 1, skippedCount: 2, retryCount: 1 },
    { workflowId: 2, runDate: '2026-10-27', successCount: 5, failureCount: 0, skippedCount: 0, retryCount: 0 },
  ],
  recentRuns: [
    { id: 9, workflow_id: 3, workflow_instance_id: 19, instance_type: 'STREAM', status: 'RUNNING', success_count: 3, failure_count: 0, skipped_count: 0, total_count: 3, started_at: '2026-10-27T10:00:00Z', dag_name: '电商实时订单流观摩样例' },
  ],
  partialFailures: [],
}

beforeEach(() => {
  pushSpy.mockReset()
  loadDashboardSpy.mockReset()
  setOptionSpy.mockReset()
  disposeSpy.mockReset()
})

describe('UX v3：项目工作台', () => {
  it('加载真实聚合并渲染双 KPI 带、三图和最近运行', async () => {
    loadDashboardSpy.mockResolvedValue(dashboard)
    const wrapper = mount(ProjectWorkbenchView, { props: { projectId: 33 } })
    await flushPromises()
    // §2 裁决 2：loadProjectDashboard 现接收 AbortSignal 作第二参数（协作式取消）
    expect(loadDashboardSpy).toHaveBeenCalledWith(33, expect.any(AbortSignal))
    expect(wrapper.findAll('[data-pipeline-kpi]')).toHaveLength(6)
    expect(wrapper.findAll('[data-governance-kpi]')).toHaveLength(7)
    expect(wrapper.text()).not.toContain('标签数量')
    expect(wrapper.findAll('[data-dashboard-chart]')).toHaveLength(3)
    expect(setOptionSpy).toHaveBeenCalledTimes(3)
    expect(wrapper.findAll('[data-recent-run]')).toHaveLength(1)
    expect(wrapper.text()).toContain('电商实时订单流观摩样例')
  })

  it('部分接口失败时保留可用数据并明确提示', async () => {
    loadDashboardSpy.mockResolvedValue({ ...dashboard, partialFailures: ['资产', '标准'] })
    const wrapper = mount(ProjectWorkbenchView, { props: { projectId: 33 } })
    await flushPromises()
    expect(wrapper.get('[data-partial-warning]').text()).toContain('资产、标准')
    expect(wrapper.findAll('[data-pipeline-kpi]')).toHaveLength(6)
  })

  it('聚合请求完全失败时提供重试入口', async () => {
    loadDashboardSpy.mockRejectedValueOnce(new Error('服务暂不可用')).mockResolvedValueOnce(dashboard)
    const wrapper = mount(ProjectWorkbenchView, { props: { projectId: 33 } })
    await flushPromises()
    expect(wrapper.get('[data-dashboard-error]').text()).toContain('服务暂不可用')
    await wrapper.get('[data-dashboard-retry]').trigger('click')
    await flushPromises()
    expect(loadDashboardSpy).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-dashboard-error]').exists()).toBe(false)
  })

  it('指标卡与最近运行进入对应业务页面', async () => {
    loadDashboardSpy.mockResolvedValue(dashboard)
    const wrapper = mount(ProjectWorkbenchView, { props: { projectId: 33 } })
    await flushPromises()
    await wrapper.get('[data-kpi-route="dag?tab=runs&status=SUCCEEDED"]').trigger('click')
    await wrapper.get('[data-recent-run]').trigger('click')
    await wrapper.get('[data-run-monitor]').trigger('click')
    expect(pushSpy).toHaveBeenNthCalledWith(1, '/p/33/dag?tab=runs&status=SUCCEEDED')
    expect(pushSpy).toHaveBeenNthCalledWith(2, '/p/33/dag?tab=runs&runId=9')
    expect(pushSpy).toHaveBeenNthCalledWith(3, '/p/33/dag?tab=runs')
  })
})
