import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, KeepAlive, h, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import WorkflowGraphWorkbench from '../WorkflowGraphWorkbench.vue'
import NodeConfigPanel from '../NodeConfigPanel.vue'
import { useWorkflowGraphStore } from '../../stores/workflowGraph'
import type { DagTab } from '../../stores/dagTabs'
import trialRunSource from '../../stores/trialRun.ts?raw'

const fixtures = vi.hoisted(() => ({
  specs: [
    {
      type: 'endpoint_select',
      publishedVersion: 7,
      componentRef: { type: 'endpoint_select', version: 7 },
      identity: { displayName: '端点选择' },
    },
    {
      type: 'field_map',
      publishedVersion: 3,
      identity: { displayName: '字段映射' },
    },
  ],
  trial: {
    projectId: 99 as number | null,
    definitionId: 99 as number | null,
    runResult: {
      status: 'SUCCEEDED',
      tasks: [{ nodeCode: 'n1', status: 'SUCCEEDED' }],
    },
    options: { nodeCodes: [], startNode: '', dryRun: true, sqlPrecheck: true },
    snapshot: null,
    output: null,
    promoteResult: null,
    running: false,
    lastError: null,
  },
  trialActions: {
    open: vi.fn(),
    createSnapshot: vi.fn(),
    run: vi.fn(),
    refreshOutput: vi.fn(),
    promote: vi.fn(),
  },
  messages: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('../../services/rebuild/workflowApi', () => ({
  WF_NODE_TYPES: ['sql', 'python', 'shell', 'dependent'],
  getWorkflowDefinition: vi.fn(async () => ({
    id: 42,
    projectId: 7,
    name: '同步工作流',
    draft: {
      nodes: [
        { nodeCode: 'n1', nodeType: 'START', name: null, params: null, positionX: 0, positionY: 0 },
        {
          nodeCode: 'n2',
          nodeType: 'SYNC',
          name: null,
          params: { component: 'endpoint_select' },
          positionX: 100,
          positionY: 0,
        },
        {
          nodeCode: 'n3',
          nodeType: 'SYNC',
          name: null,
          params: { component: 'field_map' },
          positionX: 200,
          positionY: 0,
        },
        {
          nodeCode: 'n4',
          nodeType: 'SYNC',
          name: null,
          params: { component: 'field_map_union' },
          positionX: 300,
          positionY: 0,
        },
      ],
      edges: [],
    },
  })),
  listWorkflowVersions: vi.fn(async () => []),
  publishWorkflowDefinition: vi.fn(async () => ({ version: 1 })),
}))

vi.mock('../../services/rebuild/componentSpecApi', () => ({
  loadComponentSpecs: vi.fn(async () => ({ items: fixtures.specs, etag: 'x', source: 'network' })),
}))
vi.mock('../../services/rebuild/datasourceApi', () => ({
  createDatasourceContract: vi.fn(() => ({ listDatasources: vi.fn(async () => ({ items: [] })) })),
}))
vi.mock('../../stores/trialRun', () => ({
  useTrialRunStore: () => ({
    ...fixtures.trial,
    ...fixtures.trialActions,
  }),
}))
vi.mock('element-plus', () => ({
  ElMessage: fixtures.messages,
  ElMessageBox: { prompt: vi.fn(async () => ({ value: '' })) },
}))
vi.mock('../SyncMappingEditor.vue', async () => {
  const { defineComponent, h: render } = await import('vue')
  return {
    default: defineComponent({
      name: 'SyncMappingEditor',
      setup: () => () => render('div', { 'data-testid': 'sync-mapping-stub' }),
    }),
  }
})
vi.mock('@vue-flow/core', async () => {
  const { defineComponent, h: render } = await import('vue')
  return {
    MarkerType: { ArrowClosed: 'arrowclosed' },
    VueFlow: defineComponent({
      name: 'VueFlow',
      props: { nodes: Array, edges: Array },
      emits: ['nodeClick', 'edgeClick', 'paneClick', 'connect', 'nodesChange', 'edgesChange'],
      setup: (_, { slots }) => () => render('div', { class: 'vf-stub' }, slots.default?.()),
    }),
    useVueFlow: () => ({ project: (point: { x: number; y: number }) => point }),
  }
})
vi.mock('@vue-flow/controls', () => ({ Controls: { render: () => null } }))
vi.mock('@vue-flow/minimap', () => ({ MiniMap: { render: () => null } }))

const tab: DagTab = { key: '42', docId: '42', name: '同步工作流', type: 'sync' }

function mountWorkbench() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(KeepAlive, {
    slots: { default: () => h(WorkflowGraphWorkbench, { tab, projectId: 7 }) },
    global: {
      plugins: [pinia],
      stubs: {
        WorkflowVariablePanel: true,
        TrialRunPanel: true,
        ScriptResourceEditor: { template: '<div data-testid="script-resource-editor-stub" />' },
        DependencyNodeEditor: { template: '<div data-testid="dependency-node-editor-stub" />' },
      },
      components: {
        'el-dialog': { render: () => null },
        'el-table': { render: () => null },
        'el-table-column': { render: () => null },
      },
    },
  })
  return { wrapper, graph: useWorkflowGraphStore() }
}

function mountToggleHost() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const visible = ref(true)
  const Host = defineComponent({
    setup: () => () => h(KeepAlive, null, {
      default: () => visible.value ? h(WorkflowGraphWorkbench, { tab, projectId: 7 }) : null,
    }),
  })
  const wrapper = mount(Host, {
    global: {
      plugins: [pinia],
      stubs: { WorkflowVariablePanel: true, TrialRunPanel: true },
      components: {
        'el-dialog': { render: () => null },
        'el-table': { render: () => null },
        'el-table-column': { render: () => null },
      },
    },
  })
  return { wrapper, visible }
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  fixtures.trial.projectId = 99
  fixtures.trial.definitionId = 99
})

describe('WorkflowGraphWorkbench quality regressions', () => {
  it('fails closed without a valid spec ref and pins authorized sync nodes to the catalog ref', async () => {
    const { wrapper, graph } = mountWorkbench()
    await flushPromises()

    await wrapper.find('.wf-type').trigger('click')
    expect(graph.nodes).toHaveLength(4)

    await wrapper.find('[data-testid="wf-spec-endpoint_select"]').trigger('click')
    expect(graph.nodes.at(-1)?.componentRef).toEqual({ type: 'endpoint_select', version: 7 })

    await wrapper.find('.vf-stub').trigger('drop', {
      clientX: 10,
      clientY: 20,
      dataTransfer: { getData: () => 'field_map' },
    })
    expect(graph.nodes).toHaveLength(5)
    expect(fixtures.messages.error).toHaveBeenCalledTimes(2)
  })

  it('isolates every bound trial context while retaining the unreachable legacy fixture', async () => {
    fixtures.trial.projectId = null
    fixtures.trial.definitionId = null
    const first = mountWorkbench()
    await flushPromises()
    let nodes = first.wrapper.findComponent({ name: 'VueFlow' }).props('nodes') as Array<{ class?: string }>
    expect(nodes[0].class).toBe('wf-node-succeeded')
    first.wrapper.unmount()

    fixtures.trial.projectId = 99
    fixtures.trial.definitionId = 99
    const second = mountWorkbench()
    await flushPromises()
    nodes = second.wrapper.findComponent({ name: 'VueFlow' }).props('nodes') as Array<{ class?: string }>
    expect(nodes[0].class).toBeUndefined()
  })

  it('anchors the production invariant that makes null/null plus runResult unreachable', () => {
    expect(trialRunSource).toMatch(/open\(projectId: number, definitionId: number\)[\s\S]*this\.projectId = projectId[\s\S]*this\.definitionId = definitionId/)
    expect(trialRunSource).toMatch(/open\(projectId: number, definitionId: number\)[\s\S]*this\.runResult = null/)
    expect(trialRunSource).toMatch(/async run\(\)[\s\S]*this\.projectId === null \|\| this\.definitionId === null \|\| this\.snapshot === null/)
    expect(trialRunSource).not.toMatch(/persist\s*:/)
  })

  it('renders status when both bound identifiers match exactly', async () => {
    fixtures.trial.projectId = 7
    fixtures.trial.definitionId = 42
    const { wrapper } = mountWorkbench()
    await flushPromises()
    const nodes = wrapper.findComponent({ name: 'VueFlow' }).props('nodes') as Array<{ class?: string }>
    expect(nodes[0].class).toBe('wf-node-succeeded')
  })

  it('routes endpoint_select to NodeConfigPanel and keeps SyncMappingEditor absent', async () => {
    const { wrapper } = mountWorkbench()
    await flushPromises()

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'n2' } })
    await nextTick()
    expect(wrapper.find('.wf-aside [data-testid="node-config-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="sync-mapping-stub"]').exists()).toBe(false)
  })

  it('routes field_map and field_map_union to SyncMappingEditor and keeps NodeConfigPanel absent', async () => {
    const { wrapper } = mountWorkbench()
    await flushPromises()

    for (const id of ['n3', 'n4']) {
      wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id } })
      await nextTick()
      expect(wrapper.find('[data-testid="sync-mapping-stub"]').exists()).toBe(true)
      expect(wrapper.find('.wf-aside [data-testid="node-config-panel"]').exists()).toBe(false)
    }
  })

  it('keeps raw JSON fallback closed when a core node has a variable-aware specialized editor', async () => {
    const { wrapper, graph } = mountWorkbench()
    await flushPromises()
    const flow = wrapper.findComponent({ name: 'VueFlow' })

    const sql = graph.addNode({ nodeType: 'sql', params: { component: 'sql', sql: 'select 1' } })
    await nextTick()
    flow.vm.$emit('nodeClick', { node: { id: sql.nodeCode } })
    await nextTick()
    expect(wrapper.find('[data-testid="script-resource-editor-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(false)

    const dependency = graph.addNode({ nodeType: 'dependent', params: { component: 'dependent' } })
    await nextTick()
    flow.vm.$emit('nodeClick', { node: { id: dependency.nodeCode } })
    await nextTick()
    expect(wrapper.find('[data-testid="dependency-node-editor-stub"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="node-config-panel"]').exists()).toBe(false)
  })

  it('rebinds an open trial panel when KeepAlive activates the workflow again', async () => {
    const { wrapper, visible } = mountToggleHost()
    await flushPromises()
    await wrapper.find('[data-testid="wf-trial"]').trigger('click')
    fixtures.trialActions.open.mockClear()

    visible.value = false
    await nextTick()
    visible.value = true
    await flushPromises()

    expect(fixtures.trialActions.open).toHaveBeenCalledWith(7, 42)
  })

  it('keeps component identity authoritative when JSON contains a component key', async () => {
    const wrapper = mount(NodeConfigPanel, {
      props: {
        projectId: 7,
        node: {
          nodeCode: 'n9',
          nodeType: 'SYNC',
          name: null,
          params: { component: 'field_map', original: true },
          positionX: 0,
          positionY: 0,
        },
      },
    })

    expect(wrapper.find('[data-variable-field="ncp-json"]').exists()).toBe(true)
    await wrapper.get('[data-testid="ncp-json"]').get('textarea').setValue('{"component":"endpoint_select","value":1}')
    await wrapper.find('[data-testid="ncp-save"]').trigger('click')
    expect(wrapper.emitted('save')?.[0]?.[0]).toEqual({ component: 'field_map', value: 1 })
  })

  it('routes endpoint_select text parameters through the unified variable input', async () => {
    const wrapper = mount(NodeConfigPanel, {
      props: {
        projectId: 7,
        workflowId: 42,
        node: {
          nodeCode: 'endpoint-vars',
          nodeType: 'SYNC',
          name: null,
          params: { component: 'endpoint_select', baseMode: 'src_base', srcDs: 'source', srcTable: 'orders', tgtDs: 'target' },
          positionX: 0,
          positionY: 0,
        },
      },
      global: {
        stubs: {
          VariableReferenceInput: {
            props: ['modelValue', 'context', 'label'],
            emits: ['update:modelValue'],
            template: '<button data-variable-input @click="$emit(\'update:modelValue\', \'${project.source_table}\')">{{ label }}</button>',
          },
        },
      },
    })

    await wrapper.get('[data-variable-field="ncp-srcTable"]').trigger('click')
    await wrapper.get('[data-testid="ncp-save"]').trigger('click')

    expect(wrapper.emitted('save')?.[0]?.[0]).toEqual(expect.objectContaining({
      srcTable: '${project.source_table}',
    }))
  })

  it('rejects a negative file header row count before saving endpoint_select', async () => {
    const wrapper = mount(NodeConfigPanel, {
      props: {
        projectId: 7,
        node: {
          nodeCode: 'file-endpoint',
          nodeType: 'SYNC',
          name: '文件端点',
          params: {
            component: 'endpoint_select',
            baseMode: 'file_sync',
            filePath: 'samples/orders.csv',
            fileHeaderRows: 1,
            tgtDs: 'warehouse',
          },
          positionX: 0,
          positionY: 0,
        },
      },
    })
    await flushPromises()

    await wrapper.find('[data-testid="ncp-fileHeaderRows"]').setValue('-1')
    await wrapper.find('[data-testid="ncp-save"]').trigger('click')

    expect(fixtures.messages.warning).toHaveBeenCalledWith('表头行数不能小于 0')
    expect(wrapper.emitted('save')).toBeUndefined()
  })
})
