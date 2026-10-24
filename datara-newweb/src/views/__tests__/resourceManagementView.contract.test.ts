import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import View from '../resources/ResourceManagementView.vue'

const list = vi.hoisted(() => vi.fn())
const projects = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/resourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/resourceApi')>()
  return { ...actual, createResourceContract: () => ({ listResources: list }) }
})
vi.mock('../../services/rebuild/projectApi', () => ({ listProjects: projects }))

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

  it('loads the first available project for the global resources route', async () => {
    projects.mockResolvedValue({ total: 1, list: [{ id: 7, name: '默认项目' }] })
    list.mockResolvedValue([{ resourceId: 3, name: 'job.sh', kind: 'shell', sizeBytes: 9, latestVersion: 1 }])

    const wrapper = mount(View)
    await flushPromises()

    expect(wrapper.find('[data-project-select]').exists()).toBe(true)
    expect(list).toHaveBeenCalledWith(7, undefined)
    expect(wrapper.text()).toContain('job.sh')
  })
})
