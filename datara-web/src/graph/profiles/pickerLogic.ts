/**
 * I12 T10 动态控件纯逻辑（table-picker / field-select / topic-select / dir-select）。
 * 与组件与网络解耦：数据源行 / 库表树 / 目录项由调用方（Inspector.vue）注入，vitest 直测；
 * 依赖字段名约定对齐 FieldSchema.pick（缺省键见 PICK_DEF），联动复用既有 showIf/onChange 机制。
 * 列枚举复用 /datasources/{id}/tree 返回中内联的 columns（单次请求同时供两级级联与字段多选）。
 */
import type { DsRow, DsTree } from '../../services/datasourceApi'
import type { FieldSchema } from './types'

/** 依赖字段名缺省约定（FieldSchema.pick 可覆盖；取值均存于 node.data 对应字段） */
export const PICK_DEF = {
  /** table-picker / field-select 依赖的数据源字段 */
  dsKey: 'datasource',
  /** field-select 依赖的表字段 */
  tableKey: 'table',
  /** topic-select 依赖的流源引用字段（存数据源名，解析成 ds_id 枚举 topic） */
  topicDsKey: 'dsRef',
  /** dir-select 依赖的运行时节点字段（存节点名，解析成节点 id 浏览目录） */
  nodeKey: 'runtimeNode',
} as const

export type PickWriteAs = 'table' | 'schemaTable'

/** 解析字段 pick 配置（缺省兜底；topic-select 的 dsKey 缺省走 dsRef） */
export function pickCfg(f: Pick<FieldSchema, 'type' | 'pick'>): {
  dsKey: string; tableKey: string; nodeKey: string; writeAs: PickWriteAs
} {
  return {
    dsKey: f.pick?.dsKey ?? (f.type === 'topic-select' ? PICK_DEF.topicDsKey : PICK_DEF.dsKey),
    tableKey: f.pick?.tableKey ?? PICK_DEF.tableKey,
    nodeKey: f.pick?.nodeKey ?? PICK_DEF.nodeKey,
    writeAs: f.pick?.writeAs ?? 'table',
  }
}

/** 经数据源字段值（数据源名）解析 ds_id：rows 为 Inspector 预载的数据源行；未命中/空值返回 null */
export function resolveDsId(dsName: unknown, rows: Pick<DsRow, 'id' | 'name'>[]): number | string | null {
  const name = String(dsName ?? '').trim()
  if (!name) return null
  const hit = rows.find((r) => r.name === name)
  return hit && hit.id != null ? hit.id : null
}

/** el-cascader option 形状 */
export interface PickOption { value: string; label: string; leaf?: boolean; children?: PickOption[] }

/** 连接型库表树 → 两级级联 options（库 → 表）；文件型/空树返回空（失败态候选置空） */
export function tableOptions(tree: DsTree | null | undefined): PickOption[] {
  if (!tree || tree.kind !== 'connection') return []
  return tree.databases.map((d) => ({
    value: d.name,
    label: d.name,
    children: d.tables.map((t) => ({ value: t.name, label: t.name, leaf: true })),
  }))
}

/** 当前字段值 → cascader 回显路径：{schema, table} 对象直取；纯表名在树中反查所属库 */
export function tablePickPath(value: unknown, tree: DsTree | null | undefined): string[] {
  if (value && typeof value === 'object') {
    const o = value as { schema?: unknown; table?: unknown }
    const s = String(o.schema ?? '')
    const t = String(o.table ?? '')
    return s && t ? [s, t] : t ? [t] : []
  }
  const name = String(value ?? '')
  if (!name || !tree || tree.kind !== 'connection') return []
  for (const d of tree.databases) {
    if (d.tables.some((t) => t.name === name)) return [d.name, name]
  }
  return []
}

/** cascader 选中路径 → 写回值：'schemaTable' 写 {schema, table}；缺省纯表名；清空 → 空串。
 *  el-cascader 清空时 change payload 为 null（非数组）→ 规整为空路径；
 *  schemaTable 两段皆空写回 '' 而非 {schema:'',table:''} 空对象——空对象会绕过
 *  requiredMissing 的必填保存闸门（其空值判定只认 ''/null/undefined/空数组）。 */
export function writeTablePick(writeAs: PickWriteAs, path: unknown): unknown {
  const arr = Array.isArray(path) ? path : []
  const seg = (i: number) => (arr[i] == null ? '' : String(arr[i]))
  if (writeAs === 'schemaTable') {
    const s = seg(0)
    const t = seg(1)
    return s || t ? { schema: s, table: t } : ''
  }
  return seg(1) || seg(0)
}

/** field-select 列枚举：表值自带 schema（{schema, table}）优先定位；纯表名在树中检索首个命中库 */
export function columnsOf(tree: DsTree | null | undefined, tableValue: unknown): string[] {
  if (!tree || tree.kind !== 'connection') return []
  let schema = ''
  let table = ''
  if (tableValue && typeof tableValue === 'object') {
    const o = tableValue as { schema?: unknown; table?: unknown }
    schema = String(o.schema ?? '')
    table = String(o.table ?? '')
  } else {
    table = String(tableValue ?? '')
  }
  if (!table) return []
  const dbs = schema ? tree.databases.filter((d) => d.name === schema) : tree.databases
  for (const d of dbs) {
    const hit = d.tables.find((t) => t.name === table)
    if (hit) return hit.columns.map((c) => c.name)
  }
  return []
}

/** 目录懒加载下钻路径拼接：'/x' + 'y' → '/x/y'（收敛末端斜杠，根目录不双斜杠） */
export function dirJoin(parent: string, name: string): string {
  const base = String(parent || '/').replace(/\/+$/, '') || '/'
  return base === '/' ? `/${name}` : `${base}/${name}`
}

/** 目录面包屑段：'/mnt/lei' → [{name:'/',path:'/'},{name:'mnt',path:'/mnt'},{name:'lei',path:'/mnt/lei'}] */
export function dirCrumbs(path: string): { name: string; path: string }[] {
  const crumbs = [{ name: '/', path: '/' }]
  const norm = String(path || '').replace(/\/+$/, '')
  if (!norm) return crumbs
  let acc = ''
  for (const seg of norm.split('/')) {
    if (!seg) continue
    acc += `/${seg}`
    crumbs.push({ name: seg, path: acc })
  }
  return crumbs
}

/** 上游节点按画布位置左→右排序（position.x 升序；x 缺失或相等回退原序，稳定）。
 *  I12 评审修：连线先后 ≠ 视觉左右，join 键左右候选先排序防 left join 语义静默反转。 */
export function sortByCanvasX<T extends { position?: { x?: number } }>(nodes: T[]): T[] {
  return nodes
    .map((n, i) => ({ n, i, x: Number(n.position?.x ?? NaN) }))
    .sort((a, b) => (Number.isFinite(a.x) && Number.isFinite(b.x) && a.x !== b.x ? a.x - b.x : a.i - b.i))
    .map((w) => w.n)
}
