import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ide/IdeView.vue'
import ideSource from '../ide/IdeView.vue?raw'

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
  const actual =
    await vi.importActual<typeof import('../../services/rebuild/projectApi')>('../../services/rebuild/projectApi')
  return { ...actual, listProjects: vi.fn() }
})

import { listProjects } from '../../services/rebuild/projectApi'

const datasource = { id: 7, projectId: 1, name: '订单库', kind: 'mysql', host: '10.0.0.1', port: 3306, database: 'orders', username: 'reader', createdAt: '', updatedAt: '' }

const listeners: Record<string, Array<(ev: { data: string }) => void>> = {}
const streamClose = vi.fn()

beforeEach(() => {
  router.route.params = {}
  router.route.query = {}
  for (const spy of Object.values(spies)) spy.mockReset()
  streamClose.mockReset()
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
  spies.listScripts.mockResolvedValue([])
  spies.previewResolution.mockResolvedValue({ resolvedValue: '42', diagnostics: [] })
  spies.checkReference.mockResolvedValue({ expression: '', valid: true, diagnostics: [] })
  spies.completeVariables.mockResolvedValue([{ scope: 'workflow', name: 'biz_date', valueType: 'date' }])
  spies.fetchResultPage.mockResolvedValue({ stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1]], rowsTotal: 1, offset: 0, limit: 50 })
  spies.executeSql.mockResolvedValue({ taskId: 'task-1' })
  spies.getExportDownloadUrl.mockReturnValue('/api/exports/export-1/download')
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

describe('/ide 数据开发 IDE（S9 树根节点化）', () => {
  it('uses the shared r6 theme tokens instead of page-local hex colors', () => {
    expect(ideSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(ideSource).toContain('var(--')
  })

  it('uses only the global workspace picker and skips the query when no project is in context', async () => {
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-project-select]').exists()).toBe(false)
    expect(w.find('[data-variable-manage]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-no-project]').exists()).toBe(true)
    expect(w.find('[data-object-panel]').exists()).toBe(false)
    expect(spies.listDatasources).not.toHaveBeenCalled()
  })

  it('opens variable management with the active project and closes through v-model', async () => {
    router.route.params.projectId = '1'
    const w = mount(View, {
      global: {
        stubs: {
          GlobalParamDrawer: {
            props: ['modelValue', 'projectId'],
            emits: ['update:modelValue'],
            template: '<div v-if="modelValue" data-variable-management-dialog-stub :data-project-id="projectId"><button data-close-variable-management @click="$emit(\'update:modelValue\', false)">关闭</button></div>',
          },
        },
      },
    })
    await flushPromises()

    expect(w.find('[data-variable-management-dialog-stub]').exists()).toBe(false)
    await w.find('[data-variable-manage]').trigger('click')
    expect(w.find('[data-variable-management-dialog-stub]').attributes('data-project-id')).toBe('1')
    await w.find('[data-close-variable-management]').trigger('click')
    expect(w.find('[data-variable-management-dialog-stub]').exists()).toBe(false)
  })

  it('renders authorized datasources as tree roots without a selector (S9)', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    expect(spies.listDatasources).toHaveBeenCalledTimes(1)
    expect(w.find('[data-ds-select]').exists()).toBe(false)
    expect(w.find('[data-no-datasource]').exists()).toBe(false)
    expect(w.find('[data-tree-node="source:7"]').exists()).toBe(true)
    expect(w.find('[data-node-kind="source"]').exists()).toBe(true)
    expect(spies.listDatabases).toHaveBeenCalledWith(7)
    expect(w.find('[data-tree-node="db:7:orders"]').exists()).toBe(true)
  })

  it('keeps per-root children isolated when a slow root responds after another root expanded', async () => {
    router.route.params.projectId = '1'
    spies.listDatasources.mockResolvedValue({ items: [datasource, { ...datasource, id: 8, name: '数仓库' }] })
    let resolveFirst!: (value: Awaited<ReturnType<typeof spies.listDatabases>>) => void
    spies.listDatabases
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ items: [{ name: 'warehouse' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
    const w = mount(View)
    await flushPromises()

    // 默认展开第一个根节点（source:7）时 listDatabases 挂起；点击第二个根节点（source:8）先完成
    await w.find('[data-tree-node="source:8"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-tree-node="db:8:warehouse"]').exists()).toBe(true)

    resolveFirst({ items: [{ name: 'orders' }], capability: 'supported', constraints: [], page: { nextCursor: null, hasMore: false } })
    await flushPromises()

    expect(w.find('[data-tree-node="db:7:orders"]').exists()).toBe(true)
    expect(w.find('[data-tree-node="db:8:warehouse"]').exists()).toBe(true)
  })

  it('loads the project supplied by ProjectSegmentView prop', async () => {
    const w = mount(View, { props: { projectId: 1 } })
    await flushPromises()
    expect(spies.listDatasources).toHaveBeenCalledTimes(1)
    expect(w.find('[data-project-select]').exists()).toBe(false)
    expect(w.find('[data-tree-node="source:7"]').exists()).toBe(true)
    expect(w.find('[data-tree-node="db:7:orders"]').exists()).toBe(true)
  })

  it('walks the object tree: datasource root → databases → schemas → relations → columns/indexes (S9)', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    expect(w.find('[data-ds-select]').exists()).toBe(false)
    expect(spies.listDatabases).toHaveBeenCalledWith(7)
    expect(w.find('[data-tree-node="db:7:orders"]').exists()).toBe(true)

    await w.find('[data-tree-node="db:7:orders"]').trigger('click')
    await flushPromises()
    expect(spies.listSchemas).toHaveBeenCalledWith(7, 'orders')

    await w.find('[data-tree-node="schema:7:orders:public"]').trigger('click')
    await flushPromises()
    expect(spies.listRelations).toHaveBeenCalledWith(7, 'orders', 'public', 'table')

    await w.find('[data-tree-node="rel:7:orders:public:table:orders"]').trigger('click')
    await flushPromises()
    expect(spies.listColumns).toHaveBeenCalledWith(7, 'orders', 'orders', 'public')
    expect(spies.listIndexes).toHaveBeenCalledWith(7, 'orders', 'orders', 'public')
    expect(w.find('[data-tree-node="col:7:orders:public:orders:id"]').exists()).toBe(true)
    expect(w.find('[data-tree-node="idx:7:orders:public:orders:PRIMARY"]').exists()).toBe(true)
  })

  it('marks a datasource root denied when expansion is rejected with 403 and blocks re-expansion (S9)', async () => {
    router.route.params.projectId = '1'
    spies.listDatasources.mockResolvedValue({ items: [datasource, { ...datasource, id: 8, name: '数仓库' }] })
    spies.listDatabases.mockRejectedValueOnce(Object.assign(new Error('forbidden'), { code: 403 }))
    const w = mount(View)
    await flushPromises()

    expect(w.find('[data-node-denied]').text()).toContain('无权限访问该数据源')
    expect(w.find('[data-tree-node="db:7:orders"]').exists()).toBe(false)

    // denied 节点不可再展开：重复点击不触发新的鉴权请求
    await w.find('[data-tree-node="source:7"]').trigger('click')
    await flushPromises()
    expect(spies.listDatabases).toHaveBeenCalledTimes(1)

    // 另一个有权限根节点可正常展开
    await w.find('[data-tree-node="source:8"]').trigger('click')
    await flushPromises()
    expect(spies.listDatabases).toHaveBeenCalledTimes(2)
    expect(w.find('[data-tree-node="db:8:orders"]').exists()).toBe(true)
  })

  it('switches the execution context when clicking another datasource root (S9)', async () => {
    router.route.params.projectId = '1'
    spies.listDatasources.mockResolvedValue({ items: [datasource, { ...datasource, id: 8, name: '数仓库' }] })
    const w = mount(View)
    await flushPromises()
    expect((w.vm as unknown as { datasourceId: number | null }).datasourceId).toBe(7)

    await w.find('[data-tree-node="source:8"]').trigger('click')
    await flushPromises()
    expect((w.vm as unknown as { datasourceId: number | null }).datasourceId).toBe(8)
    expect(w.find('[data-tree-node="db:8:orders"]').exists()).toBe(true)
  })

  it('executes SQL over SSE and renders the result grid', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
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
    expect(w.find('[data-result-grid]').exists()).toBe(true)
    expect(spies.listHistory).toHaveBeenCalledWith(7)
  })

  it('loads the first result page when the backend emits only a snake_case done event', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1 AS ok')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()

    await dispatch('done', {
      status: 'succeeded',
      history_id: 'history-1',
      result_set_id: 'rs1',
      elapsed_ms: 9,
      stmt_count: 1,
    })
    await flushPromises()

    expect(spies.fetchResultPage).toHaveBeenCalledWith('history-1', 'rs1', 0, 50)
    expect((w.vm as unknown as { resultColumns?: string[] }).resultColumns).toEqual(['id'])
    expect((w.vm as unknown as { executing?: boolean }).executing).toBe(false)
  })

  it('renders an inline result returned by the synchronous execution adapter', async () => {
    spies.fetchResultPage.mockResolvedValueOnce({
      stmtIndex: 0, resultSetId: 'rs-inline', columns: ['ok'], rows: [[1]], rowsTotal: 1, offset: 0, limit: 50,
    })
    spies.executeSql.mockResolvedValueOnce({
      taskId: 'task-inline',
      historyId: 'history-inline',
      resultSetId: 'rs-inline',
      columns: ['ok'],
      rows: [[1]],
      totalRows: 1,
    })
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1 AS ok')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()

    expect(w.find('[data-result-grid]').exists()).toBe(true)
    expect(w.find('[data-result-grid]').text()).toContain('ok')
  })

  it('enables the next result page when the first SSE batch is partial', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT id FROM orders')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()

    dispatch('result', { stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1]], rowsTotal: 51, elapsedMs: 5 })
    await flushPromises()

    const next = w.findAll('[data-result-grid] .ide-result-nav button')[1]
    expect(next.attributes('disabled')).toBeUndefined()
  })

  it('keeps the execution live while the authenticated SSE stream reconnects', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()

    dispatch('error', { message: 'temporary disconnect' })
    await flushPromises()

    expect(streamClose).not.toHaveBeenCalled()
    expect(w.find('[data-cancel]').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-status]').text()).toContain('事件流连接中断，正在恢复')

    dispatch('done', { status: 'succeeded', elapsedMs: 9, historyId: 56, stmtCount: 1 })
    await flushPromises()
    expect(streamClose).toHaveBeenCalledTimes(1)
    expect(w.find('[data-status]').text()).toContain('执行成功')
  })

  it('polls execution status after SSE drops and settles on a terminal status', async () => {
    vi.useFakeTimers()
    try {
      router.route.params.projectId = '1'
      const w = mount(View)
      await flushPromises()
      await w.find('[data-sql-editor]').setValue('SELECT 1')
      await w.find('[data-execute]').trigger('click')
      await flushPromises()

      dispatch('error', { message: 'temporary disconnect' })
      await flushPromises()

      spies.getExecutionStatus.mockResolvedValue({ taskId: 'task-1', status: 'succeeded' })
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()

      expect(spies.getExecutionStatus).toHaveBeenCalledWith('task-1')
      expect(streamClose).toHaveBeenCalledTimes(1)
      expect(w.find('[data-cancel]').attributes('disabled')).toBeDefined()
      expect(w.find('[data-status]').text()).toContain('执行完成')
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops waiting after consecutive status polling failures', async () => {
    vi.useFakeTimers()
    try {
      router.route.params.projectId = '1'
      const w = mount(View)
      await flushPromises()
      await w.find('[data-sql-editor]').setValue('SELECT 1')
      await w.find('[data-execute]').trigger('click')
      await flushPromises()

      dispatch('error', { message: 'temporary disconnect' })
      await flushPromises()

      spies.getExecutionStatus.mockRejectedValue(new Error('status unavailable'))
      await vi.advanceTimersByTimeAsync(10000)
      await flushPromises()

      expect(spies.getExecutionStatus).toHaveBeenCalledTimes(5)
      expect(w.find('[data-cancel]').attributes('disabled')).toBeDefined()
      expect(w.find('[data-contract-error]').text()).toContain('执行状态查询连续失败')
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops status polling once the SSE stream reconnects', async () => {
    vi.useFakeTimers()
    try {
      router.route.params.projectId = '1'
      const w = mount(View)
      await flushPromises()
      await w.find('[data-sql-editor]').setValue('SELECT 1')
      await w.find('[data-execute]').trigger('click')
      await flushPromises()

      dispatch('error', { message: 'temporary disconnect' })
      await flushPromises()

      spies.getExecutionStatus.mockResolvedValue({ taskId: 'task-1', status: 'running' })
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      const callsAtReconnect = spies.getExecutionStatus.mock.calls.length

      dispatch('open', {})
      await flushPromises()
      await vi.advanceTimersByTimeAsync(6000)
      await flushPromises()

      expect(spies.getExecutionStatus.mock.calls.length).toBe(callsAtReconnect)
      expect(w.find('[data-cancel]').attributes('disabled')).toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps a long running execution cancellable and tells the user after the wait threshold', async () => {
    vi.useFakeTimers()
    try {
      router.route.params.projectId = '1'
      const w = mount(View)
      await flushPromises()
      await w.find('[data-sql-editor]').setValue('SELECT 1')
      await w.find('[data-execute]').trigger('click')
      await flushPromises()

      await vi.advanceTimersByTimeAsync(60000)
      await flushPromises()

      expect(w.find('[data-status]').text()).toContain('可点击取消')
      expect(w.find('[data-cancel]').attributes('disabled')).toBeUndefined()
      w.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('refreshes variable references and resolution preview when SQL changes', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT ${workflow.biz_date}')
    await flushPromises()
    expect(w.find('[data-vars]').exists()).toBe(true)
    expect(w.find('[data-vars]').text()).toContain('$workflow.biz_date')
    expect(spies.previewResolution).toHaveBeenCalledWith('${workflow.biz_date}', { projectId: 1 })
    expect(w.find('[data-vars]').text()).toContain('42')
  })

  it('runs the explicit variable check button and surfaces diagnostics verbatim (§5B)', async () => {
    router.route.params.projectId = '1'
    spies.checkReference.mockResolvedValue({
      expression: 'SELECT ${workflow.oops}',
      valid: false,
      diagnostics: [{ code: 'UNDEFINED', message: '变量未定义：workflow.oops' }],
    })
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT ${workflow.oops}')
    await w.find('[data-var-check]').trigger('click')
    await flushPromises()
    expect(spies.checkReference).toHaveBeenCalledWith('SELECT ${workflow.oops}', { projectId: 1 })
    expect(w.find('[data-var-check-result]').exists()).toBe(true)
    expect(w.find('[data-var-check-result]').text()).toContain('UNDEFINED')
    expect(w.find('[data-var-check-result]').text()).toContain('变量未定义：workflow.oops')
    expect(w.find('[data-var-check-result]').text()).toContain('变量校验未通过')
  })

  it('reports a passing variable check without diagnostics (§5B)', async () => {
    router.route.params.projectId = '1'
    spies.checkReference.mockResolvedValue({
      expression: 'SELECT ${workflow.biz_date}',
      valid: true,
      diagnostics: [],
    })
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT ${workflow.biz_date}')
    await w.find('[data-var-check]').trigger('click')
    await flushPromises()
    expect(w.find('[data-var-check-result]').text()).toContain('变量校验通过')
  })

  it('completes variables from the server list and inserts the reference token (§5B)', async () => {
    router.route.params.projectId = '1'
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT ')
    await w.find('[data-var-complete]').trigger('click')
    await flushPromises()
    expect(spies.completeVariables).toHaveBeenCalledWith('', { projectId: 1 })
    expect(w.find('[data-var-suggestions]').exists()).toBe(true)
    expect(w.find('[data-var-suggestion]').text()).toContain('workflow.biz_date')
    await w.find('[data-var-suggestion]').trigger('click')
    expect((w.find('[data-sql-editor]').element as HTMLTextAreaElement).value).toContain('${workflow.biz_date}')
  })

  it('cancels a running execution', async () => {
    router.route.params.projectId = '1'
    spies.cancelExecution.mockResolvedValue({ canceled: true })
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()
    await w.find('[data-cancel]').trigger('click')
    await flushPromises()
    expect(spies.cancelExecution).toHaveBeenCalledWith('task-1')
    expect(streamClose).toHaveBeenCalledTimes(1)
    expect(w.find('[data-cancel]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-status]').text()).toContain('取消')
  })

  it('keeps the execution cancellable and reports a failed cancel request', async () => {
    router.route.params.projectId = '1'
    spies.cancelExecution.mockRejectedValue(new Error('cancel rejected'))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()
    await w.find('[data-cancel]').trigger('click')
    await flushPromises()

    expect(w.find('[data-error]').text()).toContain('cancel rejected')
    expect(w.find('[data-cancel]').attributes('disabled')).toBeUndefined()
    expect(streamClose).not.toHaveBeenCalled()
  })

  it('creates and downloads a ready result export', async () => {
    router.route.params.projectId = '1'
    spies.exportResult.mockResolvedValue({ exportId: 'export-1', status: 'ready', expiresAt: '2030-01-01T00:00:00Z' })
    const open = vi.fn()
    vi.stubGlobal('open', open)
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()
    await dispatch('result', { stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1]], rowsTotal: 1, elapsedMs: 5 })
    await dispatch('done', { status: 'succeeded', elapsedMs: 9, historyId: 55, stmtCount: 1 })
    await flushPromises()
    await w.find('[data-export]').trigger('click')
    await flushPromises()

    expect(spies.exportResult).toHaveBeenCalledWith({ historyId: 55, resultSetId: 'rs1', format: 'csv' })
    expect(spies.getExportDownloadUrl).toHaveBeenCalledWith('export-1')
    expect(open).toHaveBeenCalledWith('/api/exports/export-1/download', '_blank', 'noopener,noreferrer')
    expect(w.find('[data-status]').text()).toContain('导出下载已打开')
  })

  it('reports an export failure without discarding the result grid', async () => {
    router.route.params.projectId = '1'
    spies.exportResult.mockRejectedValue(new Error('export unavailable'))
    const w = mount(View)
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    await w.find('[data-execute]').trigger('click')
    await flushPromises()
    await dispatch('result', { stmtIndex: 0, resultSetId: 'rs1', columns: ['id'], rows: [[1]], rowsTotal: 1, elapsedMs: 5 })
    await dispatch('done', { status: 'succeeded', elapsedMs: 9, historyId: 55, stmtCount: 1 })
    await flushPromises()
    await w.find('[data-export]').trigger('click')
    await flushPromises()

    expect(w.find('[data-error]').text()).toContain('export unavailable')
    expect(w.find('[data-result-grid]').exists()).toBe(true)
    expect(w.find('[data-export]').attributes('disabled')).toBeUndefined()
  })

  it('loads and restores execution history', async () => {
    router.route.params.projectId = '1'
    spies.listHistory.mockResolvedValue([
      { historyId: 9, datasourceId: 7, db: 'orders', sqlText: 'SELECT 1', status: 'succeeded', stmtCount: 1, elapsedMs: 3, createdAt: '' },
    ])
    const w = mount(View)
    await flushPromises()
    await w.find('[data-history-toggle]').trigger('click')
    await flushPromises()
    expect(w.find('[data-history]').exists()).toBe(true)
    await w.find('.ide-history-item').trigger('click')
    expect((w.find('[data-sql-editor]').element as HTMLTextAreaElement).value).toContain('SELECT 1')
  })

  it('lists, restores, and deletes saved SQL assets', async () => {
    router.route.params.projectId = '1'
    spies.listScripts.mockResolvedValue([
      { id: 12, name: '订单日报', sqlText: 'SELECT * FROM orders', updatedAt: '', revision: 3 },
    ])
    spies.deleteScript.mockResolvedValue(undefined)
    const w = mount(View)
    await flushPromises()

    await w.find('[data-scripts-toggle]').trigger('click')
    await flushPromises()
    expect(spies.listScripts).toHaveBeenCalledTimes(1)
    expect(w.find('[data-scripts]').text()).toContain('订单日报')

    await w.find('[data-script-open]').trigger('click')
    expect((w.find('[data-sql-editor]').element as HTMLTextAreaElement).value).toBe('SELECT * FROM orders')

    await w.find('[data-script-delete]').trigger('click')
    await flushPromises()
    expect(spies.deleteScript).toHaveBeenCalledWith(12, 3)
  })

  it('surfaces backend errors without dropping the editor', async () => {
    router.route.params.projectId = '1'
    spies.listDatabases.mockRejectedValue(Object.assign(new Error('metadata browse failed'), { code: 5022 }))
    const w = mount(View)
    await flushPromises()
    expect(w.find('[role=alert]').text()).toContain('metadata browse failed')
    expect(w.find('[data-sql-editor]').exists()).toBe(true)
  })
})
