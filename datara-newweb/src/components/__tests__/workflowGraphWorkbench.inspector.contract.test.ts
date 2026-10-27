import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { KeepAlive, defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import WorkflowGraphWorkbench from '../WorkflowGraphWorkbench.vue'
import type { DagTab } from '../../stores/dagTabs'

const fixtures = vi.hoisted(() => ({
  panelMounts: { variables: 0, trial: 0 },
  trial: {
    projectId: null as number | null,
    definitionId: null as number | null,
    snapshot: null,
    options: { nodeCodes: [] as string[], startNode: '', dryRun: true, sqlPrecheck: true },
    runResult: null,
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
}))

vi.mock('../../services/rebuild/workflowApi', () => ({
  WF_NODE_TYPES: [],
  getWorkflowDefinition: vi.fn(async () => ({
    id: 42,
    projectId: 7,
    name: '检查器工作流',
    draft: {
      nodes: [
        { nodeCode: 'start', nodeType: 'START', name: null, params: null, positionX: 0, positionY: 0 },
        {
          nodeCode: 'dep',
          nodeType: 'DEPENDENT',
          name: null,
          params: { dependent_execute: 'workflow' },
          positionX: 180,
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
  loadComponentSpecs: vi.fn(async () => ({ items: [], etag: 'x', source: 'network' })),
  isDesignComponent: vi.fn(() => true),
}))
vi.mock('../../stores/trialRun', () => ({
  useTrialRunStore: () => ({ ...fixtures.trial, ...fixtures.trialActions }),
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: vi.fn(async () => ({ value: '' })) },
}))
vi.mock('@vue-flow/core', async () => {
  const { defineComponent: component, h: render } = await import('vue')
  return {
    MarkerType: { ArrowClosed: 'arrowclosed' },
    VueFlow: component({
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

const tab: DagTab = { key: '42', docId: '42', name: '检查器工作流', type: 'wf' }
const mountedWrappers: VueWrapper[] = []

function mountWorkbench() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const VariableStub = defineComponent({
    name: 'WorkflowVariablePanel',
    setup() {
      fixtures.panelMounts.variables += 1
      return () => h('div', { 'data-testid': 'variables-panel-stub' })
    },
  })
  const TrialStub = defineComponent({
    name: 'TrialRunPanel',
    setup() {
      fixtures.panelMounts.trial += 1
      return () => h('div', { 'data-testid': 'trial-panel-stub' })
    },
  })
  const wrapper = mount(KeepAlive, {
    attachTo: document.body,
    slots: { default: () => h(WorkflowGraphWorkbench, { tab, projectId: 7 }) },
    global: {
      plugins: [pinia],
      stubs: {
        Palette: true,
        WorkflowVariablePanel: VariableStub,
        TrialRunPanel: TrialStub,
        NodeConfigPanel: true,
        ScriptResourceEditor: true,
        SyncMappingEditor: true,
        StreamObservationPanel: true,
        DependencyNodeEditor: { template: '<div data-testid="dependency-node-editor-stub" />' },
      },
      components: {
        'el-dialog': { render: () => null },
        'el-table': { render: () => null },
        'el-table-column': { render: () => null },
      },
    },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

function inspectorTabs(wrapper: ReturnType<typeof mountWorkbench>) {
  return wrapper.findAll('[role="tab"]')
}

function expectActiveTab(wrapper: ReturnType<typeof mountWorkbench>, label: string) {
  const tabs = inspectorTabs(wrapper)
  expect(tabs).toHaveLength(4)
  for (const item of tabs) {
    expect(item.attributes('aria-selected')).toBe(item.text() === label ? 'true' : 'false')
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  fixtures.panelMounts.variables = 0
  fixtures.panelMounts.trial = 0
})

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) {
    if (wrapper.exists()) wrapper.unmount()
  }
  document.body.replaceChildren()
})

describe('WorkflowGraphWorkbench four-tab inspector contract', () => {
  it('clicking each tab updates the active and aria-selected state', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()

    for (const label of ['属性', '变量', '依赖', '试运行']) {
      await inspectorTabs(wrapper).find((item) => item.text() === label)!.trigger('click')
      expectActiveTab(wrapper, label)
    }

    const panels = wrapper.findAll('[role="tabpanel"]')
    expect(panels).toHaveLength(4)
    for (const panel of panels) expect(panel.attributes('tabindex')).toBe('0')
    await inspectorTabs(wrapper)[0].trigger('click')
    const propertiesPanel = panels[0].element
    expect(propertiesPanel).toBeInstanceOf(HTMLElement)
    if (!(propertiesPanel instanceof HTMLElement)) throw new TypeError('tabpanel must be an HTMLElement')
    propertiesPanel.focus()
    expect(document.activeElement).toBe(propertiesPanel)
  })

  it('ArrowLeft/ArrowRight/Home/End move activation and DOM focus', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()
    const tabs = inspectorTabs(wrapper)

    await tabs[0].trigger('keydown', { key: 'ArrowRight' })
    await nextTick()
    expectActiveTab(wrapper, '变量')
    expect(document.activeElement).toBe(inspectorTabs(wrapper)[1].element)

    await inspectorTabs(wrapper)[1].trigger('keydown', { key: 'End' })
    await nextTick()
    expectActiveTab(wrapper, '试运行')
    expect(document.activeElement).toBe(inspectorTabs(wrapper)[3].element)

    await inspectorTabs(wrapper)[3].trigger('keydown', { key: 'ArrowLeft' })
    await nextTick()
    expectActiveTab(wrapper, '依赖')
    expect(document.activeElement).toBe(inspectorTabs(wrapper)[2].element)

    await inspectorTabs(wrapper)[2].trigger('keydown', { key: 'Home' })
    await nextTick()
    expectActiveTab(wrapper, '属性')
    expect(document.activeElement).toBe(inspectorTabs(wrapper)[0].element)
  })

  it('toolbar variable and trial actions only activate their matching tabs', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()
    await inspectorTabs(wrapper)[2].trigger('click')

    await wrapper.find('[data-workflow-variables]').trigger('click')
    expectActiveTab(wrapper, '变量')
    expect(fixtures.panelMounts.variables).toBe(1)
    expect(fixtures.panelMounts.trial).toBe(0)

    await wrapper.find('[data-testid="wf-trial"]').trigger('click')
    expectActiveTab(wrapper, '试运行')
    expect(fixtures.panelMounts.variables).toBe(1)
    expect(fixtures.panelMounts.trial).toBe(1)
  })

  it('keeps variable and trial instances mounted across tab switches', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()

    await inspectorTabs(wrapper)[1].trigger('click')
    await inspectorTabs(wrapper)[0].trigger('click')
    await inspectorTabs(wrapper)[1].trigger('click')
    expect(fixtures.panelMounts.variables).toBe(1)

    await inspectorTabs(wrapper)[3].trigger('click')
    await inspectorTabs(wrapper)[0].trigger('click')
    await inspectorTabs(wrapper)[3].trigger('click')
    expect(fixtures.panelMounts.trial).toBe(1)
  })

  it('shows an explicit dependency empty state until a dependent node is selected', async () => {
    const wrapper = mountWorkbench()
    await flushPromises()
    await inspectorTabs(wrapper)[2].trigger('click')

    expect(wrapper.text()).toContain('当前节点不支持依赖配置')
    expect(wrapper.find('[data-testid="dependency-node-editor-stub"]').exists()).toBe(false)

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('nodeClick', { node: { id: 'dep' } })
    await nextTick()
    expect(wrapper.find('[data-testid="dependency-node-editor-stub"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('当前节点不支持依赖配置')
  })
})
