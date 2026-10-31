/**
 * W1 画布校验器（T4/G07）契约测试：11 validators 逐项覆盖。
 * 口径来源：画布保存闸门语义（START/END 兼备、组件图连通、成环、断链）
 * + 旧前端 dag.ts validators（重复边 warn、必填 warn、end 禁出边、流子图）。
 */
import { describe, expect, it } from 'vitest'
import type { ComponentSpecItem } from '../../services/rebuild/componentSpecApi'
import {
  detectCycle,
  validateWorkflowDraft,
} from '../workflowGraphValidators'

const DESIGN_TYPES = new Set([
  'sql', 'python', 'shell', 'dependent',
  'src_base_orch', 'tgt_base_orch', 'file_sync_orch', 'endpoint_select', 'field_map', 'field_map_union', 'condition_set',
  'stream_input', 'stream_fuse', 'stream_output', 'page_board',
])

function node(code: string, nodeType: string, params?: Record<string, unknown>) {
  return { nodeCode: code, nodeType, name: null, params: params ?? null }
}
function edge(from: string, to: string) {
  return { fromNode: from, toNode: to }
}

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

const LEGACY_PIPELINE = [node('n1', 'START'), node('n2', 'sql', { component: 'sql', sql: 'SELECT 1' }), node('n3', 'END')]
const LEGACY_EDGES = [edge('n1', 'n2'), edge('n2', 'n3')]

describe('workflowGraphValidators 11 validators', () => {
  it('1 成环：n1→n2→n3→n1 报 CYCLE error 且含环路径', () => {
    const issues = detectCycle(
      [node('n1', 'sql', { sql: '1' }), node('n2', 'sql', { sql: '2' }), node('n3', 'sql', { sql: '3' })],
      [edge('n1', 'n2'), edge('n2', 'n3'), edge('n3', 'n1')],
    )
    expect(issues).toHaveLength(1)
    expect(issues[0].level).toBe('error')
    expect(issues[0].code).toBe('CYCLE')
    expect(issues[0].msg).toContain('环')
    expect(issues[0].nodeCode).toBe('n1')
  })

  it('2 断链：边端点不存在报 BROKEN_EDGE error', () => {
    const issues = validateWorkflowDraft(
      [node('n1', 'START'), node('n3', 'END')],
      [edge('n1', 'n3'), edge('n1', 'ghost')],
    )
    const broken = issues.filter((i) => i.code === 'BROKEN_EDGE')
    expect(broken).toHaveLength(1)
    expect(broken[0].level).toBe('error')
    expect(broken[0].msg).toContain('ghost')
  })

  it('3 START/END：legacy 缺 END 报错；START 重复报错；组件图全无则合法', () => {
    const missingEnd = validateWorkflowDraft([node('n1', 'START'), node('n2', 'sql', { sql: '1' })], [edge('n1', 'n2')])
    expect(missingEnd.filter((i) => i.code === 'START_END' && i.msg.includes('END'))).toHaveLength(1)

    const dupStart = validateWorkflowDraft(
      [node('n1', 'START'), node('n1b', 'START'), node('n3', 'END')],
      [edge('n1', 'n3'), edge('n1b', 'n3')],
    )
    expect(dupStart.filter((i) => i.code === 'START_END' && i.msg.includes('只能有一个'))).toHaveLength(1)

    const componentGraph = validateWorkflowDraft(
      [node('s1', 'src_base_orch', { component: 'src_base_orch', srcDs: 'd' }), node('t1', 'tgt_base_orch', { component: 'tgt_base_orch', tgtDs: 'd' })],
      [edge('s1', 't1')],
    )
    expect(componentGraph.filter((i) => i.code === 'START_END')).toHaveLength(0)
  })

  it('4 孤立/连通：legacy 非 START 无入边报错；组件图不可达节点报错', () => {
    const legacyOrphan = validateWorkflowDraft(
      [node('n1', 'START'), node('n2', 'sql', { sql: '1' }), node('n3', 'END')],
      [edge('n1', 'n2')],
    )
    const orphan = legacyOrphan.filter((i) => i.code === 'ORPHAN' && i.nodeCode === 'n3')
    expect(orphan.length).toBeGreaterThanOrEqual(1)
    expect(orphan.every((i) => i.level === 'error')).toBe(true)

    const disconnected = validateWorkflowDraft(
      [node('a', 'src_base_orch', { component: 'src_base_orch', srcDs: 'd' }), node('b', 'tgt_base_orch', { component: 'tgt_base_orch', tgtDs: 'd' }), node('c', 'tgt_base_orch', { component: 'tgt_base_orch', tgtDs: 'd' })],
      [edge('a', 'b')],
    )
    // 组件图：全无连接的孤立节点按旧前端语义报 warn（后端视为 root 放行）
    const isolated = disconnected.filter((i) => i.code === 'ORPHAN' && i.nodeCode === 'c')
    expect(isolated).toHaveLength(1)
    expect(isolated[0].level).toBe('warn')
  })

  it('5 重复边：同 from→to 第二条报 DUPLICATE_EDGE warn', () => {
    const issues = validateWorkflowDraft(
      [node('n1', 'START'), node('n2', 'sql', { sql: '1' }), node('n3', 'END')],
      [edge('n1', 'n2'), edge('n1', 'n2'), edge('n2', 'n3')],
    )
    expect(issues.filter((i) => i.code === 'DUPLICATE_EDGE')).toHaveLength(1)
    expect(issues.find((i) => i.code === 'DUPLICATE_EDGE')?.level).toBe('warn')
  })

  it('6 流子图：混编/缺源汇/join 单路各自报 STREAM_SUBGRAPH error', () => {
    const mixing = validateWorkflowDraft(
      [node('in1', 'stream_input', { component: 'stream_input', topic: 't' }), node('s1', 'sql', { component: 'sql', sql: 'x' }), node('out1', 'stream_output', { component: 'stream_output' })],
      [edge('in1', 'out1')],
    )
    expect(mixing.some((i) => i.code === 'STREAM_SUBGRAPH' && i.msg.includes('混编'))).toBe(true)

    const missingSourceSink = validateWorkflowDraft(
      [node('f1', 'stream_fuse', { component: 'stream_fuse', fuseType: 'union' })],
      [],
    )
    // 缺流输入 + 缺流输出 + 游离（无入边）+ 未连下游（无出边）
    expect(missingSourceSink.filter((i) => i.code === 'STREAM_SUBGRAPH')).toHaveLength(4)

    const joinSingle = validateWorkflowDraft(
      [
        node('in1', 'stream_input', { component: 'stream_input', topic: 't' }),
        node('f1', 'stream_fuse', { component: 'stream_fuse', fuseType: 'join' }),
        node('out1', 'stream_output', { component: 'stream_output' }),
      ],
      [edge('in1', 'f1'), edge('f1', 'out1')],
    )
    expect(joinSingle.some((i) => i.code === 'STREAM_SUBGRAPH' && i.msg.includes('两路流'))).toBe(true)
  })

  it('7 必填缺失：设计态节点无业务参数报 REQUIRED_MISSING warn（不阻断）', () => {
    const issues = validateWorkflowDraft(LEGACY_PIPELINE, LEGACY_EDGES, { designTypes: DESIGN_TYPES })
    const missing = issues.filter((i) => i.code === 'REQUIRED_MISSING')
    expect(missing).toHaveLength(0)

    const dirty = validateWorkflowDraft(
      [node('n1', 'START'), node('n2', 'sql'), node('n3', 'END')],
      LEGACY_EDGES,
      { designTypes: DESIGN_TYPES },
    )
    const missingDirty = dirty.filter((i) => i.code === 'REQUIRED_MISSING')
    expect(missingDirty).toHaveLength(1)
    expect(missingDirty[0].level).toBe('warn')
    expect(missingDirty[0].nodeCode).toBe('n2')
  })

  it('8 END 禁出边：END 连出边报 END_OUTGOING error', () => {
    const issues = validateWorkflowDraft(
      [node('n1', 'START'), node('n2', 'sql', { sql: '1' }), node('n3', 'END'), node('n4', 'sql', { sql: '2' })],
      [edge('n1', 'n2'), edge('n2', 'n3'), edge('n3', 'n4'), edge('n4', 'n3')],
    )
    expect(issues.some((i) => i.code === 'END_OUTGOING' && i.nodeCode === 'n3')).toBe(true)
  })

  it('9 组件级约束：spec constraints.requiredIf 命中且字段为空报 CONSTRAINT error', () => {
    const specs = new Map([['endpoint_select', specOf('endpoint_select', {
      constraints: [{ field: 'tgtTable', type: 'requiredIf', value: { field: 'baseMode', op: 'eq', value: 'tgt_base' }, msg: '目标表基准：目标表必选' }],
    })]])

    const violated = validateWorkflowDraft(
      [node('n2', 'endpoint_select', { component: 'endpoint_select', baseMode: 'tgt_base' })],
      [],
      { specs, designTypes: DESIGN_TYPES },
    )
    const constraint = violated.filter((i) => i.code === 'CONSTRAINT')
    expect(constraint).toHaveLength(1)
    expect(constraint[0].msg).toContain('目标表必选')

    const satisfied = validateWorkflowDraft(
      [node('n2', 'endpoint_select', { component: 'endpoint_select', baseMode: 'src_base', srcTable: 'a.b' })],
      [],
      { specs, designTypes: DESIGN_TYPES },
    )
    expect(satisfied.filter((i) => i.code === 'CONSTRAINT')).toHaveLength(0)
  })

  it('10 分支完整性：condition_set 无出边报 BRANCH warn', () => {
    const issues = validateWorkflowDraft(
      [node('c1', 'condition_set', { component: 'condition_set', filterExpr: 'a=1' })],
      [],
      { designTypes: DESIGN_TYPES },
    )
    expect(issues.some((i) => i.code === 'BRANCH' && i.level === 'warn' && i.nodeCode === 'c1')).toBe(true)
  })

  it('11 依赖合法性：spec inputs cap.upstreamOutputs required 缺上游报错、超 max 报错', () => {
    const specs = new Map([['field_map', specOf('field_map', {
      inputs: [{ key: 'inputs', label: '输入（上游节点输出）', required: true, cap: { mode: 'upstreamOutputs', max: 2 } }],
    })]])
    const nodes = [node('f', 'field_map', { component: 'field_map' }), node('u1', 'src_base_orch', { component: 'src_base_orch', srcDs: 'd' }), node('u2', 'src_base_orch', { component: 'src_base_orch', srcDs: 'd' }), node('u3', 'src_base_orch', { component: 'src_base_orch', srcDs: 'd' })]

    const missing = validateWorkflowDraft(nodes, [], { specs, designTypes: DESIGN_TYPES })
    expect(missing.some((i) => i.code === 'UPSTREAM_DEP' && i.msg.includes('缺少上游输入'))).toBe(true)

    const overMax = validateWorkflowDraft(
      nodes,
      [edge('u1', 'f'), edge('u2', 'f'), edge('u3', 'f')],
      { specs, designTypes: DESIGN_TYPES },
    )
    expect(overMax.some((i) => i.code === 'UPSTREAM_DEP' && i.msg.includes('上限 2'))).toBe(true)

    const satisfied = validateWorkflowDraft(
      nodes,
      [edge('u1', 'f'), edge('u2', 'f')],
      { specs, designTypes: DESIGN_TYPES },
    )
    expect(satisfied.filter((i) => i.code === 'UPSTREAM_DEP')).toHaveLength(0)
  })

  it('汇总：合法管道零 issue；specs 缺失时 spec 驱动项优雅跳过', () => {
    expect(validateWorkflowDraft(LEGACY_PIPELINE, LEGACY_EDGES, { designTypes: DESIGN_TYPES })).toHaveLength(0)

    const withoutSpecs = validateWorkflowDraft([node('f', 'field_map')], [], { designTypes: DESIGN_TYPES })
    expect(withoutSpecs.filter((i) => i.code === 'UPSTREAM_DEP')).toHaveLength(0)
    expect(withoutSpecs.filter((i) => i.code === 'CONSTRAINT')).toHaveLength(0)
  })
})
