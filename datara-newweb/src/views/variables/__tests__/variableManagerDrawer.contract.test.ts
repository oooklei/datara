import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import VariableManagerDrawer from '../VariableManagerDrawer.vue'

const api = vi.hoisted(() => ({
  listVariables: vi.fn(),
  saveVariable: vi.fn(),
  deleteVariable: vi.fn(),
}))

vi.mock('../../../services/rebuild/variableApi', async (load) => {
  const actual = await load<typeof import('../../../services/rebuild/variableApi')>()
  return { ...actual, createVariableContract: () => api }
})

const variable = (name: string) => ({
  scope: 'project' as const,
  name,
  valueType: 'string' as const,
  value: name,
  sensitive: false,
})

describe('VariableManagerDrawer contract', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not render a stale variable list after the active project changes', async () => {
    let resolveOld!: (items: ReturnType<typeof variable>[]) => void
    api.listVariables
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce([variable('project-two')])

    const wrapper = mount(VariableManagerDrawer, { props: { modelValue: true, projectId: 1 } })
    await flushPromises()
    await wrapper.setProps({ projectId: 2 })
    await flushPromises()
    expect(wrapper.text()).toContain('project-two')

    resolveOld([variable('project-one')])
    await flushPromises()
    expect(wrapper.text()).toContain('project-two')
    expect(wrapper.text()).not.toContain('project-one')
  })
})
