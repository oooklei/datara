/**
 * stream profile：U3 流数据处理 · 流设计器（dagre LR 管道方向）。
 * I11 收敛：装饰性节点（s_kafka/p_window/op_cep 等）自 palette 隐藏（nodeTypes 保留供
 * 历史 mock 文档渲染），画布只暴露可执行组件 C18~C20 + 页面组件（C24 看板）；
 * 混编批处理组件由后端 extract_stream_spec 校验拦截（同口径）。
 */
import { detectCycle, findBrokenEdges, findIsolated } from '../model'
import type { ViewProfile } from './types'
import { dagProfile, streamSubgraphIssues } from './dag'
import { requiredMissing } from './formLinkage'
import StreamMetricsPanel from '../workbench/panels/StreamMetricsPanel.vue'

export const streamProfile: ViewProfile = {
  id: 'stream',
  name: '流设计器',
  mode: 'edit',
  layout: 'dagre',
  layoutDir: 'LR',
  defaultEdge: 'flow',
  nodeTypes: {
    /* 流专属节点（源/算子/输出）… */
    s_kafka: {
      type: 's_kafka', label: 'Kafka 源', icon: '⇉', color: '#0891b2',
      desc: 'Kafka Topic 消费（JSON/Canal/Avro）',
      defaults: { topic: '', format: 'JSON', startup: 'latest-offset', timeSemantics: '事件时间', watermarkDelay: '5 s' },
      form: [
        { key: 'topic', label: 'Topic', type: 'text', placeholder: 'kafka_order_pay' },
        {
          key: 'format', label: '反序列化', type: 'select',
          options: [{ value: 'JSON', label: 'JSON' }, { value: 'CANAL', label: 'Canal-JSON' }, { value: 'AVRO', label: 'Avro' }],
        },
        {
          key: 'startup', label: '启动位点', type: 'select',
          options: [{ value: 'latest-offset', label: 'latest（最新）' }, { value: 'earliest-offset', label: 'earliest（最早）' }, { value: 'group-offsets', label: 'group（按消费组）' }],
        },
        // 时间语义 + Watermark（第6章流处理：事件时间/处理时间/摄入时间与乱序容忍）
        {
          key: 'timeSemantics', label: '时间语义', type: 'select',
          options: [{ value: '事件时间', label: '事件时间' }, { value: '处理时间', label: '处理时间' }, { value: '摄入时间', label: '摄入时间' }],
        },
        { key: 'watermarkDelay', label: 'Watermark 延迟', type: 'text', placeholder: '5 s（乱序容忍）' },
      ],
      summary: (d) => String(d.topic || '未配置 Topic'),
    },
    s_cdc: {
      type: 's_cdc', label: 'CDC 采集', icon: '⎘', color: '#0891b2',
      desc: 'MySQL Binlog 实时捕获',
      defaults: { dbName: '', tableName: '', timeSemantics: '事件时间', watermarkDelay: '5 s' },
      form: [
        { key: 'dbName', label: '库名', type: 'text', placeholder: 'biz_test' },
        { key: 'tableName', label: '表名', type: 'text', placeholder: 'inventory' },
        // 时间语义 + Watermark（与 Kafka 源保持一致）
        {
          key: 'timeSemantics', label: '时间语义', type: 'select',
          options: [{ value: '事件时间', label: '事件时间' }, { value: '处理时间', label: '处理时间' }, { value: '摄入时间', label: '摄入时间' }],
        },
        { key: 'watermarkDelay', label: 'Watermark 延迟', type: 'text', placeholder: '5 s（乱序容忍）' },
      ],
      summary: (d) => `Binlog: ${d.dbName || '?'}.${d.tableName || '?'}`,
    },
    p_window: {
      type: 'p_window', label: '窗口聚合', icon: '⊞', color: '#7c3aed',
      desc: 'TUMBLE / HOP / SESSION 滚动聚合',
      defaults: { windowType: 'TUMBLE', size: '1 MINUTE', pkey: '', agg: 'COUNT(1)' },
      form: [
        {
          key: 'windowType', label: '窗口类型', type: 'select',
          options: [{ value: 'TUMBLE', label: '滚动 TUMBLE' }, { value: 'HOP', label: '滑动 HOP' }, { value: 'SESSION', label: '会话 SESSION' }],
        },
        { key: 'size', label: '窗口大小', type: 'text', placeholder: "INTERVAL '1' MINUTE" },
        { key: 'pkey', label: '分区键（必填）', type: 'text', placeholder: 'device_id' },
        { key: 'agg', label: '聚合表达式', type: 'text', placeholder: 'COUNT(1), AVG(cpu_usage)' },
      ],
      summary: (d) => `${d.windowType}(${d.size}) BY ${d.pkey || '⚠未设分区键'}`,
    },
    p_join: {
      type: 'p_join', label: '维表 Join', icon: '⋈', color: '#7c3aed',
      desc: '关联维表补全字段',
      defaults: { dimTable: '' },
      form: [{ key: 'dimTable', label: '维表', type: 'text', placeholder: 'dim_user' }],
      summary: (d) => `JOIN ${d.dimTable || '?'}`,
    },
    p_filter: {
      type: 'p_filter', label: '过滤', icon: '⑂', color: '#7c3aed',
      desc: '条件过滤 / 脏数据剔除',
      defaults: { condition: '' },
      form: [{ key: 'condition', label: '条件', type: 'text', placeholder: 'pay_amount IS NOT NULL' }],
      summary: (d) => String(d.condition || '未配置条件'),
    },
    /* CEP 复杂事件处理（第6章流处理：在数据流中匹配特定事件序列，如风控规则、异常检测） */
    op_cep: {
      type: 'op_cep', label: 'CEP复杂事件', icon: '◈', color: '#dc2626',
      desc: '模式检测：在数据流中匹配特定事件序列，适用于实时风控、异常检测、漏斗分析',
      defaults: { pattern: '', scene: '实时风控', within: '' },
      form: [
        { key: 'pattern', label: '模式表达式', type: 'textarea', placeholder: 'e1 e2 within(5 min) WHERE e1.card = e2.card' },
        {
          key: 'scene', label: '场景', type: 'select',
          options: [{ value: '实时风控', label: '实时风控' }, { value: '异常检测', label: '异常检测' }, { value: '漏斗分析', label: '漏斗分析' }],
        },
        { key: 'within', label: '时间窗', type: 'text', placeholder: '5 min' },
      ],
      summary: (d) => `${String(d.scene || 'CEP')} · ${String(d.pattern || '未配置模式')}`,
    },
    op_script: {
      type: 'op_script', label: '脚本', icon: '⌘', color: '#7c3aed',
      desc: '引用脚本库脚本或内联代码（SQL/Python/Shell），可与脚本库互通保存',
      defaults: { scriptId: '', lang: 'SQL', code: '' },
      form: [
        {
          key: 'lang', label: '语言', type: 'select',
          options: [{ value: 'SQL', label: 'SQL' }, { value: 'Python', label: 'Python' }, { value: 'Shell', label: 'Shell' }],
        },
        { key: 'scriptId', label: '脚本库脚本', type: 'script' },
        { key: 'code', label: '脚本内容', type: 'textarea', placeholder: '-- 内联脚本；引用库脚本后可载入/回存' },
      ],
      summary: (d) => d.scriptId ? `脚本库:${String(d.scriptId)}` : (d.code ? '内联脚本' : '未配置脚本'),
    },
    o_doris: {
      type: 'o_doris', label: 'Doris 输出', icon: '⛁', color: '#16a34a',
      desc: '写入 Doris 实时表（分桶键必填）',
      defaults: { table: '', pkey: '' },
      form: [
        { key: 'table', label: '目标表', type: 'text', placeholder: 'dwd_order_pay_rt' },
        { key: 'pkey', label: '分桶键（必填）', type: 'text', placeholder: 'pay_id' },
      ],
      summary: (d) => String(d.table || '未配置目标表'),
    },
    o_kafka: {
      type: 'o_kafka', label: 'Kafka 输出', icon: '⇉', color: '#16a34a',
      desc: '写回 Kafka Topic（下游再消费）',
      defaults: { topic: '' },
      form: [{ key: 'topic', label: 'Topic', type: 'text', placeholder: 'topic_inventory_cdc' }],
      summary: (d) => String(d.topic || '未配置 Topic'),
    },
    o_alert: {
      type: 'o_alert', label: '实时告警', icon: '⚠', color: '#c2410c',
      desc: 'CEP 规则命中后推送告警',
      defaults: { channel: '短信+飞书', rule: '' },
      form: [
        { key: 'rule', label: '告警规则', type: 'text', placeholder: '1 分钟失败率 > 5%' },
        { key: 'channel', label: '通知渠道', type: 'select', options: [{ value: '短信+飞书', label: '短信+飞书' }, { value: '邮件', label: '邮件' }, { value: '电话', label: '电话' }] },
      ],
      summary: (d) => String(d.rule || '未配置规则'),
    },

    /* 可视化编排（DAG）组件全量并入流设计器：逻辑关系 / 数据开发 / 数据集成 / 其他组件 */
    ...dagProfile.nodeTypes,
  },
  edgeKinds: {
    flow: { kind: 'flow', label: '数据流', color: '#1668dc' },
    branch: { kind: 'branch', label: '条件分支', color: '#d97706' },
    lag: { kind: 'lag', label: '反压/积压', color: '#e5484d', dashed: true, animated: true },
  },
  palette: [
    /* I11 收敛：只暴露可执行流组件 + 页面组件（旧装饰节点不再可拖入） */
    { name: '流处理', items: [
      { type: 'stream_input' }, { type: 'stream_fuse' }, { type: 'stream_output' }, { type: 'page_board' },
    ] },
  ],
  floats: [
    { id: 'stream-metrics', label: '指标卡', comp: StreamMetricsPanel, w: 400, h: 330 },
  ],
  validators: [
    (doc) => detectCycle(doc).length
      ? [{ level: 'error', msg: '流链路存在环（Flink DAG 不允许成环）' }]
      : [],
    (doc) => findBrokenEdges(doc).map((eid) => ({
      level: 'error' as const, msg: '边引用了不存在的节点（断链）', edgeId: eid,
    })),
    (doc) => findIsolated(doc).map((id) => ({
      level: 'warn' as const,
      msg: `孤立节点「${doc.nodes.find((n) => n.id === id)?.data.name}」未接入流链路`,
      nodeId: id,
    })),
    /* W1 补齐：流子图结构校验（缺源/缺汇/join 双路/游离），与 dag 视角同口径 */
    (doc) => streamSubgraphIssues(doc),
    /* W1 必填完整性：画布角标/校验面板/保存闸门共用 requiredMissing 判定 */
    (doc) => doc.nodes.flatMap((n) => {
      const s = streamProfile.nodeTypes[n.type]
      if (!s) return []
      return requiredMissing(s, n.data).map((lb) => ({
        level: 'warn' as const,
        msg: `「${String(n.data.name ?? n.id)}」必填项未配置：${lb}`,
        nodeId: n.id,
      }))
    }),
  ],
}
