import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../ide/IdeView.vue'

const router = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown>, query: {} as Record<string, unknown> },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => router.route, useRouter: () => ({ push: router.push }) }))

/** 契约面 mock（与 ideView.contract.test.ts 同源）：独立文件保证 window keydown 监听互不串扰。 */
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
  spies.listHistory.mockResolvedValue([])
  spies.listScripts.mockResolvedValue([])
  spies.previewResolution.mockResolvedValue({ resolvedValue: '42', diagnostics: [] })
  spies.checkReference.mockResolvedValue({ expression: '', valid: true, diagnostics: [] })
  spies.completeVariables.mockResolvedValue([{ scope: 'workflow', name: 'biz_date', valueType: 'date' }])
  spies.executeSql.mockResolvedValue({ taskId: 'task-1' })
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

function bridgeValue(w: ReturnType<typeof mount>): string {
  return (w.find('[data-sql-editor]').element as HTMLTextAreaElement).value
}

/** 活性守卫以 rootEl.isConnected 判定：测试须 attachTo document 才能模拟真实路由视图挂载态。 */
function mountIde(): ReturnType<typeof mount> {
  return mount(View, { attachTo: document.body })
}

/** §7.1.5 快捷键三件套：Ctrl+Enter 执行 / Ctrl+S 存脚本 / Ctrl+Shift+F 格式化（权威键位：对标审计-03 L129）。 */
describe('/ide 快捷键三件套（§7.1.5）', () => {
  it('runs SQL with Ctrl+Enter when the execution context is ready', async () => {
    router.route.params.projectId = '1'
    const w = mountIde()
    await flushPromises()
    expect(spies.executeSql).not.toHaveBeenCalled()
    await w.find('[data-sql-editor]').setValue('SELECT 1')
    window.dispatchEvent(new KeyboardEvent('keydown', { ctrlKey: true, key: 'Enter', cancelable: true }))
    await flushPromises()
    expect(spies.executeSql).toHaveBeenCalledTimes(1)
    expect(spies.executeSql).toHaveBeenCalledWith(expect.objectContaining({ datasourceId: 7 }))
    w.unmount()
  })

  it('skips Ctrl+Enter when there is no execution context (no project/datasource)', async () => {
    const w = mountIde()
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { ctrlKey: true, key: 'Enter', cancelable: true }))
    await flushPromises()
    expect(spies.executeSql).not.toHaveBeenCalled()
    w.unmount()
  })

  it('saves the script with Ctrl+S and blocks the browser save dialog', async () => {
    router.route.params.projectId = '1'
    const w = mountIde()
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('SELECT 42 -- ctrl-s')
    const event = new KeyboardEvent('keydown', { ctrlKey: true, key: 's', cancelable: true })
    window.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(true)
    expect(spies.saveScript).toHaveBeenCalledTimes(1)
    expect(spies.saveScript).toHaveBeenCalledWith(expect.objectContaining({ sqlText: 'SELECT 42 -- ctrl-s' }))
    w.unmount()
  })

  it('prevents browser save on Ctrl+S but skips saveScript for an empty editor', async () => {
    router.route.params.projectId = '1'
    const w = mountIde()
    await flushPromises()
    const event = new KeyboardEvent('keydown', { ctrlKey: true, key: 'S', cancelable: true })
    window.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(true)
    expect(spies.saveScript).not.toHaveBeenCalled()
    w.unmount()
  })

  it('formats the SQL with Ctrl+Shift+F (keywordCase upper, 旧版审计权威键位)', async () => {
    router.route.params.projectId = '1'
    const w = mountIde()
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('select 1')
    window.dispatchEvent(new KeyboardEvent('keydown', { ctrlKey: true, shiftKey: true, key: 'F', cancelable: true }))
    await flushPromises()
    expect(bridgeValue(w)).not.toContain('select 1')
    expect(bridgeValue(w)).toContain('SELECT')
    w.unmount()
  })

  it('backs off Ctrl+Shift+F when focus sits in a plain input control', async () => {
    router.route.params.projectId = '1'
    const w = mountIde()
    await flushPromises()
    await w.find('[data-sql-editor]').setValue('select 1')
    const input = document.createElement('input')
    document.body.appendChild(input)
    try {
      input.dispatchEvent(new KeyboardEvent('keydown', { ctrlKey: true, shiftKey: true, key: 'F', cancelable: true, bubbles: true }))
      await flushPromises()
      expect(bridgeValue(w)).toBe('select 1')
    } finally {
      input.remove()
      w.unmount()
    }
  })

  it('stops responding after unmount (liveness guard)', async () => {
    router.route.params.projectId = '1'
    const w = mountIde()
    await flushPromises()
    w.unmount()
    window.dispatchEvent(new KeyboardEvent('keydown', { ctrlKey: true, key: 's', cancelable: true }))
    await flushPromises()
    expect(spies.saveScript).not.toHaveBeenCalled()
  })
})
