import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listVariables, saveVariable, deleteVariable, completeVariables, checkReference, previewResolution } = vi.hoisted(() => ({
  listVariables: vi.fn(),
  saveVariable: vi.fn(),
  deleteVariable: vi.fn(),
  completeVariables: vi.fn(),
  checkReference: vi.fn(),
  previewResolution: vi.fn(),
}))

vi.mock('../../services/rebuild/variableApi', async (original) => {
  const actual = await original<typeof import('../../services/rebuild/variableApi')>()
  return {
    ...actual,
    createVariableContract: () => ({
      listVariables,
      saveVariable,
      deleteVariable,
      completeVariables,
      checkReference,
      previewResolution,
    }),
  }
})

import VariableManagerDrawer from '../../views/variables/VariableManagerDrawer.vue'
import VariableReferenceInput from '../VariableReferenceInput.vue'
import WorkflowVariablePanel from '../WorkflowVariablePanel.vue'

beforeEach(() => {
  vi.clearAllMocks()
  listVariables.mockResolvedValue([])
  saveVariable.mockResolvedValue({ saved: true, scope: 'project', name: 'region' })
  deleteVariable.mockResolvedValue({ deleted: true, scope: 'project', name: 'region' })
  completeVariables.mockResolvedValue([])
  checkReference.mockResolvedValue({ expression: '${project.region}', valid: true, diagnostics: [] })
  previewResolution.mockResolvedValue({ expression: '${project.region}', resolvedValue: 'cn-east', diagnostics: [] })
})

describe('variable management product surfaces', () => {
  it('loads project/global/environment variables and exposes loading, error, empty and permission states', async () => {
    const wrapper = mount(VariableManagerDrawer, { props: { modelValue: true, projectId: 7, canEdit: false } })
    expect(wrapper.find('[data-variable-loading]').exists()).toBe(true)
    await flushPromises()
    expect(listVariables).toHaveBeenCalledWith(7, ['global', 'project', 'env'], {})
    expect(wrapper.find('[data-variable-empty]').exists()).toBe(true)
    expect(wrapper.find('[data-variable-create]').attributes('disabled')).toBeDefined()

    listVariables.mockRejectedValueOnce(new Error('offline'))
    await wrapper.find('[data-variable-retry]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-variable-error]').text()).toContain('加载失败')
  })

  it('provides a workflow-scoped canvas panel with real CRUD wiring', async () => {
    listVariables.mockResolvedValueOnce([{ scope: 'workflow', name: 'biz_date', valueType: 'date', value: '2026-10-24' }])
    const wrapper = mount(WorkflowVariablePanel, { props: { projectId: 7, workflowId: 11, modelValue: true } })
    await flushPromises()
    expect(listVariables).toHaveBeenCalledWith(7, ['workflow'], { workflowId: 11 })
    expect(wrapper.text()).toContain('biz_date')
    await wrapper.find('[data-variable-name]').setValue('region')
    await wrapper.find('[data-variable-value]').setValue('cn-east')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(saveVariable).toHaveBeenCalledWith(7, expect.objectContaining({ scope: 'workflow', workflowId: 11, name: 'region' }))
  })

  it('allows editing a sensitive variable without re-displaying or re-entering its value', async () => {
    listVariables.mockResolvedValueOnce([{ scope: 'project', name: 'api_key', valueType: 'string', sensitive: true }])
    const wrapper = mount(VariableManagerDrawer, { props: { modelValue: true, projectId: 7 } })
    await flushPromises()
    await wrapper.find('tbody button').trigger('click')
    const value = wrapper.find('[data-variable-value]')
    expect(value.attributes('type')).toBe('password')
    expect(value.attributes('required')).toBeUndefined()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(saveVariable).toHaveBeenCalledWith(7, expect.objectContaining({ name: 'api_key', sensitive: true, value: '' }))
  })

  it('autocompletes, checks all diagnostics, and previews the current value without exposing secrets', async () => {
    completeVariables.mockResolvedValueOnce([
      { scope: 'project', name: 'region', valueType: 'string', currentValue: 'cn-east', sensitive: false },
    ])
    const wrapper = mount(VariableReferenceInput, {
      props: { modelValue: '${project.r', context: { projectId: 7 }, label: 'SQL 参数' },
    })
    await wrapper.find('input').trigger('input')
    await flushPromises()
    expect(wrapper.find('[data-variable-suggestion]').text()).toContain('${project.region}')
    await wrapper.find('[data-variable-suggestion]').trigger('click')
    await wrapper.find('[data-variable-check]').trigger('click')
    await flushPromises()
    expect(checkReference).toHaveBeenCalled()
    expect(previewResolution).toHaveBeenCalled()
    expect(wrapper.find('[data-variable-current-value]').text()).toContain('cn-east')
  })
})
