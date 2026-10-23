import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../datasource/DataSourceListView.vue'

const router = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => router.route, useRouter: () => ({ push: router.push }) }))

/** 契约面全量 mock：createDatasourceContract 返回受控契约，projectId 由组件按上下文注入。 */
const spies = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  test: vi.fn(),
  schemas: vi.fn(),
  objects: vi.fn(),
  columns: vi.fn(),
  get: vi.fn(),
  validate: vi.fn(),
  probe: vi.fn(),
}))

vi.mock('../../services/rebuild/datasourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/datasourceApi')>()
  return {
    ...actual,
    createDatasourceContract: () => ({
      listDatasources: spies.list,
      createDatasource: spies.create,
      updateDatasource: spies.update,
      deleteDatasource: spies.remove,
      testDatasource: spies.test,
      listSchemas: spies.schemas,
      listObjects: spies.objects,
      listColumns: spies.columns,
      getDatasource: spies.get,
      validateDraft: spies.validate,
      probeProfile: spies.probe,
    }),
  }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { listProjects } from '../../services/rebuild/projectApi'

const row = {
  id: 1,
  projectId: 1,
  name: '订单库',
  kind: 'mysql' as const,
  host: '10.0.0.1',
  port: 3306,
  database: 'orders',
  username: 'reader',
  createdAt: '2026-10-22T10:00:00Z',
  updatedAt: '2026-10-22T10:00:00Z',
}

const column = {
  schema: 'public',
  object: 'orders',
  name: 'id',
  dataType: 'bigint',
  databaseType: 'bigint',
  nullable: false,
  primaryKey: true,
  comment: '',
}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  for (const spy of Object.values(spies)) spy.mockReset()
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
  spies.list.mockResolvedValue({ items: [row] })
  spies.schemas.mockResolvedValue({ items: ['public', 'ods'], nextAfter: null, limit: 100 })
  spies.objects.mockResolvedValue({
    items: [{ schema: 'public', name: 'orders', type: 'table' }],
    nextAfter: null,
    limit: 100,
  })
  spies.columns.mockResolvedValue({ items: [column], nextAfter: null, limit: 200 })
  spies.test.mockResolvedValue({ connected: true, database: 'orders', serverVersion: '8.0.35', capabilities: [] })
  spies.create.mockResolvedValue({ ...row })
  spies.remove.mockResolvedValue({ deleted: true, id: 1 })
  vi.stubGlobal('confirm', vi.fn(() => true))
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('/ds/list 数据源管理页（增量 10/10A）', () => {
  it('renders project picker and skips the query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-ds-list]').exists()).toBe(false)
    expect(spies.list).not.toHaveBeenCalled()
  })

  it('lists datasources for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    expect(spies.list).toHaveBeenCalledTimes(1)
    expect(w.find('[data-ds-list]').exists()).toBe(true)
    expect(w.find('[data-ds-id="1"]').text()).toContain('订单库')
    expect(w.find('[data-ds-id="1"]').text()).toContain('10.0.0.1:3306')
  })

  it('registers a datasource through the dialog and reloads the list', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-create]').attributes('disabled')).toBeUndefined()

    await w.find('[data-create]').trigger('click')
    await w.find('[data-name]').setValue('订单库')
    await w.find('[data-kind]').setValue('postgresql')
    await w.find('[data-host]').setValue('10.0.0.9')
    await w.find('[data-port]').setValue('5432')
    await w.find('[data-database]').setValue('warehouse')
    await w.find('[data-username]').setValue('etl')
    await w.find('[data-password]').setValue('secret')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(spies.create).toHaveBeenCalledWith({
      name: '订单库',
      kind: 'postgresql',
      host: '10.0.0.9',
      port: 5432,
      database: 'warehouse',
      username: 'etl',
      password: 'secret',
    })
    expect(w.find('[role=dialog]').exists()).toBe(false)
    // 保存后刷新列表
    expect(spies.list.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('runs a connectivity test and reports the probe result', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-test]').trigger('click')
    await flushPromises()

    expect(spies.test).toHaveBeenCalledWith(1)
    const text = w.find('[data-test-result]').text()
    expect(text).toContain('连通成功')
    expect(text).toContain('8.0.35')
  })

  it('deletes a datasource after confirmation and reloads', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-delete]').trigger('click')
    await flushPromises()

    expect(globalThis.confirm).toHaveBeenCalled()
    expect(spies.remove).toHaveBeenCalledWith(1)
  })

  it('browses metadata three levels: schemas → objects → columns', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-ds-id="1"]').trigger('click')
    await flushPromises()
    expect(spies.schemas).toHaveBeenCalledWith(1)
    expect(w.findAll('[data-schema-list] li')).toHaveLength(2)

    await w.find('[data-schema-list] button').trigger('click')
    await flushPromises()
    expect(spies.objects).toHaveBeenCalledWith(1, 'public')

    await w.find('[data-object-list] button').trigger('click')
    await flushPromises()
    expect(spies.columns).toHaveBeenCalledWith(1, 'public', 'orders')
    expect(w.find('[data-column-list]').text()).toContain('id')
  })

  it('surfaces backend errors without dropping the list', async () => {
    router.route.params.projectId = '1'
    spies.test.mockRejectedValue(Object.assign(new Error('connection failed'), { code: 5021 }))
    const w = mount(View)
    await flushPromises()

    await w.find('[data-test]').trigger('click')
    await flushPromises()

    expect(w.find('[role=alert]').text()).toContain('connection failed')
    expect(w.find('[data-ds-list]').exists()).toBe(true)
  })
})
