<script setup lang="ts">
/**
 * B3 F0：Inspector 单字段渲染器（业务表单 25+ 分支自 Inspector 抽取）。
 * props.field 声明渲染形态（FieldKind 9 基元 + 差异参数），data 为节点数据引用
 * （行编辑/勾选/级联直接回写，响应式随 store），ctx 承载节点级共享状态（fieldCtx.ts）。
 * 分发链与抽取前逐分支等价：DOM 结构与 class 不变，写值语义不变
 * （set=写值不 dirty + onChange 钩子；行编辑/级联=直接回写 + ctx.markDirty）。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uid } from '../../model'
import type { GNode } from '../../model'
import type { BranchDef, FieldSchema } from '../../profiles/types'
import { clearOnConditionHide, dataScopeState } from '../../profiles/formLinkage'
import { columnsOf, dirCrumbs, dirJoin, pickCfg, sortByCanvasX, tableOptions, tablePickPath, writeTablePick } from '../../profiles/pickerLogic'
import type { PickOption } from '../../profiles/pickerLogic'
import { getDataSourceTree } from '../../../services/datasourceApi'
import { isMock } from '../../../services'
import { useGraphStore } from '../../../stores/graph'
import RowsField from './RowsField.vue'
import DepsField from './DepsField.vue'
import type { DirNav, FieldCtx } from './fieldCtx'

const props = defineProps<{
  /** 字段 schema（渲染形态声明） */
  field: FieldSchema
  /** 节点数据引用（直接回写） */
  data: Record<string, unknown>
  /** 'view' 时只读（Inspector effMode 透传） */
  mode: 'edit' | 'view'
  /** 当前节点 id（分支编辑清理连线用） */
  nodeId: string
  /** 节点级上下文（候选缓存/脚本库互通/目录懒加载等） */
  ctx: FieldCtx
}>()
const emit = defineEmits<{
  /** 写值事件（父层 upd + onChange 钩子；number 输入转数值存储在父层统一处理） */
  (e: 'set', f: FieldSchema, ev: Event): void
  /** 行编辑表变更（父层 markDirty） */
  (e: 'dirty'): void
  /** 打开变量引用弹窗（expr 的 $ 按钮；目标 'f:{key}' 寻址） */
  (e: 'openVarDialog', target: string): void
  /** token-insert 插入后聚焦目标 textarea（父层持根元素引用定位） */
  (e: 'focusTarget', key: string): void
}>()

const graphStore = useGraphStore()
/* ctx 对象引用稳定（Inspector 组装一次），解构顶层 ref/computed 保持响应式 */
const { upstream, upSchema, upstreamOpts, epProbe, dsRows, scripts, runtimeNodes, tagOptions, varOptions, dataCtx,
  pickTrees, pickTreeErr, pickTreeBusy, topicOpts, topicErr, topicBusy, dirNavs,
  ensureTopics, lsDir, loadScriptCode, saveToScript, saveAsNewScript, markDirty, schema } = props.ctx

/* ================= F3 数据驱动值域（dataScope 声明：候选只来自 DataContext，域空禁用并说明） ================= */
/** dataScope 字段值域状态：候选 + 域空禁用原因（判定真源 dataScopeState，纯函数单测覆盖；无声明返回 null 走原渲染） */
const scope = computed(() => {
  const s = props.field.dataScope
  if (!s) return null
  return dataScopeState(dataCtx.value, s)
})
/** 值域外存量值兜底（如上游 schema 撤回后原选中值不在候选中）：展示「（值域外）」不静默丢值；有效性由 F4 保存闸门拦截 */
const curOutside = computed(() => {
  const st = scope.value
  if (!st) return ''
  const v = String(props.data[props.field.key] ?? '')
  return v && !st.options.includes(v) ? v : ''
})

/* ================= 依赖字段展示名 / 数据源选项 ================= */
/** 依赖字段展示名（提示文案用；form 中无该字段时回退字段名） */
function depLabel(key: string): string {
  return schema.value?.form.find((x) => x.key === key)?.label ?? key
}
/** 数据源中心下拉候选（real 拉 listDataSources，mock 用 dataStore 种子；cap.dsTypes 过滤类型） */
function dsOpts(): { value: string; label: string }[] {
  return dsRows.value
    .filter((r) => isMock || !props.field.cap?.dsTypes || props.field.cap.dsTypes.includes(String(r.type)))
    .map((r) => ({ value: r.name, label: `${r.name}（${r.type}${r.env ? ' · ' + r.env : ''}）` }))
}
/** 依赖数据源字段是否为空（topic 分支行内提示用轻量判定） */
function depEmpty(): boolean {
  return !String(props.data[pickCfg(props.field).dsKey] ?? '')
}

/* ================= 业务表单行存储（kv/params/args/var/deps 共用） ================= */
function formRows(key: string): { [k: string]: unknown }[] {
  const d = props.data
  if (!Array.isArray(d[key])) d[key] = []
  return d[key] as { [k: string]: unknown }[]
}

/* ================= field-map 行编辑（源字段→目标字段映射，行格式 { src, tgt, expr? }） ================= */
type FmRow = { src: string; tgt: string; expr?: string }
function fmRows(): FmRow[] {
  return (props.data[props.field.key] as FmRow[]) ?? []
}
function onFieldMapAdd() {
  props.data[props.field.key] = [...fmRows(), { src: '', tgt: '', expr: '' }]
  markDirty()
}
function onFieldMapRemove(index: number) {
  props.data[props.field.key] = fmRows().filter((_, i) => i !== index)
  markDirty()
}
function onFieldMapChange(index: number, field: 'src' | 'tgt' | 'expr', ev: Event) {
  const rows = fmRows()
  const row = { ...(rows[index] ?? { src: '', tgt: '', expr: '' }) }
  const val = (ev.target as HTMLInputElement | HTMLSelectElement).value
  if (field === 'src') row.src = val
  else if (field === 'tgt') row.tgt = val
  else row.expr = val || undefined
  rows[index] = row
  props.data[props.field.key] = rows
  markDirty()
}

/* ================= upstreamOutputs 行编辑（上游节点输出多选，行格式 string[]） ================= */
function urVals(): string[] {
  return (props.data[props.field.key] as string[]) ?? []
}
function onUpstreamRefAdd() {
  const max = props.field.cap?.upstreamMax ?? 1
  const vals = urVals()
  if (vals.length >= max) return
  props.data[props.field.key] = [...vals, '']
  markDirty()
}
function onUpstreamRefRemove(index: number) {
  props.data[props.field.key] = urVals().filter((_, i) => i !== index)
  markDirty()
}
function onUpstreamRefChange(index: number, ev: Event) {
  const vals = urVals()
  vals[index] = (ev.target as HTMLSelectElement).value
  props.data[props.field.key] = vals
  markDirty()
}

/* ================= bool：写 + markDirty + 联动（与 select emit('set') 同口径：M-B2 conditions 条件清空 + 旧 onChange 钩子） ================= */
function onBool(ev: Event) {
  props.data[props.field.key] = (ev.target as HTMLInputElement).checked
  markDirty()
  if (schema.value?.conditions?.length) clearOnConditionHide(schema.value, props.data, props.field.key)
  props.field.onChange?.(props.data, props.data[props.field.key])
}

/* ================= expr：表达式输入（写 + markDirty；$ 按钮弹变量引用弹窗） ================= */
function onExprChange(ev: Event) {
  props.data[props.field.key] = (ev.target as HTMLInputElement).value
  markDirty()
}

/* ================= table-picker / token-insert 派生数据（单字段 computed 化，Nit3 同款收敛） ================= */
type TpD = { opts: PickOption[]; path: string[]; err: string; depEmpty: boolean; loading: boolean; dsLabel: string }
const NO_PATH: string[] = []
const NO_OPTS: PickOption[] = []
const NO_COLS: string[] = []
const tp = computed<TpD | undefined>(() => {
  const fld = props.field
  const isTp = fld.type === 'resource' && fld.cap?.mode === 'table'
  const isTi = fld.type === 'mapEditor' && fld.mapMode === 'insert'
  if (!isTp && !isTi) return undefined
  const cfg = pickCfg(fld)
  const dsName = String(props.data[cfg.dsKey] ?? '')
  const tree = pickTrees.value[dsName] ?? null
  return {
    opts: tableOptions(tree),
    path: tablePickPath(props.data[fld.key], tree),
    err: pickTreeErr.value[dsName] ?? '',
    depEmpty: !dsName,
    loading: !!pickTreeBusy.value[dsName],
    dsLabel: depLabel(cfg.dsKey),
  }
})
/* table-picker：数据源→库→表两级级联；写回纯表名（缺省）或 {schema, table}（writeAs 可配）。
   el-cascader 清空时 change payload 为 null（非数组）→ writeTablePick 内规整为空路径写回 '' */
function onTablePick(path: unknown) {
  props.data[props.field.key] = writeTablePick(pickCfg(props.field).writeAs, path)
  markDirty()
}

/* ================= field-select 派生数据（列枚举来自已缓存库表树，免二次列请求） ================= */
type FsD = { cols: string[]; val: string[]; val1: string; multi: boolean; noTable: boolean; err: string; loading: boolean; tableLabel: string }
const fs = computed<FsD | undefined>(() => {
  const fld = props.field
  if (fld.type !== 'resource' || fld.cap?.mode !== 'column') return undefined
  const multi = fld.cap.multi ?? true
  const v = props.data[fld.key]
  const val1 = Array.isArray(v) ? String(v[0] ?? '') : String(v ?? '')
  /* I12 T12 join 键升级（C19）：src='upstream' 列枚举自直接上游流输入节点（cdcDs + tablesText 首表）；
     非 CDC 上游时候选为空但保持可输入（allow-create 降级），单选写回字符串对齐 ops.py 单键契约 */
  if (fld.cap.src === 'upstream') {
    const up = sortByCanvasX(upstream.value)[fld.cap.upstreamIndex ?? 0]
    const dsName = String(up?.data.cdcDs ?? '')
    const table = String(up?.data.tablesText ?? '').split(',')[0]?.trim() ?? ''
    return {
      cols: columnsOf(pickTrees.value[dsName] ?? null, table),
      val: Array.isArray(v) ? v.map(String) : [],
      val1,
      multi,
      noTable: !table,
      err: pickTreeErr.value[dsName] ?? '',
      loading: !!pickTreeBusy.value[dsName],
      tableLabel: '上游流输入表',
    }
  }
  const cfg = pickCfg(fld)
  const dsName = String(props.data[cfg.dsKey] ?? '')
  const tv = props.data[cfg.tableKey]
  return {
    cols: columnsOf(pickTrees.value[dsName] ?? null, tv),
    val: Array.isArray(v) ? v.map(String) : [],
    val1,
    multi,
    noTable: !String(tv ?? ''),
    err: pickTreeErr.value[dsName] ?? '',
    loading: !!pickTreeBusy.value[dsName],
    tableLabel: depLabel(cfg.tableKey),
  }
})
/* field-select：cap.multi 缺省多选写回数组，false 单选写回字符串（C19 join 键对齐 worker ops.py 单键契约） */
function onFieldsPick(vals: unknown) {
  props.data[props.field.key] = (props.field.cap?.multi ?? true)
    ? (Array.isArray(vals) ? vals.map(String) : [])
    : (vals == null ? '' : String(vals))
  markDirty()
}

/* ================= field-map 列枚举（从文档中查找 cap 指定的源/目标节点，读取其 ds/table 字段；端点合一后默认 endpoint_select） ================= */
type FmD = { srcCols: string[]; tgtCols: string[]; srcErr: string; tgtErr: string; srcLoading: boolean; tgtLoading: boolean; srcNoTable: boolean; tgtNoTable: boolean }
/** 具名引用解析（设计 §3.3 端口语义）：`nodeId:port` 取前缀 nodeId 定位节点（兼容旧格式：无端口 `id` / 空端口 `id:`）；
 *  期望端口给出时，指向对端（`:sourceRef`/`:targetRef` 互异）的引用拒绝识别，防错侧取列 */
function fmRefNode(nodes: GNode[] | undefined, ref: string | undefined, port?: string): GNode | undefined {
  if (ref && port && !ref.endsWith(`:${port}`) && /:(sourceRef|targetRef)$/.test(ref)) return undefined
  const nodeId = ref ? ref.split(':')[0] ?? '' : ''
  return nodeId ? nodes?.find((n) => n.id === nodeId) : undefined
}
const fm = computed<FmD | undefined>(() => {
  const fld = props.field
  if (fld.type !== 'mapEditor' || fld.mapMode !== 'map') return undefined
  const cap = fld.cap
  const doc = graphStore.doc
  const inputs = Array.isArray(props.data.inputs)
    ? (props.data.inputs as string[])
    : []
  /* 识别优先级（设计 §3.3）：① 端口语义 —— inputs 引用以 `:sourceRef`/`:targetRef` 结尾即源端/目标端节点；
     ② 降级既有机制 —— fmSrcIndex/fmTgtIndex 顺序索引引用（对端具名引用不参与）→ cap.srcNodeType/tgtNodeType 类型查找；
     ③ 都未命中 → 节点 undefined，列枚举为空（手填，与既有空 inputs 行为一致） */
  const srcNode = fmRefNode(doc?.nodes, inputs.find((r) => r.endsWith(':sourceRef')))
    ?? fmRefNode(doc?.nodes, inputs[cap?.fmSrcIndex ?? 0], 'sourceRef')
    ?? doc?.nodes.find((n) => n.type === (cap?.srcNodeType ?? 'endpoint_select'))
  const tgtNode = fmRefNode(doc?.nodes, inputs.find((r) => r.endsWith(':targetRef')))
    ?? fmRefNode(doc?.nodes, inputs[cap?.fmTgtIndex ?? 1], 'targetRef')
    ?? doc?.nodes.find((n) => n.type === (cap?.tgtNodeType ?? 'endpoint_select'))
  const srcDsKey = cap?.srcDsKey ?? 'ds'
  const srcTableKey = cap?.srcTableKey ?? 'table'
  const tgtDsKey = cap?.tgtDsKey ?? 'ds'
  const tgtTableKey = cap?.tgtTableKey ?? 'table'
  const srcDs = String(srcNode?.data?.[srcDsKey] ?? '')
  const srcTable = String(srcNode?.data?.[srcTableKey] ?? '')
  const tgtDs = String(tgtNode?.data?.[tgtDsKey] ?? '')
  const tgtTable = String(tgtNode?.data?.[tgtTableKey] ?? '')
  return {
    srcCols: columnsOf(pickTrees.value[srcDs] ?? null, srcTable),
    tgtCols: columnsOf(pickTrees.value[tgtDs] ?? null, tgtTable),
    srcErr: pickTreeErr.value[srcDs] ?? '',
    tgtErr: pickTreeErr.value[tgtDs] ?? '',
    srcLoading: !!pickTreeBusy.value[srcDs],
    tgtLoading: !!pickTreeBusy.value[tgtDs],
    srcNoTable: !srcTable,
    tgtNoTable: !tgtTable,
  }
})

/* ================= token-insert（I12 T12 C11 库/表侧栏选择器）：点选表把 SELECT 骨架插入目标字段 ================= */
function onTokenInsert(path: unknown) {
  const arr = Array.isArray(path) ? path : []
  const schemaName = String(arr[0] ?? '')
  const table = String(arr[1] ?? '')
  if (!table) return
  const token = `SELECT * FROM \`${schemaName}\`.\`${table}\` LIMIT 100`
  const target = props.field.cap?.insertKey ?? 'sql'
  const cur = String(props.data[target] ?? '').replace(/\s*$/, '')
  props.data[target] = cur ? `${cur}\n${token}` : token
  markDirty()
  // 插入点聚焦 + 光标置末尾（I12 评审修）：父层持 Inspector 根元素引用定位（nextTick 等 patch 完再定位）
  emit('focusTarget', target)
}

/* ================= topic 派生（ds 名 → 枚举缓存/错误/加载态；刷新钮强制重拉） ================= */
const topicDsName = computed(() => String(props.data[pickCfg(props.field).dsKey] ?? ''))
const topicOptsList = computed(() => topicOpts.value[topicDsName.value] ?? [])
const topicErrMsg = computed(() => topicErr.value[topicDsName.value] ?? '')
const topicBusyNow = computed(() => !!topicBusy.value[topicDsName.value])
function topicRefresh(): void {
  void ensureTopics(topicDsName.value, true)
}

/* ================= dir-select（运行时节点 → SFTP 目录懒加载，选中写回完整路径） ================= */
const EMPTY_DIR: DirNav = { path: '', dirs: [], err: '', seq: 0 }
function dirNav(): DirNav {
  return dirNavs.value[props.field.key] ?? EMPTY_DIR
}
function dirNodeId(): number | string | null {
  const nodeName = String(props.data[pickCfg(props.field).nodeKey] ?? '')
  if (!nodeName) return null
  const hit = runtimeNodes.value.find((r) => r.name === nodeName)
  return hit ? hit.id : null
}
function dirEnter(name: string): void {
  const id = dirNodeId()
  const st = dirNavs.value[props.field.key]
  if (id == null || !st) return
  lsDir(props.field.key, id, dirJoin(st.path, name))
}
function dirTo(path: string): void {
  const id = dirNodeId()
  if (id == null) return
  lsDir(props.field.key, id, path)
}
function pickDir(): void {
  const st = dirNavs.value[props.field.key]
  if (!st?.path) return
  props.data[props.field.key] = st.path
  markDirty()
}

/* ================= C17 反选探测（mapEditor probe）：目标表为基准，探测源库同名/前缀匹配的表，勾选回填 schemas =================
   探测状态为本组件实例私有（每字段一个实例，门直接用 probeHits 非空判定，无需字段 key 比对防引用漂移） */
interface ProbeHit { db: string; table: string }
const probeHits = ref<ProbeHit[]>([])
const probeChecked = ref<string[]>([])
const probeBusy = ref(false)

/** 探测：cap.dsKey=源数据源字段，cap.tableKey=目标表字段（缺省 readerDs/writerTable）；cap.excludeDsKey=排除其默认库（缺省 writerDs，防目标表自写自读） */
async function runProbe() {
  probeHits.value = []
  probeChecked.value = []
  const fld = props.field
  const dsKey = fld.cap?.dsKey ?? 'readerDs'
  const tableKey = fld.cap?.tableKey ?? 'writerTable'
  const excludeDsKey = fld.cap?.excludeDsKey ?? 'writerDs'
  const dsName = String(props.data[dsKey] ?? '')
  const target = String(props.data[tableKey] ?? '')
  // 写端默认库排除：同源实例时目标库不参与探测（目标表自身不入源）
  const excludeRow = dsRows.value.find((r) => r.name === String(props.data[excludeDsKey] ?? ''))
  const excludeDb = excludeRow?.db ?? null
  if (!dsName) { ElMessage.warning('请先选择源数据源（读端数据源）'); return }
  if (!target) { ElMessage.warning('请先填写目标表名（写端目标表名）'); return }
  const row = dsRows.value.find((r) => r.name === dsName)
  if (!row || row.id == null) { ElMessage.warning(`数据源「${dsName}」未加载，无法探测`); return }
  probeBusy.value = true
  try {
    const tree = await getDataSourceTree(row.id)
    if (tree.kind !== 'connection') { ElMessage.warning('该数据源非连接型，无法检测库表'); return }
    const hits: ProbeHit[] = []
    for (const db of tree.databases) {
      // 跳过写端默认库（防自写自读）；其余库全部纳入匹配
      if (excludeDb && db.name === excludeDb) continue
      for (const t of db.tables) {
        // 同名或前缀匹配（目标表名为匹配表名前缀）；跳过空名
        if (t.name && (t.name === target || t.name.startsWith(target))) hits.push({ db: db.name, table: t.name })
      }
    }
    if (!hits.length) {
      ElMessage.info(
        excludeDb
          ? `源库未发现与「${target}」同名或前缀匹配的表（已排除写端默认库 ${excludeDb}）`
          : `源库未发现与「${target}」同名或前缀匹配的表`,
      )
      return
    }
    probeHits.value = hits
    probeChecked.value = hits.map((h) => `${h.db}.${h.table}`)
  } catch (e) {
    ElMessage.error(`探测失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    probeBusy.value = false
  }
}

/** 确定回填：勾选 schema 全部选中 → 保留自动纳入（autoSchema=true）；部分勾选 → 锁定清单（false） */
function applyProbe() {
  if (!probeHits.value.length) return
  const checked = probeChecked.value.filter((k) => probeHits.value.some((h) => `${h.db}.${h.table}` === k))
  if (!checked.length) { ElMessage.warning('请至少勾选一个匹配表'); return }
  const schemas = [...new Set(checked.map((k) => k.split('.')[0]))]
  const tables = [...new Set(checked.map((k) => k.slice(k.indexOf('.') + 1)))]
  const d = props.data
  d.readerTable = tables.length === 1 ? tables[0] : String(d.writerTable ?? tables[0])
  d.readerSchemasText = schemas.join(',')
  d.autoSchema = checked.length >= probeHits.value.length
  // 多 schema 反选自动切换标识列策略（与 C23 target_base 语义一致）；单表保持原策略
  if (schemas.length > 1) { d.strategy = 'src_flag'; d.flagColumn = d.flagColumn ?? 'src_schema' }
  markDirty()
  ElMessage.success(`已回填 ${schemas.length} 个 schema：${schemas.join(', ')}`)
  probeHits.value = []
  probeChecked.value = []
}

/* ================= C37 探测联动勾选（endpoint_select probeResult）：勾选与逗号文本双向同步 ================= */
/** 勾选切换：回写 probeResult 逗号文本（保持既有勾选顺序，新增追加尾部；手填条目保留） */
function epProbeToggle(key: string, ev: Event) {
  const cur = String(props.data.probeResult ?? '').split(',').map((s) => s.trim()).filter(Boolean)
  const next = (ev.target as HTMLInputElement).checked ? [...cur, key] : cur.filter((k) => k !== key)
  props.data.probeResult = next.join(',')
  markDirty()
}
/** 全选/清空：全选写全部命中候选；清空写 ''（留空 = 探测全部匹配，与字段占位语义一致） */
function epProbeSetAll(all: boolean) {
  const st = epProbe.value
  if (!st) return
  props.data.probeResult = all ? st.hits.map((h) => `${h.schema}.${h.table}`).join(',') : ''
  markDirty()
}

/* ================= 脚本库脚本选择（language 字段）：选择时与内联代码不一致仅提示 ================= */
function onScriptChange(ev: Event) {
  emit('set', props.field, ev)
  const sid = String(props.data.scriptId ?? '')
  const s = sid ? scripts.value.find((x) => x.id === sid) : null
  const code = String(props.data.code ?? '')
  if (s && code && s.code !== code) {
    ElMessage.info('节点代码与脚本库代码不一致：可「载入代码」覆盖，或「保存到脚本库」回存')
  }
}

/* ================= 分支编辑（rowsKind='branches'）：每分支独立表单 + 独立端点 ================= */
const branches = computed<BranchDef[]>(() => {
  const v = props.data.branches
  return Array.isArray(v) ? (v as BranchDef[]) : []
})

/** 浅拷贝替换 doc 触发画布重同步（边/端点级变更需重建 flowEdges） */
function resync() {
  const d = graphStore.doc
  if (d) graphStore.replace({ ...d })
}

function ensureBranches(): BranchDef[] {
  if (!Array.isArray(props.data.branches)) props.data.branches = []
  return props.data.branches as BranchDef[]
}

function setBranch(b: BranchDef, part: 'name' | 'expr', ev: Event) {
  b[part] = (ev.target as HTMLInputElement).value
  if (part === 'name') {
    // 分支名即连线标注：改名同步既有边 label
    graphStore.doc?.edges.forEach((e) => {
      if (e.source === props.nodeId && e.sourceHandle === b.id) e.label = b.name || undefined
    })
    resync()
  }
  markDirty()
}

/** 新增分支 = 节点右侧新增一个可连线端点 */
function addBranch() {
  const list = ensureBranches()
  list.push({ id: uid('br'), name: `分支${list.length + 1}`, expr: '' })
  markDirty()
}

/** 删除分支：移除端点并清理该分支的所有连线 */
function delBranch(i: number) {
  const list = ensureBranches()
  const b = list[i]
  if (!b) return
  list.splice(i, 1)
  const doc = graphStore.doc
  if (doc) doc.edges = doc.edges.filter((e) => !(e.source === props.nodeId && e.sourceHandle === b.id))
  resync()
  markDirty()
}
</script>

<template>
  <!-- select 动态候选：exec-node-tags（I7 F53 ssh-nodes 标签并集；选中后隐藏 runtime-node 字段） -->
  <select
    v-if="field.type === 'select' && field.selectFrom === 'exec-node-tags'"
    :value="String(data[field.key] ?? '')" :disabled="mode === 'view'" @change="emit('set', field, $event)"
  >
    <option value="">不使用标签（按运行时节点直连）</option>
    <option v-for="t in tagOptions" :key="t" :value="t">{{ t }}</option>
  </select>
  <!-- F3 数据驱动值域 select（dataScope 声明：候选只来自 DataContext 对应域；域空禁用并说明原因，
       值域外存量值兜底展示不静默丢值） -->
  <template v-else-if="field.type === 'select' && field.dataScope">
    <select
      :value="String(data[field.key] ?? '')"
      :disabled="mode === 'view' || !!scope?.disabledReason"
      :title="scope?.disabledReason || undefined" @change="emit('set', field, $event)"
    >
      <option value="">{{ scope?.disabledReason ? '（值域为空）' : '请选择…' }}</option>
      <option v-if="curOutside" :value="curOutside">{{ curOutside }}（值域外）</option>
      <option v-for="o in scope?.options ?? []" :key="o" :value="o">{{ o }}</option>
    </select>
    <div v-if="scope?.disabledReason" class="blk-hint">{{ scope.disabledReason }}</div>
  </template>
  <!-- select：静态候选 -->
  <select
    v-else-if="field.type === 'select'"
    :value="String(data[field.key] ?? '')" :disabled="mode === 'view'" @change="emit('set', field, $event)"
  >
    <option v-for="o in field.options ?? []" :key="o.value" :value="o.value">{{ o.label }}</option>
  </select>
  <!-- 脚本库脚本（language 存在）：select + 载入/回存/另存（与脚本任务模块互通） -->
  <template v-else-if="field.type === 'text' && field.language">
    <select
      :value="String(data[field.key] ?? '')" :disabled="mode === 'view'"
      @change="onScriptChange($event)"
    >
      <option value="">不引用（内联脚本）</option>
      <option v-for="s in scripts" :key="s.id" :value="s.id">{{ s.id }} {{ s.name }}（{{ s.lang }}）</option>
    </select>
    <div class="script-btns">
      <button :disabled="mode === 'view'" @click="loadScriptCode">载入代码</button>
      <button :disabled="mode === 'view'" @click="saveToScript">保存到脚本库</button>
      <button :disabled="mode === 'view'" @click="saveAsNewScript">另存为新脚本</button>
    </div>
  </template>
  <!-- 多行文本（multiline）：class mono + data-fkey（token-insert 插入聚焦定位锚点） -->
  <textarea
    v-else-if="field.type === 'text' && field.multiline" :rows="field.rows ?? 4"
    :value="String(data[field.key] ?? '')" :placeholder="field.placeholder"
    :disabled="mode === 'view'" class="mono" :data-fkey="field.key"
    @change="emit('set', field, $event)"
  />
  <!-- C37 探测候选联动（设计 §3.1）：endpoint_select probeResult 字段 = 文本框 + 匹配候选区，
       勾选与 probeResult 文本（逗号分隔 schema.table）双向同步；联动未激活时回落普通文本输入 -->
  <template v-else-if="field.type === 'text' && field.key === 'probeResult' && epProbe">
    <input
      type="text"
      :value="String(data[field.key] ?? '')" :placeholder="field.placeholder"
      :disabled="mode === 'view'" @change="emit('set', field, $event)"
    />
    <div class="ep-probe">
      <div v-if="epProbe.loading" class="blk-hint">源端库表加载中…</div>
      <div v-else-if="epProbe.err" class="pick-err">{{ epProbe.err }}</div>
      <div v-else-if="epProbe.noTgt" class="blk-hint">请先选择目标表（或填写匹配前缀），再探测源实例匹配表</div>
      <template v-else>
        <div class="probe-actions">
          <span class="probe-tip">共 {{ epProbe.hits.length }} 个匹配（勾选 = 纳入）</span>
          <button class="probe-mini" :disabled="mode === 'view' || !epProbe.hits.length" @click="epProbeSetAll(true)">全选</button>
          <button class="probe-mini" :disabled="mode === 'view'" @click="epProbeSetAll(false)">清空</button>
        </div>
        <div v-if="!epProbe.hits.length" class="blk-hint">无匹配表</div>
        <div v-else class="probe-list">
          <label v-for="h in epProbe.hits" :key="h.schema + '.' + h.table" class="probe-item">
            <input
              type="checkbox"
              :checked="epProbe.checked.includes(h.schema + '.' + h.table)"
              :disabled="mode === 'view'"
              @change="epProbeToggle(h.schema + '.' + h.table, $event)"
            />
            <span class="mono">{{ h.schema }}.{{ h.table }}</span>
          </label>
        </div>
        <div class="probe-tip">留空 = 探测全部匹配</div>
      </template>
    </div>
  </template>
  <!-- 分支编辑（rowsKind='branches'）：每分支独立表单（分支名+表达式），新增即新增端点 -->
  <template v-else-if="field.type === 'rows' && field.rowsKind === 'branches'">
    <div class="br-list">
      <div v-for="(b, i) in branches" :key="b.id" class="br-row">
        <input
          class="br-name" :value="b.name" placeholder="分支名"
          :disabled="mode === 'view'"
          @change="setBranch(b, 'name', $event)"
        />
        <input
          class="br-expr" :value="b.expr" placeholder="条件表达式 / 匹配值"
          :disabled="mode === 'view'"
          @change="setBranch(b, 'expr', $event)"
        />
        <button
          class="br-del" title="删除该分支端点及其连线"
          :disabled="mode === 'view' || branches.length <= 1"
          @click="delBranch(i)"
        >×</button>
      </div>
      <button v-if="mode === 'edit'" class="br-add" @click="addBranch">＋ 新增分支端点</button>
    </div>
    <div style="font-size:10.5px;color:var(--text-3);margin-top:4px">每个分支是节点右侧一个独立端点，可单独连线；连线自动标注分支名</div>
  </template>
  <!-- 行编辑表：kv（键/值/说明）/ params（键/值/来源五选一）/ args（I4 C15 过程参数）/ var（I7 C21 变量表） -->
  <RowsField
    v-else-if="field.type === 'rows' && (field.rowsKind === 'kv' || field.rowsKind === 'params' || field.rowsKind === 'args' || field.rowsKind === 'var')"
    :rows="formRows(field.key)"
    :mode="field.rowsKind === 'kv' ? 'kv' : field.rowsKind === 'args' ? 'args' : field.rowsKind === 'var' ? 'vars' : 'params'"
    :disabled="mode === 'view'" @change="emit('dirty')"
  />
  <!-- 依赖项列表（I7 C9：工作流+节点级联+可选变量条件；排除当前文档防自依赖） -->
  <DepsField
    v-else-if="field.type === 'rows' && field.rowsKind === 'deps'"
    :rows="formRows(field.key)" :exclude-id="graphStore.doc?.id"
    :disabled="mode === 'view'" @change="emit('dirty')"
  />
  <!-- resource·datasource（数据源中心下拉，cap.dsTypes 过滤类型） -->
  <select
    v-else-if="field.type === 'resource' && field.cap?.mode === 'datasource'"
    :value="String(data[field.key] ?? '')" :disabled="mode === 'view'" @change="emit('set', field, $event)"
  >
    <option value="">请选择数据源…</option>
    <option v-for="o in dsOpts()" :key="o.value" :value="o.value">{{ o.label }}</option>
  </select>
  <!-- resource·runtimeNode（I3 C14 SSH 运行时节点下拉，取值 = 节点名，worker 按名称解析） -->
  <select
    v-else-if="field.type === 'resource' && field.cap?.mode === 'runtimeNode'"
    :value="String(data[field.key] ?? '')" :disabled="mode === 'view'" @change="emit('set', field, $event)"
  >
    <option value="">请选择运行时节点…</option>
    <option v-for="rn in runtimeNodes" :key="rn.id" :value="rn.name">{{ rn.name }}（{{ rn.host }}:{{ rn.port }}）</option>
  </select>
  <!-- resource·upstreamNodes（I12 T11 C25 上游节点引用，选项=画布直接上游节点；空=自动扫描直接上游目标表） -->
  <select
    v-else-if="field.type === 'resource' && field.cap?.mode === 'upstreamNodes'"
    :value="String(data[field.key] ?? '')" :disabled="mode === 'view'" @change="emit('set', field, $event)"
  >
    <option value="">（自动扫描直接上游目标表）</option>
    <option v-for="u in upstream" :key="u.id" :value="u.id">{{ String(u.data.name ?? u.id) }}（{{ upSchema(u).label }}）</option>
  </select>
  <!-- resource·upstreamOutputs：上游节点输出多选（从画布上游节点中选择） -->
  <template v-else-if="field.type === 'resource' && field.cap?.mode === 'upstreamOutputs'">
    <div class="ur-table">
      <div class="ur-head">
        <span class="ur-col">上游节点</span>
        <span class="ur-col ur-act"></span>
      </div>
      <div v-for="(sel, i) in (data[field.key] as string[])" :key="i" class="ur-row">
        <select :value="sel" :disabled="mode === 'view'" @change="onUpstreamRefChange(i, $event)">
          <option value="">请选择上游节点输出…</option>
          <!-- 旧格式引用兜底（无端口 `id` / 空端口 `id:`）：老文档打开不崩，显式展示便于重新选择具名端口 -->
          <option v-if="sel && !upstreamOpts.some((o) => o.value === sel)" :value="sel">{{ sel }}（旧引用）</option>
          <option v-for="opt in upstreamOpts" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <button class="ur-del" :disabled="mode === 'view'" @click="onUpstreamRefRemove(i)">✕</button>
      </div>
      <div v-if="!(data[field.key] as string[])?.length" class="ur-empty">
        未选择上游输出（最多 {{ field.cap?.upstreamMax ?? 1 }} 个）
      </div>
    </div>
    <button class="ur-add"
      :disabled="mode === 'view' || (data[field.key] as string[])?.length >= (field.cap?.upstreamMax ?? 1)"
      @click="onUpstreamRefAdd()">
      ＋ 添加上游输出
    </button>
  </template>
  <!-- resource·table（I12 T10：数据源→库→表两级级联；写回纯表名或 {schema,table}；清空 payload=null 写回 ''） -->
  <template v-else-if="field.type === 'resource' && field.cap?.mode === 'table'">
    <el-cascader
      class="pick-casc"
      :model-value="tp?.path ?? NO_PATH"
      :options="tp?.opts ?? NO_OPTS"
      :disabled="mode === 'view' || !!tp?.depEmpty"
      placeholder="选择库 / 表…" clearable filterable
      @change="onTablePick($event)"
    />
    <div v-if="tp?.depEmpty" class="blk-hint">请先在「{{ tp?.dsLabel }}」选择数据源</div>
    <div v-else-if="tp?.loading" class="blk-hint">库表加载中…</div>
    <div v-else-if="tp?.err" class="pick-err">{{ tp?.err }}</div>
  </template>
  <!-- resource·column（I12 T10：列枚举多选写回数组；列来自已缓存库表树，免二次请求；
       cap.multi=false 单选写回字符串（C19 join 键）；src='upstream' 时无候选降级为可直接输入） -->
  <template v-else-if="field.type === 'resource' && field.cap?.mode === 'column'">
    <el-select
      v-if="!fs?.multi"
      class="pick-multi"
      :model-value="fs?.val1 ?? ''"
      filterable allow-create default-first-option clearable
      placeholder="选择 / 输入字段…"
      :disabled="mode === 'view'"
      @change="onFieldsPick($event)"
    >
      <el-option v-for="c in fs?.cols ?? NO_COLS" :key="c" :label="c" :value="c" />
    </el-select>
    <el-select
      v-else
      class="pick-multi"
      :model-value="fs?.val ?? NO_COLS" multiple filterable collapse-tags collapse-tags-tooltip
      placeholder="选择字段…" clearable
      :disabled="mode === 'view' || !fs?.cols.length"
      @change="onFieldsPick($event)"
    >
      <el-option v-for="c in fs?.cols ?? NO_COLS" :key="c" :label="c" :value="c" />
    </el-select>
    <div v-if="fs?.noTable" class="blk-hint">{{ fs?.multi ? `请先在「${fs?.tableLabel}」选择表` : '上游流输入未声明 CDC 源表，可直接输入字段名' }}</div>
    <div v-else-if="fs?.loading" class="blk-hint">库表加载中…</div>
    <div v-else-if="fs?.err" class="pick-err">{{ fs?.err }}</div>
    <div v-else-if="!fs?.cols.length" class="blk-hint">未获取到字段（表不在该数据源库表树中）</div>
  </template>
  <!-- resource·topic（I12 T10：经 dsRef 解析 ds_id 枚举 Kafka topic + 刷新钮） -->
  <template v-else-if="field.type === 'resource' && field.cap?.mode === 'topic'">
    <div class="expr-row">
      <select :value="String(data[field.key] ?? '')" :disabled="mode === 'view'" @change="emit('set', field, $event)">
        <option value="">{{ topicBusyNow ? 'topic 枚举中…' : (topicOptsList.length ? '请选择 topic…' : '暂无可选 topic') }}</option>
        <option v-for="t in topicOptsList" :key="t" :value="t">{{ t }}</option>
      </select>
      <button class="var-btn" :disabled="mode === 'view'" title="重新枚举 topic" @click="topicRefresh">⟳</button>
    </div>
    <div v-if="depEmpty()" class="blk-hint">请先在「{{ depLabel(pickCfg(field).dsKey) }}」选择数据流源</div>
    <div v-else-if="topicBusyNow" class="blk-hint">topic 枚举中…</div>
    <div v-else-if="topicErrMsg" class="pick-err">{{ topicErrMsg }}</div>
  </template>
  <!-- resource·dir（I12 T10：运行时节点目录懒加载浏览，选中写回完整路径） -->
  <template v-else-if="field.type === 'resource' && field.cap?.mode === 'dir'">
    <div class="dir-crumbs">
      <button
        v-for="c in dirCrumbs(dirNav().path)" :key="c.path" class="dir-crumb"
        :disabled="mode === 'view'" @click="dirTo(c.path)"
      >{{ c.name }}</button>
      <span v-if="!dirNav().path && !dirNav().err" class="blk-hint">目录加载中…</span>
    </div>
    <div class="dir-list">
      <button
        v-for="sub in dirNav().dirs" :key="sub.name" class="dir-item"
        :disabled="mode === 'view'" @click="dirEnter(sub.name)"
      >📁 {{ sub.name }}</button>
      <div v-if="dirNav().path && !dirNav().dirs.length && !dirNav().err" class="blk-empty">无子目录</div>
    </div>
    <div class="dir-actions">
      <button class="dir-ok" :disabled="mode === 'view' || !dirNav().path" @click="pickDir">选中当前目录</button>
      <span class="dir-cur mono">{{ String(data[field.key] ?? '') || '未选择' }}</span>
    </div>
    <div v-if="!String(data[pickCfg(field).nodeKey] ?? '')" class="blk-hint">请先在「{{ depLabel(pickCfg(field).nodeKey) }}」选择运行时节点</div>
    <div v-else-if="dirNav().err" class="pick-err">{{ dirNav().err }}</div>
  </template>
  <!-- mapEditor·probe（I8 C17 反选探测：目标表为基准，探测源库同名/前缀匹配的表，勾选回填） -->
  <div v-else-if="field.type === 'mapEditor' && field.mapMode === 'probe'" class="probe-box">
    <button class="probe-btn" :disabled="mode === 'view' || probeBusy" @click="runProbe">
      {{ probeBusy ? '探测中…' : '🔍 探测匹配表' }}
    </button>
    <div class="probe-hint">按目标表名探测源库所有 schema 中同名或前缀匹配的表，默认全选，可重新勾选</div>
    <div v-if="probeHits.length" class="probe-list">
      <label v-for="h in probeHits" :key="h.db + '.' + h.table" class="probe-item">
        <input
          type="checkbox" :value="h.db + '.' + h.table"
          v-model="probeChecked"
          :disabled="mode === 'view'"
        />
        <span class="mono">{{ h.db }}.{{ h.table }}</span>
      </label>
      <div class="probe-actions">
        <button class="probe-ok" :disabled="mode === 'view' || !probeChecked.length" @click="applyProbe">
          确定回填（{{ probeChecked.length }}/{{ probeHits.length }}）
        </button>
        <span class="probe-tip">回填到 参与 schema / 自动纳入 / 标识列策略</span>
      </div>
    </div>
  </div>
  <!-- mapEditor·insert（I12 T12 C11：点选表把 SELECT 骨架插入 SQL 编辑器，追加不覆盖手写；选中态复位便于重复点选） -->
  <template v-else-if="field.type === 'mapEditor' && field.mapMode === 'insert'">
    <el-cascader
      class="pick-casc"
      :model-value="NO_PATH"
      :options="tp?.opts ?? NO_OPTS"
      :disabled="mode === 'view' || !!tp?.depEmpty"
      placeholder="点选库 / 表插入 SELECT 骨架…" filterable
      @change="onTokenInsert($event)"
    />
    <div v-if="tp?.depEmpty" class="blk-hint">请先在「{{ tp?.dsLabel }}」选择数据源</div>
    <div v-else-if="tp?.loading" class="blk-hint">库表加载中…</div>
    <div v-else-if="tp?.err" class="pick-err">{{ tp?.err }}</div>
  </template>
  <!-- mapEditor·map：字段映射（源字段→目标字段映射，左右两列下拉 + 转换表达式），列枚举来自 cap 指定的源/目标节点 -->
  <template v-else-if="field.type === 'mapEditor' && field.mapMode === 'map'">
    <div class="fm-table">
      <div class="fm-head">
        <span class="fm-col">源字段</span>
        <span class="fm-arrow">→</span>
        <span class="fm-col">目标字段</span>
        <span class="fm-col">转换表达式</span>
        <span class="fm-col fm-act"></span>
      </div>
      <div v-for="(row, i) in (data[field.key] as { src: string; tgt: string; expr?: string }[])" :key="i" class="fm-row">
        <select :value="row.src" :disabled="mode === 'view' || !fm?.srcCols.length" @change="onFieldMapChange(i, 'src', $event)">
          <option value="">请选择源字段…</option>
          <option v-for="c in fm?.srcCols ?? NO_COLS" :key="c" :value="c">{{ c }}</option>
        </select>
        <span class="fm-arrow">→</span>
        <select :value="row.tgt" :disabled="mode === 'view' || !fm?.tgtCols.length" @change="onFieldMapChange(i, 'tgt', $event)">
          <option value="">请选择目标字段…</option>
          <option v-for="c in fm?.tgtCols ?? NO_COLS" :key="c" :value="c">{{ c }}</option>
        </select>
        <input :value="row.expr ?? ''" :disabled="mode === 'view'" placeholder="如 upper(name)" @change="onFieldMapChange(i, 'expr', $event)" />
        <button class="fm-del" :disabled="mode === 'view'" @click="onFieldMapRemove(i)">✕</button>
      </div>
      <div v-if="!(data[field.key] as unknown[])?.length" class="fm-empty">暂无映射行（留空 = 同名全列映射）</div>
    </div>
    <button class="fm-add" :disabled="mode === 'view'" @click="onFieldMapAdd">＋ 新增映射</button>
    <div v-if="fm?.srcNoTable" class="blk-hint">请先在「源端选择」节点选择源表</div>
    <div v-else-if="fm?.srcLoading" class="blk-hint">源表加载中…</div>
    <div v-else-if="fm?.srcErr" class="pick-err">{{ fm?.srcErr }}</div>
    <div v-if="fm?.tgtNoTable" class="blk-hint">请先在「目标端选择」节点选择目标表</div>
    <div v-else-if="fm?.tgtLoading" class="blk-hint">目标表加载中…</div>
    <div v-else-if="fm?.tgtErr" class="pick-err">{{ fm?.tgtErr }}</div>
  </template>
  <!-- hint（纯提示文案，text(data) 动态产出或 placeholder 静态） -->
  <div v-else-if="field.type === 'hint'" class="blk-hint">{{ field.text ? (typeof field.text === 'function' ? field.text(data) : field.text) : (field.placeholder ?? '') }}</div>
  <!-- expr（表达式 + 变量引用弹窗） -->
  <div v-else-if="field.type === 'expr' && !field.readonly" class="expr-row">
    <input
      class="mono" :value="String(data[field.key] ?? '')" :placeholder="field.placeholder"
      :disabled="mode === 'view'" @change="onExprChange($event)"
    />
    <button class="var-btn" :disabled="mode === 'view'" title="引用变量" @click="emit('openVarDialog', 'f:' + field.key)">$</button>
  </div>
  <!-- expr readonly（原 var-ref：变量引用选择器）；dataScope 声明时候选收窄到对应域，域空禁用并说明（F3） -->
  <template v-else-if="field.type === 'expr' && field.readonly">
    <select
      :value="String(data[field.key] ?? '')"
      :disabled="mode === 'view' || (!!field.dataScope && !!scope?.disabledReason)"
      :title="scope?.disabledReason || undefined" @change="emit('set', field, $event)"
    >
      <option value="">不引用</option>
      <option v-for="v in (field.dataScope ? scope?.options ?? [] : varOptions)" :key="v" :value="'${' + v + '}'">${{ '{' + v + '}' }}</option>
    </select>
    <div v-if="field.dataScope && scope?.disabledReason" class="blk-hint">{{ scope.disabledReason }}</div>
  </template>
  <!-- bool（开关） -->
  <label v-else-if="field.type === 'bool'" class="bool-row">
    <input type="checkbox" :checked="!!data[field.key]" :disabled="mode === 'view'" @change="onBool($event)" />
    <span>{{ field.placeholder ?? '启用' }}</span>
  </label>
  <!-- 兜底：number（change 转数值存储）/ text 单行 -->
  <input
    v-else :type="field.type === 'number' ? 'number' : 'text'"
    :value="String(data[field.key] ?? '')" :placeholder="field.placeholder"
    :disabled="mode === 'view'" @change="emit('set', field, $event)"
  />
</template>

<style scoped>
/* 表达式 + 变量引用按钮（与 Inspector 头部条件/排除区共用样式名，scoped 各自生效） */
.expr-row{display:flex;gap:4px;align-items:center}
.expr-row input{flex:1;min-width:0}
.var-btn{width:26px;height:26px;flex-shrink:0;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);color:var(--text-2);font-size:12px;cursor:pointer;font-weight:700}
.var-btn:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.var-btn:disabled{opacity:.4;cursor:not-allowed}
.bool-row{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text-2);cursor:pointer}
/* 分支编辑器 */
.br-list{display:flex;flex-direction:column;gap:5px}
.br-row{display:flex;gap:4px;align-items:center}
.br-name{width:76px;flex-shrink:0;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:5px 6px;font-size:12px;outline:none}
.br-name:focus{border-color:var(--primary)}
.br-expr{flex:1;min-width:0;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:5px 6px;font-size:12px;outline:none;font-family:var(--mono,monospace)}
.br-expr:focus{border-color:var(--primary)}
.br-del{width:24px;height:24px;flex-shrink:0;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);color:var(--text-3);font-size:13px;line-height:1;cursor:pointer}
.br-del:hover:not(:disabled){border-color:var(--danger);color:var(--danger)}
.br-del:disabled{opacity:.4;cursor:not-allowed}
.br-add{border:1px dashed var(--border-strong);background:var(--bg);border-radius:var(--radius-sm);padding:5px 0;font-size:11.5px;color:var(--text-2);cursor:pointer}
.br-add:hover{border-color:var(--primary);color:var(--primary)}
/* 脚本库互通按钮组 */
.script-btns{display:flex;gap:6px;margin-top:6px}
.script-btns button{flex:1;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 0;font-size:11px;cursor:pointer;color:var(--text-2)}
.script-btns button:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.script-btns button:disabled{opacity:.5;cursor:not-allowed}
/* I8 C17 反选探测（probe 字段） */
.probe-box{display:flex;flex-direction:column;gap:6px}
.probe-btn{border:1px solid var(--primary);background:var(--primary-light);color:var(--primary);border-radius:var(--radius-sm);padding:6px 0;font-size:12px;cursor:pointer;font-weight:600}
.probe-btn:hover:not(:disabled){background:var(--primary);color:#fff}
.probe-btn:disabled{opacity:.5;cursor:not-allowed}
.probe-hint{font-size:10px;color:var(--text-3)}
.probe-list{display:flex;flex-direction:column;gap:3px;border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 8px;background:var(--bg)}
.probe-item{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text-2);cursor:pointer}
.probe-item input{accent-color:var(--primary)}
.probe-actions{display:flex;align-items:center;gap:8px;margin-top:4px}
.probe-ok{border:1px solid var(--primary);background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:4px 10px;font-size:11.5px;cursor:pointer}
.probe-ok:hover:not(:disabled){opacity:.85}
.probe-ok:disabled{opacity:.5;cursor:not-allowed}
.probe-tip{font-size:10px;color:var(--text-3)}
/* C37 endpoint_select 探测候选区（复用 probe 控件样式；迷你按钮变体 + 区块留白） */
.ep-probe{display:flex;flex-direction:column;gap:4px;margin-top:6px}
/* 候选清单滚动上限（候选多时不撑爆面板；仅限 ep 联动区） */
.ep-probe .probe-list{max-height:140px;overflow:auto}
.probe-mini{border:1px solid var(--border);background:var(--bg);color:var(--text-2);border-radius:var(--radius-sm);padding:2px 8px;font-size:10.5px;cursor:pointer}
.probe-mini:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.probe-mini:disabled{opacity:.5;cursor:not-allowed}
/* I12 T10 动态控件（选择代替填空） */
.pick-err{font-size:10.5px;color:var(--danger);word-break:break-all}
.pick-casc,.pick-multi{width:100%}
.dir-crumbs{display:flex;flex-wrap:wrap;gap:2px;align-items:center}
.dir-crumb{border:1px solid var(--border-strong);background:var(--bg);border-radius:var(--radius-sm);padding:2px 6px;font-size:10.5px;color:var(--text-2);cursor:pointer}
.dir-crumb:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.dir-crumb:last-child{border-color:var(--primary);color:var(--primary);font-weight:600}
.dir-list{display:flex;flex-wrap:wrap;gap:4px;border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px;background:var(--bg);max-height:140px;overflow:auto}
.dir-item{border:none;background:transparent;border-radius:var(--radius-sm);padding:3px 6px;font-size:11.5px;color:var(--text-2);cursor:pointer;text-align:left}
.dir-item:hover:not(:disabled){background:var(--primary-light);color:var(--primary)}
.dir-actions{display:flex;align-items:center;gap:8px}
.dir-ok{border:1px solid var(--primary);background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:4px 10px;font-size:11.5px;cursor:pointer}
.dir-ok:hover:not(:disabled){opacity:.85}
.dir-ok:disabled{opacity:.5;cursor:not-allowed}
.dir-cur{font-size:10.5px;color:var(--text-3);word-break:break-all}
/* 区块提示（blk-hint/blk-empty 与 Inspector 六区块共用样式名，scoped 各自生效） */
.blk-hint{font-size:10px;color:var(--text-3)}
.blk-empty{font-size:10.5px;color:var(--text-3)}
</style>
