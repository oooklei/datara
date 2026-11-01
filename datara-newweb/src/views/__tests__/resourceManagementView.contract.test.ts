import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../resources/ResourceManagementView.vue'

const list = vi.hoisted(() => vi.fn())
const listVersions = vi.hoisted(() => vi.fn())
const projects = vi.hoisted(() => vi.fn())
const readContent = vi.hoisted(() => vi.fn())
const checkScript = vi.hoisted(() => vi.fn())
const appendVersion = vi.hoisted(() => vi.fn())
const listIde = vi.hoisted(() => vi.fn())
const readIde = vi.hoisted(() => vi.fn())
const saveIde = vi.hoisted(() => vi.fn())
vi.mock('../../services/rebuild/resourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/resourceApi')>()
  return {
    ...actual,
    createResourceContract: () => ({
      listResources: list,
      listResourceVersions: listVersions,
      getResourceVersionContent: readContent,
      checkResourceScript: checkScript,
      appendResourceVersion: appendVersion,
      listIdeScripts: listIde,
      getIdeScriptContent: readIde,
      saveIdeScript: saveIde,
    }),
  }
})
vi.mock('../../services/rebuild/projectApi', () => ({ listProjects: projects }))

beforeEach(() => {
  listIde.mockReset().mockResolvedValue([])
  readIde.mockReset()
  saveIde.mockReset()
})

describe('resource project scope', () => {
  it('ignores a stale resource response after the project changes', async () => {
    let resolveOld!: (value: Awaited<ReturnType<typeof list>>) => void
    let resolveNew!: (value: Awaited<ReturnType<typeof list>>) => void
    list.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveNew = resolve }))
    const wrapper = mount(View, { props: { projectId: 11 } })
    await wrapper.setProps({ projectId: 12 })
    resolveNew([{ resourceId: 2, name: 'new.py', kind: 'python', sizeBytes: 8, latestVersion: 1 }])
    await flushPromises()
    resolveOld([{ resourceId: 1, name: 'stale.sql', kind: 'sql', sizeBytes: 4, latestVersion: 1 }])
    await flushPromises()

    expect(wrapper.text()).toContain('new.py')
    expect(wrapper.text()).not.toContain('stale.sql')
  })

  it('loads the supplied project and reloads when projectId changes', async () => {
    list.mockResolvedValueOnce([{ resourceId: 1, name: 'a.sql', kind: 'sql', sizeBytes: 4, latestVersion: 1 }])
      .mockResolvedValueOnce([{ resourceId: 2, name: 'b.py', kind: 'python', sizeBytes: 8, latestVersion: 1 }])
    const wrapper = mount(View, { props: { projectId: 11 } })
    await flushPromises()
    expect(list).toHaveBeenNthCalledWith(1, 11, 'sql')
    expect(wrapper.text()).toContain('a.sql')
    listVersions.mockResolvedValue([{ resourceId: 1, version: 1, sizeBytes: 4, digest: 'sha256:a', uploadedAt: '' }])
    await wrapper.get('[data-view-versions]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

    await wrapper.setProps({ projectId: 12 })
    await flushPromises()
    expect(list).toHaveBeenNthCalledWith(2, 12, 'sql')
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

  it('opens the script editor from the row action and closes it when the project changes', async () => {
    list.mockResolvedValue([{ resourceId: 8, name: 'daily.sql', kind: 'sql', sizeBytes: 12, latestVersion: 2 }])
    readContent.mockResolvedValue({ resourceId: 8, version: 2, name: 'daily.sql', content: 'select 1' })

    const wrapper = mount(View, { props: { projectId: 11 } })
    await flushPromises()
    await wrapper.get('[data-edit-resource]').trigger('click')
    await flushPromises()

    expect(readContent).toHaveBeenCalledWith(8, 2, 11)
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('daily.sql 脚本编辑')

    await wrapper.setProps({ projectId: 12 })
    await flushPromises()
    expect(wrapper.find('[data-script-editor-mask]').exists()).toBe(false)
  })

  it('loads the first available project for the global resources route', async () => {
    projects.mockResolvedValue({ total: 1, list: [{ id: 7, name: '默认项目' }] })
    list.mockResolvedValue([{ resourceId: 3, name: 'job.sh', kind: 'shell', sizeBytes: 9, latestVersion: 1 }])

    const wrapper = mount(View)
    await flushPromises()

    expect(wrapper.find('[data-project-select]').exists()).toBe(false)
    expect(list).toHaveBeenCalledWith(7, 'sql')
    expect(wrapper.text()).toContain('job.sh')
  })
})

describe('ide script projection (same truth source as dbx IDE)', () => {
  const ideMeta = { ideFileId: 'f1', name: 'query_1.sql', connectionId: 'conn-1', database: 'ec_retail', schema: null, updatedAt: null }

  it('merges IDE query scripts into the SQL list and degrades to empty when dbx is down', async () => {
    list.mockResolvedValue([{ resourceId: 1, name: 'etl.sql', kind: 'sql', sizeBytes: 4, latestVersion: 1 }])
    listIde.mockResolvedValue([ideMeta])

    const wrapper = mount(View, { props: { projectId: 11 } })
    await flushPromises()

    expect(listIde).toHaveBeenCalledWith(11)
    expect(wrapper.text()).toContain('query_1.sql')
    expect(wrapper.find('[data-ide-open]').exists()).toBe(true)
    // IDE 行无版本/大小 → 占位符 '—'。
    expect(wrapper.text()).toContain('—')

    // dbx 不可用：IDE 投影降级为空，主列表不报错不阻断。
    listIde.mockRejectedValueOnce(new Error('dbx unavailable'))
    await wrapper.setProps({ projectId: 12 })
    await flushPromises()
    expect(wrapper.text()).toContain('etl.sql')
    expect(wrapper.find('[data-error]').exists()).toBe(false)
  })

  it('opens the IDE script viewer/editor, saves back to dbx and reloads the list', async () => {
    list.mockResolvedValue([{ resourceId: 1, name: 'etl.sql', kind: 'sql', sizeBytes: 4, latestVersion: 1 }])
    listIde.mockResolvedValue([ideMeta])
    readIde.mockResolvedValue({ ...ideMeta, content: 'select 1;' })
    saveIde.mockResolvedValue({ saved: true, ideFileId: 'f1', name: 'query_1.sql' })

    const wrapper = mount(View, { props: { projectId: 11 } })
    await flushPromises()

    await wrapper.get('[data-ide-open]').trigger('click')
    await flushPromises()
    expect(readIde).toHaveBeenCalledWith(11, 'f1')
    const editor = wrapper.get('[data-ide-editor]')
    expect((editor.element as HTMLTextAreaElement).value).toBe('select 1;')

    await editor.setValue('select 42;')
    await wrapper.get('[data-ide-save]').trigger('click')
    await flushPromises()

    expect(saveIde).toHaveBeenCalledWith(11, 'f1', 'select 42;')
    expect(wrapper.find('[data-ide-mask]').exists()).toBe(false)
    // 保存成功后刷新主列表与 IDE 投影。
    expect(list).toHaveBeenCalledTimes(2)
    expect(listIde).toHaveBeenCalledTimes(2)
  })
})
