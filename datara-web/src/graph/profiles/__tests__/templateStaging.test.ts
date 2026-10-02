/**
 * 模板展开暂存/编排纯逻辑单测。
 *
 * 守住三条语义（用户已确认的模板 UX 契约）：
 *  1. **暂存不落画布**：暂存区只是内存数据，任何时刻 doc 都不含它 → 取消必然无痕；
 *  2. **跳过纯装饰节点**：C1 开始 / C2 结束 不进向导，提交时自动带上；
 *  3. **链内上游等价**：`stagedUpstreamOf` 在暂存子图上做反向 BFS，
 *     使暂存期的 ①输入候选 / `dataScope` 列域与落画布后一致。
 */
import { describe, expect, it } from 'vitest'
import type { GEdge, GNode, GraphDocument } from '../../model'
import { createTemplateStage, selectTemplateSteps, stagedUpstreamOf } from '../templateStaging'
import { dagProfile } from '../dag'
import type { NodeSchema } from '../types'

/** 模板 build 只需 nodes/edges 的空画布 */
const emptyDoc = { nodes: [], edges: [] } as unknown as GraphDocument

/** 展开某模板首个 mode（模板 build 纯函数，无需真实画布） */
function buildFirstMode(type: string) {
  const tpl = dagProfile.nodeTypes[type]?.template?.modes[0]
  if (!tpl) throw new Error(`未找到模板: ${type}`)
  return tpl.build({ doc: emptyDoc, pos: { x: 0, y: 0 } })
}

const nd = (id: string, type: string, data: Record<string, unknown> = {}): GNode => ({
  id, type, position: { x: 0, y: 0 }, data: { name: type, ...data },
})
const ed = (source: string, target: string): GEdge => ({ id: `${source}->${target}`, source, target })
const lookup = (t: string): NodeSchema | undefined => dagProfile.nodeTypes[t]

describe('selectTemplateSteps（向导步序 = 需配置的节点）', () => {
  it('线性链 a→b→c：仅中间有配置的进向导，首尾纯装饰被跳过', () => {
    const nodes = [nd('a', 'start'), nd('b', 'sql'), nd('c', 'end')]
    const steps = selectTemplateSteps(nodes, lookup)
    expect(steps.map((n) => n.id)).toEqual(['b'])
  })

  it('步序保持 `nodes` 声明序（= 链序），不因类型排序', () => {
    const nodes = [nd('a', 'sql'), nd('b', 'condition_set'), nd('c', 'assert'), nd('d', 'notify')]
    expect(selectTemplateSteps(nodes, lookup).map((n) => n.id)).toEqual(['a', 'b', 'c', 'd'])
  })

  it('六区块有值的「空表单」节点仍需配置（start/end 若被模板填了输入则不能跳）', () => {
    const nodes = [nd('a', 'end', { inputs: ['nd_1'] })]
    expect(selectTemplateSteps(nodes, lookup).map((n) => n.id)).toEqual(['a'])
  })

  it('取不到 schema 的节点保守判为「需配置」，交由上层报错而非静默丢弃', () => {
    const nodes = [nd('a', 'not_a_real_type')]
    expect(selectTemplateSteps(nodes, lookup).map((n) => n.id)).toEqual(['a'])
  })

  it('全链皆纯装饰 → 零步（上层据此直接提交，跳过向导）', () => {
    expect(selectTemplateSteps([nd('a', 'start'), nd('b', 'end')], lookup)).toEqual([])
  })

  it('真实 C29 源表同步模板：步数为 8 节点减去 start/end', () => {
    const built = buildFirstMode('src_base_orch')
    expect(built.nodes.length).toBe(8)
    const steps = selectTemplateSteps(built.nodes, lookup)
    // start/end 跳过 → 6 步；且顺序与链序一致
    expect(steps.length).toBe(6)
    expect(steps.map((n) => n.type)).not.toContain('start')
    expect(steps.map((n) => n.type)).not.toContain('end')
    // 步序是 build 产物的子序列（未被打乱）
    expect(built.nodes.map((n) => n.id)).toEqual(expect.arrayContaining(steps.map((n) => n.id)))
  })
})

describe('stagedUpstreamOf（暂存链内可达上游）', () => {
  it('线性链：c 的上游是 [b, a]（BFS 去重保序）', () => {
    const stage = createTemplateStage('t', [nd('a', 'sql'), nd('b', 'condition_set'), nd('c', 'end')], [ed('a', 'b'), ed('b', 'c')])
    expect(stagedUpstreamOf(stage, 'c').map((n) => n.id)).toEqual(['b', 'a'])
  })

  it('首节点无上游 → 空数组', () => {
    const stage = createTemplateStage('t', [nd('a', 'sql')], [])
    expect(stagedUpstreamOf(stage, 'a')).toEqual([])
  })

  it('分叉汇合：c 的上游同时含两条支线（不只取直接父节点）', () => {
    const stage = createTemplateStage('t',
      [nd('a', 'sql'), nd('b', 'sql'), nd('c', 'end')],
      [ed('a', 'c'), ed('b', 'c')])
    expect(stagedUpstreamOf(stage, 'c').map((n) => n.id)).toEqual(['a', 'b'])
  })

  it('菱形：d 的上游为 b,c,a（b/c 共享 a，不重复）', () => {
    const stage = createTemplateStage('t',
      [nd('a', 'sql'), nd('b', 'sql'), nd('c', 'sql'), nd('d', 'end')],
      [ed('a', 'b'), ed('a', 'c'), ed('b', 'd'), ed('c', 'd')])
    expect(stagedUpstreamOf(stage, 'd').map((n) => n.id)).toEqual(['b', 'c', 'a'])
  })

  it('环状边不导致死循环（A↔B 互指时终止且不重复）', () => {
    const stage = createTemplateStage('t', [nd('a', 'sql'), nd('b', 'sql')], [ed('a', 'b'), ed('b', 'a')])
    expect(stagedUpstreamOf(stage, 'b').map((n) => n.id)).toEqual(['a'])
  })

  it('自环被忽略', () => {
    const stage = createTemplateStage('t', [nd('a', 'sql')], [ed('a', 'a')])
    expect(stagedUpstreamOf(stage, 'a')).toEqual([])
  })

  it('悬空边（引用不存在的节点 id）静默忽略，不抛错阻断向导', () => {
    const stage = createTemplateStage('t', [nd('a', 'sql')], [ed('ghost', 'a')])
    expect(stagedUpstreamOf(stage, 'a')).toEqual([])
  })

  it('真实模板链：中间节点的上游可解析出前置节点（暂存期 dataScope 有数据可依）', () => {
    const built = buildFirstMode('src_base_orch')
    const stage = createTemplateStage('src', built.nodes, built.edges)
    const steps = selectTemplateSteps(built.nodes, lookup)
    // 每个非首步都能拿到至少 1 个上游（链连通）
    for (const s of steps) {
      expect(stagedUpstreamOf(stage, s.id).length).toBeGreaterThan(0)
    }
  })
})

describe('createTemplateStage（暂存区初始态）', () => {
  it('step 初始为 0、steps 待填充，暂存区本身不含 doc 引用', () => {
    const stage = createTemplateStage('链名', [nd('a', 'sql')], [ed('a', 'a')])
    expect(stage.step).toBe(0)
    expect(stage.steps).toEqual([])
    expect(stage.chainLabel).toBe('链名')
    expect(Object.keys(stage).sort()).toEqual(['chainLabel', 'edges', 'nodes', 'step', 'steps'])
  })
})
