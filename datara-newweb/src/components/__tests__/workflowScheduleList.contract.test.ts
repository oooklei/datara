import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listWorkflowSchedules, setWorkflowScheduleOnline, success, error } = vi.hoisted(() => ({
  listWorkflowSchedules: vi.fn(),
  setWorkflowScheduleOnline: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('../../services/rebuild/orchestrationApi', () => ({
  orchestrationApi: { listWorkflowSchedules, setWorkflowScheduleOnline },
}))
vi.mock('element-plus', () => ({ ElMessage: { success, error } }))

import WorkflowScheduleList from '../WorkflowScheduleList.vue'

const row = {
  id: 7,
  workflowDefinitionCode: 88,
  workflowDefinitionName: 'orders',
  crontab: '0 0 * * * ?',
  timezoneId: 'Asia/Shanghai',
  startTime: null,
  endTime: null,
  releaseState: 'OFFLINE',
}

describe('workflow schedule list', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listWorkflowSchedules.mockResolvedValue({ list: [row], total: 1, pageNo: 1, pageSize: 10 })
    setWorkflowScheduleOnline.mockResolvedValue({ ok: true })
  })

  it('lists the project schedule, opens its workflow, and toggles its state', async () => {
    const wrapper = mount(WorkflowScheduleList, { props: { projectId: 7 } })
    await flushPromises()
    expect(listWorkflowSchedules).toHaveBeenCalledWith(7, 1, 10)
    expect(wrapper.get('[data-schedule-row="7"]').text()).toContain('orders')

    await wrapper.get('[data-schedule-edit]').trigger('click')
    expect(wrapper.emitted('edit')?.[0]).toEqual([88, 'orders'])
    await wrapper.get('[data-schedule-toggle]').trigger('click')
    await flushPromises()
    expect(setWorkflowScheduleOnline).toHaveBeenCalledWith(7, 7, true)
    expect(listWorkflowSchedules).toHaveBeenCalledTimes(2)
    expect(success).toHaveBeenCalledOnce()
  })

  it('discards a previous project response after switching projects', async () => {
    let resolveOld!: (value: unknown) => void
    listWorkflowSchedules
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce({ list: [{ ...row, id: 9, workflowDefinitionName: 'new project' }], total: 1 })
    const wrapper = mount(WorkflowScheduleList, { props: { projectId: 7 } })
    await wrapper.setProps({ projectId: 8 })
    await flushPromises()
    resolveOld({ list: [row], total: 1 })
    await flushPromises()
    expect(wrapper.text()).toContain('new project')
    expect(wrapper.text()).not.toContain('orders')
  })
})
