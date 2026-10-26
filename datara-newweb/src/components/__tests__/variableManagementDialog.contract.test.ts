import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import VariableManagementDialog from '../VariableManagementDialog.vue'

const api = vi.hoisted(() => ({
  listVariables: vi.fn(),
  saveVariable: vi.fn(),
}))

vi.mock('../../services/rebuild/variableApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/variableApi')>()
  return { ...actual, createVariableContract: () => api }
})

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() } }))

const variable = (name: string) => ({
  scope: 'project' as const,
  name,
  valueType: 'string' as const,
  value: name,
  sensitive: false,
  description: '',
})

describe('VariableManagementDialog contract', () => {
  beforeEach(() => vi.clearAllMocks())

  it('discards an old project variable response after the project changes', async () => {
    let resolveOld!: (items: ReturnType<typeof variable>[]) => void
    api.listVariables
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce([variable('new-project-variable')])

    const wrapper = mount(VariableManagementDialog, {
      props: { modelValue: true, projectId: 1 },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()
    await wrapper.setProps({ projectId: 2 })
    await flushPromises()

    expect(wrapper.text()).toContain('new-project-variable')
    resolveOld([variable('old-project-variable')])
    await flushPromises()

    expect(wrapper.text()).toContain('new-project-variable')
    expect(wrapper.text()).not.toContain('old-project-variable')
    expect(api.listVariables).toHaveBeenNthCalledWith(2, 2, ['global', 'project'])
  })
})
