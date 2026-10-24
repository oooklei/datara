import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listWorkflowRunStats } = vi.hoisted(() => ({ listWorkflowRunStats: vi.fn() }))
vi.mock('../../services/rebuild/executionStatsApi', () => ({ listWorkflowRunStats }))

import WorkflowRunMonitor from '../WorkflowRunMonitor.vue'
import type { WorkflowRunStat } from '../../services/rebuild/executionStatsApi'

describe('workflow run monitor project scope', () => {
  beforeEach(() => {
    listWorkflowRunStats.mockReset()
    listWorkflowRunStats.mockResolvedValue({ items: [] })
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
})
