/**
 * 错误聚合模型测试（工作台优化 Task 10，方案 §3.3）
 * 覆盖：collectDocErrors 三类分页签聚合 + 定位锚点；
 * issuesToSources 由 Issue[] 分类映射三类错误源（有 edgeId → edge，Task 8 双 id 场景以 edgeId 优先；
 * 否则 nodeId → node；皆无 → gate/GATE_INVALID；同节点多条 message 聚合）。
 */
import { describe, it, expect } from 'vitest'
import type { Issue } from '../index'
import { collectDocErrors, issuesToSources } from '../docErrors'

describe('collectDocErrors（方案§3.3 三类分页签）', () => {
  it('聚合节点/边/闸门错误并携带定位锚点', () => {
    const doc = { nodes: [{ id: 'n1', type: 'sql', position: { x: 0, y: 0 }, data: {} }], edges: [] } as never
    const errs = collectDocErrors(doc, {
      nodeErrors: { n1: ['参数 sql 不能为空'] },
      edgeErrors: [],
      gateErrors: [{ code: 'CYCLE', message: '存在环: n1' }],
    })
    expect(errs).toHaveLength(2)
    expect(errs[0]).toMatchObject({ kind: 'node', nodeId: 'n1', message: '参数 sql 不能为空' })
    expect(errs[1]).toMatchObject({ kind: 'gate', message: '存在环: n1' })
  })

  it('边错误携带 edgeId 锚点与 EDGE_INVALID 码', () => {
    const errs = collectDocErrors({ nodes: [], edges: [] } as never, {
      nodeErrors: {},
      edgeErrors: [{ edgeId: 'e1', message: '类型不匹配：源 table → 目标 stream' }],
      gateErrors: [],
    })
    expect(errs).toHaveLength(1)
    expect(errs[0]).toMatchObject({ kind: 'edge', edgeId: 'e1', code: 'EDGE_INVALID', message: '类型不匹配：源 table → 目标 stream' })
  })

  it('空文档零错误', () => {
    expect(collectDocErrors({ nodes: [], edges: [] } as never, { nodeErrors: {}, edgeErrors: [], gateErrors: [] })).toHaveLength(0)
  })
})

describe('issuesToSources（Issue[] → 三类错误源）', () => {
  it('有 nodeId 归 node，二者皆无归 gate（GATE_INVALID）', () => {
    const issues: Issue[] = [
      { level: 'error', msg: '「a」未接入上游流（游离节点）', nodeId: 'a' },
      { level: 'error', msg: '缺少「开始」节点' },
    ]
    const src = issuesToSources(issues)
    expect(src.nodeErrors).toEqual({ a: ['「a」未接入上游流（游离节点）'] })
    expect(src.edgeErrors).toEqual([])
    expect(src.gateErrors).toEqual([{ code: 'GATE_INVALID', message: '缺少「开始」节点' }])
  })

  it('Task 8 双 id 场景：edgeTypeIssues 同时带 edgeId+nodeId，以 edgeId 优先归 edge', () => {
    const issues: Issue[] = [
      { level: 'error', msg: '类型不匹配：源 table → 目标 stream（边 a→b）', edgeId: 'e1', nodeId: 'a' },
    ]
    const src = issuesToSources(issues)
    expect(src.edgeErrors).toEqual([{ edgeId: 'e1', message: '类型不匹配：源 table → 目标 stream（边 a→b）' }])
    expect(src.nodeErrors).toEqual({})
    expect(src.gateErrors).toEqual([])
  })

  it('同节点多条 message 聚合为一组（含 warn 级，不做 level 过滤）', () => {
    const issues: Issue[] = [
      { level: 'error', msg: 'm1', nodeId: 'x' },
      { level: 'warn', msg: 'm2', nodeId: 'x' },
    ]
    expect(issuesToSources(issues).nodeErrors).toEqual({ x: ['m1', 'm2'] })
  })

  it('空列表零错误源', () => {
    expect(issuesToSources([])).toEqual({ nodeErrors: {}, edgeErrors: [], gateErrors: [] })
  })
})
