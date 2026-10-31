/**
 * WorkflowGraphWorkbench 契约测试（L12-02 同步工作流闭环：建→配→发布→状态可见）。
 *
 * mock 策略：
 *  - workflowGraph store 用真实 pinia store（addNode/updateNode 状态转换是断言对象）；
 *  - @vue-flow/core 用工厂内 VueFlowStub 替换 VueFlow 导出（绕开 ResizeObserver/d3-zoom），
 *    useVueFlow().project 恒等映射（drop 坐标断言直取 clientX/Y 的 Math.round）；
 *  - KeepAlive 首挂载触发 onActivated（ensureLoaded + loadSyncSpecs 的唯一入口）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { KeepAlive, h, nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkflowGraphWorkbench from '../WorkflowGraphWorkbench.vue'
import { useWorkflowGraphStore } from '../../stores/workflowGraph'
import { ContractApiError } from '../../services/http'
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

const WF_NODE_TYPES_MOCK = ['sql', 'python', 'shell', 'dependent']

/** 7 白名单 + 1 白名单外（runtime_only_c17 断言不渲染） */
function specItem(type: string, displayName?: string): ComponentSpecItem {
  return {
    type,
    publishedVersion: 1,
    componentRef: { type, version: 1 },
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
  specItem('sql', 'SQL脚本'),
  specItem('src_base_orch', '源表基准'),
  specItem('tgt_base_orch', '目标表基准'),
  specItem('file_sync_orch', '文件同步'),
  specItem('endpoint_select', '端点选择'),
  specItem('field_map', '字段映射'),
  specItem('field_map_union', '字段合并映射'),
  specItem('condition_set', '条件集'),
  specItem('stream_input', '流输入'),
  specItem('stream_fuse', '流融合'),
  specItem('stream_output', '流输出'),
  specItem('page_board', '观测看板'),
  specItem('runtime_only_c17'),
]

  return { DRAFT_NODES, DRAFT_EDGES, WF_NODE_TYPES_MOCK, SPECS }
})

const specMock = vi.hoisted(() => ({
  loadComponentSpecs: vi.fn(),
  // Palette.loadRows 过滤用（与 componentSpecApi.isDesignComponent 同口径）
  isDesignComponent: (item: { type?: string; runtimeOnly?: boolean; visual?: { paletteVisible?: boolean }; workflowTypes?: string[]; componentRef?: { type?: string; version?: number } }, workflowType: string) =>
    item.runtimeOnly !== true
    && item.visual?.paletteVisible !== false
    && (item.workflowTypes ?? []).includes(workflowType)
    && item.componentRef?.type === item.type
    && Number.isInteger(item.componentRef?.version)
    && (item.componentRef?.version ?? 0) >= 1,
}))
const dsMock = vi.hoisted(() => ({
  createDatasourceContract: vi.fn(() => ({
    listDatasources: vi.fn(async () => ({ items: [{ name: 'mysql-main' }, { name: 'pg-warehouse' }] })),
  })),
}))

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

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn(async () => ({ value: '' })), confirm: vi.fn(async () => 'confirm') },
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

/** 本文件挂载过的工作台实例。变更用例（drop/删除/移动）遗留的真实 500ms canvas-state
 * 防抖定时器随实例存活，跨用例到点落盘会污染共享 localStorage（KA3 的 null 断言），
 * afterEach 统一卸载以同步 flushSnapDebounce 清定时器。 */
const liveWorkbenches: VueWrapper[] = []

function makeWorkbench(tabType: DagProfileType = 'wf', attach = false): {
  wrapper: VueWrapper
  graph: ReturnType<typeof useWorkflowGraphStore>
} {
  const pinia = createPinia()
  setActivePinia(pinia)
  const tab: DagTab = { key: '42', docId: '42', name: '同步工作流A', type: tabType }
  const wrapper = mount(KeepAlive, {
    // 快捷键用例需 attach：onPageKeydown 实例活性守卫按 rootEl.isConnected 判定，
    // 未 attach 的实例（含既有用例泄漏的历史监听器）一律不响应
    ...(attach ? { attachTo: document.body } : {}),
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
  liveWorkbenches.push(wrapper)
  return { wrapper, graph: useWorkflowGraphStore() }
}

beforeEach(() => {
  // 快照键污染（用例间 localStorage 共享：addNode → isDirty → unmount persistSnap）
  localStorage.clear()
  vi.clearAllMocks()
  specMock.loadComponentSpecs.mockResolvedValue({ items: SPECS, etag: '"00"', source: 'network' })
})

afterEach(() => {
  // 先卸载再清 DOM：onUnmounted 同步 flushSnapDebounce 清掉变更用例遗留的真实
  // 500ms 防抖定时器；卸载触发的 persistSnap 落盘由下一用例 beforeEach 的
  // localStorage.clear() 兜底清除
  while (liveWorkbenches.length > 0) {
    const w = liveWorkbenches.pop()
    try {
      w?.unmount()
    } catch {
      // 首个用例已在用例内手动 unmount，重复卸载忽略
    }
  }
  document.body.replaceChildren()
})

it('aborts the component catalogue subscription when the workbench unmounts', async () => {
  let signal: AbortSignal | undefined
  specMock.loadComponentSpecs.mockImplementation((_workflowType?: string, requestSignal?: AbortSignal) => {
    signal = requestSignal
    return new Promise(() => undefined)
  })
  const { wrapper } = makeWorkbench('wf')
  await nextTick()

  expect(signal).toBeInstanceOf(AbortSignal)
  wrapper.unmount()
  expect(signal?.aborted).toBe(true)
})

describe('WorkflowGraphWorkbench L12-02 同步工作流契约', () => {
  it('用例1 加载完成：wf-body 在位 + VueFlow 收到 3 节点 2 边 + 托盘 4 组件 + 非 spec 宿主无组件侧栏', async () => {
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()

    expect(wrapper.find('.wf-body').exists()).toBe(true)
    const vf = wrapper.findComponent({ name: 'VueFlow' })
    expect(vf.exists()).toBe(true)
    expect((vf.props('nodes') as unknown[]).length).toBe(3)
    expect((vf.props('edges') as unknown[]).length).toBe(2)
    expect(wrapper.findAll('.wf-type').length).toBe(4)
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

  it('用例4 画布 drop 承接：datara/node-type → nodeType=组件type（catalogue 冻结语义）+ Math.round 坐标', async () => {
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
      nodeType: 'endpoint_select',
      params: { component: 'endpoint_select' },
      positionX: 101,
      positionY: 200,
    })
  })

  it('用例5 spec 点击兜底添加：nodeType=组件type + params.component + 级联摆位 534/24', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()

    await wrapper.find('[data-testid="wf-spec-field_map"]').trigger('click')

    expect(graph.nodes.length).toBe(4)
    expect(graph.nodes[3]).toMatchObject({
      nodeCode: 'n4',
      nodeType: 'field_map',
      params: { component: 'field_map' },
      positionX: 534,
      positionY: 24,
    })
  })

  it('用例5b stream 宿主组件托盘：4 白名单项渲染 + drop 承接 nodeType=stream_input', async () => {
    const { wrapper, graph } = makeWorkbench('stream')
    await flushPromises()

    expect(wrapper.find('.wf-specs').exists()).toBe(true)
    expect(wrapper.findAll('.wf-spec').length).toBe(4)
    expect(wrapper.find('[data-testid="wf-spec-page_board"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wf-spec-endpoint_select"]').exists()).toBe(false)

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 60.2,
      clientY: 90.8,
      dataTransfer: { getData: () => 'stream_input' },
    })
    await nextTick()

    expect(graph.nodes.length).toBe(4)
    expect(graph.nodes[3]).toMatchObject({
      nodeType: 'stream_input',
      params: { component: 'stream_input' },
      positionX: 60,
      positionY: 91,
    })
  })

  it('用例5c NORMAL 组件经 Palette 拖入承接：nodeType=sql 且不带 params.component', async () => {
    const { wrapper, graph } = makeWorkbench('wf')
    await flushPromises()

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 10.4,
      clientY: 20.6,
      dataTransfer: { getData: () => 'sql' },
    })
    await nextTick()

    expect(graph.nodes.length).toBe(4)
    expect(graph.nodes[3]).toMatchObject({
      nodeType: 'sql',
      componentRef: { type: 'sql', version: 1 },
      positionX: 10,
      positionY: 21,
    })
    expect(graph.nodes[3].params?.component).toBeUndefined()
  })

  it('用例5d configure-first：新增节点立即选中并呈现配置面板', async () => {
    const { wrapper } = makeWorkbench('sync')
    await flushPromises()
    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(false)

    await wrapper.find('[data-testid="wf-spec-endpoint_select"]').trigger('click')

    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(true)
  })

  it('用例5e 未配置节点徽标：新拖入节点 label 带 ⚠未配置 + class wf-node-unconfigured', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 30,
      clientY: 40,
      dataTransfer: { getData: () => 'field_map' },
    })
    await nextTick()
    const vf = wrapper.findComponent({ name: 'VueFlow' })
    const added = (vf.props('nodes') as { id: string; label: string; class?: string }[]).at(-1)!
    expect(added.label).toContain('⚠未配置')
    expect(added.class).toContain('wf-node-unconfigured')

    // 配置回写业务参数后徽标解除（component 归属标记不计入业务参数）
    graph.updateNode(added.id, { params: { component: 'field_map', baseMode: 'src_base' } })
    await nextTick()
    const configured = (vf.props('nodes') as { id: string; label: string; class?: string }[]).find((n) => n.id === added.id)!
    expect(configured.label).not.toContain('⚠未配置')
  })

  it('用例5f 保存闸门：存在未配置节点时 onSave 拦截（不进入保存流程）', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()
    const saveSpy = vi.spyOn(graph, 'save').mockResolvedValue({ complete: true, dirtyKeys: [], savedKeys: [], outcomes: [], manualRecoveryKeys: [] })

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 30,
      clientY: 40,
      dataTransfer: { getData: () => 'field_map' },
    })
    await nextTick()

    await wrapper.find('.wf-btn').trigger('click')
    expect(saveSpy).not.toHaveBeenCalled()
    const { ElMessage } = await import('element-plus')
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('存在未配置节点'))
  })

  it('用例5g 保存并发冲突：save outcome 含 409 ContractApiError → 2005 语义化文案（T5）', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()
    const conflict = new ContractApiError({ httpStatus: 409, code: 2005, msg: 'version conflict' })
    vi.spyOn(graph, 'save').mockResolvedValue({
      complete: false,
      dirtyKeys: ['n2'],
      savedKeys: [],
      outcomes: [{ key: 'n2', status: 'retryable-failed', dirty: true, retryable: true, error: conflict }],
      manualRecoveryKeys: [],
    })

    await wrapper.find('.wf-btn').trigger('click')
    const { ElMessage } = await import('element-plus')
    expect(ElMessage.error).toHaveBeenCalledWith('版本冲突（2005）：草稿已被并发修改，请刷新页面后重试')
  })

  it('用例5h 发布前 flush save 遭遇 2005：拦截发布并呈现 2005 文案（T5）', async () => {
    const { wrapper, graph } = makeWorkbench('sync')
    await flushPromises()
    graph.moveNode('n2', 210, 80) // 置 isDirty → onPublish 先 flush save
    const conflict = new ContractApiError({ httpStatus: 409, code: 2005, msg: 'version conflict' })
    vi.spyOn(graph, 'save').mockResolvedValue({
      complete: false,
      dirtyKeys: ['n2'],
      savedKeys: [],
      outcomes: [{ key: 'n2', status: 'retryable-failed', dirty: true, retryable: true, error: conflict }],
      manualRecoveryKeys: [],
    })
    const { publishWorkflowDefinition } = await import('../../services/rebuild/workflowApi')

    await wrapper.findAll('.wf-btn').at(2)!.trigger('click')
    const { ElMessage } = await import('element-plus')
    expect(ElMessage.error).toHaveBeenCalledWith('版本冲突（2005）：草稿已被并发修改，请刷新页面后重试')
    expect(publishWorkflowDefinition).not.toHaveBeenCalled()
  })

  it('用例5i 发布被闸门拒绝：publish 400 → 可声明不可执行语义化文案（T5）', async () => {
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()
    const { publishWorkflowDefinition } = await import('../../services/rebuild/workflowApi')
    vi.mocked(publishWorkflowDefinition).mockRejectedValueOnce(
      new ContractApiError({ httpStatus: 400, code: 'WF_GATE_REJECTED', msg: '依赖节点缺失' }),
    )

    await wrapper.findAll('.wf-btn').at(2)!.trigger('click')
    const { ElMessage } = await import('element-plus')
    expect(ElMessage.error).toHaveBeenCalledWith('发布被校验闸门拒绝（可声明不可执行）：依赖节点缺失')
  })

  it('用例T4a 校验徽标与面板：合法画布零计数 + 点开校验面板呈现通过态（T4/G07）', async () => {
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()

    expect(wrapper.find('[data-testid="wf-validate-error-badge"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wf-validate-warn-badge"]').exists()).toBe(false)

    await wrapper.find('[data-testid="wf-validate"]').trigger('click')
    expect(wrapper.find('[data-testid="validation-overlay"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="validation-pass"]').exists()).toBe(true)
    await wrapper.find('[data-testid="validation-close"]').trigger('click')
    expect(wrapper.find('[data-testid="validation-overlay"]').exists()).toBe(false)
  })

  it('用例T4b W1 保存闸门：画布成环 → 保存拦截 + 校验面板 CYCLE 行 + 点击定位节点（T4/G07）', async () => {
    const { wrapper, graph } = makeWorkbench('wf')
    await flushPromises()
    const saveSpy = vi.spyOn(graph, 'save').mockResolvedValue({ complete: true, dirtyKeys: [], savedKeys: [], outcomes: [], manualRecoveryKeys: [] })
    // 展开坐标绕开 dagre 自动布局（聚焦闸门语义），直写边模拟成环脏数据
    graph.moveNode('n1', 0, 0)
    graph.moveNode('n2', 300, 0)
    graph.moveNode('n3', 600, 0)
    const added = graph.addNode({
      nodeType: 'sql',
      componentRef: { type: 'sql', version: 1 },
      params: { component: 'sql', sql: 'SELECT 1' },
      positionX: 900,
      positionY: 0,
    })
    graph.edges.push({ fromNode: 'n3', toNode: added.nodeCode, name: null }, { fromNode: added.nodeCode, toNode: 'n1', name: null })
    await nextTick()

    expect(wrapper.find('[data-testid="wf-validate-error-badge"]').exists()).toBe(true)

    await wrapper.find('.wf-btn').trigger('click') // 保存
    expect(saveSpy).not.toHaveBeenCalled()
    const { ElMessage } = await import('element-plus')
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('画布校验未通过'))
    expect(wrapper.find('[data-testid="validation-overlay"]').exists()).toBe(true)
    const cycleRow = wrapper.find('[data-testid="validation-issue-CYCLE"]')
    expect(cycleRow.exists()).toBe(true)

    await cycleRow.trigger('click')
    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="validation-overlay"]').exists()).toBe(false)
  })

  it('用例T4c 六区块框架层：选中组件节点 → spec-blocks 六区块 + 参数插槽承载 NodeConfigPanel（T4/G07）', async () => {
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'n2' } })
    await nextTick()

    for (const id of ['inputs', 'outputs', 'params', 'conditions', 'constraints', 'exclusions']) {
      expect(wrapper.find(`[data-testid="spec-block-${id}"]`).exists(), id).toBe(true)
    }
    expect(wrapper.find('[data-testid="spec-block-params"]').findComponent({ name: 'NodeConfigPanel' }).exists()).toBe(true)
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

  it('用例T9a 连线图例浮层：wf-legend → 五类图例 → 关闭（T9 弹窗 #10，D9 overlay 栈第二消费者）', async () => {
    const { wrapper } = makeWorkbench('wf')
    await flushPromises()

    expect(wrapper.find('[data-testid="wf-legend-panel"]').exists()).toBe(false)
    await wrapper.find('[data-testid="wf-legend"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="wf-legend-panel"]').exists()).toBe(true)
    for (const id of ['flow', 'branch', 'branch_true', 'branch_false', 'dep']) {
      expect(wrapper.find(`[data-testid="legend-item-${id}"]`).exists(), id).toBe(true)
    }
    await wrapper.find('[data-testid="wf-legend-close"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="wf-legend-panel"]').exists()).toBe(false)
  })

  it('用例T9b 删除确认：选中节点 → 删除选中 → confirm 确认删 / 取消不删（审计弹窗 #7）', async () => {
    const { wrapper, graph } = makeWorkbench('wf')
    await flushPromises()
    const before = graph.nodes.length

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'n2' } })
    await nextTick()

    const { ElMessageBox } = await import('element-plus')
    // 取消（reject）→ 不删
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('button[title="删除选中节点/连线"]').trigger('click')
    await flushPromises()
    expect(graph.nodes.length).toBe(before)

    // 确认 → 删除 + 置脏
    vi.mocked(ElMessageBox.confirm).mockResolvedValueOnce('confirm' as unknown as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
    await wrapper.find('button[title="删除选中节点/连线"]').trigger('click')
    await flushPromises()
    expect(graph.nodes.length).toBe(before - 1)
    expect(graph.isDirty).toBe(true)
  })

  it('流工作流把当前定义绑定到实时观摩面板', async () => {
    const { wrapper } = makeWorkbench('stream')
    await flushPromises()

    const panel = wrapper.findComponent({ name: 'StreamObservationPanel' })
    expect(panel.exists()).toBe(true)
    expect(panel.props('projectId')).toBe(7)
    expect(panel.props('workflowId')).toBe(42)
    expect(panel.props('workflowName')).toBe('同步工作流A')
  })

  it('用例KA1 画布快捷键 Del/Backspace：选中节点 → confirm 确认链删除；无选中不触发（§7.1.4 护栏1b）', async () => {
    const { wrapper, graph } = makeWorkbench('wf', true)
    await flushPromises()
    const { ElMessageBox } = await import('element-plus')

    // 无选中：keydown 不进确认链
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
    await flushPromises()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()

    // 选中 n2 → Delete → confirm（mock 默认 resolve）→ 删除
    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'n2' } })
    await nextTick()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
    expect(graph.nodes.length).toBe(2)
  })

  it('用例KA2 快捷键输入控件拦截：INPUT 内 Delete 冒泡到 window 也不进删除链', async () => {
    const { wrapper } = makeWorkbench('wf', true)
    await flushPromises()
    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'n2' } })
    await nextTick()
    const { ElMessageBox } = await import('element-plus')

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', bubbles: true }))
    await flushPromises()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    input.remove()
  })

  it('用例KA3 canvas-state 500ms 防抖槽：编辑期内不落盘、到期落盘；读前 flush（卸载即落最新）', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      const { wrapper, graph } = makeWorkbench('wf')
      await flushPromises()

      graph.moveNode('n2', 210, 80)
      await nextTick() // watcher（flush pre）回调执行 → 注册 500ms fake timer
      expect(localStorage.getItem('datara.dag.snap.42')).toBe(null) // 防抖未到期不落盘

      vi.advanceTimersByTime(500)
      const snap = localStorage.getItem('datara.dag.snap.42')
      expect(snap).not.toBe(null)
      expect(JSON.parse(snap ?? '{}').draft.nodes).toHaveLength(3)

      // 再编辑 → 未到期（差 1ms）→ 卸载 flush 立即落盘最新位置（读前 flush 语义）
      graph.moveNode('n2', 220, 90)
      await nextTick()
      vi.advanceTimersByTime(499)
      wrapper.unmount()
      const final = JSON.parse(localStorage.getItem('datara.dag.snap.42') ?? '{}')
      expect(final.draft.nodes[1].positionX).toBe(220)
    } finally {
      vi.useRealTimers()
    }
  })

  it('用例B3a condition_set 结构化表单：三字段承接 + 增量列显隐 + 保存回写 params（B3）', async () => {
    // attach 必需：isVisible 基于 getComputedStyle，detached 元素恒判可见
    const { wrapper, graph } = makeWorkbench('sync', true)
    await flushPromises()

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 70,
      clientY: 80,
      dataTransfer: { getData: () => 'condition_set' },
    })
    await nextTick()
    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(true)

    // 三 params 在位；incrementalExpr 依赖增量列（c-incr-expr notEmpty）默认隐藏
    expect(wrapper.find('[data-testid="ncp-filterExpr"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ncp-incrementalColumn"]').exists()).toBe(true)
    expect(wrapper.find('[data-field="incrementalExpr"]').isVisible()).toBe(false)

    // 填增量列 → 增量表达式显现；保存收集非空可见键（filterExpr 留空不携带）
    await wrapper.find('[data-testid="ncp-incrementalColumn"] input').setValue('create_time')
    await nextTick()
    expect(wrapper.find('[data-field="incrementalExpr"]').isVisible()).toBe(true)
    await wrapper.find('[data-testid="ncp-incrementalExpr"] input').setValue('yyyyMMdd-1')
    await wrapper.find('[data-testid="ncp-save"]').trigger('click')
    await flushPromises()

    expect(graph.nodes[3]).toMatchObject({
      nodeType: 'condition_set',
      params: { component: 'condition_set', incrementalColumn: 'create_time', incrementalExpr: 'yyyyMMdd-1' },
    })
  })
})
