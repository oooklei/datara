/**
 * WorkflowGraphWorkbench 契约测试（L12-02 同步工作流闭环：建→配→试运行→状态可见）。
 *
 * mock 策略：
 *  - workflowGraph store 用真实 pinia store（addNode/updateNode 状态转换是断言对象）；
 *  - trialRun store 用桩（mount 前设置 runResult——桩非 reactive，computed 首次求值即读取）；
 *  - @vue-flow/core 用工厂内 VueFlowStub 替换 VueFlow 导出（绕开 ResizeObserver/d3-zoom），
 *    useVueFlow().project 恒等映射（drop 坐标断言直取 clientX/Y 的 Math.round）；
 *  - KeepAlive 首挂载触发 onActivated（ensureLoaded + loadSyncSpecs 的唯一入口）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { KeepAlive, h, nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkflowGraphWorkbench from '../WorkflowGraphWorkbench.vue'
import { useWorkflowGraphStore } from '../../stores/workflowGraph'
import type { DagTab, DagProfileType } from '../../stores/dagTabs'
import type { ComponentSpecItem } from '../../services/rebuild/componentSpecApi'

/* ---------- hoisted fixtures / mocks ---------- */

const { DRAFT_NODES, DRAFT_EDGES, WF_NODE_TYPES_MOCK, SPECS } = vi.hoisted(() => {
  const DRAFT_NODES = [
  { nodeCode: 'n1', nodeType: 'START', name: null, params: null, positionX: 40, positionY: 80 },
  {
    nodeCode: 'n2',
    nodeType: 'SYNC',
    name: null,
    params: {
      component: 'endpoint_select',
      baseMode: 'src_base',
      srcDs: 'mysql-main',
      srcTable: 'app.users',
      tgtDs: 'pg-warehouse',
    },
    positionX: 200,
    positionY: 80,
  },
  { nodeCode: 'n3', nodeType: 'END', name: null, params: null, positionX: 360, positionY: 80 },
]

const DRAFT_EDGES = [
  { fromNode: 'n1', toNode: 'n2', name: null },
  { fromNode: 'n2', toNode: 'n3', name: null },
]

const WF_NODE_TYPES_MOCK = [
  'FLOW', 'SYNC', 'SQL', 'PYTHON', 'SHELL', 'DEPENDENCY', 'START', 'END',
  'CONDITION', 'FORK', 'JOIN', 'WAIT', 'SUB_WORKFLOW',
]

/** 7 白名单 + 1 白名单外（runtime_only_c17 断言不渲染） */
function specItem(type: string, displayName?: string): ComponentSpecItem {
  return {
    type,
    publishedVersion: 1,
    identity: displayName ? { displayName } : {},
    description: '',
    inputs: [],
    outputs: [],
    visual: {},
    behaviors: [],
    dropPolicy: null,
    extensions: {},
    specVersion: 1,
    ports: {},
  } as unknown as ComponentSpecItem
}

const SPECS = [
  specItem('src_base_orch', '源表基准'),
  specItem('tgt_base_orch', '目标表基准'),
  specItem('file_sync_orch', '文件同步'),
  specItem('endpoint_select', '端点选择'),
  specItem('field_map', '字段映射'),
  specItem('field_map_union', '字段合并映射'),
  specItem('condition_set', '条件集'),
  specItem('runtime_only_c17'),
]

  return { DRAFT_NODES, DRAFT_EDGES, WF_NODE_TYPES_MOCK, SPECS }
})

const specMock = vi.hoisted(() => ({ loadComponentSpecs: vi.fn() }))
const dsMock = vi.hoisted(() => ({
  createDatasourceContract: vi.fn(() => ({
    listDatasources: vi.fn(async () => ({ items: [{ name: 'mysql-main' }, { name: 'pg-warehouse' }] })),
  })),
}))
const trialMock = vi.hoisted(() => {
  const state = {
    projectId: null as number | null,
    definitionId: null as number | null,
    snapshot: null,
    /** TrialRunPanel 渲染即读 options.nodeCodes/startNode/dryRun/sqlPrecheck */
    options: {
      nodeCodes: [] as string[],
      startNode: '',
      testVariables: '',
      dependencyMock: '',
      dryRun: true,
      sqlPrecheck: true,
    },
    runResult: null as { status: string; tasks: { nodeCode: string; status: string }[] } | null,
    output: null,
    promoteResult: null,
    running: false,
    loadSeq: 0,
    lastError: null,
  }
  const actions = {
    open: vi.fn(),
    createSnapshot: vi.fn(),
    run: vi.fn(),
    refreshOutput: vi.fn(),
    promote: vi.fn(),
  }
  return { state, actions }
})

vi.mock('../../services/rebuild/workflowApi', () => ({
  WF_NODE_TYPES: WF_NODE_TYPES_MOCK,
  getWorkflowDefinition: vi.fn(async () => ({
    id: 42,
    projectId: 7,
    name: '同步工作流A',
    description: null,
    currentVersion: null,
    // 深拷贝：store.load 引用赋值，addNode 的 push 不得污染共享 fixture（用例间独立）
    draft: {
      nodes: JSON.parse(JSON.stringify(DRAFT_NODES)),
      edges: JSON.parse(JSON.stringify(DRAFT_EDGES)),
    },
  })),
  listWorkflowVersions: vi.fn(async () => []),
  publishWorkflowDefinition: vi.fn(async () => ({ version: 1 })),
}))

vi.mock('../../services/rebuild/componentSpecApi', () => specMock)
vi.mock('../../services/rebuild/datasourceApi', () => dsMock)
vi.mock('../../stores/trialRun', () => ({
  useTrialRunStore: () => ({ ...trialMock.state, ...trialMock.actions }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn(async () => ({ value: '' })) },
  ElDialog: { name: 'ElDialog', props: ['modelValue', 'title', 'width'], render: () => null },
  ElTable: { name: 'ElTable', props: ['data'], render: () => null },
  ElTableColumn: { name: 'ElTableColumn', render: () => null },
}))

vi.mock('@vue-flow/core', async () => {
  const { defineComponent, h: hVue } = await import('vue')
  const VueFlowStub = defineComponent({
    name: 'VueFlow',
    props: {
      nodes: { type: Array, default: () => [] },
      edges: { type: Array, default: () => [] },
    },
    emits: ['nodeClick', 'edgeClick', 'paneClick', 'connect', 'nodesChange', 'edgesChange'],
    setup(_, { slots }) {
      return () => hVue('div', { class: 'vf-stub' }, slots.default?.())
    },
  })
  return {
    MarkerType: { ArrowClosed: 'arrowclosed' },
    VueFlow: VueFlowStub,
    useVueFlow: () => ({ project: (p: { x: number; y: number }) => ({ x: p.x, y: p.y }) }),
  }
})
vi.mock('@vue-flow/controls', () => ({ Controls: { name: 'Controls', render: () => null } }))
vi.mock('@vue-flow/minimap', () => ({ MiniMap: { name: 'MiniMap', render: () => null } }))

/* ---------- mount helpers ---------- */

/** 模板解析走全局注册链（非 element-plus 模块导入），mount 时注册桩消噪 Failed to resolve component */
const ElStub = { name: 'ElStub', render: () => null }

function makeWorkbench(tabType: DagProfileType = 'wf'): {
  wrapper: VueWrapper
  graph: ReturnType<typeof useWorkflowGraphStore>
} {
  const pinia = createPinia()
  setActivePinia(pinia)
  const tab: DagTab = { key: '42', docId: '42', name: '同步工作流A', type: tabType }
  const wrapper = mount(KeepAlive, {
    slots: { default: () => h(WorkflowGraphWorkbench, { tab, projectId: 7 }) },
    global: {
      plugins: [pinia],
      components: {
        'el-dialog': ElStub,
        'el-table': ElStub,
        'el-table-column': ElStub,
      },
    },
  })
  return { wrapper, graph: useWorkflowGraphStore() }
}

beforeEach(() => {
  // 快照键污染（用例间 localStorage 共享：addNode → isDirty → unmount persistSnap）
  localStorage.clear()
  vi.clearAllMocks()
  specMock.loadComponentSpecs.mockResolvedValue({ items: SPECS, etag: '"00"', source: 'network' })
  trialMock.state.runResult = null
})

describe('WorkflowGraphWorkbench L12-02 同步工作流契约', () => {
  it('用例1 加载完成：wf-body 在位 + VueFlow 收到 3 节点 2 边 + 托盘 13 类型 + 非 sync tab 无组件侧栏', async () => {
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()

    expect(wrapper.find('.wf-body').exists()).toBe(true)
    const vf = wrapper.findComponent({ name: 'VueFlow' })
    expect(vf.exists()).toBe(true)
    expect((vf.props('nodes') as unknown[]).length).toBe(3)
    expect((vf.props('edges') as unknown[]).length).toBe(2)
    expect(wrapper.findAll('.wf-type').length).toBe(13)
    expect(wrapper.find('.wf-specs').exists()).toBe(false)
  })

  it('用例2 sync tab 组件侧栏：7 白名单项渲染 + identity.displayName 兜底 + 白名单外不渲染', async () => {
    const { wrapper } = makeWorkbench('sync')
    await flushPromises()

    expect(wrapper.find('.wf-specs').exists()).toBe(true)
    expect(wrapper.findAll('.wf-spec').length).toBe(7)
    expect(wrapper.find('[data-testid="wf-spec-endpoint_select"]').text()).toBe('端点选择')
    expect(wrapper.find('[data-testid="wf-spec-src_base_orch"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wf-spec-runtime_only_c17"]').exists()).toBe(false)
  })

  it('用例3 sync tab 组件清单加载失败：静默降级 wf-specs-failed 提示', async () => {
    specMock.loadComponentSpecs.mockRejectedValue(new Error('boom'))
    const { wrapper } = makeWorkbench('sync')
    await flushPromises()

    expect(wrapper.find('[data-testid="wf-specs-failed"]').exists()).toBe(true)
    expect(wrapper.find('.wf-spec').exists()).toBe(false)
  })

  it('用例4 画布 drop 承接：datara/node-type → addNode SYNC + component 参数 + Math.round 坐标', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 100.6,
      clientY: 200.4,
      dataTransfer: { getData: () => 'endpoint_select' },
    })
    await nextTick()

    expect(graph.nodes.length).toBe(4)
    expect(graph.nodes[3]).toMatchObject({
      nodeCode: 'n4',
      nodeType: 'SYNC',
      params: { component: 'endpoint_select' },
      positionX: 101,
      positionY: 200,
    })
  })

  it('用例5 spec 点击兜底添加：params.component + 级联摆位 534/24', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()

    await wrapper.find('[data-testid="wf-spec-field_map"]').trigger('click')

    expect(graph.nodes.length).toBe(4)
    expect(graph.nodes[3]).toMatchObject({
      nodeCode: 'n4',
      nodeType: 'SYNC',
      params: { component: 'field_map' },
      positionX: 534,
      positionY: 24,
    })
  })

  it('用例6 节点配置闭环：nodeClick → NodeConfigPanel 预填 → 保存回写 params + 面板关闭', async () => {
    const { wrapper, graph } = makeWorkbench('wf')
    await flushPromises()

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'n2' } })
    await nextTick()

    const panel = wrapper.find('[data-testid="node-config-panel"]')
    expect(panel.exists()).toBe(true)
    expect(wrapper.find('[data-testid="ncp-title"]').text()).toBe('n2 · SYNC')
    // 表单预填：baseMode select 取 node.params.baseMode
    const bm = wrapper.find('[data-testid="ncp-baseMode"]')
    expect((bm.element as HTMLSelectElement).value).toBe('src_base')

    await wrapper.find('[data-testid="ncp-save"]').trigger('click')
    await flushPromises()

    // src_base 模式：tgtTable 空串跳过；tgt_base/file_sync 专属字段不可见跳过；bool autoCreate 恒带（default true）
    expect(graph.nodes[1].params).toEqual({
      component: 'endpoint_select',
      baseMode: 'src_base',
      srcDs: 'mysql-main',
      srcTable: 'app.users',
      tgtDs: 'pg-warehouse',
      autoCreate: true,
    })
    // 保存后 clearSelection → 面板关闭
    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(false)
  })

  it('用例7 试运行入口：wf-trial → TrialRunPanel 挂载并 open(7, 42)', async () => {
    const { wrapper } = makeWorkbench('sync')
    await flushPromises()

    await wrapper.find('[data-testid="wf-trial"]').trigger('click')
    await nextTick()

    expect(wrapper.findComponent({ name: 'TrialRunPanel' }).exists()).toBe(true)
    expect(trialMock.actions.open).toHaveBeenCalledWith(7, 42)
  })

  it('用例8 状态标注：runResult.tasks → flowNodes label [STATUS] + wf-node-{status} class', async () => {
    trialMock.state.runResult = {
      status: 'SUCCEEDED',
      tasks: [
        { nodeCode: 'n1', status: 'SUCCEEDED' },
        { nodeCode: 'n3', status: 'FAILED' },
      ],
    }
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()

    const nodes = wrapper.findComponent({ name: 'VueFlow' }).props('nodes') as Array<{
      id: string
      label: string
      class?: string
    }>
    expect(nodes[0].label).toBe('n1 START [SUCCEEDED]')
    expect(nodes[0].class).toBe('wf-node-succeeded')
    // 无状态节点不标注
    expect(nodes[1].label).toBe('n2 SYNC')
    expect(nodes[1].class).toBeUndefined()
    expect(nodes[2].label).toBe('n3 END [FAILED]')
    expect(nodes[2].class).toBe('wf-node-failed')
  })
})
