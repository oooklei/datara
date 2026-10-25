import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import View from '../resources/ResourceManagementView.vue'

const list = vi.hoisted(() => vi.fn())
const listVersions = vi.hoisted(() => vi.fn())
const projects = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/resourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/resourceApi')>()
  return { ...actual, createResourceContract: () => ({ listResources: list, listResourceVersions: listVersions }) }
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
    listVersions.mockResolvedValue([{ resourceId: 1, version: 1, sizeBytes: 4, digest: 'sha256:a', uploadedAt: '' }])
    await wrapper.get('[data-view-versions]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

    await wrapper.setProps({ projectId: 12 })
    await flushPromises()
    expect(list).toHaveBeenNthCalledWith(2, 12, undefined)
    expect(wrapper.text()).toContain('b.py')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('opens the immutable version history for a resource', async () => {
    list.mockResolvedValue([{ resourceId: 8, name: 'daily.sql', kind: 'sql', sizeBytes: 12, latestVersion: 2 }])
    listVersions.mockResolvedValue([
      { resourceId: 8, version: 2, sizeBytes: 12, digest: 'sha256:new', uploadedAt: '2026-10-25T08:00:00Z' },
      { resourceId: 8, version: 1, sizeBytes: 10, digest: 'sha256:old', uploadedAt: '2026-10-24T08:00:00Z' },
    ])

    const wrapper = mount(View, { props: { projectId: 11 } })
    await flushPromises()
    await wrapper.get('[data-view-versions]').trigger('click')
    await flushPromises()

    expect(listVersions).toHaveBeenCalledWith(8, 11)
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('daily.sql 版本历史')
    expect(wrapper.text()).toContain('v2')
    expect(wrapper.text()).toContain('sha256:new')
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
