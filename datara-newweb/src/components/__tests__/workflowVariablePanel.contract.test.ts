import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listVariables, saveVariable, deleteVariable, previewResolution } = vi.hoisted(() => ({
  listVariables: vi.fn(),
  saveVariable: vi.fn(),
  deleteVariable: vi.fn(),
  previewResolution: vi.fn(),
}))
vi.mock('../../services/rebuild/variableApi', () => ({
  createVariableContract: () => ({ listVariables, saveVariable, deleteVariable, previewResolution }),
  // 七级链单一事实源（variableApi 导出），mock 与真源保持同序
  VARIABLE_SCOPE_PRIORITY: ['run', 'task', 'workflow', 'project', 'env', 'global', 'builtin'] as const,
}))

import WorkflowVariablePanel from '../WorkflowVariablePanel.vue'

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(WorkflowVariablePanel, { props: { modelValue: true, projectId: 7, workflowId: 3, ...props } })
}

describe('workflow variable panel seven-scope chain contract (T7)', () => {
  beforeEach(() => {
    listVariables.mockReset()
    listVariables.mockResolvedValue([])
    saveVariable.mockReset()
    deleteVariable.mockReset()
    previewResolution.mockReset()
  })

  it('exposes the seven-level resolution chain in fixed priority order', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const chain = wrapper.get('[data-variable-chain]')
    expect(chain.findAll('[data-chain-scope]').map((item) => item.attributes('data-chain-scope')))
      .toEqual(['run', 'task', 'workflow', 'project', 'env', 'global', 'builtin'])
  })

  it('loads panel scopes and groups rows by scope without delete actions outside the workflow scope', async () => {
    listVariables.mockResolvedValue([
      { scope: 'workflow', name: 'rate', valueType: 'string', value: '0.8' },
      { scope: 'project', name: 'owner', valueType: 'string', value: 'datara' },
      { scope: 'env', name: 'jdbc_url', valueType: 'string', value: 'mysql://a', environmentGroupId: 2 },
      { scope: 'global', name: 'env_name', valueType: 'string', value: 'prod' },
    ])
    const wrapper = mountPanel()
    await flushPromises()
    expect(listVariables).toHaveBeenCalledWith(7, ['workflow', 'project', 'env', 'global'], { workflowId: 3 })
    expect(wrapper.findAll('[data-scope-group]').map((group) => group.attributes('data-scope-group')))
      .toEqual(['workflow', 'project', 'env', 'global'])
    // 分域裁定：workflow 为画布面板管理面（可删）；上游域只读，管理面收口到任务中心「变量管理」
    expect(wrapper.find('[data-scope-group="workflow"] [data-variable-remove="rate"]').exists()).toBe(true)
    expect(wrapper.find('[data-scope-group="project"] [data-variable-remove]').exists()).toBe(false)
    expect(wrapper.find('[data-scope-group="env"] [data-variable-remove]').exists()).toBe(false)
    expect(wrapper.find('[data-scope-group="global"] [data-variable-remove]').exists()).toBe(false)
    expect(wrapper.get('[data-scope-group="global"] h4').text()).toContain('只读')
  })

  it('previews expression resolution with its source scope', async () => {
    previewResolution.mockResolvedValue({
      expression: '${workflow.rate}',
      resolvedValue: '0.8',
      source: { scope: 'workflow', name: 'rate' },
      diagnostics: [],
    })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-variable-preview-input]').setValue('${workflow.rate}')
    await wrapper.get('[data-variable-preview-run]').trigger('click')
    await flushPromises()
    expect(previewResolution).toHaveBeenCalledWith('${workflow.rate}', { projectId: 7, workflowId: 3 })
    const result = wrapper.get('[data-variable-preview-result]').text()
    expect(result).toContain('0.8')
    expect(result).toContain('workflow.rate')
  })

  it('surfaces diagnostics when the expression cannot be resolved', async () => {
    previewResolution.mockResolvedValue({
      expression: '${workflow.missing}',
      resolvedValue: null,
      diagnostics: [{ code: 'UNDEFINED', message: '变量未定义: workflow.missing' }],
    })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-variable-preview-input]').setValue('${workflow.missing}')
    await wrapper.get('[data-variable-preview-run]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-variable-preview-result]').text()).toContain('变量未定义')
  })

  it('keeps workflow-scope save and delete wired with the workflow owner', async () => {
    listVariables.mockResolvedValue([{ scope: 'workflow', name: 'rate', valueType: 'string', value: '0.8' }])
    saveVariable.mockResolvedValue({ saved: true, scope: 'workflow', name: 'k' })
    deleteVariable.mockResolvedValue({ deleted: true, scope: 'workflow', name: 'rate' })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-variable-name]').setValue('k')
    await wrapper.get('[data-variable-value]').setValue('1')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(saveVariable).toHaveBeenCalledWith(7, expect.objectContaining({ scope: 'workflow', workflowId: 3, name: 'k' }))
    await wrapper.get('[data-variable-remove="rate"]').trigger('click')
    await flushPromises()
    expect(deleteVariable).toHaveBeenCalledWith(7, 'workflow', 'rate', { workflowId: 3 })
    expect(listVariables).toHaveBeenCalledTimes(3)
  })
})
