/**
 * mock 种子数据：迁移原型 DB 的 Phase 1 相关子集。
 * DAG 工作流对齐 DolphinScheduler 任务语义；拓扑为五层泳道组件。
 */
import type { GraphDocument } from '../../graph/model'
import { dagreLayout } from '../../graph/layout/dagre'
import { forceLayout } from '../../graph/layout/force'
import { erGridLayout } from '../../graph/layout/er'
import { localTime } from './timeUtil'

export interface WorkflowMeta {
  id: string
  name: string
  cron: string
  owner: string
  status: 'online' | 'offline'
  version: number
  updatedAt: string
  nodes: number
}

export const seedWorkflows: WorkflowMeta[] = [
  { id: 'wf_order_daily', name: '订单主题日增', cron: '0 40 2 * * ?', owner: '王工', status: 'online', version: 3, updatedAt: '2026-09-12 07:32', nodes: 8 },
  { id: 'wf_pay_sync', name: '支付记录同步', cron: '0 0 1 * * ?', owner: '李工', status: 'online', version: 2, updatedAt: '2026-09-11 22:10', nodes: 5 },
  { id: 'wf_user_profile', name: '用户画像宽表加工', cron: '0 30 3 * * ?', owner: '张工', status: 'offline', version: 5, updatedAt: '2026-09-10 18:44', nodes: 6 },
]

/** 示例工作流「订单主题日增」：START → 抽取 → 清洗 → 分支(汇总/明细) → 依赖 → 质检 → END */
function orderDailyDoc(): GraphDocument {
  const n = (id: string, type: string, x: number, y: number, name: string, data: Record<string, unknown> = {}) =>
    ({ id, type, position: { x, y }, data: { name, ...data } })
  return {
    id: 'wf_order_daily',
    name: '订单主题日增',
    version: 3,
    meta: { profile: 'dag', updatedAt: '2026-09-12 07:32', type: 'batch' },
    nodes: [
      n('nd_start', 'start', 0, 170, '启动'),
      n('nd_extract', 'sql', 195, 170, 'ODS订单抽取', { datasource: 'greatdb_biz', sql: "INSERT OVERWRITE TABLE ods_gdb_biz_trade_order PARTITION(dt='${system.biz.curdate}') SELECT * FROM src_trade_order WHERE dt='${system.biz.curdate}'", pre: '', post: '' }),
      n('nd_clean', 'shell', 390, 170, '清洗与标准化', { script: 'sh /data/jobs/order_clean.sh ${system.biz.curdate}' }),
      n('nd_dws', 'spark', 585, 55, '支付汇总加工', { main: 'com.datara.dws.PaySummaryDaily', driver: '2G', executor: '4G' }),
      n('nd_dwd', 'flink', 585, 285, '明细实时写入', { parallelism: 4, checkpoint: 60000 }),
      n('nd_depend', 'dependent', 780, 170, '依赖上游分区', { deps: 'dwd_order_pay_detail(dt=${system.biz.predate})' }),
      n('nd_dq', 'dq', 975, 170, '产出质检', { ruleSet: 'QC-R-012,QC-R-031', failPolicy: '阻断' }),
      n('nd_end', 'end', 1170, 170, '结束'),
    ],
    edges: [
      { id: 'e1', source: 'nd_start', target: 'nd_extract', kind: 'flow' },
      { id: 'e2', source: 'nd_extract', target: 'nd_clean', kind: 'flow' },
      { id: 'e3', source: 'nd_clean', target: 'nd_dws', kind: 'flow' },
      { id: 'e4', source: 'nd_clean', target: 'nd_dwd', kind: 'flow' },
      { id: 'e5', source: 'nd_dws', target: 'nd_depend', kind: 'flow' },
      { id: 'e6', source: 'nd_dwd', target: 'nd_depend', kind: 'flow' },
      { id: 'e7', source: 'nd_depend', target: 'nd_dq', kind: 'flow' },
      { id: 'e8', source: 'nd_dq', target: 'nd_end', kind: 'flow' },
    ],
  }
}

/** 简化工作流「支付记录同步」 */
function paySyncDoc(): GraphDocument {
  return {
    id: 'wf_pay_sync',
    name: '支付记录同步',
    version: 2,
    meta: { profile: 'dag', updatedAt: '2026-09-11 22:10', type: 'sync' },
    nodes: [
      { id: 'ps_start', type: 'start', position: { x: 0, y: 160 }, data: { name: '启动' } },
      { id: 'ps_datax', type: 'datax', position: { x: 220, y: 160 }, data: { name: '支付流水同步', datasource: 'mysql_fin', targetTable: 'ods_gdb_biz_pay_record' } },
      { id: 'ps_sql', type: 'sql', position: { x: 440, y: 160 }, data: { name: '一致性核对', datasource: 'doris_dw', sql: 'SELECT COUNT(*) FROM ods_gdb_biz_pay_record WHERE dt=...' } },
      { id: 'ps_end', type: 'end', position: { x: 660, y: 160 }, data: { name: '结束' } },
    ],
    edges: [
      { id: 'pe1', source: 'ps_start', target: 'ps_datax', kind: 'flow' },
      { id: 'pe2', source: 'ps_datax', target: 'ps_sql', kind: 'flow' },
      { id: 'pe3', source: 'ps_sql', target: 'ps_end', kind: 'flow' },
    ],
  }
}

/** 五层泳道集群拓扑（迁移 M16） */
function clusterTopoDoc(): GraphDocument {
  const n = (id: string, type: string, lane: string, x: number, y: number, name: string, data: Record<string, unknown> = {}) =>
    ({ id, type, lane, position: { x, y }, data: { name, ...data } })
  return {
    id: 'topo_prod',
    name: '生产集群拓扑',
    version: 1,
    meta: { profile: 'topo', updatedAt: '2026-09-12 08:00' },
    nodes: [
      n('tp_lb', 'lb', 'access', 60, 150, '负载均衡', { comp: 'Nginx', addr: '192.168.10.2', health: 'healthy' }),
      n('tp_gw', 'gateway', 'access', 60, 320, 'API网关', { comp: 'Gateway', addr: '192.168.10.3', health: 'healthy' }),
      n('tp_app1', 'app', 'runtime', 300, 80, '应用实例-1', { comp: 'datara-web', addr: '192.168.20.11', health: 'healthy' }),
      n('tp_app2', 'app', 'runtime', 300, 220, '应用实例-2', { comp: 'datara-web', addr: '192.168.20.12', health: 'healthy' }),
      n('tp_master', 'ds_master', 'runtime', 300, 380, 'DS Master', { comp: 'DolphinScheduler', addr: '192.168.20.21', health: 'warn' }),
      n('tp_worker', 'ds_worker', 'runtime', 300, 520, 'DS Worker x3', { comp: 'DolphinScheduler', addr: '192.168.20.30-32', health: 'healthy' }),
      n('tp_zk', 'zk', 'middleware', 560, 100, 'ZooKeeper', { comp: 'ZooKeeper', addr: '192.168.30.1-3', health: 'healthy' }),
      n('tp_kafka', 'kafka', 'middleware', 560, 260, 'Kafka', { comp: 'Kafka', addr: '192.168.30.10', health: 'healthy' }),
      n('tp_redis', 'redis', 'middleware', 560, 420, 'Redis', { comp: 'Redis', addr: '192.168.30.20', health: 'healthy' }),
      n('tp_spark', 'spark', 'compute', 800, 180, 'Spark', { comp: 'Spark 3.x', addr: 'YARN', health: 'healthy' }),
      n('tp_flink', 'flink', 'compute', 800, 340, 'Flink', { comp: 'Flink 1.18', addr: '192.168.40.10', health: 'healthy' }),
      n('tp_mysql', 'mysql', 'storage', 1040, 100, '业务库', { comp: 'GreatDB', addr: '192.168.50.1', health: 'healthy' }),
      n('tp_hdfs', 'hdfs', 'storage', 1040, 260, 'HDFS', { comp: 'Hadoop 3.x', addr: '192.168.50.10', health: 'healthy' }),
      n('tp_doris', 'doris', 'storage', 1040, 420, 'Doris', { comp: 'Doris 2.1', addr: '192.168.50.20', health: 'healthy' }),
    ],
    edges: [
      { id: 'te1', source: 'tp_lb', target: 'tp_gw', kind: 'flow' },
      { id: 'te2', source: 'tp_gw', target: 'tp_app1', kind: 'flow' },
      { id: 'te3', source: 'tp_gw', target: 'tp_app2', kind: 'flow' },
      { id: 'te4', source: 'tp_app1', target: 'tp_zk', kind: 'flow' },
      { id: 'te5', source: 'tp_app2', target: 'tp_zk', kind: 'flow' },
      { id: 'te6', source: 'tp_app1', target: 'tp_kafka', kind: 'flow' },
      { id: 'te7', source: 'tp_app2', target: 'tp_redis', kind: 'flow' },
      { id: 'te8', source: 'tp_master', target: 'tp_worker', kind: 'flow' },
      { id: 'te9', source: 'tp_worker', target: 'tp_kafka', kind: 'dep' },
      { id: 'te10', source: 'tp_worker', target: 'tp_spark', kind: 'flow' },
      { id: 'te11', source: 'tp_worker', target: 'tp_flink', kind: 'flow' },
      { id: 'te12', source: 'tp_spark', target: 'tp_hdfs', kind: 'flow' },
      { id: 'te13', source: 'tp_flink', target: 'tp_doris', kind: 'flow' },
      { id: 'te14', source: 'tp_kafka', target: 'tp_flink', kind: 'flow' },
      { id: 'te15', source: 'tp_app2', target: 'tp_mysql', kind: 'flow' },
      { id: 'te16', source: 'tp_master', target: 'tp_zk', kind: 'dep' },
    ],
  }
}

/* ==================== Phase 2：U2/U3/U5/U6/U7 图文档 ==================== */

/** U2 ETL 清洗支付明细（迁移原型 ETL001 算子链） */
function etlPayCleanDoc(): GraphDocument {
  const doc: GraphDocument = {
    id: 'etl_pay_clean',
    name: '清洗支付明细（etl_dwd_order_pay_clean）',
    version: 1,
    meta: { profile: 'etl', updatedAt: '2026-09-10 11:20', type: 'etl' },
    nodes: [
      { id: 'op1', type: 'src_db', position: { x: 0, y: 0 }, data: { name: '读取ODS订单', sourceTable: 'ods_gdb_biz_trade_order', where: '' } },
      { id: 'op2', type: 'op_filter', position: { x: 0, y: 0 }, data: { name: '过滤无效订单', condition: 'pay_status IS NOT NULL AND amount > 0' } },
      { id: 'op3', type: 'op_join', position: { x: 0, y: 0 }, data: { name: '关联用户维度', joinType: 'LEFT JOIN', joinKeys: 'user_id = user_id', mapping: [
        { src: 'user_id', srcType: 'bigint', dst: 'user_id', dstType: 'bigint', rule: '直通' },
        { src: 'phone', srcType: 'string', dst: 'user_phone', dstType: 'string', rule: '脱敏(md5)' },
        { src: 'gender', srcType: 'string', dst: 'gender', dstType: 'string', rule: '枚举映射 M/F→男/女' },
      ] } },
      { id: 'op4', type: 'op_expr', position: { x: 0, y: 0 }, data: { name: '计算实付金额', expr: 'pay_amount = amount - discount' } },
      { id: 'op5', type: 'op_dedup', position: { x: 0, y: 0 }, data: { name: '按pay_id去重', dedupKeys: 'pay_id' } },
      { id: 'op6', type: 'out_db', position: { x: 0, y: 0 }, data: { name: '写入DWD', targetTable: 'dwd_order_pay_detail', writeMode: '覆盖分区', partition: 'dt=${biz_date}' } },
    ],
    edges: [
      { id: 'e1', source: 'op1', target: 'op2', kind: 'flow' },
      { id: 'e2', source: 'op2', target: 'op3', kind: 'flow' },
      { id: 'e3', source: 'op3', target: 'op4', kind: 'flow' },
      { id: 'e4', source: 'op4', target: 'op5', kind: 'flow' },
      { id: 'e5', source: 'op5', target: 'op6', kind: 'flow' },
    ],
  }
  return dagreLayout(doc, { dir: 'TB' })
}

/** U3 流设计器：订单支付实时入仓（迁移原型 SJ001） */
function streamRealtimeDoc(): GraphDocument {
  const doc: GraphDocument = {
    id: 'stream_realtime',
    name: '订单支付实时入仓（SJ001）',
    version: 1,
    meta: { profile: 'stream', updatedAt: '2026-09-12 22:28', type: 'stream' },
    nodes: [
      { id: 'sk1', type: 's_kafka', position: { x: 0, y: 0 }, data: { name: '支付流水源', topic: 'kafka_order_pay', format: 'JSON', startup: 'latest-offset',
        metrics: { tps: 1240, latency: '380ms', watermark: '延迟 4s', ckInterval: '60s', ckMode: 'Exactly-Once', ckRate: '99.8%' } } },
      { id: 'pf1', type: 'p_filter', position: { x: 0, y: 0 }, data: { name: '剔除空金额', condition: 'pay_amount IS NOT NULL' } },
      { id: 'pw1', type: 'p_window', position: { x: 0, y: 0 }, data: { name: '分钟支付量预聚合', windowType: 'TUMBLE', size: "INTERVAL '1' MINUTE", pkey: 'pay_channel', agg: 'COUNT(1), SUM(pay_amount)' } },
      { id: 'pj1', type: 'p_join', position: { x: 0, y: 0 }, data: { name: '补全用户标签', dimTable: 'dim_user' } },
      { id: 'od1', type: 'o_doris', position: { x: 0, y: 0 }, data: { name: '实时明细入仓', table: 'dwd_order_pay_rt', pkey: 'pay_id' } },
      { id: 'ok1', type: 'o_kafka', position: { x: 0, y: 0 }, data: { name: '广播下游', topic: 'topic_pay_summary_rt' } },
    ],
    edges: [
      { id: 'se1', source: 'sk1', target: 'pf1', kind: 'flow', label: '1240 tps' },
      { id: 'se2', source: 'pf1', target: 'pj1', kind: 'flow', label: '1238 tps' },
      { id: 'se3', source: 'pf1', target: 'pw1', kind: 'flow', label: '1238 tps' },
      { id: 'se4', source: 'pj1', target: 'od1', kind: 'flow', label: '1236 tps' },
      { id: 'se5', source: 'pw1', target: 'ok1', kind: 'lag', label: '积压 2.1k' },
    ],
  }
  return dagreLayout(doc, { dir: 'LR' })
}

/** U5 ER 画布：交易主题核心模型 */
function erDwDoc(): GraphDocument {
  const F = (arr: [string, string, ('PK' | 'FK')[]?][]) =>
    arr.map(([name, type, keys]) => ({ name, type, key: keys?.[0] }))
  const doc: GraphDocument = {
    id: 'er_dw',
    name: '交易主题 ER 模型',
    version: 1,
    meta: { profile: 'er', updatedAt: '2026-09-12 15:00' },
    nodes: [
      { id: 'en_ods_order', type: 'ent_ods', position: { x: 0, y: 0 }, data: { name: 'ods_gdb_biz_trade_order', layer: 'ODS', domain: '交易域', comment: '万里生产库订单原样接入', fields: F([
        ['order_id', 'bigint', ['PK']], ['user_id', 'bigint', ['FK']], ['amount', 'decimal(18,2)'], ['pay_status', 'int'], ['created_at', 'datetime'],
      ]) } },
      { id: 'en_ods_user', type: 'ent_ods', position: { x: 0, y: 0 }, data: { name: 'ods_gdb_biz_user_info', layer: 'ODS', domain: '公共', comment: '用户信息源表', fields: F([
        ['user_id', 'bigint', ['PK']], ['phone', 'string'], ['gender', 'string'], ['reg_dt', 'date'],
      ]) } },
      { id: 'en_ods_pay', type: 'ent_ods', position: { x: 0, y: 0 }, data: { name: 'ods_gdb_biz_pay_record', layer: 'ODS', domain: '交易域', fields: F([
        ['pay_id', 'bigint', ['PK']], ['order_id', 'bigint', ['FK']], ['pay_amount', 'decimal(18,2)'], ['pay_time', 'datetime'],
      ]) } },
      { id: 'en_dim_user', type: 'ent_dim', position: { x: 0, y: 0 }, data: { name: 'dim_user', layer: 'DIM', domain: '公共', comment: '用户维度（日更快照）', fields: F([
        ['user_id', 'bigint', ['PK']], ['user_name', 'string'], ['phone', 'string'], ['gender', 'string'], ['dt', 'date', ['PK']],
      ]) } },
      { id: 'en_dim_product', type: 'ent_dim', position: { x: 0, y: 0 }, data: { name: 'dim_product', layer: 'DIM', domain: '商品域', fields: F([
        ['product_id', 'bigint', ['PK']], ['product_name', 'string'], ['category', 'string'],
      ]) } },
      { id: 'en_dwd_pay', type: 'ent_dwd', position: { x: 0, y: 0 }, data: { name: 'dwd_order_pay_detail', layer: 'DWD', domain: '交易域', comment: '支付明细事实表', fields: F([
        ['pay_id', 'bigint', ['PK']], ['order_id', 'bigint', ['FK']], ['user_id', 'bigint', ['FK']], ['product_id', 'bigint', ['FK']], ['pay_amount', 'decimal(18,2)'], ['pay_time', 'datetime'],
      ]) } },
      { id: 'en_dwd_voucher', type: 'ent_dwd', position: { x: 0, y: 0 }, data: { name: 'dwd_gl_voucher_detail', layer: 'DWD', domain: '财务域', fields: F([
        ['voucher_id', 'bigint', ['PK']], ['subject_code', 'string'], ['amount', 'decimal(18,2)'],
      ]) } },
      { id: 'en_dws_pay', type: 'ent_dws', position: { x: 0, y: 0 }, data: { name: 'dws_pay_summary_daily', layer: 'DWS', domain: '交易域', comment: '支付主题日汇总', fields: F([
        ['stat_date', 'date', ['PK']], ['channel', 'string', ['PK']], ['pay_user_cnt', 'bigint'], ['pay_amount_sum', 'decimal(18,2)'],
      ]) } },
      { id: 'en_ads_kpi', type: 'ent_ads', position: { x: 0, y: 0 }, data: { name: 'ads_kpi_report', layer: 'ADS', domain: '经营域', fields: F([
        ['kpi_date', 'date', ['PK']], ['kpi_code', 'string', ['PK']], ['kpi_value', 'decimal(18,4)'],
      ]) } },
    ],
    edges: [
      { id: 're1', source: 'en_ods_user', target: 'en_ods_order', kind: 'rel_1n', label: '1:N' },
      { id: 're2', source: 'en_ods_order', target: 'en_ods_pay', kind: 'rel_1n', label: '1:N' },
      { id: 're3', source: 'en_ods_user', target: 'en_dim_user', kind: 'rel_1n', label: '抽取' },
      { id: 're4', source: 'en_ods_pay', target: 'en_dwd_pay', kind: 'rel_1n', label: '清洗加工' },
      { id: 're5', source: 'en_dim_user', target: 'en_dwd_pay', kind: 'rel_n1', label: 'N:1 补维' },
      { id: 're6', source: 'en_dim_product', target: 'en_dwd_pay', kind: 'rel_n1', label: 'N:1 补维' },
      { id: 're7', source: 'en_dwd_pay', target: 'en_dws_pay', kind: 'rel_n1', label: '聚合' },
      { id: 're8', source: 'en_dws_pay', target: 'en_ads_kpi', kind: 'rel_n1', label: '加工' },
    ],
  }
  return erGridLayout(doc, {})
}

/** U6 全域血缘（迁移原型 DB.lineageGraph + 任务标注） */
function lineageGlobalDoc(): GraphDocument {
  const t = (id: string, type: string, name: string, data: Record<string, unknown>) =>
    ({ id, type, position: { x: 0, y: 0 }, data: { name, ...data } })
  const doc: GraphDocument = {
    id: 'lineage_global',
    name: '全域血缘（表级）',
    version: 1,
    meta: { profile: 'lineage', updatedAt: '2026-09-12 07:35' },
    nodes: [
      t('ods_user', 'ln_ods', 'ods_gdb_biz_user_info', { layer: 'ODS', domain: '公共', rows: 1250000, core: true }),
      t('ods_pay', 'ln_ods', 'ods_gdb_biz_pay_record', { layer: 'ODS', domain: '交易域', rows: 3960000 }),
      t('ods_order', 'ln_ods', 'ods_gdb_biz_trade_order', { layer: 'ODS', domain: '交易域', rows: 4100000, core: true }),
      t('ods_voucher', 'ln_ods', 'ods_oracle_gl_voucher', { layer: 'ODS', domain: '财务域', rows: 560000 }),
      t('ods_product', 'ln_ods', 'ods_mysql_product_info', { layer: 'ODS', domain: '商品域', rows: 78000 }),
      t('dim_user', 'ln_dim', 'dim_user', { layer: 'DIM', domain: '公共', rows: 1250000, core: true }),
      t('dim_product', 'ln_dim', 'dim_product', { layer: 'DIM', domain: '商品域', rows: 78000 }),
      t('dwd_pay', 'ln_dwd', 'dwd_order_pay_detail', { layer: 'DWD', domain: '交易域', rows: 3980000, core: true }),
      t('dwd_voucher', 'ln_dwd', 'dwd_gl_voucher_detail', { layer: 'DWD', domain: '财务域', rows: 558000 }),
      t('dws_pay', 'ln_dws', 'dws_pay_summary_daily', { layer: 'DWS', domain: '交易域', rows: 1860, core: true }),
      t('ads_kpi', 'ln_ads', 'ads_kpi_report', { layer: 'ADS', domain: '经营域', rows: 365 }),
    ],
    edges: [
      { id: 'le1', source: 'ods_user', target: 'dim_user', kind: 'dep', label: 'ETL005 etl_dim_user_sync' },
      { id: 'le2', source: 'ods_pay', target: 'dwd_pay', kind: 'dep', label: 'ETL001 清洗支付明细' },
      { id: 'le3', source: 'ods_order', target: 'dwd_pay', kind: 'dep', label: 'ETL001 清洗支付明细' },
      { id: 'le4', source: 'dim_user', target: 'dwd_pay', kind: 'dep', label: 'ETL001 清洗支付明细' },
      { id: 'le5', source: 'ods_product', target: 'dwd_pay', kind: 'dep_unlinked', label: 'ETL006 未入工作流' },
      { id: 'le6', source: 'ods_product', target: 'dim_product', kind: 'dep_unlinked', label: 'ETL006 未入工作流' },
      { id: 'le7', source: 'dwd_pay', target: 'dws_pay', kind: 'dep', label: 'ETL002 支付主题日汇总' },
      { id: 'le8', source: 'dws_pay', target: 'ads_kpi', kind: 'dep', label: 'ETL003 经营KPI宽表' },
      { id: 'le9', source: 'ods_voucher', target: 'dwd_voucher', kind: 'dep_unlinked', label: 'ETL004 未入工作流' },
    ],
  }
  return dagreLayout(doc, { dir: 'LR' })
}

/** U7 资产地图（表/指标/报表/API/标签 力导向关联） */
function assetMapDoc(): GraphDocument {
  const n = (id: string, type: string, name: string, data: Record<string, unknown>) =>
    ({ id, type, position: { x: 0, y: 0 }, data: { name, ...data } })
  const doc: GraphDocument = {
    id: 'asset_map',
    name: '数据资产地图',
    version: 1,
    meta: { profile: 'relation', updatedAt: '2026-09-12 08:00' },
    nodes: [
      n('a_ods_order', 'as_table', 'ods_gdb_biz_trade_order', { domain: '交易域', rows: 4100000 }),
      n('a_ods_user', 'as_table', 'ods_gdb_biz_user_info', { domain: '公共', rows: 1250000 }),
      n('a_dwd_pay', 'as_table', 'dwd_order_pay_detail', { domain: '交易域', rows: 3980000 }),
      n('a_dws_pay', 'as_table', 'dws_pay_summary_daily', { domain: '交易域', rows: 1860 }),
      n('a_ads_kpi', 'as_table', 'ads_kpi_report', { domain: '经营域', rows: 365 }),
      n('a_dim_user', 'as_table', 'dim_user', { domain: '公共', rows: 1250000 }),
      n('a_m_user', 'as_metric', 'pay_user_cnt 支付用户数', { owner: '李工' }),
      n('a_m_amt', 'as_metric', 'pay_amount_sum 支付金额', { owner: '李工' }),
      n('a_rpt_kpi', 'as_report', '经营KPI日报', { owner: '赵工' }),
      n('a_api_pay', 'as_api', '/api/v1/pay/summary', { owner: '刘工' }),
      n('a_tag_core', 'as_tag', '核心资产', {}),
      n('a_tag_pii', 'as_tag', 'PII敏感', {}),
    ],
    edges: [
      { id: 'ae1', source: 'a_ods_order', target: 'a_dwd_pay', kind: 'produce', label: 'ETL001' },
      { id: 'ae2', source: 'a_ods_user', target: 'a_dim_user', kind: 'produce', label: 'ETL005' },
      { id: 'ae3', source: 'a_dwd_pay', target: 'a_dws_pay', kind: 'produce', label: 'ETL002' },
      { id: 'ae4', source: 'a_dws_pay', target: 'a_ads_kpi', kind: 'produce', label: 'ETL003' },
      { id: 'ae5', source: 'a_dws_pay', target: 'a_m_user', kind: 'refer' },
      { id: 'ae6', source: 'a_dws_pay', target: 'a_m_amt', kind: 'refer' },
      { id: 'ae7', source: 'a_m_user', target: 'a_rpt_kpi', kind: 'refer' },
      { id: 'ae8', source: 'a_m_amt', target: 'a_rpt_kpi', kind: 'refer' },
      { id: 'ae9', source: 'a_api_pay', target: 'a_dws_pay', kind: 'call' },
      { id: 'ae10', source: 'a_tag_core', target: 'a_dwd_pay', kind: 'tag' },
      { id: 'ae11', source: 'a_tag_core', target: 'a_ads_kpi', kind: 'tag' },
      { id: 'ae12', source: 'a_tag_pii', target: 'a_ods_user', kind: 'tag' },
      { id: 'ae13', source: 'a_tag_pii', target: 'a_dim_user', kind: 'tag' },
    ],
  }
  return forceLayout(doc, { iterations: 320, idealLen: 190 })
}

const seedStore = new Map<string, GraphDocument>([
  ['wf_order_daily', orderDailyDoc()],
  ['wf_pay_sync', paySyncDoc()],
  ['topo_prod', clusterTopoDoc()],
  ['etl_pay_clean', etlPayCleanDoc()],
  ['stream_realtime', streamRealtimeDoc()],
  ['er_dw', erDwDoc()],
  ['lineage_global', lineageGlobalDoc()],
  ['asset_map', assetMapDoc()],
])

export function getSeedDoc(id: string): GraphDocument | null {
  return seedStore.get(id) ?? null
}

/** DAG 工作台引用：seed 中的工作流图文档（id+name，仅 dag profile），供变量复制等工作流下拉使用 */
export function listSeedWfDocs(): { id: string; name: string }[] {
  return [...seedStore.values()].filter((d) => d.meta.profile === 'dag').map((d) => ({ id: d.id, name: d.name }))
}

/** 任务中心引用：seed 中的任务类图文档（id+name+业务类型），供四类任务视角按类型直达画布 */
export function listSeedTaskDocs(): { id: string; name: string; type?: 'batch' | 'sync' | 'etl' | 'stream' }[] {
  return [...seedStore.values()]
    .filter((d) => d.meta.profile === 'dag' || d.meta.profile === 'etl' || d.meta.profile === 'stream')
    .map((d) => ({ id: d.id, name: d.name, type: d.meta.type }))
}

export function newWorkflowDoc(id: string, name: string, type: 'batch' | 'sync' = 'batch'): GraphDocument {
  return {
    id,
    name,
    version: 1,
    meta: { profile: 'dag', updatedAt: localTime(), type },
    nodes: [
      { id: 'nd_start', type: 'start', position: { x: 0, y: 160 }, data: { name: '启动' } },
      { id: 'nd_end', type: 'end', position: { x: 480, y: 160 }, data: { name: '结束' } },
    ],
    edges: [],
  }
}
