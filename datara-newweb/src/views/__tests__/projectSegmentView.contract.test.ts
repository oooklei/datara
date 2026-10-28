/**
 * L12-02 full 段契约测试：ProjectSegmentView dag 段接驳 TaskCenterView
 * （s326 裁定④方案 A：/p/:projectId/dag 项目路由集成，约 3 行接驳+本测试）。
 *
 * 覆盖：
 *  1. seg='dag' → TaskCenterView 挂载（data-tc-tabs 特征锚）+ 项目上下文激活：
 *     route.params.projectId 承接 → loadDefPool 调 listWorkflowDefinitions(7)
 *     （L12-02 候裁披露「/dag 过渡路由无项目段 → undefined；项目路由集成即活」
 *     的契约兑现——接驳后 route.params 由 /p/:projectId/dag 供给）；
 *  2. seg='dag' 时占位 section 不渲染（正式功能页替换占位的票面语义）；
 *  3. seg='resources' → ResourceManagementView 挂载（既有分支回归锚）；
 *  4. 未知 seg → 占位「未知的段标识」不 crash（1.4 §7.3 判据保持）。
 *
 * 依赖 mock：TaskCenterView 链（vue-router/element-plus/componentSpecApi/
 * workflowApi/scheduleCrudApi/Workbench 桩）与 taskCenterView.contract.test.ts
 * 同构；ResourceManagementView 链（resourceApi）与
 * resourceManagementView.contract.test.ts 同构。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { replaceSpy, routeQuery, routeParams, poolLoad, resourceList, wfCreate, specLoad, schedApi, qcRuns, projectList } = vi.hoisted(() => ({
  replaceSpy: vi.fn(() => Promise.resolve()),
  routeQuery: { value: {} as Record<string, unknown> },
  routeParams: { value: {} as Record<string, unknown> },
  poolLoad: vi.fn(),
  resourceList: vi.fn(),
  wfCreate: vi.fn(),
  specLoad: vi.fn(),
  qcRuns: vi.fn(),
  projectList: vi.fn(),
  schedApi: {
    listSchedules: vi.fn(),
    createSchedule: vi.fn(),
    updateSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
    onlineSchedule: vi.fn(),
    offlineSchedule: vi.fn(),
    previewCrontab: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery.value, params: routeParams.value }),
  useRouter: () => ({ replace: replaceSpy }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), warning: vi.fn(), error: vi.fn(), success: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()), prompt: vi.fn(() => Promise.resolve({ value: '' })) },
}))

// TaskCenterView 空态挂真实 Palette：组件规格一源不进网络层（空快照即空目录）
vi.mock('../../services/rebuild/componentSpecApi', () => ({
  loadComponentSpecs: specLoad,
  resetComponentSpecCache: vi.fn(),
}))

// Workbench SFC 桩化（vue-flow 真挂载归 1.9 E2E；dag 分支空态无 Tab 不渲染画布区，
// 桩仅为 TaskCenterView import 链可加载）
vi.mock('../../components/WorkflowGraphWorkbench.vue', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'WorkflowGraphWorkbench',
      props: { tab: { type: Object, required: true }, projectId: { type: Number, default: undefined } },
      emits: ['schedule'],
      setup(props: { tab: { name: string } }) {
        return () => h('div', { class: 'tc-canvas-slot', 'data-tc-canvas-slot': '' }, `画布：${props.tab.name}`)
      },
    },
  }
})

vi.mock('../../services/rebuild/workflowApi', () => ({
  listWorkflowDefinitions: poolLoad,
  createWorkflowDefinition: wfCreate,
  deleteWorkflowDefinition: vi.fn(),
  getWorkflowDefinition: vi.fn(),
  upsertWorkflowDraftNode: vi.fn(),
  upsertWorkflowDraftEdge: vi.fn(),
  deleteWorkflowDraftNode: vi.fn(),
  deleteWorkflowDraftEdge: vi.fn(),
  WF_CATEGORIES_NOT_WIRED: 'WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet',
  workflowCategories: {
    listCategories: vi.fn(() => Promise.reject(new Error('WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet'))),
    createCategory: vi.fn(),
    deleteCategory: vi.fn(),
    setWfTags: vi.fn(),
  },
}))

// 9-04 单实例 ScheduleDialog：真实子组件挂载，打开即拉 list——mock 空列表
vi.mock('../../services/rebuild/scheduleCrudApi', () => ({
  createScheduleCrudContract: vi.fn(() => schedApi),
}))

// ResourceManagementView 链：resourceApi 契约工厂 mock（不进网络层）
vi.mock('../../services/rebuild/resourceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/resourceApi')>()
  return {
    ...actual,
    createResourceContract: () => ({
      listResources: resourceList,
      listResourceVersions: vi.fn(),
      bindResourceVersion: vi.fn(),
      downloadResourceVersion: vi.fn(),
      uploadResource: vi.fn(),
      getResourceVersion: vi.fn(),
    }),
  }
})

// E17-E19 真实视图（B5-c 接驳）链：governanceApi.listRuns 与项目列表不进网络层
vi.mock('../../services/rebuild/projectApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/projectApi')>()
  return { ...actual, listProjects: projectList }
})

vi.mock('../../services/rebuild/governanceApi', async (load) => {
  const actual = await load<typeof import('../../services/rebuild/governanceApi')>()
  return { ...actual, governanceApi: { ...actual.governanceApi, listRuns: qcRuns } }
})

// meta 段治理枢纽桩化：8 页各自治理 API 链不进本契约（页签接入为唯一断言面）
vi.mock('../../views/meta/MetadataCatalogView.vue', () => ({
  default: {
    name: 'MetadataCatalogView',
    template: '<div class="meta-catalog" data-meta-catalog=""></div>',
  },
}))

// ide 段正式页桩化：IdeView 的 IDE API 链（数据源/对象浏览/执行）不进本契约，
// 本用例只断言 seg 映射（s326 裁定④：ide 已交付正式页，不再落占位）
vi.mock('../../views/ide/IdeView.vue', async () => {
  const { getCurrentInstance } = await import('vue')
  return {
    default: {
      name: 'IdeView',
      setup() {
        return { instanceId: getCurrentInstance()?.uid }
      },
      template: '<div class="ide-stub" data-ide-view :data-instance-id="instanceId"></div>',
    },
  }
})

import ProjectSegmentView from '../ProjectSegmentView.vue'

function mountSeg(seg: string, projectId = 7) {
  return mount(ProjectSegmentView, {
    props: { projectId, seg },
    global: { plugins: [createPinia()] },
  })
}

beforeEach(() => {
  routeQuery.value = {}
  routeParams.value = { projectId: '7' } // /p/7/dag 形态：项目路由集成后 params 供给
  poolLoad.mockReset()
  poolLoad.mockResolvedValue([])
  resourceList.mockReset()
  resourceList.mockResolvedValue([])
  wfCreate.mockReset()
  specLoad.mockReset()
  specLoad.mockResolvedValue({ items: [], etag: '"00"', source: 'network' })
  qcRuns.mockReset()
  qcRuns.mockResolvedValue({ total: 0, list: [] })
  projectList.mockReset()
  projectList.mockResolvedValue({ total: 0, list: [] })
  localStorage.clear()
})

describe('L12-02 full 段 ProjectSegmentView dag 接驳（s326 裁定④方案 A）', () => {
  it("seg='dag' 挂 TaskCenterView：data-tc-tabs 渲染 + 项目上下文激活（listWorkflowDefinitions(7)）", async () => {
    const w = mountSeg('dag')
    await flushPromises() // TaskCenterView onMounted loadDefPool 消费 params.projectId
    expect(w.find('[data-tc-tabs]').exists()).toBe(true)
    expect(w.find('[data-testid="new-workflow"]').exists()).toBe(true)
    // 项目路由集成即活：候选池以接驳后的 params.projectId 拉取（候裁披露契约兑现）
    expect(poolLoad).toHaveBeenCalledWith(7)
  })

  it("seg='dag' 时占位 section 不渲染（正式功能页替换占位）", () => {
    const w = mountSeg('dag')
    expect(w.find('.segment-page').exists()).toBe(false)
    expect(w.find('[data-tc-empty]').exists()).toBe(true)
  })

  it("seg='resources' 挂 ResourceManagementView：projectId 透传（既有分支回归锚）", async () => {
    const w = mountSeg('resources')
    await flushPromises()
    expect(w.find('[data-tc-tabs]').exists()).toBe(false)
    expect(w.find('.segment-page').exists()).toBe(false)
    // 第二参为 kind 默认值：裁定 fix#4 后 resources 默认 sql（对齐 resourceManagementView 契约 L60）
    expect(resourceList).toHaveBeenCalledWith(7, 'sql')
  })

  it('切换全局项目后重挂同一功能段并按新 projectId 重新加载', async () => {
    const w = mountSeg('resources', 7)
    await flushPromises()
    resourceList.mockClear()

    await w.setProps({ projectId: 8, seg: 'resources' })
    await flushPromises()

    expect(resourceList).toHaveBeenCalledWith(8, 'sql')
  })

  it("segmentPath='meta/catalog' 直达元数据目录（治理页面不再经过粗粒度枢纽）", () => {
    const w = mountSeg('meta/catalog')
    expect(w.find('[data-meta-catalog]').exists()).toBe(true)
    expect(w.find('.segment-page').exists()).toBe(false)
  })

  it("seg='ide' 挂 IdeView 正式页（功能已交付，不再落「尚未开放」占位）", () => {
    const w = mountSeg('ide')
    expect(w.find('[data-ide-view]').exists()).toBe(true)
    expect(w.find('.segment-page').exists()).toBe(false)
    expect(w.find('[data-tc-tabs]').exists()).toBe(false)
  })

  it("E17-E19 段挂冻结表点名真实视图（B5-c 纠偏：QualityReadOnlyView 聚合旧页退役出路由，项目上下文由 route.params 承接）", async () => {
    const exception = mountSeg('qc/exception')
    await flushPromises()
    expect(exception.find('main[aria-label="异常数据核查"]').exists()).toBe(true)
    expect(qcRuns).toHaveBeenCalledWith(7, 1, 100)

    const report = mountSeg('qc/report')
    await flushPromises()
    expect(report.find('main[aria-label="质量报告"]').exists()).toBe(true)

    const alarm = mountSeg('qc/alarm')
    await flushPromises()
    expect(alarm.find('main[aria-label="质量告警"]').exists()).toBe(true)
    expect(exception.find('.quality-page').exists()).toBe(false)
  })

  it('remounts the active feature when the workspace project changes', async () => {
    const w = mountSeg('ide', 7)
    const firstInstance = w.get('[data-ide-view]').attributes('data-instance-id')

    await w.setProps({ projectId: 8, seg: 'ide' })

    expect(w.get('[data-ide-view]').attributes('data-instance-id')).not.toBe(firstInstance)
  })

  it("未知 segmentPath（'bogus'）提供可返回项目工作台的 404 状态", () => {
    const w = mountSeg('bogus')
    expect(w.find('.segment-page').exists()).toBe(true)
    expect(w.find('h1').text()).toBe('未找到项目功能')
    expect(w.text()).toContain('bogus')
    expect(w.find('[data-tc-tabs]').exists()).toBe(false)
  })
})

