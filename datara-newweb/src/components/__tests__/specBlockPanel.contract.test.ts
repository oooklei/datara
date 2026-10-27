/**
 * SpecBlockPanel（T4/G07 六区块框架层）契约测试：
 * ①输入双源（spec 声明 + T3 params.inputs 具名引用）、②输出、③参数插槽叠加、
 * ④条件/⑤约束只读描述、⑥排除空态；spec 缺失（START/END 等流程节点）空态呈现。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SpecBlockPanel from '../SpecBlockPanel.vue'
import type { ComponentSpecItem } from '../../services/rebuild/componentSpecApi'
import type { WorkflowDraftNode } from '../../services/rebuild/workflowApi'

function specOf(type: string, form: Record<string, unknown[]>): ComponentSpecItem {
  return {
    type,
    publishedVersion: 1,
    componentRef: { type, version: 1 },
    workflowTypes: ['NORMAL'],
    runtimeOnly: false,
    identity: {},
    description: {},
    inputs: [],
    outputs: [],
    form: {
      inputs: [], outputs: [], params: [], conditions: [], constraints: [], exclusions: [], refs: [], exports: [],
      ...form,
    },
    visual: {},
    behaviors: [],
    dropPolicy: null,
    extensions: {},
    specVersion: 1,
    ports: {},
  } as unknown as ComponentSpecItem
}

const ENDPOINT_SPEC = specOf('endpoint_select', {
  inputs: [{ key: 'inputs', label: '输入（上游节点输出）', required: true, uiType: 'resource', cap: { mode: 'upstreamOutputs', max: 2 } }],
  outputs: [
    { key: 'sourceRef', label: '源端表', uiType: 'text', required: true, visible: true },
    { key: 'targetRef', label: '目标端表', uiType: 'text', required: true, visible: true },
  ],
  params: [{ key: 'baseMode', label: '基准类型', uiType: 'select', required: true, visible: true, default: 'src_base' }],
  conditions: [{ id: 'c-src-ds', when: { field: 'baseMode', op: 'ne', value: 'file_sync' }, show: ['srcDs'] }],
  constraints: [{ field: 'srcTable', type: 'requiredIf', value: { field: 'baseMode', op: 'eq', value: 'src_base' }, msg: '源表基准：源表必选' }],
})

const NODE: WorkflowDraftNode = {
  nodeCode: 'n2',
  nodeType: 'endpoint_select',
  name: '端点A',
  params: { component: 'endpoint_select', inputs: { in: 'n1:out', in2: 'n3:out' } },
  positionX: 0,
  positionY: 0,
}

describe('SpecBlockPanel 六区块框架层', () => {
  it('六区块 testid 齐全 + ①输入双源（spec 声明 + T3 具名引用）+ 计数', () => {
    const wrapper = mount(SpecBlockPanel, { props: { node: NODE, spec: ENDPOINT_SPEC } })
    for (const id of ['inputs', 'outputs', 'params', 'conditions', 'constraints', 'exclusions']) {
      expect(wrapper.find(`[data-testid="spec-block-${id}"]`).exists(), id).toBe(true)
    }
    const refs = wrapper.findAll('[data-testid="spec-input-ref"]')
    expect(refs).toHaveLength(2)
    expect(refs[0].text()).toContain('in')
    expect(refs[0].text()).toContain('n1:out')
    expect(refs[1].text()).toContain('in2')
    expect(refs[1].text()).toContain('n3:out')
    // ① 计数 = spec 声明 1 + 具名引用 2
    expect(wrapper.find('[data-testid="spec-block-inputs"]').text()).toContain('3 项')
    // spec 声明行渲染 key + 必填 + uiType
    expect(wrapper.find('[data-testid="spec-block-inputs"]').text()).toContain('inputs')
    expect(wrapper.find('[data-testid="spec-block-inputs"]').text()).toContain('必填')
  })

  it('②输出/④条件/⑤约束只读描述渲染（活体 spec 形状）', () => {
    const wrapper = mount(SpecBlockPanel, { props: { node: NODE, spec: ENDPOINT_SPEC } })
    const outputs = wrapper.find('[data-testid="spec-block-outputs"]').text()
    expect(outputs).toContain('sourceRef')
    expect(outputs).toContain('源端表')
    const conditions = wrapper.find('[data-testid="spec-block-conditions"]').text()
    expect(conditions).toContain('baseMode ≠ file_sync')
    expect(conditions).toContain('srcDs')
    const constraints = wrapper.find('[data-testid="spec-block-constraints"]').text()
    expect(constraints).toContain('srcTable')
    expect(constraints).toContain('源表基准：源表必选')
  })

  it('③参数插槽叠加业务表单（插槽存在时不渲染 spec 声明兜底）', () => {
    const wrapper = mount(SpecBlockPanel, {
      props: { node: NODE, spec: ENDPOINT_SPEC },
      slots: { params: '<div data-testid="biz-form">NODE_CONFIG_PANEL</div>' },
    })
    expect(wrapper.find('[data-testid="spec-block-params"]').text()).toContain('NODE_CONFIG_PANEL')
    expect(wrapper.find('[data-testid="spec-block-params"]').text()).not.toContain('baseMode')
  })

  it('③参数无插槽时回退 spec 声明；⑥排除空态', () => {
    const wrapper = mount(SpecBlockPanel, { props: { node: NODE, spec: ENDPOINT_SPEC } })
    expect(wrapper.find('[data-testid="spec-block-params"]').text()).toContain('baseMode')
    expect(wrapper.find('[data-testid="spec-block-exclusions"]').text()).toContain('spec 未声明排除')
  })

  it('spec 缺失（START/END 流程节点）：六区块空态 + T3 引用仍呈现', () => {
    const wrapper = mount(SpecBlockPanel, { props: { node: NODE, spec: null } })
    expect(wrapper.find('[data-testid="spec-block-inputs"]').text()).toContain('n1:out')
    expect(wrapper.find('[data-testid="spec-block-outputs"]').text()).toContain('spec 未声明输出')
    expect(wrapper.find('[data-testid="spec-block-conditions"]').text()).toContain('spec 未声明条件')
    expect(wrapper.find('[data-testid="spec-block-constraints"]').text()).toContain('spec 未声明约束')
  })

  it('params.inputs 非对象（null/缺失）时引用列表为空 + 输入空态', () => {
    const wrapper = mount(SpecBlockPanel, {
      props: { node: { ...NODE, params: null }, spec: null },
    })
    expect(wrapper.findAll('[data-testid="spec-input-ref"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="spec-block-inputs"]').text()).toContain('未声明输入')
  })
})
