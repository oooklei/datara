import { defineComponent, h, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { authAccount } from '../authApi'
import { useEnvironmentContext } from '../environmentContext'

const { listEnvironments } = vi.hoisted(() => ({ listEnvironments: vi.fn() }))
vi.mock('../orchestrationApi', () => ({
  orchestrationApi: { listEnvironments },
}))

const Harness = defineComponent({
  setup() {
    const projectId = ref<number | null>(7)
    const context = useEnvironmentContext(projectId)
    return { context, projectId }
  },
  render() {
    return h('div', { 'data-selected': this.context.selectedId.value ?? 'none' })
  },
})

describe('environment context', () => {
  beforeEach(() => {
    listEnvironments.mockReset()
    authAccount.value = { id: 1, username: 'admin', role: 'admin' }
  })

  afterEach(() => { authAccount.value = null })

  it('首次加载优先选择预置 default-env，并保留 id/code 对应项', async () => {
    listEnvironments.mockResolvedValue([
      { id: 3, code: '188356866898880', name: 'e2e-env-2' },
      { id: 2, code: '188356094854656', name: 'default-env' },
    ])
    const wrapper = mount(Harness)
    await flushPromises()
    expect(wrapper.get('[data-selected]').attributes('data-selected')).toBe('2')
    expect(wrapper.vm.context.selected.value).toMatchObject({ id: 2, code: '188356094854656' })
  })

  it('用户显式选择未指定后刷新不被默认值抢回', async () => {
    listEnvironments.mockResolvedValue([{ id: 2, code: '188356094854656', name: 'default-env' }])
    const wrapper = mount(Harness)
    await flushPromises()
    wrapper.vm.context.selectedId.value = null
    await nextTick()
    await wrapper.vm.context.refresh()
    expect(wrapper.vm.context.selectedId.value).toBeNull()
  })
})
