import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const {
  getWorkflowRunStat,
  listWorkflowRunStats,
  getWorkflowRunLogs,
  cancelWorkflowRun,
  rerunWorkflowInstance,
  messageSuccess,
  messageError,
  messageBoxConfirm,
} = vi.hoisted(() => ({
  getWorkflowRunStat: vi.fn(),
  listWorkflowRunStats: vi.fn(),
  getWorkflowRunLogs: vi.fn(),
  cancelWorkflowRun: vi.fn(),
  rerunWorkflowInstance: vi.fn(),
  messageSuccess: vi.fn(),
  messageError: vi.fn(),
  messageBoxConfirm: vi.fn(),
}))
vi.mock('../../services/rebuild/executionStatsApi', () => ({
  getWorkflowRunStat,
  listWorkflowRunStats,
  getWorkflowRunLogs,
  cancelWorkflowRun,
  rerunWorkflowInstance,
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: messageSuccess, error: messageError },
  ElMessageBox: { confirm: messageBoxConfirm },
}))

import WorkflowRunMonitor from '../WorkflowRunMonitor.vue'
import type { WorkflowRunReconcileDetail, WorkflowRunStat } from '../../services/rebuild/executionStatsApi'

describe('workflow run monitor project scope', () => {
  beforeEach(() => {
    listWorkflowRunStats.mockReset()
    listWorkflowRunStats.mockResolvedValue({ items: [] })
    getWorkflowRunStat.mockReset()
    getWorkflowRunStat.mockResolvedValue({ details: [], detail_total: 0 })
    getWorkflowRunLogs.mockReset()
    getWorkflowRunLogs.mockResolvedValue({ instance_id: 0, workflow_id: 0, instance_type: 'FORMAL', status: 'SUCCEEDED', logs: [] })
    cancelWorkflowRun.mockReset()
    rerunWorkflowInstance.mockReset()
    messageSuccess.mockReset()
    messageError.mockReset()
    messageBoxConfirm.mockReset()
    messageBoxConfirm.mockResolvedValue('confirm')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads immediately and reloads when the kept-alive project changes', async () => {
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    expect(listWorkflowRunStats).toHaveBeenCalledWith(7)
    await wrapper.setProps({ projectId: 8 })
    await flushPromises()
    expect(listWorkflowRunStats).toHaveBeenLastCalledWith(8)
    expect(listWorkflowRunStats).toHaveBeenCalledTimes(2)
  })

  it('renders authoritative success/failure/skipped counters', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ items: [{ id: 1, workflow_id: 3, workflow_instance_id: 9, instance_type: 'WORKFLOW', status: 'SUCCEEDED', success_count: 4, failure_count: 1, skipped_count: 2, total_count: 7, started_at: '2026-10-25T00:00:00Z', dag_name: 'daily' }] })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    expect(wrapper.find('tbody').text()).toContain('daily')
    expect(wrapper.find('tbody').text()).toContain('4')
    expect(wrapper.find('tbody').text()).toContain('1')
    expect(wrapper.find('tbody').text()).toContain('2')
  })

  it('filters the monitor by the required TRIAL, FORMAL and STREAM instance types', async () => {
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    const filter = wrapper.get('[data-run-instance-type]')
    expect(filter.findAll('option').map((option) => option.attributes('value'))).toEqual(['', 'TRIAL', 'FORMAL', 'STREAM'])
    await filter.setValue('STREAM')
    await flushPromises()
    expect(listWorkflowRunStats).toHaveBeenLastCalledWith(7, { instanceType: 'STREAM' })
  })

  it('pages through all persisted run statistics instead of truncating at fifty rows', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ total: 51, items: [{ id: 1, workflow_id: 3, workflow_instance_id: 9, instance_type: 'FORMAL', status: 'SUCCEEDED', success_count: 1, failure_count: 0, skipped_count: 0, total_count: 1, started_at: '2026-10-25T00:00:00Z' }] })
      .mockResolvedValueOnce({ total: 51, items: [{ id: 2, workflow_id: 4, workflow_instance_id: 10, instance_type: 'FORMAL', status: 'SUCCEEDED', success_count: 1, failure_count: 0, skipped_count: 0, total_count: 1, started_at: '2026-10-25T01:00:00Z' }] })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    expect(wrapper.get('[data-run-next]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-run-next]').trigger('click')
    await flushPromises()
    expect(listWorkflowRunStats).toHaveBeenLastCalledWith(7, { offset: 50, limit: 50 })
  })

  it('discards a late response from the previous project scope', async () => {
    let resolveOld!: (value: { items: WorkflowRunStat[] }) => void
    const oldResponse = new Promise<{ items: WorkflowRunStat[] }>((resolve) => { resolveOld = resolve })
    listWorkflowRunStats.mockReturnValueOnce(oldResponse).mockResolvedValueOnce({ items: [{ id: 2, workflow_id: 8, workflow_instance_id: 10, instance_type: 'WORKFLOW', status: 'SUCCEEDED', success_count: 8, failure_count: 0, skipped_count: 0, total_count: 8, started_at: '2026-10-25T01:00:00Z', dag_name: 'project-8' }] })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await wrapper.setProps({ projectId: 8 })
    await flushPromises()
    expect(wrapper.find('tbody').text()).toContain('project-8')
    resolveOld({ items: [{ id: 1, workflow_id: 7, workflow_instance_id: 9, instance_type: 'WORKFLOW', status: 'SUCCEEDED', success_count: 7, failure_count: 0, skipped_count: 0, total_count: 7, started_at: '2026-10-25T00:00:00Z', dag_name: 'project-7' }] })
    await flushPromises()
    expect(wrapper.find('tbody').text()).toContain('project-8')
    expect(wrapper.find('tbody').text()).not.toContain('project-7')
  })

  it('drills into persisted table-level reconciliation counts', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ items: [{ id: 5, workflow_id: 3, workflow_instance_id: 9, instance_type: 'FORMAL', status: 'SUCCEEDED', source_count: 12, target_count: 11, success_count: 10, failure_count: 1, skipped_count: 0, total_count: 11, started_at: '2026-10-25T00:00:00Z', dag_name: 'daily' }] })
    getWorkflowRunStat.mockResolvedValueOnce({ details: [{ id: 8, source_object: 'ods.orders', target_object: 'dwd.orders', source_count: 12, target_count: 11, success_count: 10, failure_count: 1, skipped_count: 0, difference_count: -1 }], detail_total: 1 })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    await wrapper.get('button[aria-expanded="false"]').trigger('click')
    await flushPromises()
    expect(getWorkflowRunStat).toHaveBeenCalledWith(7, 5)
    expect(wrapper.get('[data-run-stat-details]').text()).toContain('ods.orders')
    expect(wrapper.get('[data-run-stat-details]').text()).toContain('dwd.orders')
    expect(wrapper.get('[data-run-stat-details]').text()).toContain('10')
  })

  it('drops an in-flight detail response when project scope changes', async () => {
    let resolveDetail!: (value: { details: WorkflowRunReconcileDetail[]; detail_total: number }) => void
    const detailResponse = new Promise<{ details: WorkflowRunReconcileDetail[]; detail_total: number }>((resolve) => { resolveDetail = resolve })
    listWorkflowRunStats.mockResolvedValueOnce({ items: [{ id: 5, workflow_id: 3, workflow_instance_id: 9, instance_type: 'FORMAL', status: 'SUCCEEDED', success_count: 1, failure_count: 0, skipped_count: 0, total_count: 1, started_at: '2026-10-25T00:00:00Z' }] }).mockResolvedValueOnce({ items: [] })
    getWorkflowRunStat.mockReturnValueOnce(detailResponse)
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    await wrapper.get('button[aria-expanded="false"]').trigger('click')
    await wrapper.setProps({ projectId: 8 })
    resolveDetail({ details: [{ id: 8, source_object: 'old.source', target_object: 'old.target', success_count: 1, failure_count: 0, skipped_count: 0 }], detail_total: 1 })
    await flushPromises()
    expect(wrapper.find('[data-run-stat-details]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('old.source')
  })

  /* ---- D8 下钻契约（G02）：工作台 KPI/最近实例 ?status=/?runId= 透传 ---- */

  it('applies the D8 initial status filter to the backend list query', async () => {
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7, initialStatus: 'SUCCEEDED' } })
    await flushPromises()
    expect(wrapper.get('[data-run-status]').element as HTMLSelectElement).toBeTruthy()
    expect((wrapper.get('[data-run-status]').element as HTMLSelectElement).value).toBe('SUCCEEDED')
    expect(listWorkflowRunStats).toHaveBeenLastCalledWith(7, { status: 'SUCCEEDED' })
  })

  it('locates a single drilled run by id instead of listing', async () => {
    getWorkflowRunStat.mockResolvedValueOnce({ id: 9, workflow_id: 3, workflow_instance_id: 12, instance_type: 'FORMAL', status: 'FAILED', success_count: 0, failure_count: 2, skipped_count: 0, total_count: 2, started_at: '2026-10-26T00:00:00Z', dag_name: 'daily', details: [], detail_total: 0 })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7, initialRunId: 9 } })
    await flushPromises()
    expect(getWorkflowRunStat).toHaveBeenCalledWith(7, 9)
    expect(listWorkflowRunStats).not.toHaveBeenCalled()
    expect(wrapper.find('tbody').text()).toContain('daily')
    expect(wrapper.find('[data-run-pagination]').exists()).toBe(false)
  })

  it('reloads when the D8 drill props change while kept alive', async () => {
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    listWorkflowRunStats.mockClear()
    await wrapper.setProps({ initialStatus: 'FAILED' })
    await flushPromises()
    expect(listWorkflowRunStats).toHaveBeenLastCalledWith(7, { status: 'FAILED' })
    await wrapper.setProps({ initialStatus: undefined, initialRunId: 12 })
    getWorkflowRunStat.mockResolvedValueOnce({ id: 12, workflow_id: 3, workflow_instance_id: 15, instance_type: 'FORMAL', status: 'SUCCEEDED', success_count: 1, failure_count: 0, skipped_count: 0, total_count: 1, started_at: '2026-10-26T01:00:00Z', details: [], detail_total: 0 })
    await flushPromises()
    expect(getWorkflowRunStat).toHaveBeenLastCalledWith(7, 12)
  })

  /* ---- T6 运行监控日志通道（审计弹窗 #9 LogPanel）：3s 轮询 / 终态即停 / 停止与重跑 ---- */

  function rowOf(overrides: Partial<WorkflowRunStat>): WorkflowRunStat {
    return { id: 5, workflow_id: 3, workflow_instance_id: 9, instance_type: 'FORMAL', status: 'SUCCEEDED', success_count: 0, failure_count: 0, skipped_count: 0, total_count: 0, started_at: '2026-10-26T00:00:00Z', ...overrides }
  }

  it('polls run logs every three seconds while the instance is running', async () => {
    // 仅 fake interval：flushPromises 依赖 setImmediate/setTimeout，必须保持真实
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    listWorkflowRunStats.mockResolvedValueOnce({ items: [rowOf({ status: 'RUNNING' })] })
    getWorkflowRunLogs.mockResolvedValue({ instance_id: 9, workflow_id: 3, instance_type: 'FORMAL', status: 'RUNNING', logs: [{ task_instance_id: 1, attempt_no: 1, level: 'INFO', message: 'run started' }] })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    await wrapper.get('button[aria-expanded="false"]').trigger('click')
    await flushPromises()
    expect(getWorkflowRunLogs).toHaveBeenCalledWith(7, 9)
    expect(getWorkflowRunLogs).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-run-logs-body]').text()).toContain('run started')
    expect(wrapper.find('[data-run-logs-live]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(getWorkflowRunLogs).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(getWorkflowRunLogs).toHaveBeenCalledTimes(3)
  })

  it('fetches logs once and stops polling once the run reaches a terminal state', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    listWorkflowRunStats.mockResolvedValueOnce({ items: [rowOf({ status: 'FAILED' })] })
    getWorkflowRunLogs.mockResolvedValue({ instance_id: 9, workflow_id: 3, instance_type: 'FORMAL', status: 'FAILED', logs: [{ task_instance_id: 1, attempt_no: 1, level: 'ERROR', message: 'boom' }] })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    await wrapper.get('button[aria-expanded="false"]').trigger('click')
    await flushPromises()
    expect(getWorkflowRunLogs).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-run-logs-live]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(9000)
    await flushPromises()
    expect(getWorkflowRunLogs).toHaveBeenCalledTimes(1)
  })

  it('stops a running instance after confirmation and reloads the monitor', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ items: [rowOf({ status: 'RUNNING' })] })
    cancelWorkflowRun.mockResolvedValue({ instance_id: 9, status: 'CANCELLED' })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    expect(wrapper.get('[data-run-stop]').text()).toBe('停止')
    await wrapper.get('[data-run-stop]').trigger('click')
    await flushPromises()
    expect(messageBoxConfirm).toHaveBeenCalledTimes(1)
    expect(cancelWorkflowRun).toHaveBeenCalledWith(7, 9)
    expect(messageSuccess).toHaveBeenCalledTimes(1)
    expect(listWorkflowRunStats).toHaveBeenCalledTimes(2)
  })

  it('keeps the run untouched when the stop confirmation is dismissed', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ items: [rowOf({ status: 'RUNNING' })] })
    messageBoxConfirm.mockRejectedValueOnce('cancel')
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    await wrapper.get('[data-run-stop]').trigger('click')
    await flushPromises()
    expect(cancelWorkflowRun).not.toHaveBeenCalled()
    expect(listWorkflowRunStats).toHaveBeenCalledTimes(1)
  })

  it('offers rerun only for finished TRIAL or STREAM runs and posts the rerun request', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ items: [
      rowOf({ id: 1, workflow_id: 3, workflow_instance_id: 9, instance_type: 'TRIAL', status: 'FAILED' }),
      rowOf({ id: 2, workflow_id: 4, workflow_instance_id: 10, instance_type: 'FORMAL', status: 'SUCCEEDED' }),
      rowOf({ id: 3, workflow_id: 5, workflow_instance_id: 11, instance_type: 'STREAM', status: 'RUNNING' }),
    ] })
    rerunWorkflowInstance.mockResolvedValue({ instance_id: 20, status: 'PENDING' })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()
    const rerunButtons = wrapper.findAll('[data-run-rerun]')
    // TRIAL FAILED 可重跑；FORMAL 终态不提供重跑（无 published version_id 可还原）；STREAM RUNNING 仅停止
    expect(rerunButtons).toHaveLength(1)
    expect(wrapper.findAll('[data-run-stop]')).toHaveLength(1)
    await rerunButtons[0]!.trigger('click')
    await flushPromises()
    expect(rerunWorkflowInstance).toHaveBeenCalledWith(7, 3, 'TRIAL')
    expect(messageSuccess).toHaveBeenCalledTimes(1)
  })

  it('D13 列表搜索：关键字对当前页运行记录前端过滤，不触发后端', async () => {
    listWorkflowRunStats.mockResolvedValueOnce({ items: [
      rowOf({ id: 1, dag_name: 'daily-etl' }),
      rowOf({ id: 2, workflow_id: 4, workflow_instance_id: 10, dag_name: 'nightly-load' }),
    ] })
    const wrapper = mount(WorkflowRunMonitor, { props: { projectId: 7 } })
    await flushPromises()

    expect(wrapper.findAll('tbody > tr')).toHaveLength(2)
    await wrapper.get('[data-run-keyword]').setValue('daily')
    const rows = wrapper.findAll('tbody > tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('daily-etl')
    expect(listWorkflowRunStats).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-run-keyword]').setValue('zzz')
    expect(wrapper.find('tbody').text()).toContain('无匹配运行记录')
  })
})
