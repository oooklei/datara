/**
 * etl profile：U2 批处理与同步 · ETL 设计器（对齐原型 ETL001 清洗支付明细）。
 * 算子库（输入输出 / 转换算子）拖拽 + 数据流连线；校验：断链/孤立/环；
 * 字段映射浮窗；试运行复用 run 状态机（拓扑序点亮）。
 */
import { detectCycle, findBrokenEdges, findDuplicateEdges, findIsolated } from '../model'
import type { GraphDocument } from '../model'
import type { ViewProfile } from './types'
import { dagProfile } from './dag'

const flowEdge = { kind: 'flow', label: '数据流', color: '#1668dc' }

/** 输入源必须流出、输出必须流入（链路完整） */
const validatorChain = (doc: GraphDocument) => {
  const issues: { level: 'error' | 'warn'; msg: string; nodeId?: string }[] = []
  doc.nodes.forEach((n) => {
    const out = doc.edges.some((e) => e.source === n.id)
    const inc = doc.edges.some((e) => e.target === n.id)
    if (n.type.startsWith('src_') && !out) {
      issues.push({ level: 'error', msg: `输入算子「${n.data.name}」没有输出连线`, nodeId: n.id })
    }
    if (n.type.startsWith('out_') && !inc) {
      issues.push({ level: 'error', msg: `输出算子「${n.data.name}」没有输入连线`, nodeId: n.id })
    }
  })
  return issues
}

export const etlProfile: ViewProfile = {
  id: 'etl',
  name: 'ETL 设计器',
  mode: 'edit',
  layout: 'dagre',
  layoutDir: 'TB',
  defaultEdge: 'flow',
  nodeTypes: {
    src_db: {
      type: 'src_db', label: '数据库输入', icon: '⛁', color: '#0891b2',
      desc: '读取库表（JDBC/ODBC）',
      defaults: { sourceTable: '', where: '' },
      form: [
        { key: 'sourceTable', label: '源表', type: 'text', placeholder: 'ods_gdb_biz_trade_order' },
        { key: 'where', label: '过滤条件', type: 'text', placeholder: 'pay_status IS NOT NULL' },
      ],
      summary: (d) => String(d.sourceTable || '未配置源表'),
    },
    src_file: {
      type: 'src_file', label: '文件输入', icon: '▦', color: '#0891b2',
      desc: '读取 CSV/Excel/JSON 文件',
      defaults: { filePath: '', format: 'CSV' },
      form: [
        { key: 'filePath', label: '文件路径', type: 'text', placeholder: '/data/inlet/orders.csv' },
        { key: 'format', label: '格式', type: 'select', options: [{ value: 'CSV', label: 'CSV' }, { value: 'JSON', label: 'JSON' }, { value: 'Excel', label: 'Excel' }] },
      ],
      summary: (d) => String(d.filePath || '未配置文件'),
    },
    op_filter: {
      type: 'op_filter', label: '过滤', icon: '⑂', color: '#1668dc',
      desc: '按条件过滤行',
      defaults: { condition: '' },
      form: [{ key: 'condition', label: '过滤条件', type: 'text', placeholder: 'amount > 0' }],
      summary: (d) => String(d.condition || '未配置条件'),
    },
    op_join: {
      type: 'op_join', label: 'Join', icon: '⋈', color: '#1668dc',
      desc: '关联另一输入（维表/事实表）',
      defaults: { joinType: 'LEFT JOIN', joinKeys: '', mapping: [] },
      form: [
        {
          key: 'joinType', label: 'Join 类型', type: 'select',
          options: [{ value: 'LEFT JOIN', label: 'LEFT JOIN' }, { value: 'INNER JOIN', label: 'INNER JOIN' }, { value: 'FULL JOIN', label: 'FULL JOIN' }],
        },
        { key: 'joinKeys', label: '关联键', type: 'text', placeholder: 'user_id = user_id' },
      ],
      summary: (d) => `${d.joinType} ON ${d.joinKeys || '?'}`,
    },
    op_expr: {
      type: 'op_expr', label: '表达式', icon: 'ƒ', color: '#1668dc',
      desc: '派生列 / 字段计算',
      defaults: { expr: '' },
      form: [{ key: 'expr', label: '计算表达式', type: 'text', placeholder: 'pay_amount = amount - discount' }],
      summary: (d) => String(d.expr || '未配置表达式'),
    },
    op_agg: {
      type: 'op_agg', label: '聚合', icon: 'Σ', color: '#1668dc',
      desc: '分组聚合（count/sum/avg）',
      defaults: { groupKeys: '', aggs: '' },
      form: [
        { key: 'groupKeys', label: '分组键', type: 'text', placeholder: 'stat_date, channel' },
        { key: 'aggs', label: '聚合表达式', type: 'text', placeholder: 'SUM(pay_amount)' },
      ],
      summary: (d) => `GROUP BY ${d.groupKeys || '?'}`,
    },
    op_dedup: {
      type: 'op_dedup', label: '去重', icon: '①', color: '#1668dc',
      desc: '按主键去重',
      defaults: { dedupKeys: '' },
      form: [{ key: 'dedupKeys', label: '去重键', type: 'text', placeholder: 'pay_id' }],
      summary: (d) => `DISTINCT ${d.dedupKeys || '?'}`,
    },
    /* ---- 常用转换算子补充（第5章：共 12 种，此处补齐后 7 种）---- */
    op_select: {
      type: 'op_select', label: '字段选择', icon: '⊟', color: '#1668dc',
      desc: '按列裁剪行：仅保留或排除指定字段，常用于宽表瘦身',
      defaults: { keepFields: '', dropFields: '' },
      form: [
        { key: 'keepFields', label: '保留字段', type: 'text', placeholder: 'id,name,age' },
        { key: 'dropFields', label: '排除字段', type: 'text', placeholder: 'tmp_col, debug_info' },
      ],
      summary: (d) => String(d.keepFields || (d.dropFields ? `排除 ${d.dropFields}` : '未配置字段')),
    },
    op_sort: {
      type: 'op_sort', label: '排序', icon: '↕', color: '#1668dc',
      desc: '按字段全局排序，多字段可用逗号分隔并带 ASC/DESC 方向',
      defaults: { sortKeys: '' },
      form: [{ key: 'sortKeys', label: '排序字段', type: 'text', placeholder: 'create_time DESC' }],
      summary: (d) => `ORDER BY ${String(d.sortKeys || '?')}`,
    },
    op_split: {
      type: 'op_split', label: '拆分', icon: '⋔', color: '#1668dc',
      desc: '按条件把数据流拆成多路分支，供下游分别处理',
      defaults: { rule: '', outCount: '2' },
      form: [
        { key: 'rule', label: '拆分规则', type: 'textarea', placeholder: 'amount>10000 → 大额；否则 → 小额' },
        {
          key: 'outCount', label: '输出路数', type: 'select',
          options: [{ value: '2', label: '2 路' }, { value: '3', label: '3 路' }, { value: '4', label: '4 路' }],
        },
      ],
      summary: (d) => `${String(d.outCount || '2')} 路 · ${String(d.rule || '未配置规则')}`,
    },
    op_merge: {
      type: 'op_merge', label: '合并', icon: '⊕', color: '#1668dc',
      desc: '将多路输入合并为一路：追加不去重，或按键去重后合并',
      defaults: { mergeMode: '追加 UNION ALL' },
      form: [
        {
          key: 'mergeMode', label: '合并方式', type: 'select',
          options: [{ value: '追加 UNION ALL', label: '追加 UNION ALL' }, { value: '去重合并', label: '去重合并' }],
        },
      ],
      summary: (d) => String(d.mergeMode || '未配置合并方式'),
    },
    op_replace: {
      type: 'op_replace', label: '查找替换', icon: '⇄', color: '#1668dc',
      desc: '按映射表替换字段取值（如编码转文案），多组映射用分号分隔',
      defaults: { mapping: '', targetField: '' },
      form: [
        { key: 'mapping', label: '映射表', type: 'textarea', placeholder: 'M→男；F→女' },
        { key: 'targetField', label: '目标字段', type: 'text', placeholder: 'gender' },
      ],
      summary: (d) => String(d.targetField || '未配置目标字段'),
    },
    op_sample: {
      type: 'op_sample', label: '采样', icon: '⁂', color: '#1668dc',
      desc: '按比例抽取部分数据，用于开发调试与统计分析',
      defaults: { rate: '10%', method: '随机采样' },
      form: [
        { key: 'rate', label: '采样比例', type: 'text', placeholder: '10%' },
        {
          key: 'method', label: '采样方式', type: 'select',
          options: [{ value: '随机采样', label: '随机采样' }, { value: '分层采样', label: '分层采样' }],
        },
      ],
      summary: (d) => `${String(d.method || '随机采样')} ${String(d.rate || '?')}`,
    },
    op_udf: {
      type: 'op_udf', label: 'UDF', icon: 'λ', color: '#1668dc',
      desc: '注册自定义函数对行级字段加工，适合内置算子覆盖不了的业务逻辑',
      defaults: { funcName: '', lang: 'Python', inputFields: '' },
      form: [
        { key: 'funcName', label: '函数名', type: 'text', placeholder: 'udf_risk_score' },
        { key: 'lang', label: '语言', type: 'select', options: [{ value: 'Python', label: 'Python' }, { value: 'Java', label: 'Java' }] },
        { key: 'inputFields', label: '输入字段', type: 'text', placeholder: 'user_id, pay_amount' },
      ],
      summary: (d) => String(d.funcName || '未配置函数'),
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
    out_db: {
      type: 'out_db', label: '数据库输出', icon: '⛁', color: '#16a34a',
      desc: '写入目标表（覆盖/追加分区）',
      defaults: { targetTable: '', writeMode: '覆盖分区', partition: '' },
      form: [
        { key: 'targetTable', label: '目标表', type: 'text', placeholder: 'dwd_order_pay_detail' },
        {
          key: 'writeMode', label: '写入模式', type: 'select',
          options: [{ value: '覆盖分区', label: '覆盖分区' }, { value: '追加', label: '追加' }, { value: '全量覆盖', label: '全量覆盖' }],
        },
        { key: 'partition', label: '分区表达式', type: 'text', placeholder: 'dt=${biz_date}' },
      ],
      summary: (d) => `${d.writeMode} ${d.targetTable || '未配置目标表'}`,
    },
    out_file: {
      type: 'out_file', label: '文件输出', icon: '▦', color: '#16a34a',
      desc: '导出文件（CSV/Excel）',
      defaults: { filePath: '' },
      form: [{ key: 'filePath', label: '导出路径', type: 'text', placeholder: '/data/export/kpi.csv' }],
      summary: (d) => String(d.filePath || '未配置路径'),
    },
    // 可视化编排（DAG）组件全量并入 ETL：SQL/SHELL/Spark/Flink/Python/DQ/DataX 等
    ...dagProfile.nodeTypes,
  },
  edgeKinds: {
    flow: flowEdge,
    branch: { kind: 'branch', label: '条件分支', color: '#d97706' },
  },
  palette: [
    { name: '输入 / 输出', types: ['src_db', 'src_file', 'out_db', 'out_file'] },
    { name: '转换算子', types: ['op_filter', 'op_join', 'op_expr', 'op_agg', 'op_dedup', 'op_select', 'op_sort', 'op_split', 'op_merge', 'op_replace', 'op_sample', 'op_udf'] },
    { name: '脚本', types: ['op_script'] },
    // 可视化编排组件分组原样可用：逻辑关系 / 数据开发 / 数据集成 / 其他组件
    ...dagProfile.palette,
  ],
  // I1 意见③：EtlMappingPanel 字段映射浮窗删除；算子映射由数据同步（C17，I6）承接
  floats: [],
  validators: [
    (doc) => detectCycle(doc).length
      ? [{ level: 'error', msg: '数据流存在环（ETL 管道不允许成环）' }]
      : [],
    validatorChain,
    (doc) => findBrokenEdges(doc).map((eid) => ({
      level: 'error' as const, msg: '边引用了不存在的节点（断链）', edgeId: eid,
    })),
    (doc) => findIsolated(doc).map((id) => ({
      level: 'warn' as const,
      msg: `孤立算子「${doc.nodes.find((n) => n.id === id)?.data.name}」未接入数据流`,
      nodeId: id,
    })),
    (doc) => findDuplicateEdges(doc).map((eid) => ({
      level: 'warn' as const, msg: '存在重复数据流边', edgeId: eid,
    })),
  ],
}
