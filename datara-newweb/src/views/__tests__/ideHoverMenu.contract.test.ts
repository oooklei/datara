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

/** 契约面全量 mock（B4-d 需 table-data 四方法受控）。 */
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

const datasource = { id: 7, projectId: 1, name: '订单库', kind: 'mysql', host: '10.0.0.1', port: 3306, database: 'orders', username: 'reader', createdAt: '', updatedAt: '' }

beforeEach(() => {
  router.route.params = { projectId: '1' }
  router.route.query = {}
  for (const spy of Object.values(spies)) spy.mockReset()
  sessionStorage.clear()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.mocked(listProjects).mockResolvedValue({ total: 1, list: [{ id: 1, name: '订单库' }] })
  spies.listDatasources.mockResolvedValue({ items: [datasource] })
  spies.listDatabases.mockResolvedValue({ items: [{ name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listSchemas.mockResolvedValue({ items: [{ database: 'orders', name: 'public' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listRelations.mockResolvedValue({ items: [{ kind: 'table', schema: 'public', name: 'orders' }, { kind: 'view', schema: 'public', name: 'v_orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listRoutines.mockResolvedValue({ items: [], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listColumns.mockResolvedValue({ items: [{ table: 'orders', name: 'id', dataType: 'bigint', nullable: false, key: 'PRI' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listIndexes.mockResolvedValue({ items: [{ table: 'orders', name: 'PRIMARY', columns: ['id'], unique: true }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
  spies.listHistory.mockResolvedValue([])
  spies.listScripts.mockResolvedValue([])
  spies.previewResolution.mockResolvedValue({ resolvedValue: '42', diagnostics: [] })
  spies.checkReference.mockResolvedValue({ expression: '', valid: true, diagnostics: [] })
  spies.completeVariables.mockResolvedValue([])
  spies.getDefinition.mockResolvedValue({ definition: 'CREATE TABLE orders (id INT)', capability: 'supported', constraints: [] })
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

async function mountWithTree(): Promise<VueWrapper> {
  const w = mount(View, { global: { stubs: { teleport: true } } })
  await flushPromises()
  // S9 默认已展开第一个根节点（source:7 → db:7:orders），再点击会折叠
  await w.find('[data-tree-node="db:7:orders"]').trigger('click')
  await flushPromises()
  await w.find('[data-tree-node="schema:7:orders:public"]').trigger('click')
  await flushPromises()
  return w
}

async function openMenu(w: VueWrapper, key = 'rel:7:orders:public:table:orders'): Promise<VueWrapper> {
  await w.find(`[data-tree-node="${key}"]`).trigger('mouseenter', { clientX: 20, clientY: 20 })
  await flushPromises()
  return w
}

function editorValue(w: VueWrapper): string {
  return (w.find('[data-sql-editor]').element as HTMLTextAreaElement).value
}

describe('B4-d G10 表/视图悬浮菜单（S5/S6）', () => {
  it('keeps the fill-only SQL contract in source (no auto-execution path)', () => {
    expect(ideSource).toContain('预制 SQL 仅填充编辑器，不自动执行')
    // 编辑数据/CSV/稽核弹窗与菜单全量接线（B4-d）
    expect(ideSource).toContain('auditTable')
    expect(ideSource).toContain('editDataOpen')
    expect(ideSource).toContain('csvImportOpen')
    expect(ideSource).toContain('generateAddColumn')
    expect(ideSource).toContain('generateAddIndex')
  })

  it('shows 11 items for tables and 7 for views with the fixed footer hint', async () => {
    const w = await openMenu(await mountWithTree())
    const menu = w.find('[data-hover-menu]')
    expect(menu.exists()).toBe(true)
    expect(menu.findAll('[data-menu-item]')).toHaveLength(11)
    expect(menu.find('.ide-menu-foot').text()).toContain('仅填充编辑器')
    expect(menu.find('[data-menu-item="drop"]').text()).toContain('删除表')
    expect(menu.find('[data-menu-item="truncate-audit"]').text()).toContain('截断表')

    await menu.find('[data-menu-item="count"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-hover-menu]').exists()).toBe(false)
    expect(editorValue(w)).toContain('SELECT COUNT(*) AS cnt FROM public.orders;')
    expect(spies.executeSql).not.toHaveBeenCalled()

    await openMenu(w, 'rel:7:orders:public:view:v_orders')
    expect(w.find('[data-hover-menu]').findAll('[data-menu-item]')).toHaveLength(7)
    expect(w.find('[data-menu-item="drop"]').exists()).toBe(false)
  })

  it('hides the menu after the 260ms delayed mouseleave', async () => {
    vi.useFakeTimers()
    try {
      const w = await mountWithTree()
      await w.find('[data-tree-node="rel:7:orders:public:table:orders"]').trigger('mouseenter', { clientX: 20, clientY: 20 })
      await flushPromises()
      expect(w.find('[data-hover-menu]').exists()).toBe(true)
      await w.find('[data-tree-node="rel:7:orders:public:table:orders"]').trigger('mouseleave')
      await w.find('[data-hover-menu]').trigger('mouseenter')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(w.find('[data-hover-menu]').exists()).toBe(true)
      await w.find('[data-hover-menu]').trigger('mouseleave')
      vi.advanceTimersByTime(300)
      await flushPromises()
      expect(w.find('[data-hover-menu]').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('fills a limited SELECT via the row-count prompt without executing', async () => {
    const prompt = vi.fn(() => '50')
    vi.stubGlobal('prompt', prompt)
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="select"]').trigger('click')
    await flushPromises()
    expect(prompt).toHaveBeenCalled()
    expect(editorValue(w)).toContain('SELECT * FROM public.orders LIMIT 50;')
    expect(spies.executeSql).not.toHaveBeenCalled()

    prompt.mockReturnValue('abc')
    await openMenu(w)
    await w.find('[data-menu-item="select"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-error]').text()).toContain('非负整数')
  })

  it('fills the DDL definition through getDefinition', async () => {
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="ddl"]').trigger('click')
    await flushPromises()
    expect(spies.getDefinition).toHaveBeenCalledWith(expect.objectContaining({ datasourceId: 7, objectKind: 'table', objectRef: { schema: 'public', name: 'orders' } }))
    expect(editorValue(w)).toContain('-- public.orders 结构')
    expect(editorValue(w)).toContain('CREATE TABLE orders (id INT);')
    expect(spies.executeSql).not.toHaveBeenCalled()
  })

  it('opens the edit-data dialog wired to the rows contract', async () => {
    spies.listTableRows.mockResolvedValue({ columns: ['id', 'note'], rows: [[1, 'a'], [2, 'b']], total: 2, primaryKeys: ['id'], offset: 0, capability: 'supported', constraints: ['read-only'] })
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="edit"]').trigger('click')
    await flushPromises()
    const dialog = w.find('[data-table-dialog]')
    expect(dialog.exists()).toBe(true)
    expect(dialog.text()).toContain('public.orders')
    expect(dialog.text()).toContain('主键：id')
    expect(spies.listTableRows).toHaveBeenCalledWith({ datasourceId: 7, schema: 'public', table: 'orders', limit: 200, offset: 0 })
    expect(dialog.findAll('tbody tr')).toHaveLength(2)
  })

  it('opens the csv import dialog with column mapping loaded', async () => {
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="csv"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-csv-dialog]').exists()).toBe(true)
    expect(spies.listColumns).toHaveBeenCalledWith(7, 'public', 'orders', null)
    expect(w.find('[data-csv-mapping-table]').exists()).toBe(true)
  })

  it('hard-blocks destructive SQL when the audit verdict is block', async () => {
    spies.auditTable.mockResolvedValue({ status: 'block', op: 'drop', schema: 'public', table: 'orders', rowCount: null, findings: [{ severity: 'block', code: 'TABLE_NOT_FOUND', message: 'table public.orders does not exist' }] })
    const alert = vi.fn()
    const confirm = vi.fn(() => true)
    vi.stubGlobal('alert', alert)
    vi.stubGlobal('confirm', confirm)
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="drop-audit"]').trigger('click')
    await flushPromises()
    expect(spies.auditTable).toHaveBeenCalledWith({ datasourceId: 7, schema: 'public', table: 'orders', op: 'drop' })
    expect(alert).toHaveBeenCalledWith(expect.stringContaining('已硬阻断'))
    expect(confirm).not.toHaveBeenCalled()
    expect(editorValue(w)).not.toContain('DROP TABLE')
  })

  it('fills DROP only after the audit passes and the user confirms (audit detail variant)', async () => {
    spies.auditTable.mockResolvedValue({ status: 'pass', op: 'drop', schema: 'public', table: 'orders', rowCount: 12, findings: [{ severity: 'warning', code: 'DESTRUCTIVE_OP', message: 'permanently destroys data' }] })
    const confirm = vi.fn(() => true)
    vi.stubGlobal('confirm', confirm)
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="drop-audit"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('稽核明细'))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('约 12 行'))
    expect(editorValue(w)).toContain('DROP TABLE public.orders;')
    expect(spies.executeSql).not.toHaveBeenCalled()

    confirm.mockReturnValue(false)
    await openMenu(w)
    await w.find('[data-menu-item="truncate-audit"]').trigger('click')
    await flushPromises()
    expect(editorValue(w)).not.toContain('TRUNCATE TABLE')
  })

  it('audits the unconditional drop/truncate items too and fills on confirm', async () => {
    spies.auditTable.mockResolvedValue({ status: 'pass', op: 'truncate', schema: 'public', table: 'orders', rowCount: 3, findings: [] })
    const confirm = vi.fn(() => true)
    vi.stubGlobal('confirm', confirm)
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="truncate"]').trigger('click')
    await flushPromises()
    expect(spies.auditTable).toHaveBeenCalledWith({ datasourceId: 7, schema: 'public', table: 'orders', op: 'truncate' })
    expect(confirm).not.toHaveBeenCalledWith(expect.stringContaining('稽核明细'))
    expect(editorValue(w)).toContain('TRUNCATE TABLE public.orders;')
  })

  it('generates ALTER TABLE ADD COLUMN from the column dialog (fill only)', async () => {
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="add-column"]').trigger('click')
    await flushPromises()
    const dialog = w.find('[data-add-column-dialog]')
    expect(dialog.exists()).toBe(true)
    expect((dialog.find('[data-target-table]').element as HTMLInputElement).value).toBe('public.orders')
    await dialog.find('[data-column-name]').setValue('remark')
    await dialog.find('[data-column-type]').setValue('VARCHAR')
    await dialog.find('[data-column-length]').setValue('64')
    await dialog.find('[data-generate-column]').trigger('click')
    await flushPromises()
    expect(editorValue(w)).toContain('ALTER TABLE public.orders ADD COLUMN remark VARCHAR(64);')
    expect(w.find('[data-add-column-dialog]').exists()).toBe(false)
    expect(spies.executeSql).not.toHaveBeenCalled()
  })

  it('generates CREATE UNIQUE INDEX with a default name (fill only)', async () => {
    const w = await openMenu(await mountWithTree())
    await w.find('[data-menu-item="add-index"]').trigger('click')
    await flushPromises()
    const dialog = w.find('[data-add-index-dialog]')
    await dialog.find('[data-index-columns]').setValue('a,b')
    await dialog.find('[data-index-unique]').setValue(true)
    await dialog.find('[data-generate-index]').trigger('click')
    await flushPromises()
    expect(editorValue(w)).toContain('CREATE UNIQUE INDEX idx_orders ON public.orders (a, b);')
    expect(spies.executeSql).not.toHaveBeenCalled()
  })
})

describe('B4-d S5 搜索合并（本地已加载 + 后端）', () => {
  it('merges local tree hits marked 已加载 with backend hits and fills SELECT on click', async () => {
    spies.searchObjects.mockResolvedValue({ items: [{ kind: 'table', name: 'orders', parent: 'public' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
    const w = await mountWithTree()
    await w.find('[data-search-input]').setValue('ord')
    await w.find('[data-search]').trigger('click')
    await flushPromises()
    const hits = w.findAll('[data-search-hit]')
    expect(hits.length).toBeGreaterThanOrEqual(2)
    const localHit = hits.find((h) => h.text().includes('已加载'))
    expect(localHit).toBeDefined()
    await hits[0].trigger('click')
    await flushPromises()
    expect(editorValue(w)).toContain('SELECT * FROM public.orders LIMIT 100;')
    expect(spies.executeSql).not.toHaveBeenCalled()
  })
})
