import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ide/IdeView.vue'

const router = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => router.route, useRouter: () => ({ push: router.push }) }))

/** 契约面全量 mock：createSqlIdeContract / createDatasourceContract 返回受控契约。 */
const spies = vi.hoisted(() => ({
  listDatabases: vi.fn(),
  listSchemas: vi.fn(),
  listRelations: vi.fn(),
  listColumns: vi.fn(),
  listRoutines: vi.fn(),
  listIndexes: vi.fn(),
  searchObjects: vi.fn(),
  lintSql: vi.fn(),
  executeSql: vi.fn(),
  cancelExecution: vi.fn(),
  openEventStream: vi.fn(),
  fetchResultPage: vi.fn(),
  listHistory: vi.fn(),
  deleteHistory: vi.fn(),
  listScripts: vi.fn(),
  saveScript: vi.fn(),
  deleteScript: vi.fn(),
  getDefinition: vi.fn(),
  exportResult: vi.fn(),
  listDatasources: vi.fn(),
  previewResolution: vi.fn(),
}))

vi.mock('../../services/rebuild/sqlIdeApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/sqlIdeApi')>()
  return {
    ...actual,
    createSqlIdeContract: () => ({
      listDatabases: spies.listDatabases,
      listSchemas: spies.listSchemas,
      listRelations: spies.listRelations,
      listColumns: spies.listColumns,
      listRoutines: spies.listRoutines,
      listIndexes: spies.listIndexes,
      searchObjects: spies.searchObjects,
      lintSql: spies.lintSql,
      executeSql: spies.executeSql,
      cancelExecution: spies.cancelExecution,
      openEventStream: spies.openEventStream,
      fetchResultPage: spies.fetchResultPage,
      listHistory: spies.listHistory,
      deleteHistory: spies.deleteHistory,
      listScripts: spies.listScripts,
      saveScript: spies.saveScript,
      deleteScript: spies.deleteScript,
      getDefinition: spies.getDefinition,
      exportResult: spies.exportResult,
      exportTable: vi.fn(),
      getExport: vi.fn(),
      getExportDownloadUrl: vi.fn(),
      cancelExport: vi.fn(),
    }),
  }
})

vi.mock('../../services/rebuild/datasourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/datasourceApi')>()
  return { ...actual, createDatasourceContract: () => ({ listDatasources: spies.listDatasources }) }
})

vi.mock('../../services/rebuild/variableApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/variableApi')>()
  return { ...actual, createVariableContract: () => ({ previewResolution: spies.previewResolution }) }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { listProjects } from '../../services/rebuild/projectApi'

const datasource = { id: 7, projectId: 1, name: '订单库', kind: 'mysql', host: '10.0.0.1', port: 3306, database: 'orders', username: 'reader', createdAt: '', updatedAt: '' }

const listeners: Record<string, Array<(ev: { data: string }) => void>> = {}

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  for (const spy of Object.values(spies)) spy.mockReset()
  for (const key of Object.keys(listeners)) delete listeners[key]
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
  spies.listDatasources.mockResolvedValue({ items: [datasource] })
  spies.listDatabases.mockResolvedValue({ items: [{ name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listSchemas.mockResolvedValue({ items: [{ database: 'orders', name: 'public' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listRelations.mockResolvedValue({ items: [{ kind: 'table', schema: 'public', name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listRoutines.mockResolvedValue({ items: [], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listColumns.mockResolvedValue({ items: [{ table: 'orders', name: 'id', dataType: 'bigint', nullable: false, key: 'PRI' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listIndexes.mockResolvedValue({ items: [{ table: 'orders', name: 'PRIMARY', columns: ['id'], unique: true }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listHistory.mockResolvedValue([])
  spies.previewResolution.mockResolvedValue({ resolvedValue: '42', diagnostics: [] })
  spies.fetchResultPage.mockResolvedValue({ stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1]], rowsTotal: 1, offset: 0, limit: 50 })
  spies.executeSql.mockResolvedValue({ taskId: 'task-1' })
  spies.openEventStream.mockImplementation(() => ({
    close: vi.fn(),
    addEventListener: (type: string, cb: (ev: { data: string }) => void) => {
      ;(listeners[type] ??= []).push(cb)
    },
  }))
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function dispatch(type: string, payload: unknown): void {
  for (const cb of listeners[type] ?? []) cb({ data: JSON.stringify(payload) })
}

describe('/ide 数据开发 IDE 只读态（增量 11/R5-A）', () => {
  it('renders project picker and skips the query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(true)
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-object-panel]').exists()).toBe(false)
    expect(spies.listDatasources).not.toHaveBeenCalled()
  })

  it('lists datasources for the project carried by route params', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    expect(spies.listDatasources).toHaveBeenCalledTimes(1)
    expect(w.find('[data-ds-select]').exists()).toBe(true)
    expect(w.find('[data-no-datasource]').exists()).toBe(true)
  })

  it('discards a stale database response after the datasource changes', async () => {
    router.route.params.projectId = '1'
    spies.listDatasources.mockResolvedValue({ items: [datasource, { ...datasource, id: 8, name: '数仓库' }] })
    let resolveFirst!: (value: Awaited<ReturnType<typeof spies.listDatabases>>) => void
    spies.listDatabases
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ items: [{ name: 'warehouse' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
    const w = mount(View)
    await flushPromises()

    await w.find('[data-ds-select]').setValue('7')
    await w.find('[data-ds-select]').setValue('8')
    await flushPromises()
    resolveFirst({ items: [{ name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
    await flushPromises()

    expect(w.find('[data-database-list]').text()).toContain('warehouse')
    expect(w.find('[data-database-list]').text()).not.toContain('orders')
  })

  it('loads the project supplied by ProjectSegmentView prop', async () => {
    const w = mount(View, { props: { projectId: 1 } })
    await flushPromises()
    expect(spies.listDatasources).toHaveBeenCalledTimes(1)
    expect((w.find('[data-project-select]').element as HTMLSelectElement).value).toBe('1')
    expect(w.find('[data-no-datasource]').exists()).toBe(true)
  })

  it('walks the object tree: databases → schemas → relations → columns/indexes', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-select]').setValue('7')
    await flushPromises()
    expect(spies.listDatabases).toHaveBeenCalledWith(7)
    expect(w.find('[data-database-list]').exists()).toBe(true)

    await w.find('[data-database-list] button').trigger('click')
    await flushPromises()
    expect(spies.listSchemas).toHaveBeenCalledWith(7, 'orders')

    await w.find('[data-schema-list] button').trigger('click')
    await flushPromises()
    expect(spies.listRelations).toHaveBeenCalledWith(7, 'orders', 'public', 'table')

    await w.find('[data-relation-list] button').trigger('click')
    await flushPromises()
    expect(spies.listColumns).toHaveBeenCalledWith(7, 'orders', 'orders', 'public')
    expect(spies.listIndexes).toHaveBeenCalledWith(7, 'orders', 'orders', 'public')
    expect(w.find('[data-column-list]').text()).toContain('id')
    expect(w.find('[data-index-list]').text()).toContain('PRIMARY')
  })

  it('executes SQL over SSE and renders the result grid', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-select]').setValue('7')
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT id FROM orders')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()
    expect(spies.executeSql).toHaveBeenCalled()
    expect(spies.openEventStream).toHaveBeenCalledWith('task-1')

    dispatch('result', { stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1], [2]], rowsTotal: 2, elapsedMs: 5 })
    await flushPromises()
    expect(w.find('[data-result-grid]').exists()).toBe(true)
    expect(w.find('[data-result-grid]').text()).toContain('id')

    dispatch('done', { status: 'succeeded', elapsedMs: 9, historyId: 55, stmtCount: 1 })
    await flushPromises()
    expect(w.find('[data-status]').text()).toContain('执行成功')
    expect(spies.listHistory).toHaveBeenCalledWith(7)
  })

  it('refreshes variable references and resolution preview when SQL changes', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-select]').setValue('7')
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT ${workflow.biz_date}')
    await flushPromises()
    expect(w.find('[data-vars]').exists()).toBe(true)
    expect(w.find('[data-vars]').text()).toContain('$workflow.biz_date')
    expect(spies.previewResolution).toHaveBeenCalledWith('${workflow.biz_date}', { projectId: 1 })
    expect(w.find('[data-vars]').text()).toContain('42')
  })

  it('cancels a running execution', async () => {
    router.route.params.projectId = '1'
    spies.cancelExecution.mockResolvedValue({ canceled: true })
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-select]').setValue('7')
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()
    await w.find('[data-cancel]').trigger('click')
    await flushPromises()
    expect(spies.cancelExecution).toHaveBeenCalledWith('task-1')
  })

  it('loads and restores execution history', async () => {
    router.route.params.projectId = '1'
    spies.listHistory.mockResolvedValue([
      { historyId: 9, datasourceId: 7, db: 'orders', sqlText: 'SELECT 1', status: 'succeeded', stmtCount: 1, elapsedMs: 3, createdAt: '' },
    ])
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-select]').setValue('7')
    await flushPromises()
    await w.find('[data-history-toggle]').trigger('click')
    await flushPromises()
    expect(w.find('[data-history]').exists()).toBe(true)
    await w.find('.ide-history-item').trigger('click')
    expect((w.find('[data-sql-editor]').element as HTMLTextAreaElement).value).toContain('SELECT 1')
  })

  it('surfaces backend errors without dropping the editor', async () => {
    router.route.params.projectId = '1'
    spies.listDatabases.mockRejectedValue(Object.assign(new Error('metadata browse failed'), { code: 5022 }))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-ds-select]').setValue('7')
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('metadata browse failed')
    expect(w.find('[data-sql-editor]').exists()).toBe(true)
  })
})
