import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { saveDependency, success, warning } = vi.hoisted(() => ({
  saveDependency: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('../../services/rebuild/dependencyApi', () => ({
  createDependencyContract: () => ({ saveDependency }),
}))
vi.mock('element-plus', () => ({ ElMessage: { success, warning, error: vi.fn() } }))

import DependencyNodeEditor from '../DependencyNodeEditor.vue'

describe('DependencyNodeEditor contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    saveDependency.mockResolvedValue({ saved: true, version: 1, configId: 41 })
  })

  it('saves an exact dependency config identity onto the DAG node params', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: { projectId: 7, workflowId: 12, taskId: 'dep_1', modelValue: { upstream_workflow_id: '9' } },
    })

    await wrapper.get('[data-test="save-dependency"]').trigger('click')
    await flushPromises()

    expect(saveDependency).toHaveBeenCalledWith(expect.objectContaining({
      projectId: 7,
      workflowId: 12,
      taskId: 'dep_1',
      groups: [{ join: 'AND', conditions: [expect.objectContaining({ selector: 'workflow', upstreamWorkflowId: 9, upstreamTaskCode: '0' })] }],
    }))
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      upstream_workflow_id: 9,
      dependency_id: 41,
    }))
    expect(wrapper.get('[data-test="save-dependency"]').text()).toBe('已保存')
    expect(success).toHaveBeenCalledWith('依赖配置已保存')
  })

  it('rejects an invalid task selector and resets saved state after editing', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: { projectId: 7, workflowId: 12, taskId: 'dep_1', modelValue: { upstream_workflow_id: 9 } },
    })
    await wrapper.get('[data-test="save-dependency"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="save-dependency"]').text()).toBe('已保存')

    await wrapper.get('[data-test="dependency-scope"]').setValue('task')
    expect(wrapper.get('[data-test="save-dependency"]').text()).toBe('保存依赖配置')
    await wrapper.setProps({ modelValue: { upstream_workflow_id: 9, dependent_execute: 'task' } })
    await wrapper.get('[data-test="save-dependency"]').trigger('click')

    expect(warning).toHaveBeenCalledWith('指定任务依赖需要填写正整数任务编码')
    expect(saveDependency).toHaveBeenCalledTimes(1)
  })
})
