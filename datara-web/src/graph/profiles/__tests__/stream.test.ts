/**
 * I8 i8-1 留痕（设计文档 §1.2 本机验证门 + §3.4）：
 * - C18~C20 分型表单 defaults（四源/五算子/四通道键齐备）与 palette 解禁；
 * - streamSubgraphIssues 流子图校验纯函数（混编/源汇缺失/join 入边/游离）。
 * 防回归锁点：palette 灰置状态漂移、分型键漂移、校验语义漂移。
 */
import { describe, it, expect } from 'vitest'
import { dagProfile, streamSubgraphIssues } from '../dag'
import type { GraphDocument, GNode, GEdge } from '../../model'

const nd = (id: string, type: string, data: Record<string, unknown> = {}): GNode =>
  ({ id, type, position: { x: 0, y: 0 }, data: { name: id, ...data } })
const ed = (source: string, target: string): GEdge =>
  ({ id: `e_${source}_${target}`, source, target, kind: 'flow' })

describe('I8 C18~C20 palette 解禁与分型表单', () => {
  it('palette 流处理分组解禁（无 disabled / 无 phase 灰置标记）', () => {
    const grp = dagProfile.palette.find((g) => g.name === '流处理')
    expect(grp?.items?.map((i) => i.type)).toEqual(['stream_input', 'stream_fuse', 'stream_output'])
    grp?.items?.forEach((i) => {
      expect(i.disabled).toBeFalsy()
      expect(i.phase).toBeUndefined()
    })
  })

  it('C18 四源分型键齐备（kafka/cdc/http/file），页面化为运行浮窗', () => {
    const d = dagProfile.nodeTypes.stream_input.defaults ?? {}
    ;['srcType', 'brokers', 'topic', 'group', 'startFrom', 'cdcDs', 'schemasText', 'tablesText',
      'posMode', 'httpUrl', 'intervalSec', 'dataPath', 'cursorParam', 'filePath', 'fileEncoding'].forEach((k) => {
      expect(d, `缺分型键 ${k}`).toHaveProperty(k)
    })
    expect(d.srcType).toBe('kafka')
    const schema = dagProfile.nodeTypes.stream_input
    expect(schema.page?.comp).toBeTruthy()
    expect(schema.form.some((f) => f.key === 'srcType' && f.type === 'select')).toBe(true)
  })

  it('C19 五算子分型键齐备（union/join/window/filter/map），join 默认窗口 60s', () => {
    const d = dagProfile.nodeTypes.stream_fuse.defaults ?? {}
    ;['fuseType', 'alignMap', 'joinKeyLeft', 'joinKeyRight', 'joinWindowSec', 'joinType',
      'filterExpr', 'fieldMap', 'groupKeys', 'aggs', 'windowType', 'windowSizeSec', 'slideSec', 'watermarkSec'].forEach((k) => {
      expect(d, `缺分型键 ${k}`).toHaveProperty(k)
    })
    expect(d.fuseType).toBe('union')
    expect(d.joinWindowSec).toBe(60)
    expect(d.windowType).toBe('tumbling')
  })

  it('C20 四通道分型键齐备（api/table/kafka/file），API 为默认通道', () => {
    const d = dagProfile.nodeTypes.stream_output.defaults ?? {}
    ;['outType', 'keepLast', 'schemaText', 'outDs', 'outTable', 'outFieldMap', 'uniqueKey',
      'kafkaBrokers', 'kafkaTopic', 'outPath', 'rollBy'].forEach((k) => {
      expect(d, `缺分型键 ${k}`).toHaveProperty(k)
    })
    expect(d.outType).toBe('api')
    expect(d.keepLast).toBe(100)
    expect(dagProfile.nodeTypes.stream_output.page?.title).toBe('实时数据展示')
  })
})

describe('I8 streamSubgraphIssues 流子图校验', () => {
  it('无流组件画布不产出问题（批处理画布零打扰）', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '批', version: 1, meta: { profile: 'dag' },
      nodes: [nd('a', 'start'), nd('b', 'sql'), nd('c', 'end')], edges: [ed('a', 'b'), ed('b', 'c')],
    }
    expect(streamSubgraphIssues(doc)).toEqual([])
  })

  it('缺流输出/缺流输入 → error', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '流', version: 1, meta: { profile: 'dag' },
      nodes: [nd('s1', 'stream_input'), nd('f1', 'stream_fuse')], edges: [ed('s1', 'f1')],
    }
    const msgs = streamSubgraphIssues(doc).map((i) => i.msg)
    expect(msgs.some((m) => m.includes('流输出'))).toBe(true)
    const doc2: GraphDocument = {
      id: 'wf_x', name: '流', version: 1, meta: { profile: 'dag' },
      nodes: [nd('o1', 'stream_output')], edges: [],
    }
    const msgs2 = streamSubgraphIssues(doc2).map((i) => i.msg)
    expect(msgs2.some((m) => m.includes('流输入'))).toBe(true)
  })

  it('流组件与批处理组件混编 → error', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '混', version: 1, meta: { profile: 'dag' },
      nodes: [nd('s1', 'stream_input'), nd('o1', 'stream_output'), nd('b1', 'sql'), nd('a', 'start'), nd('z', 'end')],
      edges: [ed('s1', 'o1'), ed('a', 'z')],
    }
    const issues = streamSubgraphIssues(doc)
    expect(issues.some((i) => i.level === 'error' && i.msg.includes('不可混编'))).toBe(true)
  })

  it('join 融合单入边 → error；双入边通过', () => {
    const base: GraphDocument = {
      id: 'wf_x', name: 'join', version: 1, meta: { profile: 'dag' },
      nodes: [
        nd('s1', 'stream_input'), nd('s2', 'stream_input', { srcType: 'cdc' }),
        nd('j1', 'stream_fuse', { fuseType: 'join', joinKeyLeft: 'id', joinKeyRight: 'oid' }),
        nd('o1', 'stream_output'),
      ],
      edges: [],
    }
    const one = { ...base, edges: [ed('s1', 'j1'), ed('j1', 'o1')] }
    expect(streamSubgraphIssues(one).some((i) => i.msg.includes('两路流'))).toBe(true)
    const two = { ...base, edges: [ed('s1', 'j1'), ed('s2', 'j1'), ed('j1', 'o1')] }
    expect(streamSubgraphIssues(two)).toEqual([])
  })

  it('游离融合节点（无上游/无下游）→ error', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '游离', version: 1, meta: { profile: 'dag' },
      nodes: [
        nd('s1', 'stream_input'), nd('o1', 'stream_output'), nd('f1', 'stream_fuse'),
      ],
      edges: [ed('s1', 'o1')],
    }
    const msgs = streamSubgraphIssues(doc).map((i) => i.msg)
    expect(msgs.some((m) => m.includes('f1') && m.includes('上游'))).toBe(true)
    expect(msgs.some((m) => m.includes('f1') && m.includes('下游'))).toBe(true)
  })

  it('合法最小流子图（源→融合→汇）零问题', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '合法', version: 1, meta: { profile: 'dag' },
      nodes: [
        nd('s1', 'stream_input'), nd('f1', 'stream_fuse', { fuseType: 'window' }), nd('o1', 'stream_output'),
      ],
      edges: [ed('s1', 'f1'), ed('f1', 'o1')],
    }
    expect(streamSubgraphIssues(doc)).toEqual([])
  })
})
