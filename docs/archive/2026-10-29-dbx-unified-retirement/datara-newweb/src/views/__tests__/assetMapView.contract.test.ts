import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../meta/AssetMapView.vue'

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
  return { ...actual, governanceApi: { listAssets: vi.fn(), listMetrics: vi.fn(), listStandards: vi.fn() } }
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

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/meta/map 资产地图页（增量 14）', () => {
  it('renders project picker and skips the asset query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(false)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-asset-table]').exists()).toBe(false)
    expect(governanceApi.listAssets).not.toHaveBeenCalled()
  })

  it('lists assets for the project carried by route params and groups by database', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listAssets).toHaveBeenCalledWith(1, { q: undefined })
    expect(w.find('[data-asset-groups]').exists()).toBe(true)
    expect(w.find('[data-asset-table]').exists()).toBe(true)
    expect(w.find('[data-asset-table]').text()).toContain('订单表')
  })

  it('passes the keyword filter through to the list call', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 0, page: 1, pageSize: 50, list: [] })
    const w = mount(View)
    await flushPromises()
    await w.find('input[placeholder="资产名/描述"]').setValue('orders')
    await w.find('button[type="button"]').trigger('click')
    await flushPromises()
    expect(governanceApi.listAssets).toHaveBeenLastCalledWith(1, { q: 'orders' })
  })

  it('renders the empty state when the project has no assets', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 0, page: 1, pageSize: 50, list: [] })
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-asset-table]').exists()).toBe(false)
  })

  it('surfaces backend errors without dropping the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockRejectedValue(Object.assign(new Error('asset list failed'), { code: 4041 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('asset list failed')
    expect(w.find('[data-project-select]').exists()).toBe(false)
  })

  it('does not cache failed summaries, renders unknown instead of zero, and retries', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    vi.mocked(governanceApi.listMetrics)
      .mockRejectedValueOnce(new Error('metrics failed'))
      .mockResolvedValue({ total: 1, list: [{ id: 1, projectId: 1, code: 'M1', name: 'Recovered metric', formula: '1', description: '', status: 'active', createdAt: null, updatedAt: null }] })
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 0, list: [] })
    const w = mount(View)
    await flushPromises()
    await w.findAll('[data-asset-views] button')[2]!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('指标— 项')
    await w.findAll('[data-asset-views] button')[2]!.trigger('click')
    await flushPromises()
    expect(governanceApi.listMetrics).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('Recovered metric')
  })

  it('preserves project context in metric and standard navigation', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    vi.mocked(governanceApi.listMetrics).mockResolvedValue({ total: 0, list: [] })
    vi.mocked(governanceApi.listStandards).mockResolvedValue({ total: 0, list: [] })
    const w = mount(View)
    await flushPromises()
    await w.findAll('[data-asset-views] button')[2]!.trigger('click')
    await flushPromises()
    const links = w.findAll('.cat-link')
    await links[1]!.trigger('click')
    expect(router.push).toHaveBeenCalledWith({ path: '/ind/list', query: { projectId: '1' } })
    await links[2]!.trigger('click')
    expect(router.push).toHaveBeenCalledWith({ path: '/std/element', query: { projectId: '1' } })
  })
})
