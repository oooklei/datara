import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ide/IdeView.vue'
import ideSource from '../ide/IdeView.vue?raw'

const router = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => router.route, useRouter: () => ({ push: router.push }) }))

vi.mock('../ide/ResultGrid.vue', () => ({
  default: {
    name: 'ResultGrid',
    props: { columns: { type: Array, default: () => [] }, rows: { type: Array, default: () => [] } },
    emits: ['copied'],
    template: '<div class="result-grid-stub" />',
  },
}))

/** 契约面全量 mock（B4-e 历史抽屉：listHistory/deleteHistory/fetchResultPage/executeSql 受控）。 */
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
  getExecutionStatus: vi.fn(),
  openEventStream: vi.fn(),
  fetchResultPage: vi.fn(),
  listHistory: vi.fn(),
  deleteHistory: vi.fn(),
  listScripts: vi.fn(),
  saveScript: vi.fn(),
  deleteScript: vi.fn(),
  getDefinition: vi.fn(),
  exportResult: vi.fn(),
  getExportDownloadUrl: vi.fn(),
  listTableRows: vi.fn(),
  applyTableRows: vi.fn(),
  importCsv: vi.fn(),
  auditTable: vi.fn(),
  listDatasources: vi.fn(),
  previewResolution: vi.fn(),
  checkReference: vi.fn(),
  completeVariables: vi.fn(),
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
      getExecutionStatus: spies.getExecutionStatus,
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
      getExportDownloadUrl: spies.getExportDownloadUrl,
      cancelExport: vi.fn(),
      listTableRows: spies.listTableRows,
      applyTableRows: spies.applyTableRows,
      importCsv: spies.importCsv,
      auditTable: spies.auditTable,
    }),
  }
})

vi.mock('../../services/rebuild/datasourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/datasourceApi')>()
  return { ...actual, createDatasourceContract: () => ({ listDatasources: spies.listDatasources }) }
})

vi.mock('../../services/rebuild/variableApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/variableApi')>()
  return {
    ...actual,
    createVariableContract: () => ({
      previewResolution: spies.previewResolution,
      checkReference: spies.checkReference,
      completeVariables: spies.completeVariables,
    }),
  }
})

vi.mock('../../services/rebuild/projectApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { listProjects } from '../../services/rebuild/projectApi'
import type { HistoryEntry } from '../../services/rebuild/sqlIdeApi'

const datasource = { id: 7, projectId: 1, name: '订单库', kind: 'mysql', host: '10.0.0.1', port: 3306, database: 'orders', username: 'reader', createdAt: '', updatedAt: '' }

const listeners: Record<string, Array<(ev: { data: string }) => void>> = {}
const streamClose = vi.fn()

function historyEntry(overrides: Partial<HistoryEntry> & { historyId: string | number }): HistoryEntry {
  return {
    datasourceId: 7,
    db: 'orders',
    sqlText: 'SELECT * FROM orders;',
    status: 'succeeded',
    stmtCount: 1,
    elapsedMs: 12,
    createdAt: '2026-10-28T08:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  router.route.params = { projectId: '1' }
  router.route.query = {}
  for (const spy of Object.values(spies)) spy.mockReset()
  streamClose.mockReset()
  for (const key of Object.keys(listeners)) delete listeners[key]
  sessionStorage.clear()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
  spies.listDatasources.mockResolvedValue({ items: [datasource] })
  spies.listDatabases.mockResolvedValue({ items: [{ name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listSchemas.mockResolvedValue({ items: [{ database: 'orders', name: 'public' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listRelations.mockResolvedValue({ items: [{ kind: 'table', schema: 'public', name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listRoutines.mockResolvedValue({ items: [], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listColumns.mockResolvedValue({ items: [{ table: 'orders', name: 'id', dataType: 'bigint', nullable: false, key: 'PRI' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listIndexes.mockResolvedValue({ items: [], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listHistory.mockResolvedValue([])
  spies.listScripts.mockResolvedValue([])
  spies.previewResolution.mockResolvedValue({ resolvedValue: '42', diagnostics: [] })
  spies.checkReference.mockResolvedValue({ expression: '', valid: true, diagnostics: [] })
  spies.completeVariables.mockResolvedValue([])
  spies.fetchResultPage.mockResolvedValue({ stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1]], rowsTotal: 1, offset: 0, limit: 200 })
  spies.executeSql.mockResolvedValue({ taskId: 'task-1', historyId: 55, resultSetId: 'rs1' })
  spies.openEventStream.mockImplementation(() => ({
    close: streamClose,
    addEventListener: (type: string, cb: (ev: { data: string }) => void) => {
      ;(listeners[type] ??= []).push(cb)
    },
  }))
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

async function dispatch(type: string, payload: unknown): Promise<void> {
  await Promise.all((listeners[type] ?? []).map((cb) => cb({ data: JSON.stringify(payload) })))
}

async function mountView(): Promise<VueWrapper> {
  const w = mount(View, { global: { stubs: { teleport: true } } })
  await flushPromises()
  return w
}

async function openDrawer(w: VueWrapper): Promise<void> {
  await w.find('[data-history-toggle]').trigger('click')
  await flushPromises()
}

describe('/ide 执行历史抽屉（S8，§6.7 核心子集）', () => {
  it('keeps the r6 token discipline and wires the S8 drawer identifiers', () => {
    expect(ideSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(ideSource).toContain('HISTORY_PAGE_SIZE = 20')
    expect(ideSource).toContain('historyKeyword')
    expect(ideSource).toContain('execStmtDetails')
    expect(ideSource).toContain('fetchResultPage(h.historyId, null, 0, 1, i)')
    expect(ideSource).toContain('变量快照')
    expect(ideSource).toContain('按当前模式再次执行该历史 SQL？')
  })

  it('opens the drawer, lists the datasource history and refreshes on demand', async () => {
    spies.listHistory.mockResolvedValue([historyEntry({ historyId: 'h-1' })])
    const w = await mountView()
    expect(spies.listHistory).toHaveBeenCalledTimes(1) // 挂载时已按当前数据源预载
    await openDrawer(w)
    expect(spies.listHistory).toHaveBeenCalledTimes(2)
    expect(w.find('.ide-history-item').exists()).toBe(true)

    await w.find('[data-history-refresh]').trigger('click')
    await flushPromises()
    expect(spies.listHistory).toHaveBeenCalledTimes(3)
  })

  it('renders status badge, sequence number, db, counters and formatted time per row', async () => {
    spies.listHistory.mockResolvedValue([
      historyEntry({ historyId: 'h-1', status: 'succeeded' }),
      historyEntry({ historyId: 'h-2', status: 'failed', sqlText: 'DROP TABLE ghost;' }),
    ])
    const w = await mountView()
    await openDrawer(w)
    const badges = w.findAll('[data-history-status]')
    expect(badges).toHaveLength(2)
    expect(badges[0].classes()).toContain('is-ok')
    expect(badges[1].classes()).toContain('is-fail')
    const first = w.findAll('.ide-history-item')[0]
    expect(first.text()).toContain('#1')
    expect(first.text()).toContain('orders')
    expect(first.text()).toContain('1 语句 · 12ms')
    expect(first.text()).toContain('2026-10-28 08:00:00')
  })

  it('filters the history by keyword on Enter', async () => {
    spies.listHistory.mockResolvedValue([
      historyEntry({ historyId: 'h-1', sqlText: 'SELECT * FROM orders;' }),
      historyEntry({ historyId: 'h-2', sqlText: 'SELECT 1;', db: 'warehouse' }),
    ])
    const w = await mountView()
    await openDrawer(w)
    expect(w.findAll('.ide-history-item')).toHaveLength(2)
    await w.find('[data-history-keyword]').setValue('orders')
    await w.find('[data-history-keyword]').trigger('keydown.enter')
    await flushPromises()
    expect(w.findAll('.ide-history-item')).toHaveLength(1)
    expect(w.find('.ide-history-item').text()).toContain('SELECT * FROM orders')
  })

  it('paginates the history 20 entries per page', async () => {
    spies.listHistory.mockResolvedValue(
      Array.from({ length: 22 }, (_, i) => historyEntry({ historyId: `h-${i}` })),
    )
    const w = await mountView()
    await openDrawer(w)
    expect(w.findAll('.ide-history-item')).toHaveLength(20)
    expect(w.find('[data-history]').text()).toContain('1 / 2')

    const next = w.findAll('[data-history] .ide-history-pager button')[1]
    await next.trigger('click')
    await flushPromises()
    expect(w.findAll('.ide-history-item')).toHaveLength(2)
    expect(w.find('[data-history]').text()).toContain('2 / 2')
  })

  it('expands per-statement details by replaying snapshots with stmtIndex and collapses on second click', async () => {
    spies.listHistory.mockResolvedValue([
      historyEntry({ historyId: 'h-1', sqlText: 'SELECT * FROM a; UPDATE b SET x = 1;', stmtCount: 2 }),
    ])
    spies.fetchResultPage
      .mockResolvedValueOnce({ stmtIndex: 0, resultSetId: 'rs-a', columns: ['id'], rows: [[1]], rowsTotal: 5, offset: 0, limit: 1 })
      .mockRejectedValueOnce(new Error('result snapshot is not available'))
    const w = await mountView()
    await openDrawer(w)

    await w.find('[data-history-view]').trigger('click')
    await flushPromises()
    expect(w.find('[data-history-detail]').exists()).toBe(true)
    const stmts = w.findAll('[data-history-stmt]')
    expect(stmts).toHaveLength(2)
    expect(stmts[0].text()).toContain('5 行')
    expect(stmts[1].text()).toContain('succeeded')
    expect(spies.fetchResultPage).toHaveBeenNthCalledWith(1, 'h-1', null, 0, 1, 0)
    expect(spies.fetchResultPage).toHaveBeenNthCalledWith(2, 'h-1', null, 0, 1, 1)

    await w.find('[data-history-view]').trigger('click')
    await flushPromises()
    expect(w.find('[data-history-detail]').exists()).toBe(false)
    expect(spies.fetchResultPage).toHaveBeenCalledTimes(2)
  })

  it('binds live-captured statement details and the variable snapshot after done (S7/S8)', async () => {
    const w = await mountView()
    await w.find('[data-sql-editor]').setValue('UPDATE t SET x = 1 WHERE rate = ${global.rate};')
    await flushPromises()
    await w.find('[data-execute]').trigger('click')
    await flushPromises()

    await dispatch('log', { stmtIndex: 0, type: 'end', kind: 'exec', affected: 3, elapsedMs: 8, sql: 'UPDATE t SET x = 1' })
    await dispatch('done', { status: 'succeeded', elapsedMs: 20, historyId: 55, stmtCount: 1 })
    await flushPromises()

    spies.listHistory.mockResolvedValue([historyEntry({ historyId: 55, sqlText: 'UPDATE t SET x = 1 WHERE rate = 42;', datasourceId: 7 })])
    await openDrawer(w)
    await w.find('[data-history-view]').trigger('click')
    await flushPromises()

    const stmts = w.findAll('[data-history-stmt]')
    expect(stmts).toHaveLength(1)
    expect(stmts[0].text()).toContain('affected 3')
    expect(spies.fetchResultPage).not.toHaveBeenCalledWith(55, null, 0, 1, 0)
    expect(w.find('[data-history-vars]').text()).toContain('${global.rate} = 42')
  })

  it('asks for confirmation before deleting and falls back from an emptied last page', async () => {
    const entries = Array.from({ length: 21 }, (_, i) => historyEntry({ historyId: `h-${i}` }))
    const deleted = new Set<string | number>()
    spies.listHistory.mockImplementation(async () => entries.filter((e) => !deleted.has(e.historyId)))
    spies.deleteHistory.mockImplementation(async (historyId: string | number) => { deleted.add(historyId) })
    const confirm = vi.fn(() => true)
    vi.stubGlobal('confirm', confirm)
    const w = await mountView()
    await openDrawer(w)

    const next = w.findAll('[data-history] .ide-history-pager button')[1]
    await next.trigger('click')
    await flushPromises()
    expect(w.findAll('.ide-history-item')).toHaveLength(1)

    await w.find('[data-history-del]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('确认删除该条执行历史？')
    expect(spies.deleteHistory).toHaveBeenCalledWith('h-20')
    expect(spies.listHistory).toHaveBeenCalledTimes(3) // 挂载预载 + 开抽屉 + 删除后刷新
    expect(w.findAll('.ide-history-item')).toHaveLength(20)
    expect(w.find('[data-history-pager], .ide-history-pager').exists()).toBe(false)

    confirm.mockReturnValue(false)
    await w.find('[data-history-del]').trigger('click')
    await flushPromises()
    expect(spies.deleteHistory).toHaveBeenCalledTimes(1)
  })

  it('reruns the history SQL after confirmation and blocks cross-datasource rerun', async () => {
    spies.listHistory.mockResolvedValue([
      historyEntry({ historyId: 'h-1', sqlText: 'SELECT * FROM orders;', datasourceId: 7 }),
      historyEntry({ historyId: 'h-2', sqlText: 'SELECT 1;', datasourceId: 99 }),
    ])
    const confirm = vi.fn(() => true)
    vi.stubGlobal('confirm', confirm)
    const w = await mountView()
    await openDrawer(w)

    const rerunButtons = w.findAll('[data-history-rerun]')
    expect(rerunButtons[1].attributes('disabled')).toBeDefined()

    await w.find('[data-sql-editor]').setValue('SELECT old;')
    await rerunButtons[0].trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('按当前模式再次执行该历史 SQL？')
    expect(spies.executeSql).toHaveBeenCalledTimes(1)
    expect(spies.executeSql.mock.calls[0][0].sql).toBe('SELECT * FROM orders;')
  })

  it('loads the history SQL into the editor without executing (编辑)', async () => {
    spies.listHistory.mockResolvedValue([historyEntry({ historyId: 'h-1', sqlText: 'SELECT editable;' })])
    const w = await mountView()
    await openDrawer(w)
    await w.find('[data-history-edit]').trigger('click')
    await flushPromises()
    expect((w.find('[data-sql-editor]').element as HTMLTextAreaElement).value).toBe('SELECT editable;')
    expect(spies.executeSql).not.toHaveBeenCalled()
  })
})
