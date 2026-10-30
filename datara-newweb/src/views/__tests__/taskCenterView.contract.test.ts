/**
 * 任务中心契约测试（/dag，s260 派令 + §10.4 海豚 iframe embed + §10.5 B 列表归属）。
 *
 * FE-1 覆盖（§5A.1 照抄语义 + 内容门控）：
 *  1. 四视角页签照抄渲染（顺序 + icon + label）；
 *  2. 默认 edit 主视角 + 非法 ?tab= 回落 edit；
 *  3. ?tab= 激活分流：runs=datara 自建运行监控（§10.5 B）、templates/alarm=G09 空态；
 *  4. switchTab → router.replace 合并既有 query（保书签）。
 *
 * §10.5 B 工作流定义列表覆盖：
 *  - 有项目 → 调编排网关 workflow-definitions，datara 自建表格渲染（不进 iframe）；
 *  - 无项目 → 「请先选择项目」空态，不发列表/会话请求；
 *  - 上线/下线、删除（二次确认）走网关并回列表刷新。
 *
 * §10.4 嵌入机制覆盖：
 *  - 列表态不取编排会话（惰性加载）；
 *  - 点列表行 → 取会话 → iframe src = /dolphinscheduler/ui/projects/{code}/workflow/definitions/{code}?embed=1；
 *  - 监听 ds-ready 后下发会话 + 兜底下发一次（覆盖 ready 竞态）；
 *  - 会话失败/缺 projectCode → 画布态空态注明原因，不设 iframe；
 *  - 「＋新建工作流」= 宿主驱动画布路由切换（DS 新建定义路由）；
 *  - 画布内配套元素不拆到 datara（iframe 内闭环，故本页无画布 DOM 断言）。
 *
 * 依赖 mock：vue-router（query/params）、element-plus（ElMessage / ElMessageBox spy）、
 * orchestrationApi（会话 + 定义列表）、dsBridge（postMessage 桥）、executionStatsApi（runs 页签）。
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { shallowRef } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const {
  replaceSpy,
  routeState,
  sessionLoad,
  readyListen,
  sessionSend,
  embedUrl,
  msgWarning,
  msgError,
  msgSuccess,
  boxConfirm,
  wfList,
  wfRelease,
  wfDelete,
} = vi.hoisted(() => ({
  replaceSpy: vi.fn(() => Promise.resolve()),
  routeState: {
    query: {} as Record<string, unknown>,
    params: {} as Record<string, unknown>,
  },
  sessionLoad: vi.fn(),
  readyListen: vi.fn((_frame: unknown, _onReady: () => void) => () => {}),
  sessionSend: vi.fn((_frame: unknown, _payload: unknown) => true),
  embedUrl: vi.fn((code: string, path: string) => `/dolphinscheduler/ui${path.replace('{code}', code)}?embed=1`),
  msgWarning: vi.fn(),
  msgError: vi.fn(),
  msgSuccess: vi.fn(),
  boxConfirm: vi.fn(),
  wfList: vi.fn(),
  wfRelease: vi.fn(),
  wfDelete: vi.fn(),
}))

// 路由状态必须是真正的响应式引用：TaskCenterView 用 computed(route.params.projectId)
// + watch 驱动画布重载，普通对象的属性替换无法被追踪（项目切换用例的根因）。
// shallowRef 保证 value 仍是普通对象，避免 toHaveBeenCalledWith 比对 Proxy。
const routeQuery = shallowRef<Record<string, unknown>>(routeState.query)
const routeParams = shallowRef<Record<string, unknown>>(routeState.params)

// 路由状态已响应式化：残留挂载实例的 watch 会跨用例累积触发，必须逐例卸载。
enableAutoUnmount(afterEach)

vi.mock('vue-router', () => ({
  // Accessors preserve the ref dependency so route back/forward changes can
  // exercise TaskCenterView's query watcher in this contract suite.
  useRoute: () => ({
    get query() {
      return routeQuery.value
    },
    get params() {
      return routeParams.value
    },
  }),
  useRouter: () => ({ replace: replaceSpy }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), warning: msgWarning, error: msgError, success: msgSuccess },
  ElMessageBox: { confirm: boxConfirm, prompt: vi.fn() },
}))

vi.mock('../../services/rebuild/orchestrationApi', () => ({
  getOrchestrationSession: sessionLoad,
  orchestrationApi: {
    listWorkflowDefinitions: wfList,
    releaseWorkflowDefinition: wfRelease,
    deleteWorkflowDefinition: wfDelete,
  },
}))

vi.mock('../../services/rebuild/dsBridge', () => ({
  dsEmbedUrl: embedUrl,
  listenDsReady: readyListen,
  sendSessionToDs: sessionSend,
}))

// D8 下钻契约（G02）：runs 页签真挂载 WorkflowRunMonitor，其执行统计 API 不进网络层
const { runStatsList, runStatGet } = vi.hoisted(() => ({
  runStatsList: vi.fn(),
  runStatGet: vi.fn(),
}))
vi.mock('../../services/rebuild/executionStatsApi', () => ({
  listWorkflowRunStats: runStatsList,
  getWorkflowRunStat: runStatGet,
}))

import TaskCenterView from '../TaskCenterView.vue'
import type { OrchestrationSession, WorkflowDefinitionRow } from '../../services/rebuild/orchestrationApi'

function mountView() {
  // 每用例独立 pinia（store 状态隔离）；setActivePinia 供测试体种入/读取同一实例
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(TaskCenterView, { global: { plugins: [pinia] } })
}

const SESSION: OrchestrationSession = {
  token: 'internal-token',
  user: 'datara',
  projectCode: '1234567890',
  projectName: 'demo',
  projectId: 33,
  apiBaseUrl: 'http://192.168.1.9:18091',
  userToken: 'datara-session',
}

const DEFINITION: WorkflowDefinitionRow = {
  code: 188282273576704,
  name: 'A1验收工作流',
  state: null,
  releaseState: 'OFFLINE',
  scheduleReleaseState: null,
  createTime: '2026-10-30 02:50:07',
  updateTime: '2026-10-30 02:50:07',
  description: '',
  userName: 'admin',
  projectName: null,
  executionType: 'PARALLEL',
}

const DEFINITION_LIST = { list: [DEFINITION], total: 1, pageNo: 1, pageSize: 10 }

/** 蓝本 tabs 数组原文（顺序 + icon + label） */
const BLUEPRINT_TABS = [
  { k: 'edit', label: '任务编排', icon: '⑃' },
  { k: 'templates', label: '模板中心', icon: '▦' },
  { k: 'runs', label: '运行监控', icon: '▶' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂' },
]

beforeEach(() => {
  routeQuery.value = {}
  routeParams.value = {}
  sessionLoad.mockReset()
  sessionLoad.mockResolvedValue(SESSION)
  readyListen.mockReset()
  readyListen.mockImplementation(() => () => {})
  sessionSend.mockReset()
  sessionSend.mockImplementation(() => true)
  embedUrl.mockClear()
  replaceSpy.mockClear()
  msgWarning.mockClear()
  msgError.mockClear()
  msgSuccess.mockClear()
  boxConfirm.mockReset()
  boxConfirm.mockResolvedValue('confirm')
  wfList.mockReset()
  wfList.mockResolvedValue(DEFINITION_LIST)
  wfRelease.mockReset()
  wfRelease.mockResolvedValue({})
  wfDelete.mockReset()
  wfDelete.mockResolvedValue({})
  runStatsList.mockReset()
  runStatGet.mockReset()
})

describe('INC4-FE-1 任务中心顶部视角页签框架（/dag，s260 派令）', () => {
  it('四视角页签照抄渲染：顺序 + icon + label 与蓝本一致，页签条单实例', () => {
    const w = mountView()
    expect(w.find('[data-tc-tabs]').exists()).toBe(true)
    const els = w.findAll('[data-tc-tabs] .tc-tab')
    expect(els).toHaveLength(BLUEPRINT_TABS.length)
    BLUEPRINT_TABS.forEach((t, i) => {
      expect(els[i].attributes('data-tab')).toBe(t.k)
      expect(els[i].text()).toBe(`${t.icon}${t.label}`)
    })
  })

  it('默认 edit 主视角：edit 页签 .on 态 + 右上专属操作在位（变量管理/新建工作流/视角名）', () => {
    const w = mountView()
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
    expect(w.find('[data-testid="variable-management"]').exists()).toBe(true)
    expect(w.find('[data-testid="new-workflow"]').exists()).toBe(true)
    expect(w.find('.tc-view').text()).toBe('DAG 编排')
  })

  it('非法 ?tab= 回落 edit（蓝本初始化语义照抄）', () => {
    routeQuery.value = { tab: 'nope' }
    const w = mountView()
    expect(w.find('[data-tab="edit"]').classes()).toContain('on')
  })

  it('?tab=runs：runs 页签激活 + 无项目时占位注记（§10.5 B datara 自建页）', () => {
    routeQuery.value = { tab: 'runs' }
    const w = mountView()
    expect(w.find('[data-tab="runs"]').classes()).toContain('on')
    expect(w.find('[data-tab="edit"]').classes()).not.toContain('on')
    expect(w.find('[data-tc-runs-slot]').exists()).toBe(true)
    expect(w.find('[data-tc-runs-slot]').text()).toContain('请先选择项目')
  })

  it('D8 下钻：?tab=runs&status=&runId= 在有项目上下文时透传运行监控（G02）', async () => {
    routeQuery.value = { tab: 'runs', status: 'FAILED', runId: '9' }
    routeParams.value = { projectId: '33' }
    runStatGet.mockResolvedValue({
      id: 9,
      workflow_id: 3,
      workflow_instance_id: 12,
      instance_type: 'FORMAL',
      status: 'FAILED',
      success_count: 0,
      failure_count: 2,
      skipped_count: 0,
      total_count: 2,
      started_at: '2026-10-26T00:00:00Z',
      details: [],
      detail_total: 0,
    })
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-workflow-run-monitor]').exists()).toBe(true)
    expect((w.get('[data-run-status]').element as HTMLSelectElement).value).toBe('FAILED')
    expect(runStatGet).toHaveBeenCalledWith(33, 9)
    expect(runStatsList).not.toHaveBeenCalled()
  })

  it('?tab=templates / ?tab=alarm：页签激活态正确，G09 空态注明原因（无契约保留页签）', () => {
    for (const k of ['templates', 'alarm']) {
      routeQuery.value = { tab: k }
      const w = mountView()
      expect(w.find(`[data-tab="${k}"]`).classes()).toContain('on')
      expect(w.find('[data-tc-runs-slot]').exists()).toBe(false)
      expect(w.find('[data-tc-body]').text()).toContain('G09')
    }
  })

  it('点击页签 → switchTab → router.replace 合并既有 query（保书签，蓝本语义）', async () => {
    routeQuery.value = { tab: 'edit', foo: 'bar' }
    const w = mountView()
    await w.find('[data-tab="runs"]').trigger('click')
    expect(replaceSpy).toHaveBeenCalledTimes(1)
    expect(replaceSpy).toHaveBeenCalledWith({ query: { tab: 'runs', foo: 'bar' } })
    // 本地激活态即时切换（不等路由响应）
    expect(w.find('[data-tab="runs"]').classes()).toContain('on')
  })

  it('右上专属操作仅 edit 态在位（templates/runs/alarm 不渲染）', () => {
    for (const k of ['templates', 'runs', 'alarm']) {
      routeQuery.value = { tab: k }
      const w = mountView()
      expect(w.find('[data-testid="variable-management"]').exists()).toBe(false)
      expect(w.find('[data-testid="new-workflow"]').exists()).toBe(false)
      expect(w.find('.tc-view').exists()).toBe(false)
    }
  })
})

describe('§10.5 B 工作流定义列表（datara 自建页，不进 iframe）', () => {
  it('无项目上下文：「请先选择项目」空态，不发列表/会话请求', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-tc-wf-list]').exists()).toBe(true)
    expect(w.find('[data-tc-wf-list]').text()).toContain('请先选择项目')
    expect(wfList).not.toHaveBeenCalled()
    expect(sessionLoad).not.toHaveBeenCalled()
    expect(w.find('[data-tc-ds-frame]').exists()).toBe(false)
  })

  it('有项目：调编排网关列表并按行渲染（名称/上线状态/创建人），列表态不取会话', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    expect(wfList).toHaveBeenCalledWith(7, 1, 10, '')
    expect(sessionLoad).not.toHaveBeenCalled()
    expect(w.find('[data-wf-table]').exists()).toBe(true)
    const row = w.get('[data-wf-row="188282273576704"]')
    expect(row.text()).toContain('A1验收工作流')
    expect(row.text()).toContain('未上线')
    expect(row.text()).toContain('admin')
  })

  it('关键字查询：点查询后以新关键字回第一页重新请求', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-keyword]').setValue('  A1  ')
    await w.get('[data-wf-search]').trigger('click')
    await flushPromises()
    expect(wfList).toHaveBeenLastCalledWith(7, 1, 10, 'A1')
  })

  it('上线/下线：调网关 release 并回列表刷新', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-release]').trigger('click')
    await flushPromises()
    expect(wfRelease).toHaveBeenCalledWith(188282273576704, 7, 'ONLINE')
    expect(msgSuccess).toHaveBeenCalled()
    expect(wfList).toHaveBeenCalledTimes(2)
  })

  it('删除：二次确认后调网关 delete 并回列表刷新', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-delete]').trigger('click')
    await flushPromises()
    expect(boxConfirm).toHaveBeenCalledTimes(1)
    expect(wfDelete).toHaveBeenCalledWith(188282273576704, 7)
    expect(wfList).toHaveBeenCalledTimes(2)
  })

  it('删除取消：不调网关、不刷新', async () => {
    routeParams.value = { projectId: '7' }
    boxConfirm.mockRejectedValue(new Error('cancel'))
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-delete]').trigger('click')
    await flushPromises()
    expect(wfDelete).not.toHaveBeenCalled()
    expect(wfList).toHaveBeenCalledTimes(1)
  })

  it('列表失败：错误态注明原因，不渲染表格', async () => {
    routeParams.value = { projectId: '7' }
    wfList.mockRejectedValue(new Error('gateway down'))
    const w = mountView()
    await flushPromises()
    expect(w.find('[data-wf-error]').text()).toContain('gateway down')
    expect(w.find('[data-wf-table]').exists()).toBe(false)
  })
})

describe('§10.4 海豚 iframe embed 宿主（单个 DAG 画布路由）', () => {
  it('点列表行：取会话 → iframe src 指向单个 DAG 画布路由（embed=1）+ 监听 ds-ready', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    expect(sessionLoad).toHaveBeenCalledWith(7)
    expect(embedUrl).toHaveBeenCalledWith('1234567890', '/projects/{code}/workflow/definitions/188282273576704')
    const frame = w.find('[data-tc-ds-frame]')
    expect(frame.exists()).toBe(true)
    expect(frame.attributes('src')).toBe(
      '/dolphinscheduler/ui/projects/1234567890/workflow/definitions/188282273576704?embed=1',
    )
    expect(readyListen).toHaveBeenCalledTimes(1)
    expect(w.find('[data-tc-wf-list]').exists()).toBe(false)
  })

  it('会话下发：ds-ready 回调 + 兜底各一次（覆盖 ready 竞态），载荷为普通对象', async () => {
    routeParams.value = { projectId: '7' }
    let readyHandler: (() => void) | null = null
    readyListen.mockImplementation((_frame, onReady) => {
      readyHandler = onReady
      return () => {}
    })
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    // 兜底下发（监听挂载后立即）
    expect(sessionSend).toHaveBeenCalledTimes(1)
    expect(sessionSend.mock.calls[0][1]).toEqual(SESSION)
    // ds-ready 到达 → 再下发一次
    ;(readyHandler as unknown as () => void)()
    expect(sessionSend).toHaveBeenCalledTimes(2)
    // 载荷必须是可结构化克隆的普通对象（非 Vue Proxy）
    const payload = sessionSend.mock.calls[0][1] as OrchestrationSession
    expect(Object.getPrototypeOf(payload)).toBe(Object.prototype)
  })

  it('会话获取失败：画布态空态注明原因，不设 iframe', async () => {
    routeParams.value = { projectId: '7' }
    sessionLoad.mockRejectedValue(new Error('gateway down'))
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    expect(w.find('[data-tc-ds-frame]').exists()).toBe(false)
    expect(w.find('[data-tc-empty]').text()).toContain('编排会话获取失败')
  })

  it('会话缺 projectCode：画布态空态注明原因，不设 iframe', async () => {
    routeParams.value = { projectId: '7' }
    sessionLoad.mockResolvedValue({ ...SESSION, projectCode: '' })
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    expect(w.find('[data-tc-ds-frame]').exists()).toBe(false)
    expect(w.find('[data-tc-empty]').text()).toContain('缺少海豚项目编码')
  })

  it('返回列表：卸下 iframe 并重载列表', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    await w.get('[data-tc-back-list]').trigger('click')
    await flushPromises()
    expect(w.find('[data-tc-ds-frame]').exists()).toBe(false)
    expect(w.find('[data-tc-wf-list]').exists()).toBe(true)
    expect(wfList).toHaveBeenCalledTimes(2)
  })

  it('项目切换：会话缓存失效，重开画布按新项目重新取会话', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    expect(sessionLoad).toHaveBeenCalledTimes(1)
    routeParams.value = { projectId: '8' }
    await flushPromises()
    await w.get('[data-wf-open]').trigger('click')
    await flushPromises()
    expect(sessionLoad).toHaveBeenCalledTimes(2)
    expect(sessionLoad).toHaveBeenLastCalledWith(8)
  })

  it('「＋新建工作流」= 宿主驱动画布路由切换（DS 新建定义路由）', async () => {
    routeParams.value = { projectId: '7' }
    const w = mountView()
    await flushPromises()
    await w.find('[data-testid="new-workflow"]').trigger('click')
    await flushPromises()
    expect(embedUrl).toHaveBeenCalledWith('1234567890', '/projects/{code}/workflow/definitions/create')
    expect(w.find('[data-tc-ds-frame]').attributes('src')).toBe(
      '/dolphinscheduler/ui/projects/1234567890/workflow/definitions/create?embed=1',
    )
  })

  it('无项目上下文时「＋新建工作流」降级提示，不切路由', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('[data-testid="new-workflow"]').trigger('click')
    expect(msgWarning).toHaveBeenCalledWith(expect.stringContaining('请先选择项目'))
    expect(embedUrl).not.toHaveBeenCalled()
  })
})
