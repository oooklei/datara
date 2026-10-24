import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import View from '../resources/ResourceManagementView.vue'

const list = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/resourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/resourceApi')>()
  return { ...actual, createResourceContract: () => ({ listResources: list }) }
})

describe('resource project scope', () => {
  it('loads the supplied project and reloads when projectId changes', async () => {
    list.mockResolvedValueOnce([{ resourceId: 1, name: 'a.sql', kind: 'sql', sizeBytes: 4, latestVersion: 1 }])
      .mockResolvedValueOnce([{ resourceId: 2, name: 'b.py', kind: 'python', sizeBytes: 8, latestVersion: 1 }])
    const wrapper = mount(View, { props: { projectId: 11 } })
    await flushPromises()
    expect(list).toHaveBeenNthCalledWith(1, 11, undefined)
    expect(wrapper.text()).toContain('a.sql')

    await wrapper.setProps({ projectId: 12 })
    await flushPromises()
    expect(list).toHaveBeenNthCalledWith(2, 12, undefined)
    expect(wrapper.text()).toContain('b.py')
  })
})
