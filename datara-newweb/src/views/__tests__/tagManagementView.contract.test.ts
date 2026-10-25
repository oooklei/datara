import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../meta/TagManagementView.vue'

const confirmClear = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: confirmClear } }))

const router = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => router.route, useRouter: () => ({ push: router.push }) }))

vi.mock('../../services/rebuild/governanceApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/governanceApi')>(
      '../../services/rebuild/governanceApi',
    )
  return {
    ...actual,
    governanceApi: { listAssets: vi.fn(), createTag: vi.fn(), assignAssetTags: vi.fn() },
  }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { governanceApi } from '../../services/rebuild/governanceApi'
import { listProjects } from '../../services/rebuild/projectApi'

const asset = {
  id: 9,
  projectId: 1,
  sourceSystem: 'mysql',
  databaseName: 'orders',
  schemaName: 'public',
  assetName: 'orders',
  assetType: 'table',
  displayName: '订单表',
  description: '订单主表',
  ownerName: 'alice',
  domainName: '交易',
  rowCount: 100,
  createdAt: null,
  updatedAt: null,
}

const tag = { id: 1, namespace: 'default', tagKey: 'owner', displayName: '负责人', description: '', createdAt: null, updatedAt: null }

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/meta/tag 标签管理页（增量 14）', () => {
  it('renders project picker and skips the asset query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-asset-select]').exists()).toBe(false)
    expect(governanceApi.listAssets).not.toHaveBeenCalled()
  })

  it('lists assets for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listAssets).toHaveBeenCalledWith(1)
    expect(w.find('[data-asset-select]').exists()).toBe(true)
    expect(w.find('[data-asset-select]').attributes('disabled')).toBeUndefined()
  })

  it('creates a tag through the form and reports the result', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    vi.mocked(governanceApi.createTag).mockResolvedValue(tag)
    const w = mount(View)
    await flushPromises()
    const inputs = w.findAll('.create input')
    await inputs[1]!.setValue('owner')
    await inputs[2]!.setValue('负责人')
    await inputs[3]!.setValue('资产负责人')
    await w.find('form.create').trigger('submit')
    await flushPromises()
    expect(governanceApi.createTag).toHaveBeenCalledWith(1, {
      namespace: 'default',
      tagKey: 'owner',
      displayName: '负责人',
      description: '资产负责人',
    })
    expect(w.find('[data-assign-result]').text()).toContain('已创建标签 #1 default:owner')
  })

  it('assigns tag ids to the selected asset', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    vi.mocked(governanceApi.assignAssetTags).mockResolvedValue({ assetId: 9, tagIds: [1, 2] })
    const w = mount(View)
    await flushPromises()
    await w.find('[data-asset-select]').setValue('9')
    await w.find('input[placeholder="1,2,3"]').setValue('1,2')
    await w.find('.assign button[type="button"]').trigger('click')
    await flushPromises()
    expect(governanceApi.assignAssetTags).toHaveBeenCalledWith(9, [1, 2])
    expect(w.find('[data-assign-result]').text()).toContain('资产 #9 已挂载标签：1, 2')
  })

  it('surfaces backend errors without dropping the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockRejectedValue(Object.assign(new Error('asset list failed'), { code: 4041 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('asset list failed')
    expect(w.find('[data-project-select]').exists()).toBe(true)
  })

  it('keeps tag creation available with no assets and clears created history on project change', async () => {
    vi.mocked(listProjects).mockResolvedValue({ total: 2, list: [{ id: 1, name: 'P1' }, { id: 2, name: 'P2' }] })
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 0, page: 1, pageSize: 50, list: [] })
    vi.mocked(governanceApi.createTag).mockResolvedValue(tag)
    const w = mount(View)
    await flushPromises()
    await w.find('[data-project-select]').setValue('1')
    await flushPromises()
    expect(w.find('[data-no-assets]').exists()).toBe(true)
    expect(w.find('form.create').exists()).toBe(true)
    const inputs = w.findAll('.create input')
    await inputs[1]!.setValue('owner')
    await inputs[2]!.setValue('Owner')
    await w.find('form.create').trigger('submit')
    await flushPromises()
    expect(w.find('.recent-list').exists()).toBe(true)
    await w.find('[data-project-select]').setValue('2')
    await flushPromises()
    expect(w.find('.recent-list').exists()).toBe(false)
  })

  it('requires confirmation before clearing all tags and does nothing when cancelled', async () => {
    const tagged = { ...asset, tags: [tag] }
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [tagged] })
    confirmClear.mockRejectedValue(new Error('cancel'))
    const w = mount(View)
    await flushPromises()
    await w.find('.op-btn.danger').trigger('click')
    await flushPromises()
    expect(confirmClear).toHaveBeenCalledTimes(1)
    expect(governanceApi.assignAssetTags).not.toHaveBeenCalled()
  })

  it('clears all tags only after confirmation succeeds', async () => {
    const tagged = { ...asset, tags: [tag] }
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [tagged] })
    vi.mocked(governanceApi.assignAssetTags).mockResolvedValue({ assetId: 9, tagIds: [] })
    confirmClear.mockResolvedValue('confirm')
    const w = mount(View)
    await flushPromises()
    await w.find('.op-btn.danger').trigger('click')
    await flushPromises()
    expect(confirmClear).toHaveBeenCalledTimes(1)
    expect(governanceApi.assignAssetTags).toHaveBeenCalledWith(9, [])
  })

  it('clears stale assets and selections immediately while a new project is loading', async () => {
    let resolveP2!: (value: { total: number; page: number; pageSize: number; list: typeof asset[] }) => void
    vi.mocked(listProjects).mockResolvedValue({ total: 2, list: [{ id: 1, name: 'P1' }, { id: 2, name: 'P2' }] })
    vi.mocked(governanceApi.listAssets).mockImplementation((projectId) => projectId === 1
      ? Promise.resolve({ total: 1, page: 1, pageSize: 50, list: [asset] })
      : new Promise((resolve) => { resolveP2 = resolve }))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-project-select]').setValue('1')
    await flushPromises()
    await w.find('[data-asset-select]').setValue('9')
    await w.find('[data-project-select]').setValue('2')
    expect(w.find('[data-tag-assets]').exists()).toBe(false)
    expect(w.find<HTMLSelectElement>('[data-asset-select]').element.value).toBe('')
    expect(w.find('[data-asset-select]').attributes('disabled')).toBeDefined()
    expect(w.find('form.create button[type="submit"]').attributes('disabled')).toBeDefined()
    resolveP2({ total: 0, page: 1, pageSize: 50, list: [] })
    await flushPromises()
  })
})
