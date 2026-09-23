<script setup lang="ts">
/**
 * Inspector 属性面板（F60 六区块 + F61 页面化入口）。
 * 结构（§8.2）：标题(C编号徽标+页面按钮) → ①输入 ②输出 ③参数 ④条件 ⑤限定约束 ⑥排除（框架级折叠面板）
 * → 业务配置(schema.form) → 关联信息。
 * 六区块数据存 node.data.inputs/outputs/params/condition/constraints/exclude；
 * 老节点无字段时显示默认空值（缺省懒初始化：首次编辑才落键），向后兼容既有裁定。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { GNode } from '../model'
import { uid } from '../model'
import type { BranchDef, FieldSchema, NodeSchema, ViewProfile } from '../profiles/types'
import { requiredMissing } from '../profiles/formLinkage'
import { useGraphStore } from '../../stores/graph'
import { useAuthStore } from '../../stores/auth'
import { useFloatStore } from '../../stores/float'
import { dataStore } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import { isMock, listRuntimeNodes, listSshNodes, listVariables } from '../../services'
import { getDataSourceTree, listDataSources, listKafkaTopics, listNodeDir } from '../../services/datasourceApi'
import type { DsRow, DsTree } from '../../services/datasourceApi'
import { columnsOf, dirCrumbs, dirJoin, pickCfg, resolveDsId, sortByCanvasX, tableOptions, tablePickPath, writeTablePick } from '../profiles/pickerLogic'
import type { PickOption } from '../profiles/pickerLogic'
import type { Script } from '../../services/types'
import RowsField from './fields/RowsField.vue'
import DepsField from './fields/DepsField.vue'

type KvRow = { k: string; v: string; note?: string }
type ParamRow = { key: string; value: string; source: string }
type Constraints = {
  timeoutMin?: number; timeoutPolicy?: string
  retryTimes?: number; retryInterval?: number
  failPolicy?: string; priority?: number; workerGroup?: string
}
type ExcludeDef = { skipCond?: string; disabled?: boolean }

const props = defineProps<{ node: GNode | null; profile: ViewProfile }>()

const auth = useAuthStore()
const floatStore = useFloatStore()
/** 系统权限降级（M15）：只读角色锁定编辑 */
const effMode = computed(() => (props.profile.mode === 'edit' && !auth.canEdit ? 'view' : props.profile.mode))
const emit = defineEmits<{ (e: 'delete', id: string): void }>()

const graphStore = useGraphStore()

const FALLBACK_SCHEMA: NodeSchema = { type: 'unknown', label: '未知', icon: '?', color: '#94a3b8', form: [] }

const schema = computed(() =>
  props.node ? props.profile.nodeTypes[props.node.type] ?? null : null)

function markDirty() { graphStore.markDirty() }

/* ================= F61 页面化入口（schema.page → 浮窗挂载，props {node, doc}） ================= */
const page = computed(() => schema.value?.page)
const pageVisible = computed(() =>
  !!page.value && (!page.value!.mode || page.value!.mode === effMode.value))
function openPage() {
  const p = page.value
  if (!p || !props.node || !graphStore.doc) return
  floatStore.open({
    id: `page_${props.node.id}`,
    title: p.title,
    x: 300 + (floatStore.floats.length % 3) * 30,
    y: 80 + (floatStore.floats.length % 3) * 30,
    w: p.w ?? 540,
    h: p.h ?? 400,
    minimized: false,
    comp: p.comp,
    props: { node: props.node, doc: graphStore.doc },
  })
}

/* ================= 六区块折叠状态 ================= */
const folds = ref<Record<string, boolean>>({
  inputs: true, outputs: true, params: true, condition: true, constraints: true, exclude: true,
})
function toggleBlk(k: string) { folds.value[k] = !folds.value[k] }

/* ================= ① 输入：上游只读列表 + 输入引用 ================= */
const upstream = computed<GNode[]>(() => {
  const doc = graphStore.doc
  if (!doc || !props.node) return []
  return doc.edges
    .filter((e) => e.target === props.node!.id)
    .map((e) => doc.nodes.find((n) => n.id === e.source))
    .filter((n): n is GNode => !!n)
})
function upSchema(n: GNode): NodeSchema {
  return props.profile.nodeTypes[n.type] ?? FALLBACK_SCHEMA
}
const inputRefs = computed<string[]>(() => {
  const v = props.node?.data.inputs
  return Array.isArray(v) ? (v as string[]) : []
})
/** 上游输出引用候选：上游节点 outputs.params/tables 汇总为「节点名.键（类型）」 */
const upstreamOuts = computed<string[]>(() => upstream.value.flatMap((u) => {
  const out = u.data.outputs as { params?: KvRow[]; tables?: KvRow[] } | undefined
  const name = String(u.data.name ?? u.id)
  return [
    ...((out?.params ?? []).filter((p) => p?.k).map((p) => `${name}.${p.k}（参数）`)),
    ...((out?.tables ?? []).filter((t) => t?.k).map((t) => `${name}.${t.k}（结果表）`)),
  ]
}))
function addInputRef(ev: Event) {
  if (!props.node) return
  const sel = ev.target as HTMLSelectElement
  const v = sel.value
  if (!v) return
  if (!Array.isArray(props.node.data.inputs)) props.node.data.inputs = []
  const list = props.node.data.inputs as string[]
  if (!list.includes(v)) { list.push(v); markDirty() }
  sel.value = ''
}
function delInputRef(i: number) {
  if (!props.node) return
  ;(props.node.data.inputs as string[]).splice(i, 1)
  markDirty()
}

/* ================= ② 输出：输出参数注册表 + 结果表注册表（kv-table） ================= */
function ensureOut(kind: 'params' | 'tables'): KvRow[] {
  const d = props.node?.data
  if (!d) return []
  if (typeof d.outputs !== 'object' || d.outputs === null || Array.isArray(d.outputs)) d.outputs = {}
  const o = d.outputs as { params?: KvRow[]; tables?: KvRow[] }
  if (!Array.isArray(o[kind])) o[kind] = []
  return o[kind]!
}
const outParams = computed<KvRow[]>(() => ensureOut('params'))
const outTables = computed<KvRow[]>(() => ensureOut('tables'))

/* ================= ③ 参数：params-table（键/值/来源五选一） ================= */
const nodeParams = computed<ParamRow[]>(() => {
  const d = props.node?.data
  if (!d) return []
  if (!Array.isArray(d.params)) d.params = []
  return d.params as ParamRow[]
})

/* ================= ④ 条件 / ⑥ 排除：表达式（expr + 变量引用弹窗） ================= */
function ensureExclude(): ExcludeDef {
  const d = props.node!.data
  if (typeof d.exclude !== 'object' || d.exclude === null || Array.isArray(d.exclude)) d.exclude = {}
  return d.exclude as ExcludeDef
}
const excl = computed<ExcludeDef>(() => (props.node ? ensureExclude() : {}))
function setDisabled(ev: Event) {
  ensureExclude().disabled = (ev.target as HTMLInputElement).checked
  markDirty()
}

/** 表达式目标统一寻址：condition | exclude | f:{formKey} */
function exprOf(target: string): string {
  if (!props.node) return ''
  if (target === 'condition') return String(props.node.data.condition ?? '')
  if (target === 'exclude') return String(excl.value.skipCond ?? '')
  if (target.startsWith('f:')) return String(props.node.data[target.slice(2)] ?? '')
  return ''
}
function setExprValue(target: string, v: string) {
  if (!props.node) return
  if (target === 'condition') props.node.data.condition = v
  else if (target === 'exclude') ensureExclude().skipCond = v
  else props.node.data[target.slice(2)] = v
  markDirty()
}
function setExpr(target: string, ev: Event) {
  setExprValue(target, (ev.target as HTMLInputElement).value)
}

/* 变量引用弹窗：下拉已注册变量 + 插入 ${var}（I1 仅 UI 层，解析引擎 I3） */
const BASE_VARS = ['run.instanceId', 'biz_date', 'system.date', 'system.datetime']
const varOptions = ref<string[]>([...BASE_VARS])
watch(() => graphStore.doc?.id, async (wf) => {
  if (!wf) return
  try {
    const rows = await listVariables(wf)
    const names = rows.map((r) => r.name).filter(Boolean).filter((n) => !BASE_VARS.includes(n))
    varOptions.value = [...BASE_VARS, ...names]
  } catch { /* real 后端未就绪时仅保留内置变量 */ }
}, { immediate: true })

const varDlg = ref(false)
const varTarget = ref('condition')
const varPick = ref('')
const varPreview = computed(() => exprOf(varTarget.value))
function openVarDialog(target: string) {
  varTarget.value = target
  varPick.value = ''
  varDlg.value = true
}
function insertVar() {
  if (!varPick.value) { ElMessage.warning('请选择要引用的变量'); return }
  const cur = exprOf(varTarget.value)
  const token = '${' + varPick.value + '}'
  setExprValue(varTarget.value, cur ? `${cur} ${token}` : token)
  varDlg.value = false
  ElMessage.success(`已插入 ${token}`)
}

/* ================= ⑤ 限定约束：固定字段组（框架内置，对齐海豚任务定义通用参数） ================= */
const C_DEF: Constraints = {
  timeoutMin: 60, timeoutPolicy: 'fail', retryTimes: 0,
  retryInterval: 1, failPolicy: 'stop', priority: 5, workerGroup: '默认',
}
const cons = computed<Constraints>(() =>
  (props.node?.data.constraints as Constraints | undefined) ?? C_DEF)
function setC(key: keyof Constraints, ev: Event) {
  if (!props.node) return
  const t = ev.target as HTMLInputElement | HTMLSelectElement
  let v: unknown = t.value
  if (t instanceof HTMLInputElement && t.type === 'number') {
    if (t.value === '') { v = undefined }
    else {
      let n = Number(t.value)
      if (!Number.isFinite(n)) return
      /* 值域校验（I3 §13）：超时/重试次数/重试间隔 ≥ 0，优先级收敛 1~5 */
      if (key === 'priority') n = Math.min(5, Math.max(1, Math.round(n)))
      else if (n < 0) n = 0
      v = n
    }
  }
  props.node.data.constraints = { ...cons.value, [key]: v }
  markDirty()
}

/* ================= 业务表单：kv-table/params-table/args-table/expr/var-ref/bool/datasource/hint ================= */
function formRows(key: string): { [k: string]: unknown }[] {
  const d = props.node?.data
  if (!d) return []
  if (!Array.isArray(d[key])) d[key] = []
  return d[key] as { [k: string]: unknown }[]
}
function updBool(f: FieldSchema, ev: Event) {
  if (!props.node) return
  props.node.data[f.key] = (ev.target as HTMLInputElement).checked
  markDirty()
  if (f.onChange) f.onChange(props.node.data, props.node.data[f.key]) // 与 select updF 同口径（C22 清值先例；现仅 groupOverride 用）
}

/** 条件展示字段过滤（I4 表单联动：showIf 按当前 node.data 判定，响应式） */
const visibleForm = computed<FieldSchema[]>(() => {
  const form = schema.value?.form ?? []
  const d = props.node?.data
  if (!d) return form.filter((f) => !f.showIf)
  return form.filter((f) => !f.showIf || f.showIf(d))
})

/** W1 必填完整性：当前分型下缺失的必填项（与画布角标/校验面板/保存闸门共用判定） */
const missingLabels = computed(() =>
  props.node && schema.value ? requiredMissing(schema.value, props.node.data) : [])

/** select 值变更：写值 + 触发 onChange 联动钩子（如 C22 来源模式切换清空对方参数） */
function updF(f: FieldSchema, ev: Event) {
  upd(f.key, ev)
  if (props.node && f.onChange) f.onChange(props.node.data, props.node.data[f.key])
}

/* ---------- 数据源中心下拉（I4 type='datasource'）：real 拉 listDataSources，mock 用 dataStore 种子 ---------- */
const dsRows = ref<DsRow[]>([])
function dsOpts(f: FieldSchema): { value: string; label: string }[] {
  return dsRows.value
    .filter((r) => isMock || !f.dsTypes || f.dsTypes.includes(String(r.type)))
    .map((r) => ({ value: r.name, label: `${r.name}（${r.type}${r.env ? ' · ' + r.env : ''}）` }))
}

/* ---------- C17 反选探测（type='probe'）：目标表为基准，探测源库同名/前缀匹配的表，勾选回填 schemas ---------- */
interface ProbeHit { db: string; table: string }
const probeField = ref<FieldSchema | null>(null)
const probeHits = ref<ProbeHit[]>([])
const probeChecked = ref<string[]>([])
const probeBusy = ref(false)

/** 探测：dsKey=源数据源字段，tableKey=目标表字段（缺省 readerDs/writerTable）；excludeDsKey=排除其默认库（缺省 writerDs，防目标表自写自读） */
async function runProbe(f: FieldSchema) {
  probeField.value = null
  probeHits.value = []
  probeChecked.value = []
  if (!props.node) return
  const node = props.node
  const dsKey = f.probe?.dsKey ?? 'readerDs'
  const tableKey = f.probe?.tableKey ?? 'writerTable'
  const excludeDsKey = f.probe?.excludeDsKey ?? 'writerDs'
  const dsName = String(node.data[dsKey] ?? '')
  const target = String(node.data[tableKey] ?? '')
  // 写端默认库排除：同源实例时目标库不参与探测（目标表自身不入源）
  const excludeRow = dsRows.value.find((r) => r.name === String(node.data[excludeDsKey] ?? ''))
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
    probeField.value = f
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
  if (!props.node || !probeField.value || !probeHits.value.length) return
  const checked = probeChecked.value.filter((k) => probeHits.value.some((h) => `${h.db}.${h.table}` === k))
  if (!checked.length) { ElMessage.warning('请至少勾选一个匹配表'); return }
  const schemas = [...new Set(checked.map((k) => k.split('.')[0]))]
  const tables = [...new Set(checked.map((k) => k.slice(k.indexOf('.') + 1)))]
  const d = props.node.data
  d.readerTable = tables.length === 1 ? tables[0] : String(d.writerTable ?? tables[0])
  d.readerSchemasText = schemas.join(',')
  d.autoSchema = checked.length >= probeHits.value.length
  // 多 schema 反选自动切换标识列策略（与 C23 target_base 语义一致）；单表保持原策略
  if (schemas.length > 1) { d.strategy = 'src_flag'; d.flagColumn = d.flagColumn ?? 'src_schema' }
  markDirty()
  ElMessage.success(`已回填 ${schemas.length} 个 schema：${schemas.join(', ')}`)
  probeField.value = null
  probeHits.value = []
  probeChecked.value = []
}

/* ---------- 脚本库互通（type === 'script' 字段） ---------- */
const scripts = ref<Script[]>([])
/** 当前用户（F56d：取 auth store 登录账号，mock 演示态回退 current 身份；替代 dataStore 'user' mock 残留） */
const userName = computed(() => auth.account?.name ?? auth.current.name)

/* ---------- 运行时节点下拉（type === 'runtime-node'，C14 SSH）：real 拉注册表，mock 用 dataStore.runtimeNodes ---------- */
type RuntimeNodeOpt = { id: number | string; name: string; host: string; port: number }
const runtimeNodes = ref<RuntimeNodeOpt[]>([])

/* ---------- 执行节点标签下拉（type === 'exec-node-tag'，I7 F53）：选项 = ssh-nodes 标签并集 ---------- */
const sshNodes = ref<{ id: number; tags: string[] }[]>([])
const tagOptions = computed(() => {
  const seen = new Set<string>()
  for (const n of sshNodes.value) for (const t of n.tags) if (t.trim()) seen.add(t.trim())
  return [...seen]
})

/* ---------- I12 T10 动态控件（选择代替填空）：table-picker / field-select / topic-select / dir-select ---------- */
type DirNav = { path: string; dirs: { name: string }[]; err: string; seq: number }
const EMPTY_DIR: DirNav = { path: '', dirs: [], err: '', seq: 0 }

/** 库表树缓存（ds 名 → 树；table-picker 与 field-select 共用一次请求，columns 内联免列枚举调用） */
const pickTrees = ref<Record<string, DsTree>>({})
const pickTreeErr = ref<Record<string, string>>({})
const pickTreeBusy = ref<Record<string, boolean>>({})
/** topic 枚举缓存（ds 名 → topics，失败不缓存；「刷新」钮强制重拉） */
const topicOpts = ref<Record<string, string[]>>({})
const topicErr = ref<Record<string, string>>({})
const topicBusy = ref<Record<string, boolean>>({})
/** 目录浏览导航状态（字段 key → 当前路径/子目录/错误；节点或依赖切换时整体重置） */
const dirNavs = ref<Record<string, DirNav>>({})
/** Inspector 根元素（token-insert 插入后聚焦目标 textarea；查询限定组件内，不污染全局） */
const rootEl = ref<HTMLElement | null>(null)

function pickErrMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

function nodeData(): Record<string, unknown> {
  return props.node?.data ?? {}
}

/** 依赖字段展示名（提示文案用；form 中无该字段时回退字段名） */
function depLabel(key: string): string {
  return schema.value?.form.find((x) => x.key === key)?.label ?? key
}

/** 按需拉取库表树（按 ds 名缓存、并发去重；失败置行内错误不抛出，不阻塞表单其余字段） */
async function ensureTree(dsName: string): Promise<DsTree | null> {
  const hit = pickTrees.value[dsName]
  if (hit) return hit
  const id = resolveDsId(dsName, dsRows.value)
  if (id == null) {
    if (dsName) pickTreeErr.value[dsName] = `数据源「${dsName}」未加载或已删除`
    return null
  }
  if (pickTreeBusy.value[dsName]) return null
  pickTreeBusy.value[dsName] = true
  pickTreeErr.value[dsName] = ''
  try {
    const t = await getDataSourceTree(id)
    pickTrees.value[dsName] = t
    return t
  } catch (e) {
    pickTreeErr.value[dsName] = `库表加载失败：${pickErrMsg(e)}`
    return null
  } finally {
    pickTreeBusy.value[dsName] = false
  }
}

/* table-picker / field-select 派生数据 computed 化（Nit3）：模板每次渲染重复调
   tableOptions/tablePickPath/columnsOf（全树遍历）与 pickCfg 分配，收敛为依赖变化时一次计算，
   options/cols 数组引用跨渲染稳定，避免 cascader 内部因换数组引用而重算 */
type TpD = { opts: PickOption[]; path: string[]; err: string; depEmpty: boolean; loading: boolean; dsLabel: string }
type FsD = { cols: string[]; val: string[]; val1: string; multi: boolean; noTable: boolean; err: string; loading: boolean; tableLabel: string }
const NO_PATH: string[] = []
const NO_OPTS: PickOption[] = []
const NO_COLS: string[] = []
const tpDerived = computed<Record<string, TpD>>(() => {
  const d = nodeData()
  const out: Record<string, TpD> = {}
  for (const f of visibleForm.value) {
    if (f.type !== 'table-picker' && f.type !== 'token-insert') continue
    const cfg = pickCfg(f)
    const dsName = String(d[cfg.dsKey] ?? '')
    const tree = pickTrees.value[dsName] ?? null
    out[f.key] = {
      opts: tableOptions(tree),
      path: tablePickPath(d[f.key], tree),
      err: pickTreeErr.value[dsName] ?? '',
      depEmpty: !dsName,
      loading: !!pickTreeBusy.value[dsName],
      dsLabel: depLabel(cfg.dsKey),
    }
  }
  return out
})
const fsDerived = computed<Record<string, FsD>>(() => {
  const d = nodeData()
  const out: Record<string, FsD> = {}
  for (const f of visibleForm.value) {
    if (f.type !== 'field-select') continue
    const multi = f.pick?.multiple ?? true
    const v = d[f.key]
    const val1 = Array.isArray(v) ? String(v[0] ?? '') : String(v ?? '')
    /* I12 T12 join 键升级（C19）：src='upstream' 列枚举自直接上游流输入节点（cdcDs + tablesText 首表）；
       非 CDC 上游时候选为空但保持可输入（allow-create 降级），单选写回字符串对齐 ops.py 单键契约 */
    if (f.pick?.src === 'upstream') {
      const up = sortByCanvasX(upstream.value)[f.pick.upstreamIndex ?? 0]
      const dsName = String(up?.data.cdcDs ?? '')
      const table = String(up?.data.tablesText ?? '').split(',')[0]?.trim() ?? ''
      out[f.key] = {
        cols: columnsOf(pickTrees.value[dsName] ?? null, table),
        val: Array.isArray(v) ? v.map(String) : [],
        val1,
        multi,
        noTable: !table,
        err: pickTreeErr.value[dsName] ?? '',
        loading: !!pickTreeBusy.value[dsName],
        tableLabel: '上游流输入表',
      }
      continue
    }
    const cfg = pickCfg(f)
    const dsName = String(d[cfg.dsKey] ?? '')
    const tv = d[cfg.tableKey]
    out[f.key] = {
      cols: columnsOf(pickTrees.value[dsName] ?? null, tv),
      val: Array.isArray(v) ? v.map(String) : [],
      val1,
      multi,
      noTable: !String(tv ?? ''),
      err: pickTreeErr.value[dsName] ?? '',
      loading: !!pickTreeBusy.value[dsName],
      tableLabel: depLabel(cfg.tableKey),
    }
  }
  return out
})
function tpD(f: FieldSchema): TpD | undefined { return tpDerived.value[f.key] }
function fsD(f: FieldSchema): FsD | undefined { return fsDerived.value[f.key] }

/** 依赖数据源字段是否为空（tp/fs 由派生 computed 判定；topic-select 分支复用此轻量判定） */
function tpDepEmpty(f: FieldSchema): boolean {
  return !String(nodeData()[pickCfg(f).dsKey] ?? '')
}
/* table-picker：数据源→库→表两级级联；写回纯表名（缺省）或 {schema, table}（writeAs 可配）。
   el-cascader 清空时 change payload 为 null（非数组）→ writeTablePick 内规整为空路径写回 '' */
function onTablePick(f: FieldSchema, path: unknown) {
  if (!props.node) return
  props.node.data[f.key] = writeTablePick(pickCfg(f).writeAs, path)
  markDirty()
}

/* field-select：列枚举来自已缓存的库表树（免二次列请求）；multiple 缺省多选写回数组，
   pick.multiple=false 单选写回字符串（C19 join 键对齐 worker ops.py 单键契约） */
function onFieldsPick(f: FieldSchema, vals: unknown) {
  if (!props.node) return
  props.node.data[f.key] = (f.pick?.multiple ?? true)
    ? (Array.isArray(vals) ? vals.map(String) : [])
    : (vals == null ? '' : String(vals))
  markDirty()
}

/* token-insert（I12 T12 C11 库/表侧栏选择器）：点选表把 SELECT 骨架插入 pick.insertKey 目标字段
   （缺省 sql），追加不覆盖手写内容；不写自身字段值，级联选中态常驻 NO_PATH 复位以便重复点选 */
function onTokenInsert(f: FieldSchema, path: unknown) {
  if (!props.node) return
  const arr = Array.isArray(path) ? path : []
  const schema = String(arr[0] ?? '')
  const table = String(arr[1] ?? '')
  if (!table) return
  const token = `SELECT * FROM \`${schema}\`.\`${table}\` LIMIT 100`
  const target = f.pick?.insertKey ?? 'sql'
  const cur = String(props.node.data[target] ?? '').replace(/\s*$/, '')
  props.node.data[target] = cur ? `${cur}\n${token}` : token
  markDirty()
  // 插入点聚焦 + 光标置末尾（I12 评审修）：连续点选免手动定位；nextTick 等 Vue patch 完 textarea :value 再定位
  void nextTick(() => {
    const el = rootEl.value?.querySelector<HTMLTextAreaElement>(`textarea[data-fkey="${target}"]`)
    if (!el) return
    el.focus()
    const end = el.value.length
    el.setSelectionRange(end, end)
  })
}

/* topic-select：经 dsRef 字段值解析 ds_id → 枚举 topic；失败候选置空 + 行内错误 */
async function ensureTopics(dsName: string, force = false): Promise<void> {
  if (!dsName) return
  if (!force && (topicOpts.value[dsName] || topicBusy.value[dsName])) return
  const id = resolveDsId(dsName, dsRows.value)
  if (id == null) {
    topicOpts.value[dsName] = []
    topicErr.value[dsName] = `流源「${dsName}」未加载或已删除`
    return
  }
  if (topicBusy.value[dsName]) return
  topicBusy.value[dsName] = true
  topicErr.value[dsName] = ''
  try {
    topicOpts.value[dsName] = await listKafkaTopics(id)
  } catch (e) {
    delete topicOpts.value[dsName]
    topicErr.value[dsName] = `topic 枚举失败：${pickErrMsg(e)}`
  } finally {
    topicBusy.value[dsName] = false
  }
}
function topicRefresh(f: FieldSchema): void {
  void ensureTopics(String(nodeData()[pickCfg(f).dsKey] ?? ''), true)
}
function topicOptsOf(f: FieldSchema): string[] {
  return topicOpts.value[String(nodeData()[pickCfg(f).dsKey] ?? '')] ?? []
}
function topicErrOf(f: FieldSchema): string {
  return topicErr.value[String(nodeData()[pickCfg(f).dsKey] ?? '')] ?? ''
}
function topicBusyOf(f: FieldSchema): boolean {
  return !!topicBusy.value[String(nodeData()[pickCfg(f).dsKey] ?? '')]
}

/* dir-select：运行时节点（节点名解析 id）→ SFTP 目录懒加载（面包屑导航），选中写回完整路径 */
function dirNodeIdOf(f: FieldSchema): number | string | null {
  const nodeName = String(nodeData()[pickCfg(f).nodeKey] ?? '')
  if (!nodeName) return null
  const hit = runtimeNodes.value.find((r) => r.name === nodeName)
  return hit ? hit.id : null
}
let dirSeq = 0 // 目录浏览请求序号（全局单调递增）
/** 目录浏览懒加载：seq 防护——快速连点面包屑/子目录响应乱序、或 watcher 重置 dirNavs
 *  后 in-flight 落为孤儿对象时，await 后校验失败一律丢弃，不覆盖新状态、不写孤儿 */
async function lsDir(fKey: string, nodeId: number | string, path: string): Promise<void> {
  const st: DirNav = dirNavs.value[fKey] ?? { path: '', dirs: [], err: '', seq: 0 }
  dirNavs.value[fKey] = st
  const mySeq = ++dirSeq
  st.seq = mySeq
  const stale = () => dirNavs.value[fKey] !== st || st.seq !== mySeq
  try {
    const r = await listNodeDir(nodeId, path)
    if (stale()) return
    st.path = r.path
    st.dirs = r.entries.filter((e) => e.dir).map((e) => ({ name: e.name }))
    st.err = ''
  } catch (e) {
    if (stale()) return
    st.dirs = []
    st.err = `目录浏览失败：${pickErrMsg(e)}`
  }
}
function dirNavOf(f: FieldSchema): DirNav {
  return dirNavs.value[f.key] ?? EMPTY_DIR
}
function dirEnter(f: FieldSchema, name: string): void {
  const id = dirNodeIdOf(f)
  const st = dirNavs.value[f.key]
  if (id == null || !st) return
  void lsDir(f.key, id, dirJoin(st.path, name))
}
function dirTo(f: FieldSchema, path: string): void {
  const id = dirNodeIdOf(f)
  if (id == null) return
  void lsDir(f.key, id, path)
}
function pickDir(f: FieldSchema): void {
  if (!props.node) return
  const st = dirNavs.value[f.key]
  if (!st?.path) return
  props.node.data[f.key] = st.path
  markDirty()
}

/** 按需拉取动态控件候选（全部带缓存/去重，重复触发为空操作；失败态行内提示不抛出） */
function syncDynamicOptions(): void {
  const d = nodeData()
  for (const f of visibleForm.value) {
    if (f.type === 'table-picker' || f.type === 'token-insert') {
      const dsName = String(d[pickCfg(f).dsKey] ?? '')
      if (dsName) void ensureTree(dsName)
    } else if (f.type === 'field-select') {
      if (f.pick?.src === 'upstream') {
        const up = sortByCanvasX(upstream.value)[f.pick.upstreamIndex ?? 0]
        const dsName = String(up?.data.cdcDs ?? '')
        if (dsName) void ensureTree(dsName)
      } else {
        const dsName = String(d[pickCfg(f).dsKey] ?? '')
        if (dsName) void ensureTree(dsName)
      }
    } else if (f.type === 'topic-select') {
      void ensureTopics(String(d[pickCfg(f).dsKey] ?? ''))
    } else if (f.type === 'dir-select') {
      const id = dirNodeIdOf(f)
      if (id != null && !dirNavs.value[f.key]) void lsDir(f.key, id, '')
    }
  }
}

/** 依赖值签名：节点切换 / 依赖字段值 / 候选行数（dsRows/runtimeNodes 异步就绪）变化时重新按需加载 */
watch(
  () => [
    props.node?.id ?? '',
    dsRows.value.length,
    runtimeNodes.value.length,
    ...visibleForm.value.flatMap((f) => {
      const d = nodeData()
      if (f.type === 'field-select' && f.pick?.src === 'upstream') {
        const up = sortByCanvasX(upstream.value)[f.pick.upstreamIndex ?? 0]
        return [String(up?.data.cdcDs ?? ''), String(up?.data.tablesText ?? '')]
      }
      if (f.type === 'table-picker' || f.type === 'field-select' || f.type === 'topic-select' || f.type === 'token-insert') {
        return [String(d[pickCfg(f).dsKey] ?? '')]
      }
      if (f.type === 'dir-select') return ['@' + String(d[pickCfg(f).nodeKey] ?? '')]
      return []
    }),
  ].join('\u0000'),
  () => {
    dirNavs.value = {} // 导航状态整体重置（及时释放旧节点残留）
    syncDynamicOptions()
  },
  { immediate: true },
)

onMounted(async () => {
  // 必须展开为新数组：dataStore 内部数组原地修改，直接赋值不会触发 ref 更新（对齐 ScriptListView）
  scripts.value = [...((await dataStore.list<Script>('scripts')) ?? [])]
  try {
    runtimeNodes.value = isMock
      ? ((await dataStore.list<RuntimeNodeOpt>('runtimeNodes')) ?? [])
      : (await listRuntimeNodes()).map((r) => ({ id: r.id, name: r.name, host: r.host, port: r.port }))
  } catch { /* real 后端未就绪时下拉留空，不阻断表单 */ }
  try {
    sshNodes.value = isMock
      ? ((await dataStore.list<{ id: number; tags: string[] }>('sshNodes')) ?? [])
      : (await listSshNodes()).map((r) => ({ id: r.id, tags: r.tags }))
  } catch { /* SSH 节点未就绪时标签下拉留空，不阻断表单 */ }
  try {
    dsRows.value = isMock
      ? ((await dataStore.list<{ name: string; type: string }>('datasources')) ?? []).map((r, i) => ({
          id: i, name: r.name, type: r.type, host: null, port: null, db: null, user: null,
          pwd: '', env: null, group: null, tags: [], params: null, status: null,
          owner: '', createdAt: '', updateTime: '',
        }) as DsRow)
      : await listDataSources()
  } catch { /* 数据源中心未就绪时下拉留空，不阻断表单 */ }
})

/** 按节点 scriptId 定位脚本库脚本；未引用/已删除时仅提示不阻断 */
function selectedScript(): Script | null {
  const sid = props.node ? String(props.node.data.scriptId ?? '') : ''
  if (!sid) {
    ElMessage.warning('未引用脚本库脚本，请先选择或「另存为新脚本」')
    return null
  }
  const s = scripts.value.find((x) => x.id === sid) ?? null
  if (!s) ElMessage.warning(`脚本库中未找到 ${sid}（可能已被删除）`)
  return s
}

/** 载入代码：脚本库 code/lang 覆盖节点内联值 */
function loadScriptCode() {
  if (!props.node) return
  const s = selectedScript()
  if (!s) return
  props.node.data.code = s.code
  props.node.data.lang = s.lang
  ElMessage.success('已载入脚本库代码')
}

/** 保存到脚本库：更新已引用脚本的 code/lang/updated */
async function saveToScript() {
  if (!props.node) return
  const s = selectedScript()
  if (!s) return
  s.code = String(props.node.data.code ?? '')
  s.lang = String(props.node.data.lang ?? '') || s.lang
  s.updated = localTime()
  await dataStore.save('scripts', s)
  const i = scripts.value.findIndex((x) => x.id === s.id)
  if (i >= 0) scripts.value.splice(i, 1, { ...s }) // 替换引用触发本地列表更新
  ElMessage.success(`已保存至脚本库（${s.id}）`)
}

/** 另存为新脚本：id 取现有同格式最大序号+1（与 ScriptListView 新建逻辑一致，禁止数组长度） */
async function saveAsNewScript() {
  if (!props.node) return
  const nextSeq = scripts.value.reduce((m, s) => {
    const n = Number(String(s.id).replace(/^\D+/, ''))
    return Number.isFinite(n) && n > m ? n : m
  }, 0) + 1
  const row: Script = {
    id: 'SC' + String(nextSeq).padStart(3, '0'),
    name: String(props.node.data.name ?? '') || '脚本节点',
    lang: String(props.node.data.lang ?? '') || 'SQL',
    status: 'draft',
    owner: userName.value,
    updated: localTime().slice(0, 10),
    code: String(props.node.data.code ?? ''),
  }
  scripts.value.push(row)
  await dataStore.save('scripts', row)
  props.node.data.scriptId = row.id
  ElMessage.success('已保存至脚本库')
}

/** 选择脚本时与内联代码不一致仅提示，不做强制 */
function onScriptChange(key: string, ev: Event) {
  upd(key, ev)
  if (!props.node) return
  const sid = String(props.node.data.scriptId ?? '')
  const s = sid ? scripts.value.find((x) => x.id === sid) : null
  const code = String(props.node.data.code ?? '')
  if (s && code && s.code !== code) {
    ElMessage.info('节点代码与脚本库代码不一致：可「载入代码」覆盖，或「保存到脚本库」回存')
  }
}

/* ---------- 分支编辑（type === 'branches' 字段）：每分支独立表单 + 独立端点 ---------- */
const branches = computed<BranchDef[]>(() => {
  const v = props.node?.data.branches
  return Array.isArray(v) ? (v as BranchDef[]) : []
})

/** 浅拷贝替换 doc 触发画布重同步（边/端点级变更需重建 flowEdges） */
function resync() {
  const d = graphStore.doc
  if (d) graphStore.replace({ ...d })
}

function ensureBranches(): BranchDef[] {
  if (!props.node) return []
  if (!Array.isArray(props.node.data.branches)) props.node.data.branches = []
  return props.node.data.branches as BranchDef[]
}

function setBranch(b: BranchDef, part: 'name' | 'expr', ev: Event) {
  b[part] = (ev.target as HTMLInputElement).value
  if (part === 'name') {
    // 分支名即连线标注：改名同步既有边 label
    graphStore.doc?.edges.forEach((e) => {
      if (e.source === props.node!.id && e.sourceHandle === b.id) e.label = b.name || undefined
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
  if (doc) doc.edges = doc.edges.filter((e) => !(e.source === props.node!.id && e.sourceHandle === b.id))
  resync()
  markDirty()
}

/** 视角语义关联信息（表→已绑规则 / 规则→绑定表等） */
const related = computed(() =>
  props.node && schema.value?.related && graphStore.doc
    ? schema.value.related(props.node, graphStore.doc)
    : [])

function upd(key: string, ev: Event) {
  if (!props.node) return
  const t = ev.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  // number 输入转为数值存储，保持 data 类型契约（summary/统计直接可用）
  if (t instanceof HTMLInputElement && t.type === 'number' && t.value !== '') {
    const n = Number(t.value)
    if (Number.isFinite(n)) {
      props.node.data[key] = n
      return
    }
  }
  props.node.data[key] = t.value
}

/* ---------- 六区块头部摘要 ---------- */
const condSummary = computed(() => (exprOf('condition') ? '已配置' : '未设置'))
const consSummary = computed(() =>
  `${cons.value.timeoutMin ?? 60}min · 重试${cons.value.retryTimes ?? 0} · ${cons.value.failPolicy === 'continue' ? '继续' : '终止'}`)
const exclSummary = computed(() =>
  excl.value.disabled ? '已禁用' : (excl.value.skipCond ? '有跳过条件' : '未设置'))
</script>

<template>
  <aside ref="rootEl" class="wb-inspector">
    <template v-if="node && schema">
      <div class="insp-title">
        <span class="p-ico" :style="{ background: schema.color, width: '22px', height: '22px', borderRadius: '5px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '11px' }">{{ schema.icon }}</span>
        {{ schema.label }}属性
        <span v-if="schema.code" class="insp-code">{{ schema.code }}</span>
        <span class="insp-spacer" />
        <button v-if="pageVisible" class="pg-btn" title="打开页面化展示（F61）" @click="openPage">页面</button>
        <button v-if="effMode === 'edit'" class="pg-btn pg-del" title="删除该节点" @click="emit('delete', node.id)">删除</button>
      </div>
      <div v-if="missingLabels.length" class="insp-miss">必填未配置：{{ missingLabels.join('、') }}</div>
      <div class="insp-form">
        <div class="field">
          <label>节点名称</label>
          <input :value="String(node.data.name ?? '')" :disabled="effMode === 'view'" @change="upd('name', $event)" />
        </div>

        <!-- ① 输入：上游只读列表 + 输入引用 -->
        <div class="blk">
          <div class="blk-head" @click="toggleBlk('inputs')">
            <span class="blk-arrow" :class="{ open: !folds.inputs }">▼</span>① 输入
            <span class="blk-sum">{{ upstream.length }} 上游 · {{ inputRefs.length }} 引用</span>
          </div>
          <div v-show="!folds.inputs" class="blk-body">
            <div v-if="upstream.length" class="up-list">
              <div v-for="u in upstream" :key="u.id" class="up-item">
                <span class="up-ico" :style="{ background: upSchema(u).color }">{{ upSchema(u).icon }}</span>
                <span class="up-name">{{ u.data.name }}</span>
                <span class="up-type">{{ upSchema(u).label }}</span>
              </div>
            </div>
            <div v-else class="blk-empty">无上游节点（起始节点）</div>
            <label class="blk-cap">输入引用（上游输出参数 / 结果表）</label>
            <div class="ref-chips">
              <span v-for="(r, i) in inputRefs" :key="r" class="ref-chip">
                {{ r }}
                <button v-if="effMode === 'edit'" @click="delInputRef(i)">×</button>
              </span>
              <span v-if="!inputRefs.length" class="blk-empty">未引用上游输出</span>
            </div>
            <select v-if="effMode === 'edit' && upstreamOuts.length" class="ref-add" @change="addInputRef($event)">
              <option value="">＋ 选择上游输出引用…</option>
              <option v-for="o in upstreamOuts" :key="o" :value="o">{{ o }}</option>
            </select>
          </div>
        </div>

        <!-- ② 输出：输出参数注册表 + 结果表注册表 -->
        <div class="blk">
          <div class="blk-head" @click="toggleBlk('outputs')">
            <span class="blk-arrow" :class="{ open: !folds.outputs }">▼</span>② 输出
            <span class="blk-sum">{{ outParams.length }} 参数 · {{ outTables.length }} 结果表</span>
          </div>
          <div v-show="!folds.outputs" class="blk-body">
            <label class="blk-cap">输出参数注册表</label>
            <RowsField :rows="outParams" mode="kv" :disabled="effMode === 'view'" @change="markDirty" />
            <label class="blk-cap" style="margin-top:8px">结果表注册表</label>
            <RowsField :rows="outTables" mode="kv" :disabled="effMode === 'view'" @change="markDirty" />
          </div>
        </div>

        <!-- ③ 参数：params-table（键/值/来源五选一） -->
        <div class="blk">
          <div class="blk-head" @click="toggleBlk('params')">
            <span class="blk-arrow" :class="{ open: !folds.params }">▼</span>③ 参数
            <span class="blk-sum">{{ nodeParams.length }} 项</span>
          </div>
          <div v-show="!folds.params" class="blk-body">
            <RowsField :rows="nodeParams" mode="params" :disabled="effMode === 'view'" @change="markDirty" />
            <div class="blk-hint">解析优先级：节点参数 &gt; 工作流变量 &gt; 环境组 &gt; 全局</div>
          </div>
        </div>

        <!-- ④ 条件：运行条件表达式 -->
        <div class="blk">
          <div class="blk-head" @click="toggleBlk('condition')">
            <span class="blk-arrow" :class="{ open: !folds.condition }">▼</span>④ 条件
            <span class="blk-sum">{{ condSummary }}</span>
          </div>
          <div v-show="!folds.condition" class="blk-body">
            <div class="expr-row">
              <input
                class="mono" :value="exprOf('condition')" placeholder="运行条件表达式，留空 = 总是执行"
                :disabled="effMode === 'view'" @change="setExpr('condition', $event)"
              />
              <button class="var-btn" :disabled="effMode === 'view'" title="引用变量" @click="openVarDialog('condition')">$</button>
            </div>
          </div>
        </div>

        <!-- ⑤ 限定约束：超时/重试/失败策略/优先级/worker分组（框架内置字段组） -->
        <div class="blk">
          <div class="blk-head" @click="toggleBlk('constraints')">
            <span class="blk-arrow" :class="{ open: !folds.constraints }">▼</span>⑤ 限定约束
            <span class="blk-sum">{{ consSummary }}</span>
          </div>
          <div v-show="!folds.constraints" class="blk-body blk-grid">
            <div class="field"><label>超时（分钟）</label><input type="number" :value="cons.timeoutMin ?? 60" :disabled="effMode === 'view'" @change="setC('timeoutMin', $event)" /></div>
            <div class="field"><label>超时策略</label>
              <select :value="cons.timeoutPolicy ?? 'fail'" :disabled="effMode === 'view'" @change="setC('timeoutPolicy', $event)">
                <option value="fail">失败</option>
                <option value="warn">告警</option>
              </select>
            </div>
            <div class="field"><label>重试次数</label><input type="number" :value="cons.retryTimes ?? 0" :disabled="effMode === 'view'" @change="setC('retryTimes', $event)" /></div>
            <div class="field"><label>重试间隔（分）</label><input type="number" :value="cons.retryInterval ?? 1" :disabled="effMode === 'view'" @change="setC('retryInterval', $event)" /></div>
            <div class="field"><label>失败策略</label>
              <select :value="cons.failPolicy ?? 'stop'" :disabled="effMode === 'view'" @change="setC('failPolicy', $event)">
                <option value="stop">终止</option>
                <option value="continue">继续</option>
              </select>
            </div>
            <div class="field"><label>优先级</label><input type="number" :value="cons.priority ?? 5" :disabled="effMode === 'view'" @change="setC('priority', $event)" /></div>
            <div class="field"><label>Worker 分组</label><input :value="String(cons.workerGroup ?? '默认')" :disabled="effMode === 'view'" @change="setC('workerGroup', $event)" /></div>
          </div>
        </div>

        <!-- ⑥ 排除：跳过条件 + 禁用开关 -->
        <div class="blk">
          <div class="blk-head" @click="toggleBlk('exclude')">
            <span class="blk-arrow" :class="{ open: !folds.exclude }">▼</span>⑥ 排除
            <span class="blk-sum">{{ exclSummary }}</span>
          </div>
          <div v-show="!folds.exclude" class="blk-body">
            <label class="blk-cap">跳过条件（表达式）</label>
            <div class="expr-row">
              <input
                class="mono" :value="exprOf('exclude')" placeholder="满足则跳过本节点，留空 = 不跳过"
                :disabled="effMode === 'view'" @change="setExpr('exclude', $event)"
              />
              <button class="var-btn" :disabled="effMode === 'view'" title="引用变量" @click="openVarDialog('exclude')">$</button>
            </div>
            <label class="bool-row" style="margin-top:8px">
              <input type="checkbox" :checked="!!excl.disabled" :disabled="effMode === 'view'" @change="setDisabled($event)" />
              <span>禁用本节点（调度时直接跳过）</span>
            </label>
          </div>
        </div>

        <!-- 业务配置（schema.form 按 type 渲染，既有机制 + F60/I4 新类型；showIf 条件展示联动） -->
        <div v-for="f in visibleForm" :key="f.key" class="field">
          <label v-if="f.type !== 'hint'">{{ f.label }}<span v-if="f.required" class="req-star" title="必填">*</span></label>
          <select v-if="f.type === 'select'" :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="updF(f, $event)">
            <option v-for="o in f.options ?? []" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <textarea
            v-else-if="f.type === 'textarea'" rows="4"
            :value="String(node.data[f.key] ?? '')" :placeholder="f.placeholder"
            :disabled="effMode === 'view'" class="mono" :data-fkey="f.key"
            @change="upd(f.key, $event)"
          />
          <!-- 脚本库脚本：select + 载入/回存/另存（与脚本任务模块互通） -->
          <template v-else-if="f.type === 'script'">
            <select
              :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'"
              @change="onScriptChange(f.key, $event)"
            >
              <option value="">不引用（内联脚本）</option>
              <option v-for="s in scripts" :key="s.id" :value="s.id">{{ s.id }} {{ s.name }}（{{ s.lang }}）</option>
            </select>
            <div class="script-btns">
              <button :disabled="effMode === 'view'" @click="loadScriptCode">载入代码</button>
              <button :disabled="effMode === 'view'" @click="saveToScript">保存到脚本库</button>
              <button :disabled="effMode === 'view'" @click="saveAsNewScript">另存为新脚本</button>
            </div>
          </template>
          <!-- 分支编辑：每分支独立表单（分支名+表达式），新增即新增端点 -->
          <template v-else-if="f.type === 'branches'">
            <div class="br-list">
              <div v-for="(b, i) in branches" :key="b.id" class="br-row">
                <input
                  class="br-name" :value="b.name" placeholder="分支名"
                  :disabled="effMode === 'view'"
                  @change="setBranch(b, 'name', $event)"
                />
                <input
                  class="br-expr" :value="b.expr" placeholder="条件表达式 / 匹配值"
                  :disabled="effMode === 'view'"
                  @change="setBranch(b, 'expr', $event)"
                />
                <button
                  class="br-del" title="删除该分支端点及其连线"
                  :disabled="effMode === 'view' || branches.length <= 1"
                  @click="delBranch(i)"
                >×</button>
              </div>
              <button v-if="effMode === 'edit'" class="br-add" @click="addBranch">＋ 新增分支端点</button>
            </div>
            <div style="font-size:10.5px;color:var(--text-3);margin-top:4px">每个分支是节点右侧一个独立端点，可单独连线；连线自动标注分支名</div>
          </template>
          <!-- F60 新类型：kv-table / params-table / I4 args-table（C15 过程参数） -->
          <RowsField
            v-else-if="f.type === 'kv-table' || f.type === 'params-table' || f.type === 'args-table'"
            :rows="formRows(f.key)" :mode="f.type === 'kv-table' ? 'kv' : f.type === 'args-table' ? 'args' : 'params'"
            :disabled="effMode === 'view'" @change="markDirty"
          />
          <!-- I7 C21：变量表（名/值/类型/覆盖）行编辑 -->
          <RowsField
            v-else-if="f.type === 'var-table'"
            :rows="formRows(f.key)" mode="vars"
            :disabled="effMode === 'view'" @change="markDirty"
          />
          <!-- I7 C9：依赖项列表（工作流+节点级联+可选变量条件；排除当前文档防自依赖） -->
          <DepsField
            v-else-if="f.type === 'deps-list'"
            :rows="formRows(f.key)" :exclude-id="graphStore.doc?.id"
            :disabled="effMode === 'view'" @change="markDirty"
          />
          <!-- I4 新类型：datasource（数据源中心下拉，dsTypes 过滤类型） -->
          <select v-else-if="f.type === 'datasource'" :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="upd(f.key, $event)">
            <option value="">请选择数据源…</option>
            <option v-for="o in dsOpts(f)" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <!-- I8 新类型：probe（C17 反选探测：目标表为基准，探测源库同名/前缀匹配的表，勾选回填） -->
          <div v-else-if="f.type === 'probe'" class="probe-box">
            <button class="probe-btn" :disabled="effMode === 'view' || probeBusy" @click="runProbe(f)">
              {{ probeBusy ? '探测中…' : '🔍 探测匹配表' }}
            </button>
            <div class="probe-hint">按目标表名探测源库所有 schema 中同名或前缀匹配的表，默认全选，可重新勾选</div>
            <!-- 门用字段 key 比较而非对象引用：visibleForm 为计算属性，渲染时可能重建字段对象（引用漂移），
                 引用相等会静默失败导致探测结果列表不渲染；probe 字段 key 在 form 内唯一且稳定 -->
            <div v-if="probeField?.key === f.key && probeHits.length" class="probe-list">
              <label v-for="h in probeHits" :key="h.db + '.' + h.table" class="probe-item">
                <input
                  type="checkbox" :value="h.db + '.' + h.table"
                  v-model="probeChecked"
                  :disabled="effMode === 'view'"
                />
                <span class="mono">{{ h.db }}.{{ h.table }}</span>
              </label>
              <div class="probe-actions">
                <button class="probe-ok" :disabled="effMode === 'view' || !probeChecked.length" @click="applyProbe">
                  确定回填（{{ probeChecked.length }}/{{ probeHits.length }}）
                </button>
                <span class="probe-tip">回填到 参与 schema / 自动纳入 / 标识列策略</span>
              </div>
            </div>
          </div>
          <!-- I4 新类型：hint（纯提示文案，text(data) 动态产出或 placeholder 静态） -->
          <div v-else-if="f.type === 'hint'" class="blk-hint">{{ f.text ? f.text(node.data) : (f.placeholder ?? '') }}</div>
          <!-- F60 新类型：expr（表达式 + 变量引用弹窗） -->
          <div v-else-if="f.type === 'expr'" class="expr-row">
            <input
              class="mono" :value="exprOf('f:' + f.key)" :placeholder="f.placeholder"
              :disabled="effMode === 'view'" @change="setExpr('f:' + f.key, $event)"
            />
            <button class="var-btn" :disabled="effMode === 'view'" title="引用变量" @click="openVarDialog('f:' + f.key)">$</button>
          </div>
          <!-- F60 新类型：var-ref（变量引用选择器） -->
          <select v-else-if="f.type === 'var-ref'" :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="upd(f.key, $event)">
            <option value="">不引用</option>
            <option v-for="v in varOptions" :key="v" :value="'${' + v + '}'">${{ '{' + v + '}' }}</option>
          </select>
          <!-- F60 新类型：bool（开关） -->
          <label v-else-if="f.type === 'bool'" class="bool-row">
            <input type="checkbox" :checked="!!node.data[f.key]" :disabled="effMode === 'view'" @change="updBool(f, $event)" />
            <span>{{ f.placeholder ?? '启用' }}</span>
          </label>
          <!-- I3：runtime-node（C14 SSH 运行时节点下拉，取值 = 节点名，worker 按名称解析） -->
          <select v-else-if="f.type === 'runtime-node'" :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="upd(f.key, $event)">
            <option value="">请选择运行时节点…</option>
            <option v-for="rn in runtimeNodes" :key="rn.id" :value="rn.name">{{ rn.name }}（{{ rn.host }}:{{ rn.port }}）</option>
          </select>
          <!-- I7 F53：exec-node-tag（C14 执行节点标签，选项 = ssh-nodes 标签并集；选中后隐藏 runtime-node 字段） -->
          <select v-else-if="f.type === 'exec-node-tag'" :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="upd(f.key, $event)">
            <option value="">不使用标签（按运行时节点直连）</option>
            <option v-for="t in tagOptions" :key="t" :value="t">{{ t }}</option>
          </select>
          <!-- I12 T11：upstream-ref（C25 上游节点引用，选项=画布直接上游节点；空=自动扫描直接上游目标表） -->
          <select v-else-if="f.type === 'upstream-ref'" :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="upd(f.key, $event)">
            <option value="">（自动扫描直接上游目标表）</option>
            <option v-for="u in upstream" :key="u.id" :value="u.id">{{ String(u.data.name ?? u.id) }}（{{ upSchema(u).label }}）</option>
          </select>
          <!-- I12 T10 动态控件：table-picker（数据源→库→表两级级联；写回纯表名或 {schema,table}；清空 payload=null 写回 ''） -->
          <template v-else-if="f.type === 'table-picker'">
            <el-cascader
              class="pick-casc"
              :model-value="tpD(f)?.path ?? NO_PATH"
              :options="tpD(f)?.opts ?? NO_OPTS"
              :disabled="effMode === 'view' || !!tpD(f)?.depEmpty"
              placeholder="选择库 / 表…" clearable filterable
              @change="onTablePick(f, $event)"
            />
            <div v-if="tpD(f)?.depEmpty" class="blk-hint">请先在「{{ tpD(f)?.dsLabel }}」选择数据源</div>
            <div v-else-if="tpD(f)?.loading" class="blk-hint">库表加载中…</div>
            <div v-else-if="tpD(f)?.err" class="pick-err">{{ tpD(f)?.err }}</div>
          </template>
          <!-- I12 T12：token-insert（C11 库/表侧栏选择器：点选表把 SELECT 骨架插入 SQL 编辑器，追加不覆盖手写；选中态复位便于重复点选） -->
          <template v-else-if="f.type === 'token-insert'">
            <el-cascader
              class="pick-casc"
              :model-value="NO_PATH"
              :options="tpD(f)?.opts ?? NO_OPTS"
              :disabled="effMode === 'view' || !!tpD(f)?.depEmpty"
              placeholder="点选库 / 表插入 SELECT 骨架…" filterable
              @change="onTokenInsert(f, $event)"
            />
            <div v-if="tpD(f)?.depEmpty" class="blk-hint">请先在「{{ tpD(f)?.dsLabel }}」选择数据源</div>
            <div v-else-if="tpD(f)?.loading" class="blk-hint">库表加载中…</div>
            <div v-else-if="tpD(f)?.err" class="pick-err">{{ tpD(f)?.err }}</div>
          </template>
          <!-- I12 T10 动态控件：field-select（列枚举多选写回数组；列来自已缓存库表树，免二次请求；
               pick.multiple=false 单选写回字符串（C19 join 键）；src='upstream' 时无候选降级为可直接输入） -->
          <template v-else-if="f.type === 'field-select'">
            <el-select
              v-if="!fsD(f)?.multi"
              class="pick-multi"
              :model-value="fsD(f)?.val1 ?? ''"
              filterable allow-create default-first-option clearable
              placeholder="选择 / 输入字段…"
              :disabled="effMode === 'view'"
              @change="onFieldsPick(f, $event)"
            >
              <el-option v-for="c in fsD(f)?.cols ?? NO_COLS" :key="c" :label="c" :value="c" />
            </el-select>
            <el-select
              v-else
              class="pick-multi"
              :model-value="fsD(f)?.val ?? NO_COLS" multiple filterable collapse-tags collapse-tags-tooltip
              placeholder="选择字段…" clearable
              :disabled="effMode === 'view' || !fsD(f)?.cols.length"
              @change="onFieldsPick(f, $event)"
            >
              <el-option v-for="c in fsD(f)?.cols ?? NO_COLS" :key="c" :label="c" :value="c" />
            </el-select>
            <div v-if="fsD(f)?.noTable" class="blk-hint">{{ fsD(f)?.multi ? `请先在「${fsD(f)?.tableLabel}」选择表` : '上游流输入未声明 CDC 源表，可直接输入字段名' }}</div>
            <div v-else-if="fsD(f)?.loading" class="blk-hint">库表加载中…</div>
            <div v-else-if="fsD(f)?.err" class="pick-err">{{ fsD(f)?.err }}</div>
            <div v-else-if="!fsD(f)?.cols.length" class="blk-hint">未获取到字段（表不在该数据源库表树中）</div>
          </template>
          <!-- I12 T10 动态控件：topic-select（经 dsRef 解析 ds_id 枚举 Kafka topic + 刷新钮） -->
          <template v-else-if="f.type === 'topic-select'">
            <div class="expr-row">
              <select :value="String(node.data[f.key] ?? '')" :disabled="effMode === 'view'" @change="upd(f.key, $event)">
                <option value="">{{ topicBusyOf(f) ? 'topic 枚举中…' : (topicOptsOf(f).length ? '请选择 topic…' : '暂无可选 topic') }}</option>
                <option v-for="t in topicOptsOf(f)" :key="t" :value="t">{{ t }}</option>
              </select>
              <button class="var-btn" :disabled="effMode === 'view'" title="重新枚举 topic" @click="topicRefresh(f)">⟳</button>
            </div>
            <div v-if="tpDepEmpty(f)" class="blk-hint">请先在「{{ depLabel(pickCfg(f).dsKey) }}」选择数据流源</div>
            <div v-else-if="topicBusyOf(f)" class="blk-hint">topic 枚举中…</div>
            <div v-else-if="topicErrOf(f)" class="pick-err">{{ topicErrOf(f) }}</div>
          </template>
          <!-- I12 T10 动态控件：dir-select（运行时节点目录懒加载浏览，选中写回完整路径） -->
          <template v-else-if="f.type === 'dir-select'">
            <div class="dir-crumbs">
              <button
                v-for="c in dirCrumbs(dirNavOf(f).path)" :key="c.path" class="dir-crumb"
                :disabled="effMode === 'view'" @click="dirTo(f, c.path)"
              >{{ c.name }}</button>
              <span v-if="!dirNavOf(f).path && !dirNavOf(f).err" class="blk-hint">目录加载中…</span>
            </div>
            <div class="dir-list">
              <button
                v-for="sub in dirNavOf(f).dirs" :key="sub.name" class="dir-item"
                :disabled="effMode === 'view'" @click="dirEnter(f, sub.name)"
              >📁 {{ sub.name }}</button>
              <div v-if="dirNavOf(f).path && !dirNavOf(f).dirs.length && !dirNavOf(f).err" class="blk-empty">无子目录</div>
            </div>
            <div class="dir-actions">
              <button class="dir-ok" :disabled="effMode === 'view' || !dirNavOf(f).path" @click="pickDir(f)">选中当前目录</button>
              <span class="dir-cur mono">{{ String(node.data[f.key] ?? '') || '未选择' }}</span>
            </div>
            <div v-if="!String(node.data[pickCfg(f).nodeKey] ?? '')" class="blk-hint">请先在「{{ depLabel(pickCfg(f).nodeKey) }}」选择运行时节点</div>
            <div v-else-if="dirNavOf(f).err" class="pick-err">{{ dirNavOf(f).err }}</div>
          </template>
          <input
            v-else :type="f.type === 'number' ? 'number' : 'text'"
            :value="String(node.data[f.key] ?? '')" :placeholder="f.placeholder"
            :disabled="effMode === 'view'" @change="upd(f.key, $event)"
          />
        </div>
        <!-- 视角语义关联信息（schema.related 注入） -->
        <div v-if="related.length" class="field" style="margin-top:12px">
          <label>关联信息</label>
          <div class="rel-list">
            <div v-for="(it, i) in related" :key="i" class="rel-item">
              <span v-if="it.color" class="rel-dot" :style="{ background: it.color }" />
              <span>{{ it.text }}</span>
            </div>
          </div>
        </div>
        <div style="font-size:10.5px;color:var(--text-3);margin-top:14px">
          ID: <span class="mono">{{ node.id }}</span> · 类型: <span class="mono">{{ node.type }}</span>
        </div>
      </div>
    </template>
    <div v-else class="insp-empty">
      <div class="ia-art" aria-hidden="true">
        <span class="ia-node"></span>
        <span class="ia-line"></span>
        <span class="ia-node ia-b"></span>
      </div>
      <div class="ia-title">未选中节点</div>
      <div class="ia-sub">点击画布中的节点，在此查看 / 编辑属性</div>
      <div v-if="effMode === 'edit'" class="ia-hint">从左侧组件库拖入节点，开始编排任务流</div>
      <div class="ia-keys">
        <span><kbd>Del</kbd> 删除</span>
        <span><kbd>Ctrl+F</kbd> 搜索</span>
        <span><kbd>Ctrl+Z</kbd> 撤销</span>
      </div>
    </div>

    <!-- 变量引用弹窗（F60）：下拉已注册变量 + 插入 ${var} -->
    <el-dialog v-model="varDlg" title="引用变量" width="400px" append-to-body>
      <div class="var-body">
        <label class="blk-cap">选择变量（插入 ${'{'}var{'}'}）</label>
        <select v-model="varPick" style="width:100%">
          <option value="">请选择…</option>
          <option v-for="v in varOptions" :key="v" :value="v">${{ '{' + v + '}' }}</option>
        </select>
        <label class="blk-cap" style="margin-top:10px">当前表达式预览</label>
        <div class="var-preview mono">{{ varPreview || '（空）' }}</div>
        <div class="var-hint">解析优先级：节点参数 &gt; 工作流变量 &gt; 环境组 &gt; 全局（解析引擎 I3 落地）</div>
      </div>
      <template #footer>
        <el-button @click="varDlg = false">取消</el-button>
        <el-button type="primary" @click="insertVar">插入</el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<style scoped>
.pg-del{border-color:var(--danger);color:var(--danger)}
.pg-del:hover{border-color:var(--danger);color:#fff;background:var(--danger)}
/* C 编号徽标 + 页面按钮（F61） */
.insp-code{font-size:9.5px;font-weight:700;color:var(--primary);background:var(--primary-light);border-radius:4px;padding:1px 5px;margin-left:4px}
/* W1 必填完整性：缺失提示条 + 必填红星 */
.insp-miss{margin:0 12px;padding:5px 9px;background:rgba(217,119,6,.08);border:1px solid rgba(217,119,6,.35);border-radius:var(--radius-sm);font-size:11px;color:#b45309}
.req-star{color:var(--danger);margin-left:2px;font-weight:700}
.insp-spacer{flex:1}
.pg-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:2px 8px;font-size:11px;cursor:pointer;color:var(--text-2)}
.pg-btn:hover{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
/* 六区块折叠面板 */
.blk{margin-top:8px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden}
.blk-head{display:flex;align-items:center;gap:5px;padding:6px 8px;font-size:12px;font-weight:600;background:var(--bg);cursor:pointer;user-select:none;color:var(--text-2)}
.blk-head:hover{color:var(--primary)}
.blk-arrow{font-size:9px;transition:transform .15s}
.blk-arrow.open{transform:rotate(0)}
.blk-arrow:not(.open){transform:rotate(-90deg)}
.blk-sum{margin-left:auto;font-size:10px;font-weight:400;color:var(--text-3)}
.blk-body{padding:7px 8px;background:var(--card);display:flex;flex-direction:column;gap:4px}
.blk-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.blk-grid .field{margin:0}
.blk-cap{font-size:10.5px;color:var(--text-3);font-weight:600}
.blk-hint{font-size:10px;color:var(--text-3)}
.blk-empty{font-size:10.5px;color:var(--text-3)}
/* ① 上游只读列表 + 输入引用 */
.up-list{display:flex;flex-direction:column;gap:3px}
.up-item{display:flex;align-items:center;gap:6px;font-size:11.5px;padding:3px 5px;background:var(--bg);border-radius:var(--radius-sm)}
.up-ico{width:16px;height:16px;border-radius:4px;color:#fff;font-size:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.up-name{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.up-type{margin-left:auto;font-size:10px;color:var(--text-3);flex-shrink:0}
.ref-chips{display:flex;flex-wrap:wrap;gap:4px}
.ref-chip{display:inline-flex;align-items:center;gap:3px;font-size:10.5px;background:var(--primary-light);color:var(--primary);border-radius:999px;padding:1px 4px 1px 8px;max-width:100%}
.ref-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ref-chip button{border:none;background:transparent;color:inherit;cursor:pointer;font-size:11px;line-height:1;padding:0 2px}
.ref-add{margin-top:2px;width:100%}
/* 表达式 + 变量引用按钮 */
.expr-row{display:flex;gap:4px;align-items:center}
.expr-row input{flex:1;min-width:0}
.var-btn{width:26px;height:26px;flex-shrink:0;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);color:var(--text-2);font-size:12px;cursor:pointer;font-weight:700}
.var-btn:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.var-btn:disabled{opacity:.4;cursor:not-allowed}
.bool-row{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text-2);cursor:pointer}
/* 变量弹窗 */
.var-body{display:flex;flex-direction:column;gap:4px}
.var-body select{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;outline:none}
.var-preview{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 8px;font-size:11.5px;min-height:32px;word-break:break-all}
.var-hint{font-size:10.5px;color:var(--text-3)}
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
.script-btns{display:flex;gap:6px;margin-top:6px}
.script-btns button{flex:1;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 0;font-size:11px;cursor:pointer;color:var(--text-2)}
.script-btns button:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.script-btns button:disabled{opacity:.5;cursor:not-allowed}
.rel-list{display:flex;flex-direction:column;gap:4px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 9px;max-height:180px;overflow:auto}
.rel-item{display:flex;align-items:flex-start;gap:6px;font-size:11.5px;line-height:1.5;color:var(--text-2);word-break:break-all}
.rel-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:4px}
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
</style>
