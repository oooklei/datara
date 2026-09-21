/**
 * 任务 → 图文档派生（纯函数）：任务打开设计器时，把任务定义（可视化算子链 / SQL / 脚本）
 * 派生为与 seed 同构的"具体用例流图"并落库，画布即可编辑且用户修改可持久化。
 * 容错优先：任何取不到的信息给占位文案（'未配置'），不抛异常；取不到时返回 null 由调用方渲染空画布。
 */
import type { EtlOp, EtlTask, StreamJob } from '../../services/types'
import type { GNode, GraphDocument } from './index'
import { dagreLayout } from '../layout/dagre'

const RE_FROM = /\bFROM\s+([A-Za-z_][\w$.`]*)/i
const RE_INSERT_OVERWRITE = /\bINSERT\s+OVERWRITE\s+TABLE\s+([A-Za-z_][\w$.`]*)/i
const RE_GROUP_BY = /\bGROUP\s+BY\b/i
const RE_WINDOW_TYPE = /\b(TUMBLE|HOP|SESSION)\b/i
const RE_AGG = /\b(COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)/gi
/** 子句结束关键字（取字段列表时截断扫描范围） */
const RE_CLAUSE_STOP = /\b(HAVING|ORDER\s+BY|LIMIT|WINDOW|FROM)\b/i

function node(id: string, type: string, name: string, data: Record<string, unknown> = {}): GNode {
  return { id, type, position: { x: 0, y: 0 }, data: { name, ...data } }
}

/** 依序连成单链 + 按方向预布局（与 seed 文档同构：坐标由 dagre 预计算，工作台打开即可读） */
function chain(id: string, name: string, profile: string, dir: 'TB' | 'LR', nodes: GNode[]): GraphDocument {
  const edges = nodes.slice(1).map((n, i) => ({
    id: `e${i + 1}`,
    source: nodes[i]!.id,
    target: n.id,
    kind: 'flow' as const,
  }))
  return dagreLayout({ id, name, version: 1, meta: { profile }, nodes, edges }, { dir })
}

/** 正则首捕获并清理表名尾部符号；取不到返回兜底 */
function capture(re: RegExp, s: string, fallback: string): string {
  const raw = re.exec(s)?.[1]?.trim()
  if (!raw) return fallback
  return raw.replace(/[,;`.)]+$/, '').trim() || fallback
}

/** 子句后首个普通字段（跳过 TUMBLE(...) 等函数调用项）；取不到返回空串 */
function firstFieldAfter(re: RegExp, sql: string): string {
  const m = re.exec(sql)
  if (!m) return ''
  const tail = sql.slice(m.index + m[0].length)
  const stop = tail.search(RE_CLAUSE_STOP)
  const seg = stop >= 0 ? tail.slice(0, stop) : tail
  const plain = seg.split(/[;,]/)[0]?.split(',').map((x) => x.trim()).find((x) => x && !x.includes('('))
  return plain ? plain.split(/\s+AS\s+/i)[0]!.trim() : ''
}

/** SELECT 首个普通字段（DISTINCT/别名/聚合项跳过）；用于分桶键兜底 */
function firstSelectField(sql: string): string {
  const m = /\bSELECT\b/i.exec(sql)
  if (!m) return ''
  const tail = sql.slice(m.index + m[0].length).replace(/^\s*DISTINCT\s+/i, '')
  const stop = tail.search(/\bFROM\b/i)
  const seg = stop >= 0 ? tail.slice(0, stop) : tail
  const plain = seg.split(',').map((x) => x.trim()).find((x) => x && !x.includes('('))
  return plain ? plain.split(/\s+AS\s+/i)[0]!.trim() : ''
}

/** 窗口函数括号内大小（优先 INTERVAL 'n' UNIT 片段），兜底 '1 MINUTE' */
function windowSize(sql: string, win: string): string {
  const inner = new RegExp(`\\b${win}\\s*\\(([^)]*)\\)`, 'i').exec(sql)?.[1]?.trim()
  if (inner) {
    const iv = /INTERVAL\s+'[^']*'\s+[A-Za-z]+/i.exec(inner)
    if (iv) return iv[0]
    const last = inner.split(',').map((x) => x.trim()).filter(Boolean).pop()
    if (last) return last
  }
  return '1 MINUTE'
}

/** SELECT 中的聚合表达式片段（COUNT/SUM/AVG/MIN/MAX），兜底 COUNT(1) */
function aggFragments(sql: string): string {
  const hits = sql.match(RE_AGG)
  return hits?.length ? hits.join(', ') : 'COUNT(1)'
}

/* ==================== ETL 任务派生（TB 算子链） ==================== */

/** 可视化算子 → 图节点映射（未知类型回落表达式节点） */
function opNode(op: EtlOp, i: number): GNode {
  const cfg = String(op.cfg ?? '')
  const id = `n${i + 1}`
  switch (op.type) {
    case '输入源':
      return node(id, 'src_db', op.name || '输入源', { sourceTable: cfg || '未配置', where: '' })
    case '过滤':
      return node(id, 'op_filter', op.name || '过滤', { condition: cfg })
    case 'Join':
      return node(id, 'op_join', op.name || 'Join', { joinType: 'LEFT JOIN', joinKeys: cfg || '未配置', mapping: [] })
    case '表达式':
      return node(id, 'op_expr', op.name || '表达式', { expr: cfg })
    case '去重':
      return node(id, 'op_dedup', op.name || '去重', { dedupKeys: cfg })
    case '输出': {
      // cfg 形如 'dwd_order_pay_detail（覆盖分区 dt=${biz_date}）'：表名取"（"前部分
      const table = cfg.split(/[（(]/)[0]?.trim() ?? ''
      return node(id, 'out_db', op.name || '输出', {
        targetTable: table || '未配置',
        writeMode: cfg.includes('覆盖分区') ? '覆盖分区' : '追加',
        partition: '',
      })
    }
    default:
      return node(id, 'op_expr', op.name || op.type || '算子', { expr: cfg || '未配置' })
  }
}

/**
 * ETL 任务 → etl 视角图文档：
 * - 可视化 ETL（t.ops 非空，如 ETL001）：按算子类型映射并依序 chain；
 * - SQL 任务（t.sql，如 ETL002/003）：src_db → op_script(SQL) → out_db；
 * - 脚本任务（t.script，如 ETL004）：src_db → op_script(scriptLang) → out_db；
 * - 均无：占位三节点链（待用户在画布补全）。
 */
export function buildEtlDoc(t: EtlTask | null | undefined): GraphDocument | null {
  try {
    if (!t || !t.id) return null
    const name = t.name || t.id
    const ops = Array.isArray(t.ops) ? t.ops.filter(Boolean) : []
    if (ops.length > 0) {
      return chain(t.id, name, 'etl', 'TB', ops.map((op, i) => opNode(op, i)))
    }
    if (typeof t.sql === 'string' && t.sql.trim()) {
      const src = capture(RE_FROM, t.sql, 'dwd_order_pay_detail')
      const dst = capture(RE_INSERT_OVERWRITE, t.sql, t.code || '未配置')
      return chain(t.id, name, 'etl', 'TB', [
        node('n1', 'src_db', '读取源表', { sourceTable: src, where: '' }),
        node('n2', 'op_script', 'SQL 加工', { scriptId: '', lang: 'SQL', code: t.sql }),
        node('n3', 'out_db', '写入目标表', { targetTable: dst, writeMode: '覆盖分区', partition: '' }),
      ])
    }
    if (typeof t.script === 'string' && t.script.trim()) {
      return chain(t.id, name, 'etl', 'TB', [
        node('n1', 'src_db', '数据源', { sourceTable: '', where: '' }),
        node('n2', 'op_script', '脚本执行', { scriptId: '', lang: t.scriptLang || 'Python', code: t.script }),
        node('n3', 'out_db', '写入目标表', { targetTable: t.code || '待配置', writeMode: '追加', partition: '' }),
      ])
    }
    return chain(t.id, name, 'etl', 'TB', [
      node('n1', 'src_db', '数据源', { sourceTable: '', where: '' }),
      node('n2', 'op_script', '脚本', { scriptId: '', lang: 'SQL', code: '' }),
      node('n3', 'out_db', '输出', { targetTable: t.code || '', writeMode: '追加', partition: '' }),
    ])
  } catch {
    return null
  }
}

/* ==================== 流任务派生（LR 链路） ==================== */

function sourceNode(source: string): GNode {
  const s = source.trim()
  const kafka = /^Kafka:\s*(.+)$/i.exec(s)
  if (kafka) {
    return node('n1', 's_kafka', 'Kafka 源', { topic: kafka[1]!.trim() || '未配置', format: 'JSON', startup: 'latest-offset' })
  }
  const cdc = /^MySQL Binlog:\s*(.+)$/i.exec(s)
  if (cdc) {
    const [dbName = '', tableName = ''] = cdc[1]!.trim().split('.')
    return node('n1', 's_cdc', 'CDC 采集', { dbName: dbName.trim() || '未配置', tableName: tableName.trim() || '未配置' })
  }
  return node('n1', 's_kafka', 'Kafka 源', { topic: s || '未配置', format: 'JSON', startup: 'latest-offset' })
}

function sinkNode(sink: string, pkey: string, id: string): GNode {
  const s = sink.trim()
  const doris = /^Doris:\s*(.+)$/i.exec(s)
  if (doris) {
    return node(id, 'o_doris', 'Doris 入仓', { table: doris[1]!.trim() || '未配置', pkey })
  }
  const kafka = /^Kafka:\s*(.+)$/i.exec(s)
  if (kafka) {
    return node(id, 'o_kafka', 'Kafka 输出', { topic: kafka[1]!.trim() || '未配置' })
  }
  return node(id, 'o_kafka', 'Kafka 输出', { topic: s || '未配置' })
}

/**
 * 流任务 → stream 视角图文档（LR）：
 * - source：'Kafka: topic'→s_kafka；'MySQL Binlog: db.tbl'→s_cdc；其他→s_kafka{topic:原文}；
 * - 含窗口关键字（TUMBLE/HOP/SESSION，如 SJ002）：中段插入 p_window（size/pkey/agg 从 SQL 解析）；
 * - sink：'Doris: tbl'→o_doris（pkey 必填）；其余→o_kafka；
 * - 分桶/分区键：GROUP BY 首字段 → SELECT 首字段 → 'id'（保证派生后校验无 error 级问题）。
 */
export function buildStreamDoc(j: StreamJob | null | undefined): GraphDocument | null {
  try {
    if (!j || !j.id) return null
    const sql = String(j.sql ?? '')
    const pkey = firstFieldAfter(RE_GROUP_BY, sql) || firstSelectField(sql) || 'id'
    const nodes: GNode[] = [sourceNode(String(j.source ?? ''))]
    let seq = 1
    const w = RE_WINDOW_TYPE.exec(sql)
    if (w) {
      nodes.push(node(`n${++seq}`, 'p_window', '窗口聚合', {
        windowType: w[1]!.toUpperCase(),
        size: windowSize(sql, w[1]!),
        pkey,
        agg: aggFragments(sql),
      }))
    }
    nodes.push(node(`n${++seq}`, 'op_script', 'SQL 加工', { scriptId: '', lang: 'Flink SQL', code: sql }))
    nodes.push(sinkNode(String(j.sink ?? ''), pkey, `n${++seq}`))
    return chain(j.id, j.name || j.id, 'stream', 'LR', nodes)
  } catch {
    return null
  }
}
