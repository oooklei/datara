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

const variableInputStub = {
  props: ['modelValue', 'context', 'label'],
  emits: ['update:modelValue'],
  template: '<button data-variable-input :data-label="label" @click="$emit(\'update:modelValue\', \'${project.dynamic_target}\')">{{ label }}</button>',
}

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

  it('saves the relative range window without also sending the named window', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: {
        projectId: 7,
        workflowId: 12,
        taskId: 'dep_1',
        modelValue: {
          upstream_workflow_id: 9,
          window_mode: 'range',
          period_type: 'day',
          begin_offset: -2,
          end_offset: 0,
        },
      },
    })

    await wrapper.get('[data-test="save-dependency"]').trigger('click')
    await flushPromises()
    const condition = saveDependency.mock.calls[0][0].groups[0].conditions[0]
    expect(condition).toEqual(expect.objectContaining({
      dateRange: { periodType: 'day', beginOffset: -2, endOffset: 0 },
    }))
    expect(condition).not.toHaveProperty('cycle')
    expect(condition).not.toHaveProperty('dateValue')
  })

  it('saves a file dependency with its explicit target identifier', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: {
        projectId: 7,
        workflowId: 12,
        taskId: 'dep_file',
        modelValue: { kind: 'file', file_id: 'landing/orders.done' },
      },
    })

    expect(wrapper.get('[data-test="dependency-kind"]').findAll('option')).toHaveLength(5)
    expect(wrapper.get('[data-test="dependency-target"]').get('input').element).toHaveProperty('value', 'landing/orders.done')
    await wrapper.get('[data-test="save-dependency"]').trigger('click')
    await flushPromises()

    const condition = saveDependency.mock.calls[0][0].groups[0].conditions[0]
    expect(condition).toEqual(expect.objectContaining({
      kind: 'file',
      fileId: 'landing/orders.done',
      cycle: 'day',
      dateValue: 'last1Days',
    }))
    expect(condition).not.toHaveProperty('upstreamWorkflowId')
  })

  it('converts the DS failure waiting duration from minutes to contract seconds', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: {
        projectId: 7,
        workflowId: 12,
        taskId: 'dep_waiting',
        modelValue: {
          upstream_workflow_id: 9,
          failure_policy: 'waiting',
          failure_waiting_minutes: 2,
        },
      },
    })

    await wrapper.get('[data-test="save-dependency"]').trigger('click')
    await flushPromises()

    expect(saveDependency).toHaveBeenCalledWith(expect.objectContaining({
      failurePolicy: 'waiting',
      failureWaitingSeconds: 120,
    }))
  })

  it('blocks non-positive polling and timeout values before calling the backend', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: {
        projectId: 7,
        workflowId: 12,
        taskId: 'dep_invalid_policy',
        modelValue: { upstream_workflow_id: 9, check_interval_seconds: 0, timeout_seconds: 30 },
      },
    })

    await wrapper.get('[data-test="save-dependency"]').trigger('click')

    expect(warning).toHaveBeenCalledWith('检查周期和超时必须是正整数秒')
    expect(saveDependency).not.toHaveBeenCalled()
  })

  it('uses the unified variable contract for string dependency targets', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: {
        projectId: 7,
        workflowId: 12,
        taskId: 'dep_file',
        modelValue: { kind: 'file', file_id: '/landing/ready.flag' },
      },
      global: { stubs: { VariableReferenceInput: variableInputStub } },
    })

    await wrapper.get('[data-variable-field="dependency-target"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      file_id: '${project.dynamic_target}',
    }))
  })

  it('uses positive integer identifiers and the frozen backend named-window value domain', async () => {
    const wrapper = mount(DependencyNodeEditor, {
      props: {
        projectId: 7,
        workflowId: 12,
        taskId: 'dep_domain',
        modelValue: { kind: 'task', dependent_execute: 'task', cycle: 'day', date_value: 'last1Days' },
      },
    })

    expect(wrapper.get('[data-test="upstream-workflow"]').attributes()).toEqual(expect.objectContaining({ type: 'number', min: '1', step: '1' }))
    expect(wrapper.get('[data-test="upstream-task"]').attributes()).toEqual(expect.objectContaining({ type: 'number', min: '1', step: '1' }))
    expect(wrapper.get('[data-test="dependency-date-value"]').findAll('option').map((item) => item.attributes('value'))).toEqual([
      'today', 'last1Days', 'last2Days', 'last3Days', 'last7Days',
    ])

    await wrapper.get('[data-test="dependency-cycle"]').setValue('hour')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      cycle: 'hour',
      date_value: 'currentHour',
    }))
  })
})
