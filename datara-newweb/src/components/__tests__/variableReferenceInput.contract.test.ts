import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import VariableReferenceInput from '../VariableReferenceInput.vue'

const api = vi.hoisted(() => ({
  completeVariables: vi.fn(),
  checkReference: vi.fn(),
  previewResolution: vi.fn(),
}))

vi.mock('../../services/rebuild/variableApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/variableApi')>()
  return { ...actual, createVariableContract: () => api }
})

describe('VariableReferenceInput completion contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.completeVariables.mockResolvedValue([
      { scope: 'project', name: 'tenant_id', valueType: 'string', currentValue: 'acme' },
    ])
  })

  it('replaces only the active variable token and preserves surrounding script', async () => {
    const wrapper = mount(VariableReferenceInput, {
      props: { modelValue: '', context: { projectId: 7 }, multiline: true },
    })
    const source = 'select * from orders where tenant = ${project.ten and enabled = 1'
    const editor = wrapper.get('textarea')
    const caret = source.indexOf(' and enabled')
    ;(editor.element as HTMLTextAreaElement).value = source
    ;(editor.element as HTMLTextAreaElement).setSelectionRange(caret, caret)
    await editor.trigger('input')
    await flushPromises()

    expect(api.completeVariables).toHaveBeenCalledWith('${project.ten', { projectId: 7 })
    await wrapper.get('[data-variable-suggestion]').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([
      'select * from orders where tenant = ${project.tenant_id} and enabled = 1',
    ])
  })

  it('does not request suggestions without an active variable token', async () => {
    const wrapper = mount(VariableReferenceInput, {
      props: { modelValue: '', context: { projectId: 7 } },
    })
    await wrapper.get('input').setValue('plain text')
    await flushPromises()

    expect(api.completeVariables).not.toHaveBeenCalled()
    expect(wrapper.find('[data-variable-suggestion]').exists()).toBe(false)
  })

  it('checks references and renders every diagnostic class with the current value preview', async () => {
    const diagnostics = [
      { code: 'SYNTAX', message: 'syntax' },
      { code: 'UNDEFINED', message: 'undefined' },
      { code: 'TYPE_MISMATCH', message: 'type' },
      { code: 'SCOPE_INVISIBLE', message: 'scope' },
      { code: 'CYCLE', message: 'cycle' },
    ]
    api.checkReference.mockResolvedValue({ expression: '${project.region}', valid: false, diagnostics })
    api.previewResolution.mockResolvedValue({
      expression: '${project.region}',
      resolvedValue: 'cn-north-1',
      diagnostics: [],
    })
    const wrapper = mount(VariableReferenceInput, {
      props: { modelValue: '${project.region}', context: { projectId: 7 } },
    })

    await wrapper.get('[data-variable-check]').trigger('click')
    await flushPromises()

    expect(api.checkReference).toHaveBeenCalledWith('${project.region}', { projectId: 7 })
    expect(api.previewResolution).toHaveBeenCalledWith('${project.region}', { projectId: 7 })
    for (const diagnostic of diagnostics) expect(wrapper.text()).toContain(diagnostic.code)
    expect(wrapper.get('[data-variable-current-value]').text()).toContain('cn-north-1')
  })
})
