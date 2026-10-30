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
const row2 = { ...row, id: 2, name: '仓库', kind: 'postgresql' as const, host: '10.0.0.2', port: 5432, database: 'warehouse' }

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
  spies.update.mockResolvedValue({ ...row })
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
    expect(w.find('[data-project-select]').exists()).toBe(false)
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

  it('filters the datasource list by keyword, kind, and connectivity state', async () => {
    router.route.params.projectId = '1'
    spies.list.mockResolvedValue({ items: [row, row2] })
    const w = mount(View)
    await flushPromises()

    await w.find('[data-filter-keyword]').setValue('仓库')
    expect(w.findAll('[data-ds-id]')).toHaveLength(1)
    expect(w.find('[data-ds-id="2"]').exists()).toBe(true)
    await w.find('[data-filter-keyword]').setValue('')
    await w.find('[data-filter-kind]').setValue('postgresql')
    expect(w.findAll('[data-ds-id]')).toHaveLength(1)

    await w.find('[data-filter-kind]').setValue('')
    await w.find('[data-ds-id="1"] [data-test]').trigger('click')
    await flushPromises()
    await w.find('[data-filter-status]').setValue('online')
    expect(w.findAll('[data-ds-id]')).toHaveLength(1)
    expect(w.find('[data-ds-id="1"]').exists()).toBe(true)
  })

  it('opens datasource metadata through the explicit detail action', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-detail-action]').trigger('click')
    await flushPromises()
    expect(spies.schemas).toHaveBeenCalledWith(1)
    expect(w.find('[data-detail]').exists()).toBe(true)
  })

  it('edits a datasource by jumping straight to the connection step without resending a blank password', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-edit]').trigger('click')
    // 编辑直进连接步（§7.4），标题「编辑数据源」
    expect(w.get('[data-wizard]').attributes('aria-label')).toBe('编辑数据源')
    expect(w.find('[data-wiz-step-conn]').exists()).toBe(true)
    await w.get('[data-host]').setValue('10.0.0.8')
    await w.get('[data-wiz-next]').trigger('click')
    await w.get('[data-save-test]').trigger('click')
    await flushPromises()

    expect(spies.update).toHaveBeenCalledWith(1, expect.objectContaining({ host: '10.0.0.8', password: undefined }))
    expect(spies.test).toHaveBeenCalledWith(1)
    expect(spies.list).toHaveBeenCalledTimes(2)
  })

  it('registers a datasource through the 3-step wizard and reloads the list', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-create]').attributes('disabled')).toBeUndefined()

    await w.find('[data-create]').trigger('click')
    // ① 类型选择：标题先为「注册数据源」
    expect(w.get('[data-wizard]').attributes('aria-label')).toBe('注册数据源')
    await w.get('[data-wiz-type="postgresql"]').trigger('click')
    await w.get('[data-wiz-name]').setValue('订单库')
    // 注册流程标题带上名称（复刻旧 dialogTitle）
    expect(w.get('[data-wizard]').attributes('aria-label')).toBe('注册数据源:订单库')
    await w.get('[data-wiz-next]').trigger('click')
    // ② 连接信息：选中类型带出默认端口 5432
    expect(w.find('[data-wiz-step-conn]').exists()).toBe(true)
    expect(Number((w.get('[data-port]').element as HTMLInputElement).value)).toBe(5432)
    await w.get('[data-host]').setValue('10.0.0.9')
    await w.get('[data-port]').setValue('5432')
    await w.get('[data-database]').setValue('warehouse')
    await w.get('[data-username]').setValue('etl')
    await w.get('[data-password]').setValue('secret')
    await w.get('[data-wiz-next]').trigger('click')
    // ③ 保存并测试：连通成功即关窗并刷新列表
    expect(w.find('[data-wiz-step-test]').exists()).toBe(true)
    await w.get('[data-save-test]').trigger('click')
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
    expect(spies.test).toHaveBeenCalledWith(1)
    expect(w.find('[role=dialog]').exists()).toBe(false)
    // 保存后刷新列表
    expect(spies.list.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('guards wizard steps and supports param retest after a failed save-and-test', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-create]').trigger('click')
    // 未选类型 / 未填名称不得进入连接步
    await w.get('[data-wiz-next]').trigger('click')
    expect(w.find('[data-wiz-error]').text()).toContain('数据源类型')
    await w.get('[data-wiz-type="mysql"]').trigger('click')
    await w.get('[data-wiz-next]').trigger('click')
    expect(w.find('[data-wiz-error]').text()).toContain('名称')
    await w.get('[data-wiz-name]').setValue('流复制源')
    await w.get('[data-wiz-next]').trigger('click')
    expect(w.find('[data-wiz-step-conn]').exists()).toBe(true)
    await w.get('[data-wiz-next]').trigger('click')
    expect(w.find('[data-wiz-error]').text()).toContain('主机')
    await w.get('[data-host]').setValue('10.0.0.5')
    await w.get('[data-port]').setValue('3306')
    await w.get('[data-database]').setValue('biz')
    await w.get('[data-username]').setValue('etl')
    await w.get('[data-wiz-next]').trigger('click')

    // 首测失败：banner 呈现 + 已注册提示；create 仅 1 次（savedId 固化防重复创建）
    spies.test.mockRejectedValueOnce(Object.assign(new Error('connection refused'), { code: 5021 }))
    await w.get('[data-save-test]').trigger('click')
    await flushPromises()
    expect(spies.create).toHaveBeenCalledTimes(1)
    const banner = w.get('[data-wiz-banner]')
    expect(banner.text()).toContain('连通失败')
    expect(banner.text()).toContain('connection refused')
    expect(w.text()).toContain('可返回上一步调整参数')

    // 仅重测（不改参）：不再触发 create/update
    await w.get('[data-retest]').trigger('click')
    await flushPromises()
    expect(spies.test).toHaveBeenCalledTimes(2)
    expect(w.find('[role=dialog]').exists()).toBe(false)
  })

  it('keeps the wizard open for param fixes after a failed save-and-test (retest loop)', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()

    await w.find('[data-create]').trigger('click')
    await w.get('[data-wiz-type="mysql"]').trigger('click')
    await w.get('[data-wiz-name]').setValue('离线库')
    await w.get('[data-wiz-next]').trigger('click')
    await w.get('[data-host]').setValue('10.0.0.5')
    await w.get('[data-database]').setValue('biz')
    await w.get('[data-username]').setValue('etl')
    await w.get('[data-wiz-next]').trigger('click')

    spies.test.mockRejectedValueOnce(Object.assign(new Error('connection refused'), { code: 5021 }))
    await w.get('[data-save-test]').trigger('click')
    await flushPromises()
    expect(w.find('[role=dialog]').exists()).toBe(true)

    // 返回上一步改参后再次保存并测试：走 update（savedId），成功后关窗
    await w.get('[data-wiz-prev]').trigger('click')
    await w.get('[data-host]').setValue('10.0.0.6')
    await w.get('[data-wiz-next]').trigger('click')
    await w.get('[data-save-test]').trigger('click')
    await flushPromises()
    expect(spies.create).toHaveBeenCalledTimes(1)
    expect(spies.update).toHaveBeenCalledTimes(1)
    expect(spies.update).toHaveBeenCalledWith(1, expect.objectContaining({ host: '10.0.0.6' }))
    expect(spies.test).toHaveBeenCalledTimes(2)
    expect(w.find('[role=dialog]').exists()).toBe(false)
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

  it('discards a stale schema response after selecting another datasource', async () => {
    router.route.params.projectId = '1'
    spies.list.mockResolvedValue({ items: [row, { ...row, id: 2, name: '数仓库' }] })
    let resolveFirst!: (value: { items: string[]; nextAfter: null; limit: number }) => void
    spies.schemas
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ items: ['warehouse'], nextAfter: null, limit: 100 })
    const w = mount(View)
    await flushPromises()

    await w.find('[data-ds-id="1"]').trigger('click')
    await w.find('[data-ds-id="2"]').trigger('click')
    await flushPromises()
    resolveFirst({ items: ['stale_orders'], nextAfter: null, limit: 100 })
    await flushPromises()

    expect(w.find('[data-schema-list]').text()).toContain('warehouse')
    expect(w.find('[data-schema-list]').text()).not.toContain('stale_orders')
  })

  it('discards a stale object response after selecting another schema', async () => {
    router.route.params.projectId = '1'
    let resolvePublic!: (value: { items: Array<{ schema: string; name: string; type: 'table' }>; nextAfter: null; limit: number }) => void
    spies.objects.mockImplementation((_id: number, schema: string) => schema === 'public'
      ? new Promise((resolve) => { resolvePublic = resolve })
      : Promise.resolve({ items: [{ schema: 'ods', name: 'customers', type: 'table' }], nextAfter: null, limit: 100 }))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-id="1"]').trigger('click')
    await flushPromises()

    const schemaButtons = w.findAll('[data-schema-list] button')
    await schemaButtons[0]!.trigger('click')
    await schemaButtons[1]!.trigger('click')
    await flushPromises()
    resolvePublic({ items: [{ schema: 'public', name: 'stale_orders', type: 'table' }], nextAfter: null, limit: 100 })
    await flushPromises()

    expect(w.find('[data-object-list]').text()).toContain('customers')
    expect(w.find('[data-object-list]').text()).not.toContain('stale_orders')
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
