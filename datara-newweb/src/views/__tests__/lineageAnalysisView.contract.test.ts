import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../meta/LineageAnalysisView.vue'

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
  return { ...actual, governanceApi: { listAssets: vi.fn(), getLineage: vi.fn() } }
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

const graph = {
  assetId: 9,
  direction: 'both' as const,
  depth: 3,
  nodes: [asset],
  edges: [
    {
      id: 1,
      externalId: 'e1',
      sourceAssetId: 9,
      targetAssetId: 10,
      sourceFieldName: 'id',
      targetFieldName: 'order_id',
      lineageType: 'derived',
      processRef: 'etl-1',
      createdAt: null,
    },
  ],
}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
})

afterEach(() => vi.clearAllMocks())

describe('/meta/lineage 血缘分析页（增量 14）', () => {
  it('renders project picker and skips the asset query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(false)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-lineage-graph]').exists()).toBe(false)
    expect(governanceApi.listAssets).not.toHaveBeenCalled()
  })

  it('lists assets for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    const w = mount(View)
    await flushPromises()
    expect(governanceApi.listAssets).toHaveBeenCalledWith(1)
    expect(w.find('[data-asset-select]').exists()).toBe(true)
    expect(w.find('[data-no-asset]').exists()).toBe(true)
  })

  it('loads the lineage graph for the selected asset', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    vi.mocked(governanceApi.getLineage).mockResolvedValue(graph)
    const w = mount(View)
    await flushPromises()
    await w.find('[data-asset-select]').setValue('9')
    await flushPromises()
    expect(governanceApi.getLineage).toHaveBeenCalledWith(9, { direction: 'both', depth: 3 })
    expect(w.find('[data-lineage-graph]').exists()).toBe(true)
    expect(w.find('[data-lineage-graph]').text()).toContain('derived')
  })

  it('surfaces backend errors without dropping the picker', async () => {
    router.route.params.projectId = '1'
    vi.mocked(governanceApi.listAssets).mockRejectedValue(Object.assign(new Error('asset list failed'), { code: 4041 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('asset list failed')
    expect(w.find('[data-project-select]').exists()).toBe(false)
  })

  it('selects and loads the asset supplied by catalog lineage navigation', async () => {
    router.route.query = { projectId: '1', assetId: '9' }
    vi.mocked(governanceApi.listAssets).mockResolvedValue({ total: 1, page: 1, pageSize: 50, list: [asset] })
    vi.mocked(governanceApi.getLineage).mockResolvedValue(graph)
    const w = mount(View)
    await flushPromises()
    expect(w.find<HTMLSelectElement>('[data-asset-select]').element.value).toBe('9')
    expect(governanceApi.getLineage).toHaveBeenCalledWith(9, { direction: 'both', depth: 3 })
    expect(w.find('[data-no-asset]').exists()).toBe(false)
  })

})
