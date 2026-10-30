import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listVariables } = vi.hoisted(() => ({ listVariables: vi.fn() }))
vi.mock('../../../services/rebuild/variableApi', () => ({
  createVariableContract: () => ({ listVariables }),
}))
vi.mock('../../../composables/useDraggable', async () => {
  const { ref } = await import('vue')
  return { useDraggable: () => ({ dragStyle: ref({}), onHandlePointerdown: vi.fn() }) }
})

import VariableManagerDrawer from '../VariableManagerDrawer.vue'

describe('variable manager workflow scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listVariables.mockResolvedValue([])
  })

  it('loads workflow and task scopes only when both owners are known', async () => {
    const wrapper = mount(VariableManagerDrawer, {
      props: { modelValue: true, projectId: 7, workflowId: 88, taskId: 'sql_1' },
    })
    await flushPromises()
    expect(listVariables).toHaveBeenCalledWith(
      7, ['global', 'project', 'env', 'workflow', 'task'], { workflowId: 88, taskId: 'sql_1' },
    )
    await wrapper.get('[data-variable-create]').trigger('click')
    expect(wrapper.get('.editor').text()).toContain('任务')

    await wrapper.setProps({ workflowId: undefined })
    await flushPromises()
    expect(listVariables).toHaveBeenLastCalledWith(7, ['global', 'project', 'env'], {})
    expect(wrapper.get('.editor').text()).not.toContain('任务')
  })
})
