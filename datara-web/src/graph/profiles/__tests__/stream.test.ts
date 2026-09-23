/**
 * I8 i8-1 留痕（设计文档 §1.2 本机验证门 + §3.4）：
 * - C18~C20 分型表单 defaults（四源/五算子/四通道键齐备）与 palette 解禁；
 * - streamSubgraphIssues 流子图校验纯函数（混编/源汇缺失/join 入边/游离）。
 * I11 增量：C24 页面组件（page_board）注册 + 校验放行；stream palette 收敛
 * （只暴露 C18~C20+page_board，旧装饰节点不再可拖入）。
 * 防回归锁点：palette 灰置状态漂移、分型键漂移、校验语义漂移。
 */
import { describe, it, expect } from 'vitest'
import { dagProfile, streamSubgraphIssues } from '../dag'
import { streamProfile } from '../stream'
import { requiredMissing } from '../formLinkage'
import type { GraphDocument, GNode, GEdge } from '../../model'

const nd = (id: string, type: string, data: Record<string, unknown> = {}): GNode =>
  ({ id, type, position: { x: 0, y: 0 }, data: { name: id, ...data } })
const ed = (source: string, target: string): GEdge =>
  ({ id: `e_${source}_${target}`, source, target, kind: 'flow' })

describe('I8 C18~C20 palette 解禁与分型表单', () => {
  it('palette 流处理分组解禁（无 disabled / 无 phase 灰置标记）', () => {
    const grp = dagProfile.palette.find((g) => g.name === '流处理')
    expect(grp?.items?.map((i) => i.type)).toEqual(['stream_input', 'stream_fuse', 'stream_output', 'page_board'])
    grp?.items?.forEach((i) => {
      expect(i.disabled).toBeFalsy()
      expect(i.phase).toBeUndefined()
    })
  })

  it('I11 stream palette 收敛：只暴露 C18~C20+page_board，旧装饰节点不可拖入', () => {
    const exposed = streamProfile.palette.flatMap((g) => g.items?.map((i) => i.type) ?? g.types ?? [])
    expect(exposed).toEqual(['stream_input', 'stream_fuse', 'stream_output', 'page_board'])
    // 装饰节点定义保留（历史 mock 文档渲染），但不在 palette
    expect(streamProfile.nodeTypes.s_kafka).toBeTruthy()
    expect(exposed).not.toContain('s_kafka')
    expect(exposed).not.toContain('p_window')
  })

  it('C18 七源分型键齐备（kafka/cdc/http/file/simulate/redis/mqtt），页面化为运行浮窗', () => {
    const d = dagProfile.nodeTypes.stream_input.defaults ?? {}
    ;['srcType', 'brokers', 'topic', 'group', 'startFrom', 'cdcDs', 'schemasText', 'tablesText',
      'posMode', 'httpUrl', 'intervalSec', 'dataPath', 'cursorParam', 'filePath', 'fileEncoding',
      'simDataset', 'simEvents', 'simEps', 'redisUrl', 'streamsText', 'redisGroup', 'redisConsumer',
      'mqttHost', 'mqttPort', 'mqttTopics'].forEach((k) => {
      expect(d, `缺分型键 ${k}`).toHaveProperty(k)
    })
    expect(d.srcType).toBe('kafka')
    const schema = dagProfile.nodeTypes.stream_input
    expect(schema.page?.comp).toBeTruthy()
    expect(schema.form.some((f) => f.key === 'srcType' && f.type === 'select')).toBe(true)
    // I11 W1：三分型表单字段必须注册（Inspector 按 srcType showIf 显隐）
    ;['simDataset', 'simEps', 'redisUrl', 'streamsText', 'mqttHost', 'mqttTopics'].forEach((k) => {
      expect(schema.form.some((f) => f.key === k), `表单缺字段 ${k}`).toBe(true)
    })
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

  it('I11 C24 page_board 注册：看板模板分型 + 看板浮窗页面化', () => {
    const schema = dagProfile.nodeTypes.page_board
    expect(schema).toBeTruthy()
    expect(schema.defaults?.preset).toBe('ecommerce')
    expect(schema.form.some((f) => f.key === 'preset' && f.type === 'select')).toBe(true)
    expect(schema.page?.comp).toBeTruthy()
    expect(schema.page?.title).toBe('实时看板')
  })

  it('09-21 连接性注册化：dsRef 引用下拉 + 引用模式隐藏内联连接字段（存量内联画布零改动）', () => {
    const schema = dagProfile.nodeTypes.stream_input
    expect(schema.defaults).toHaveProperty('dsRef')
    expect(schema.defaults?.dsRef).toBe('')
    // 四分型各有一个 dsRef 下拉（type=datasource 且按 srcType 显隐、按注册类型过滤）
    const refFields = schema.form.filter((f) => f.key === 'dsRef' && f.type === 'datasource')
    expect(refFields).toHaveLength(4)
    expect(refFields.map((f) => f.dsTypes?.[0]).sort()).toEqual(['http', 'kafka', 'mqtt', 'redis'])
    // 引用模式（dsRef 非空）：内联连接字段隐藏；业务字段（topic/streams/mqtt 订阅）始终显示
    const referenced = { srcType: 'kafka', dsRef: 'kafka-prod' }
    const visible = (f: { key?: string; showIf?: (d: Record<string, unknown>) => boolean }, d: Record<string, unknown>) =>
      !f.showIf || f.showIf(d)
    expect(visible(schema.form.find((f) => f.key === 'brokers')!, referenced)).toBe(false)
    expect(visible(schema.form.find((f) => f.key === 'topic')!, referenced)).toBe(true)
    expect(visible(schema.form.find((f) => f.key === 'brokers')!, { srcType: 'kafka' })).toBe(true) // 内联模式照旧
    const redisRef = { srcType: 'redis', dsRef: 'redis-prod' }
    expect(visible(schema.form.find((f) => f.key === 'redisUrl')!, redisRef)).toBe(false)
    expect(visible(schema.form.find((f) => f.key === 'streamsText')!, redisRef)).toBe(true)
    const mqttRef = { srcType: 'mqtt', dsRef: 'mqtt-prod' }
    expect(visible(schema.form.find((f) => f.key === 'mqttHost')!, mqttRef)).toBe(false)
    expect(visible(schema.form.find((f) => f.key === 'mqttTopics')!, mqttRef)).toBe(true)
    const httpRef = { srcType: 'http', dsRef: 'api-prod' }
    expect(visible(schema.form.find((f) => f.key === 'httpUrl')!, httpRef)).toBe(false)
    expect(visible(schema.form.find((f) => f.key === 'intervalSec')!, httpRef)).toBe(true)
  })

  it('09-21 分型摘要：引用模式显示注册源名，内联模式保持原文案', () => {
    const schema = dagProfile.nodeTypes.stream_input
    const summary = schema.summary as (d: Record<string, unknown>) => string
    expect(summary({ srcType: 'kafka', topic: 'orders', dsRef: 'kafka-prod' })).toContain('kafka-prod')
    expect(summary({ srcType: 'kafka', topic: 'orders', brokers: 'k:9092' })).toContain('k:9092')
    expect(summary({ srcType: 'redis', streamsText: 's1', dsRef: 'redis-prod' })).toContain('redis-prod')
    expect(summary({ srcType: 'mqtt', mqttTopics: 't', dsRef: 'mqtt-prod' })).toContain('mqtt-prod')
    expect(summary({ srcType: 'http', dsRef: 'api-prod' })).toContain('api-prod')
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

  it('I11 page_board 挂接流子图 → 不判混编（展示型节点合法共存）', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '带看板', version: 1, meta: { profile: 'dag' },
      nodes: [
        nd('s1', 'stream_input'), nd('o1', 'stream_output'), nd('b1', 'page_board', { preset: 'ecommerce' }),
      ],
      edges: [ed('s1', 'o1'), ed('o1', 'b1')],
    }
    expect(streamSubgraphIssues(doc)).toEqual([])
  })
})

describe('W1 必填完整性（requiredMissing + validators 集成）', () => {
  const schemaOf = (t: string) => dagProfile.nodeTypes[t]

  it('C18 kafka 缺 topic → 缺失；配齐后为空；showIf 未激活分型不参与', () => {
    expect(requiredMissing(schemaOf('stream_input'), { srcType: 'kafka' })).toEqual(['Topic'])
    expect(requiredMissing(schemaOf('stream_input'), { srcType: 'kafka', topic: 'orders' })).toEqual([])
    // cdc 分型：topic（showIf kafka）不参与，只查 cdcDs
    expect(requiredMissing(schemaOf('stream_input'), { srcType: 'cdc' }))
      .toEqual(['CDC 数据源（引用 I4 注册）'])
  })

  it('C19 分型必填：filter 缺表达式 / join 缺关联键 / window 缺聚合表；union 无必填', () => {
    expect(requiredMissing(schemaOf('stream_fuse'), { fuseType: 'filter' })).toEqual(['过滤条件表达式'])
    expect(requiredMissing(schemaOf('stream_fuse'), { fuseType: 'join' }))
      .toEqual(['左流关联键', '右流关联键'])
    expect(requiredMissing(schemaOf('stream_fuse'), { fuseType: 'window' })).toEqual(['聚合函数表（键=字段，值=函数:别名，如 amount:sum:amt_total）'])
    expect(requiredMissing(schemaOf('stream_fuse'), { fuseType: 'union' })).toEqual([])
  })

  it('C20 分型必填：table 缺数据源与表名 / kafka 缺地址与 Topic / file 缺路径；api 无必填', () => {
    expect(requiredMissing(schemaOf('stream_output'), { outType: 'table' })).toEqual(['目标数据源', '目标表名'])
    expect(requiredMissing(schemaOf('stream_output'), { outType: 'kafka' })).toEqual(['Broker 地址', '目标 Topic'])
    expect(requiredMissing(schemaOf('stream_output'), { outType: 'file' })).toEqual(['输出文件路径（/datara/files 相对）'])
    expect(requiredMissing(schemaOf('stream_output'), { outType: 'api' })).toEqual([])
  })

  it('dagProfile.validators：未配置流节点产出 warn（不阻断保存），不影响合法链路', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '校验', version: 1, meta: { profile: 'dag' },
      nodes: [
        nd('a', 'start'),
        nd('s1', 'stream_input', { srcType: 'kafka' }),
        nd('f1', 'stream_fuse', { fuseType: 'window' }),
        nd('o1', 'stream_output', { outType: 'api' }),
        nd('z', 'end'),
      ],
      edges: [ed('a', 's1'), ed('s1', 'f1'), ed('f1', 'o1'), ed('o1', 'z')],
    }
    const issues = dagProfile.validators.flatMap((v) => v(doc))
    const warns = issues.filter((i) => i.level === 'warn' && i.msg.includes('必填项未配置'))
    expect(warns.some((i) => i.nodeId === 's1' && i.msg.includes('Topic'))).toBe(true)
    expect(warns.some((i) => i.nodeId === 'f1')).toBe(true)
    expect(warns.some((i) => i.nodeId === 'o1')).toBe(false) // api 通道无必填
    expect(issues.some((i) => i.level === 'error')).toBe(false)
  })

  it('streamProfile.validators 补齐流子图校验（缺汇 → error）与必填完整性（warn）', () => {
    const doc: GraphDocument = {
      id: 'wf_x', name: '流设计器校验', version: 1, meta: { profile: 'stream' },
      nodes: [nd('s1', 'stream_input', { srcType: 'kafka' })],
      edges: [],
    }
    const issues = streamProfile.validators.flatMap((v) => v(doc))
    expect(issues.some((i) => i.level === 'error' && i.msg.includes('流输出'))).toBe(true)
    expect(issues.some((i) => i.level === 'warn' && i.msg.includes('Topic'))).toBe(true)
  })
})
