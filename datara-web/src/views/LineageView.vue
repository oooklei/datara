<script lang="ts">
/** loadGraph 并发请求序（模块级）：来源筛选 watch 与中心表搜索/深链会异步并发调用 loadGraph，
 * 直写 tableDoc/tableLineage 无序则旧响应后至覆盖新状态 —— 自增序号守卫，过期响应直接丢弃。 */
let graphLoadSeq = 0
</script>

<script setup lang="ts">
/**
 * U6 血缘分析：全域表级/字段级血缘探查（只读）。
 * real 模式（I5 F26）：/lineage/tables + /lineage/fields 接真；mock 模式保留 dataStore 演示。
 * 表级（Task 5 数据面切换）：/lineage/graph 聚合端点（design/runtime 双源 + 来源筛选 +
 * 中心表下推）；?instance=&node= 实例追溯深链仍走旧 /lineage/tables 路径（graph 无实例维度，Task 8 重做）。
 * 表级交互：选中表 → 上游/下游 N 层切换 + 影响分析面板（通用推导）+ 中心表搜索。
 * 来源视觉体系：实线=运行事实 / 虚线=设计推导 / 边label「（双源）」=双源佐证 / 节点「未验」角标=仅设计。
 * 字段级（Task 6 图上呈现）：选中中心表 → 字段映射图（FieldLineageMap 两列 + field_dep 连线），
 * 页签「映射图 / 映射明细」（明细=原弹层平铺：映射行 + transform + 语句/实例溯源）。
 * 数据契约：/lineage/fields 无 source 参数 → 字段级隐藏来源筛选；键为「裸表.字段」。
 * 三入口预置（F27）：路由 query ?table=（中心表）/ ?level=field&table=&field=（字段级深链定位）
 * / ?instance=&node=（实例追溯过滤）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { lineageProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
import FieldLineageMap, { type FieldMapRow } from './FieldLineageMap.vue'
import { useGraphStore } from '../stores/graph'
import type { GraphDocument } from '../graph/model'
import { dataStore } from '../services/mock/dataStore'
import { getInstanceDetail, isMock } from '../services'
import type { InstanceRow } from '../services'
import {
  fetchLineageGraph, listFieldLineage, listTableLineage, type LineageEdgeRow,
} from '../services/lineageApi'
import type { FieldLineage, ImpactExample, MetaTable, TableLineage } from '../services/types'
import type { ImpactSubgraph } from '../graph/model'
import {
  annotateStmtNo,
  buildLineageGraphDoc,
  buildTableLineageDoc,
  deriveImpact,
  focusAllEdges,
  graphEdgesToRows,
  impactSummary,
  matchCenter,
} from '../services/mock/lineageUtils'

const graphStore = useGraphStore()
const route = useRoute()
const router = useRouter()

const level = ref<'table' | 'field'>('table')
/** Task 7 参数下推：方向/深度直传 /lineage/graph（downstream/upstream/both；0=∞ 全链），
 * 服务端裁剪取代前端 filterByDepth；both=全连通域（无中心表初始态） */
const direction = ref<'down' | 'up' | 'both'>('down')
const depth = ref(1)
const selected = ref<string | null>(null)
const impactOpen = ref(true)
const ready = ref(false)
const searchKw = ref('')
/** Task 7 一键聚焦：''=关 / impact=下游全链 / source=上游全链（depth 置 0 重拉 + dep_focus 边高亮） */
const focusMode = ref<'' | 'impact' | 'source'>('')
/** Task 7 最近浏览表栈（面包屑）：内存、末尾 10 个、连续重复不压栈 */
const crumbs = ref<string[]>([])
/** 字段级视图（Task 6）：映射图/映射明细页签 + 深链 ?field= 定位高亮 */
const fieldTab = ref<'map' | 'detail'>('map')
const fieldKw = ref('')
/** Task 5 来源筛选（all/design/runtime，下推 /lineage/graph source 参数） */
const sourceFilter = ref<'all' | 'design' | 'runtime'>('all')
/** ?instance=&node= 实例追溯深链模式（旧 /lineage/tables 路径，无来源筛选语义） */
const traceMode = ref(false)
/** Task 8 实例追溯上下文：实例详情（getInstanceDetail，real 专用；失败/缺失字段不硬造，展示 '-'）
 * 与追溯节点 id（节点名优先取详情 taskInstances 匹配，缺失退化显示 nodeId） */
const traceInfo = ref<InstanceRow | null>(null)
const traceNodeId = ref('')
/** 实例详情请求序：二次 reload 深链时旧响应迟到不得覆盖新 traceInfo（Task 8 审查 I-3） */
let traceDetailSeq = 0
/** graph 聚合结果截断标记（后端 limit 上限） */
const graphTruncated = ref(false)

const tableDoc = ref<GraphDocument | null>(null)  // 表级图文档（graph 聚合构建 / 旧路径构建）
const fieldLineage = ref<FieldLineage>({})
const impactExample = ref<ImpactExample | null>(null)
const metaTables = ref<MetaTable[]>([])
const tableLineage = ref<TableLineage[]>([])  // 影响分析 BFS 输入行
const edgeRows = ref<LineageEdgeRow[]>([])  // 字段级映射明细页语句溯源（切字段级时懒加载）
const edgeRowsLoaded = ref(false)

/** 表级文档（graph 聚合 / 旧路径构建）；字段级不渲染画布（Task 6 映射图面板），无字段文档。
 * Task 7：N 层裁剪已下推服务端（loadGraph 直传 direction/depth），此处仅做聚焦态边高亮（浅拷贝）。
 * Task 8：追溯模式边标注 stmt_no 次序（数据 = 追溯行自带 stmtNo，浅拷贝）。 */
const doc = computed<GraphDocument | null>(() => {
  if (!ready.value || !tableDoc.value) return null
  if (traceMode.value) return annotateStmtNo(tableDoc.value, edgeRows.value)
  if (level.value === 'table' && focusMode.value) return focusAllEdges(tableDoc.value)
  return tableDoc.value
})

/* ---------- Task 8 实例追溯上下文条 ---------- */

/** 实例状态 → pill 类/文案（对齐 InstanceRunsView instCls/instLabel；色类用 theme.css ok/err/info） */
const TRACE_STATES: Record<string, { cls: string; label: string }> = {
  running: { cls: 'info', label: '运行中' },
  submitted: { cls: 'info', label: '已提交' },
  success: { cls: 'ok', label: '成功' },
  failure: { cls: 'err', label: '失败' },
  kill: { cls: 'err', label: '已终止' },
}
const traceState = computed(() =>
  TRACE_STATES[traceInfo.value?.state ?? ''] ?? { cls: 'off', label: '-' })

/** 工作流名：追溯边行 wf 字段（后端回填的名字符串）；空/- 退化 #wfCode（不硬造名称） */
const traceWfLabel = computed(() => {
  const r = edgeRows.value[0]
  if (!r) return '-'
  return r.wf && r.wf !== '-' ? r.wf : r.wfCode != null ? `#${r.wfCode}` : '-'
})

/** 节点名：实例详情 taskInstances 按 nodeId 匹配；详情缺失退化显示 nodeId */
const traceNodeLabel = computed(() => {
  if (!traceNodeId.value) return '-'
  const t = traceInfo.value?.taskInstances?.find((x) => x.nodeId === traceNodeId.value)
  return t?.name ?? traceNodeId.value
})

/** 深链实例 id（上下文条展示；route 响应式，回全量清参后随隐） */
const traceInstanceId = computed(() => String(route.query.instance ?? ''))

/* ---------- Task 7 影响分析独立请求 ---------- */

/** 影响分析行：画布请求已覆盖下游全链（非 trace + 非 up + depth=0）时复用 tableLineage（null），
 * 否则独立拉中心表下游全链（跨 direction/depth 限制，行为对齐旧 filterByDepth 前的全链 BFS） */
const impactRows = ref<TableLineage[] | null>(null)
let impactSeq = 0
const impactKey = ref('')

const impact = computed<ImpactSubgraph | null>(() => {
  if (level.value !== 'table' || !selected.value) return null
  return deriveImpact(selected.value, impactRows.value ?? tableLineage.value, impactExample.value)
})

/** 影响分析数据保障：key=中心表+来源去重；过期响应（impactSeq 守卫）与换选中后的迟到回写均丢弃；
 * 失败回退画布可见行（不回退旧行为）。trace 模式沿用旧路径行（无 graph 语义）。 */
async function ensureImpactData() {
  if (level.value !== 'table' || !selected.value) return
  if (traceMode.value || (direction.value !== 'up' && depth.value === 0)) {
    impactRows.value = null
    return
  }
  const center = selected.value
  const key = `${center}\n${sourceFilter.value}`
  if (impactKey.value === key) return
  const mySeq = ++impactSeq
  impactKey.value = key
  impactRows.value = null  // 在途期不展示旧表行（Task 7 审查 I-1）
  try {
    const res = await fetchLineageGraph({
      level: 'table',
      source: sourceFilter.value,
      table: center,
      direction: 'downstream',
      depth: 0,
    })
    if (mySeq !== impactSeq || selected.value !== center) return
    impactKey.value = key  // 与 rows 原子回写：防外部回滚（applySearch miss）后 key 滞留旧值（I-1）
    impactRows.value = graphEdgesToRows(res)
  } catch {
    if (mySeq !== impactSeq) return
    impactKey.value = ''  // 失败不占 key：同参数下次可重试（Task 7 审查 M-2）
    impactRows.value = null
  }
}

/* ---------- Task 6 字段级映射（数据契约见 FieldLineageMap 头注释） ---------- */

/** 字段映射键 "表.字段" → 表部（最后一段为字段名，对齐后端 rpartition 口径；fq 表名多点安全） */
function fieldTableOf(key: string): string {
  const i = key.lastIndexOf('.')
  return i < 0 ? key : key.slice(0, i)
}

/** 字段映射键表部与中心表命中（matchCenter 同口径：selected 允许裸名/ fq） */
function matchFieldTable(key: string, tbl: string): boolean {
  return matchCenter(fieldTableOf(key), tbl)
}

/** 字段级中心表下拉：有字段映射的表（裸名 + 映射数，字典序） */
const fieldTables = computed(() => {
  const counts = new Map<string, number>()
  Object.keys(fieldLineage.value).forEach((k) => {
    const t = fieldTableOf(k)
    counts.set(t, (counts.get(t) ?? 0) + 1)
  })
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

/** 当前选中表的字段映射行（target/from 为「裸表.字段」，from="" 常量已在 reload 过滤） */
const fieldRows = computed<FieldMapRow[]>(() => {
  if (level.value !== 'field' || !selected.value) return []
  const out: FieldMapRow[] = []
  Object.entries(fieldLineage.value).forEach(([k, items]) => {
    if (matchFieldTable(k, selected.value!)) {
      items.forEach((it) => out.push({ target: k, from: it.from, transform: it.transform }))
    }
  })
  return out
})

/** 映射明细页溯源：目标表最近边行（语句/实例/数据源；edgeRows r.to 为裸表名，matchCenter 兜 fq） */
const fieldStmtRow = computed(() => {
  if (!selected.value) return null
  return edgeRows.value.find((r) => matchCenter(r.to, selected.value!)) ?? null
})

/* 同步到 graphStore，使「血缘统计」浮窗读取当前构建文档 */
watch(doc, (d) => { if (d) graphStore.setDoc(d) })

/** 选中末项落空（换心重拉 miss / 切级重置）时同步弹出面包屑末项，防落空表残留 .cur（Task 7 审查 M-1） */
function popCrumbIfCurrent(id: string) {
  if (crumbs.value[crumbs.value.length - 1] === id) {
    crumbs.value = crumbs.value.slice(0, -1)
  }
}

/** 退出实例追溯（Task 8）：重置 trace 态 + 恢复表级默认视图（both + 全链，同初始态语义）；
 * clearQuery=true（「回到全量」按钮）同步清路由深链参数；切级退出不清（保留深链可刷新回到追溯） */
async function exitTrace(clearQuery: boolean) {
  traceMode.value = false
  traceInfo.value = null
  traceNodeId.value = ''
  crumbs.value = []
  selected.value = null
  impactOpen.value = true
  // 复位方向/深度/聚焦（Task 8 审查 I-2）：trace 中控件已隐藏（I-1），但历史静默改值需归位默认
  const changed = direction.value !== 'down' || depth.value !== 1
  direction.value = 'down'
  depth.value = 1
  focusMode.value = ''
  if (clearQuery) {
    const q = { ...route.query }
    delete q.instance
    delete q.node
    void router.replace({ query: q })
  }
  // 参数 watcher 同 tick 合并触发 reloadCenter（selected=null → both/全链）：
  // 参数确有变化时省略自身拉取交由 watcher 单发（仿 runFocus changed 模式，防双发同参请求）
  if (!changed) await loadGraph(undefined)
}

/** 切级即重置从属选择态（sync：深链程序化切级后可继续安全赋值 selected/fieldTab）；
 * Task 8：追溯模式下手动切级即退出追溯并恢复全量视图（上下文条不再常驻） */
watch(level, () => {
  const prev = selected.value
  if (traceMode.value) {
    traceMode.value = false
    traceInfo.value = null
    traceNodeId.value = ''
    // 显式复位与 exitTrace 对称（Task 9 复审建议）：不依赖「trace 中参数不可变」隐式不变式；
    // trace 深链 level 恒为 table，此处只经字段级切出触发，复位值不会经 watcher 回拉（watcher 对 field return）
    direction.value = 'down'
    depth.value = 1
    void loadGraph(undefined)
  }
  selected.value = null; impactOpen.value = true
  fieldTab.value = 'map'; fieldKw.value = ''
  focusMode.value = ''
  if (prev) popCrumbIfCurrent(prev)  // 末项选中被重置：切回表级后不残留 .cur（Task 7 审查 M-1）
  if (level.value === 'field') void ensureEdgeRows()
}, { flush: 'sync' })

/** 选中变更（Task 7）：表级非追溯 → 面包屑压栈（末尾 10、连续重复不压）+ 影响分析数据保障
 * （ensureImpactData 覆盖搜索跳表/双击换心等全部路径，防面板残留旧表下游行）；清空选中即撤行 */
watch(selected, (id) => {
  if (level.value !== 'table' || traceMode.value) return
  if (!id) { impactRows.value = null; return }
  if (crumbs.value[crumbs.value.length - 1] !== id) {
    crumbs.value = [...crumbs.value, id].slice(-10)
  }
  void ensureImpactData()
})

/** 以当前中心表带参重拉（方向/深度/来源切换与一键聚焦共用）；
 * 无选中（初始态）→ both/全链重拉全连通域（保持旧「未选中切来源重拉」行为）；
 * 新子图不含当前选中表（matchCenter 校验）则清空选中，避免中心落空空画布 */
async function reloadCenter() {
  if (level.value !== 'table' || traceMode.value) return
  await loadGraph(selected.value ?? undefined)
  if (selected.value && !tableDoc.value?.nodes.some((n) => matchCenter(n.id, selected.value!))) {
    const gone = selected.value
    selected.value = null
    popCrumbIfCurrent(gone)  // 换心落空：面包屑同步弹出，不以 .cur 展示落空表（M-1）
  }
}

/** 方向/深度/来源变更（Task 7 下推）：带参重拉（graphLoadSeq 竞态守卫在 loadGraph 内；
 * 无选中时 reloadCenter 降级为 both/全链，保持旧「未选中切来源重拉」行为） */
watch([direction, depth, sourceFilter], () => {
  if (level.value !== 'table' || traceMode.value) return
  void reloadCenter()
})

/** 手动控件点击（与一键聚焦互斥）：清聚焦态（doc computed 即时撤销 dep_focus 高亮） */
function setDirection(d: 'down' | 'up' | 'both') { focusMode.value = ''; direction.value = d }
function setDepth(n: number) { focusMode.value = ''; depth.value = n }
function setSource(s: 'all' | 'design' | 'runtime') { focusMode.value = ''; sourceFilter.value = s }

/** 一键影响分析 / 源头追踪（Task 7）：全链参数（目标方向 + depth=0）+ dep_focus 边高亮。
 * 参数变化由 watcher 触发重拉；已为目标参数时 watcher 不触发，手动补拉一次。 */
function runFocus(mode: 'impact' | 'source') {
  if (level.value !== 'table' || traceMode.value || !selected.value) return
  focusMode.value = mode
  const nd: 'down' | 'up' = mode === 'impact' ? 'down' : 'up'
  const changed = direction.value !== nd || depth.value !== 0
  direction.value = nd
  depth.value = 0
  if (!changed) void reloadCenter()
}

/** 以某表为中心（Task 7）：双击/右键菜单/面包屑回跳共用入口；同中心幂等跳过（不压栈不重拉，M-3） */
async function centerOn(id: string) {
  if (level.value !== 'table' || traceMode.value) return
  if (id === selected.value) return
  selected.value = id
  impactOpen.value = true
  await reloadCenter()
}

function onSelect(id: string | null) {
  selected.value = id
  impactOpen.value = true
}

/** 字段级中心表下拉选择（select change → selected；空值不处理）。
 * 深链 ?field= 高亮仅对入参表有效：换表即清 fieldKw，避免残留误高亮新表同名字段（Task 6 审查 M-2） */
function onFieldTablePick(name: string) {
  if (!name) return
  selected.value = name
  fieldKw.value = ''
}

/** 中心表搜索：命中当前图即选中；未命中且非追溯模式 → 中心表下推重查（后端 _bare/endsWith 兜底）。
 * 字段级：在字段映射表集内命中即切中心表（fieldLineage 已全量在内存，无重查语义）。 */
async function applySearch() {
  const kw = searchKw.value.trim()
  if (!kw) return
  if (level.value === 'field') {
    const hit = Object.keys(fieldLineage.value).find((k) => matchFieldTable(k, kw))
    if (hit) {
      const tbl = fieldTableOf(hit)
      // 深链 ?field= 高亮仅对入参表有效：换表即清（对齐 onFieldTablePick，Task 6 复审残留）
      if (tbl !== selected.value) fieldKw.value = ''
      selected.value = tbl
    } else {
      ElMessage.info(`字段级血缘中未找到表：${kw}`)
    }
    return
  }
  if (level.value !== 'table') level.value = 'table'
  const hit = tableDoc.value?.nodes.find((n) => matchCenter(n.id, kw))
  if (hit) {
    selected.value = hit.id
    impactOpen.value = true
    return
  }
  // 追溯深链（已按实例/节点过滤，重查无意义）与 mock（样例为固定全集，重查同结果）直接提示
  if (traceMode.value || isMock) {
    ElMessage.info(`血缘图中未找到表：${kw}`)
    return
  }
  // 未命中快照回滚：重查 miss 时保留当前画布（对齐旧行为只提示不换图）；
  // 影响分析行/键一并回滚（防 miss 请求的下游全链残留到旧中心表面板）
  const snapDoc = tableDoc.value
  const snapRows = tableLineage.value
  const snapTrunc = graphTruncated.value
  const snapImpact = impactRows.value
  const snapImpactKey = impactKey.value
  await loadGraph(kw)
  const hit2 = tableDoc.value?.nodes.find((n) => matchCenter(n.id, kw))
  if (hit2) {
    selected.value = hit2.id
    impactOpen.value = true
  } else {
    tableDoc.value = snapDoc
    tableLineage.value = snapRows
    graphTruncated.value = snapTrunc
    impactRows.value = snapImpact
    impactKey.value = snapImpactKey
    ElMessage.info(`血缘图中未找到表：${kw}`)
  }
}

/** 表级图加载（Task 5 数据面切换 → Task 7 参数下推）：/lineage/graph 聚合端点。
 * 有中心表 → 直传当前方向/深度（服务端 BFS 裁剪，取代前端 filterByDepth）；
 * 无中心表初始态 → both + 全链拉全连通域（保持旧默认视图语义）。
 * 并发守卫：进入即占序号，响应后过期（已被更新请求取代）则丢弃，不回写状态。 */
async function loadGraph(center?: string) {
  const mySeq = ++graphLoadSeq
  try {
    const res = await fetchLineageGraph({
      level: 'table',
      source: sourceFilter.value,
      table: center || undefined,
      direction: center ? dirParam() : 'both',
      depth: center ? depth.value : 0,
    })
    if (mySeq !== graphLoadSeq) return
    tableDoc.value = buildLineageGraphDoc(res, metaTables.value)
    tableLineage.value = graphEdgesToRows(res)
    graphTruncated.value = res.truncated
    void ensureImpactData()
  } catch (e) {
    if (mySeq !== graphLoadSeq) return
    ElMessage.error('血缘图加载失败：' + (e instanceof Error ? e.message : String(e)))
  }
}

/** 前端方向值 → /lineage/graph direction 参数 */
function dirParam(): 'upstream' | 'downstream' | 'both' {
  return direction.value === 'up' ? 'upstream' : direction.value === 'down' ? 'downstream' : 'both'
}

/** 字段级语句溯源明细（/lineage/tables 全量行）：首次切字段级时懒加载一次 */
async function ensureEdgeRows() {
  if (edgeRowsLoaded.value || isMock) return
  edgeRowsLoaded.value = true
  try {
    edgeRows.value = await listTableLineage()
  } catch { /* 溯源明细失败不阻断字段级浏览（弹层显示「无语句溯源」） */ }
}

/** 实例追溯深链旧路径（?instance=&node=）：/lineage/tables + node 过滤（Task 8 迁移 graph） */
async function loadTraceLegacy(instanceId: string, nodeId: string): Promise<TableLineage[]> {
  if (isMock) return [...((await dataStore.list<TableLineage>('tableLineage')) ?? [])]
  const edges = await listTableLineage(instanceId ? { instance_id: instanceId } : {})
  let rows: LineageEdgeRow[] = edges
  if (nodeId) rows = rows.filter((r) => r.nodeId === nodeId)
  edgeRows.value = rows
  return rows.map((r) => ({ from: r.from, to: r.to, task: r.task, wf: r.wf }))
}

/** 常量来源项（from=""）不构映射节点/连线：/lineage/fields 契约由视图层过滤，
 * mock 种子同契约 —— 过滤提为共用，reload 两分支末尾统一走（Task 6 审查 I-1） */
function filterConstSources(fl: FieldLineage): FieldLineage {
  const out: FieldLineage = {}
  Object.entries(fl).forEach(([k, items]) => {
    const arr = items.filter((it) => it.from)
    if (arr.length) out[k] = arr
  })
  return out
}

async function reload() {
  const q = route.query
  if (isMock) {
    fieldLineage.value = (await dataStore.get<FieldLineage>('fieldLineage')) ?? {}
    impactExample.value = (await dataStore.get<ImpactExample>('impactExample')) ?? null
    metaTables.value = [...((await dataStore.list<MetaTable>('metaTables')) ?? [])]
  } else {
    try {
      fieldLineage.value = await listFieldLineage()
      impactExample.value = null
      metaTables.value = []
    } catch (e) {
      ElMessage.error('血缘加载失败：' + (e instanceof Error ? e.message : String(e)))
    }
  }
  fieldLineage.value = filterConstSources(fieldLineage.value)
  if (q.instance || q.node) {
    traceMode.value = true
    crumbs.value = []
    traceNodeId.value = q.node ? String(q.node) : ''
    try {
      tableLineage.value = await loadTraceLegacy(
        q.instance ? String(q.instance) : '', q.node ? String(q.node) : '')
      tableDoc.value = buildTableLineageDoc(tableLineage.value, metaTables.value)
    } catch (e) {
      ElMessage.error('血缘加载失败：' + (e instanceof Error ? e.message : String(e)))
    }
    // Task 8 实例详情（增强信息：状态/起止时间/节点名；real 专用 API 无 mock 分支）：
    // 不 await 不阻断追溯主体；失败置 null，上下文条缺失字段按 '-' 呈现（不硬造）；
    // 序号守卫（I-3）：二次深链时旧响应迟到不得回写新上下文
    if (!isMock && q.instance) {
      const my = ++traceDetailSeq
      getInstanceDetail(String(q.instance))
        .then((d) => { if (my === traceDetailSeq && traceMode.value) traceInfo.value = d })
        .catch(() => { if (my === traceDetailSeq) traceInfo.value = null })
    }
    // 畸形深链（?instance=&level=field&table=x）：trace 分支优先，忽略 level/table 参数
    //（先建追溯 doc 后不再走字段级/中心表分支，避免切级触发退出追溯致状态混杂，M-1）
  } else {
    await loadGraph(q.table ? String(q.table) : undefined)
    if (q.table) {
      const kw = String(q.table)
      searchKw.value = kw
      // 深链归一（同 applySearch 命中逻辑）：graph 文档节点 id 为数据源点分 fq，
      // 入口传裸表名（如数据源详情页 ?table=t.name）→ 归一为命中节点的 fq，避免 filterByDepth 中心落空
      const hit = tableDoc.value?.nodes.find((n) => matchCenter(n.id, kw))
      selected.value = hit ? hit.id : kw
      // 字段级深链（?level=field&table=x&field=y）：切字段级 + 按字段映射表集归一裸表名 + field 定位高亮
      if (String(q.level ?? '') === 'field') {
        level.value = 'field'  // sync watch 清空 selected（从属态重置），随后统一回填
        void ensureEdgeRows()
        const fhit = Object.keys(fieldLineage.value).find((k) => matchFieldTable(k, kw))
        selected.value = fhit ? fieldTableOf(fhit) : kw  // 未命中保留入参（fieldRows 空态提示）
        if (q.field) {
          fieldKw.value = String(q.field)
          fieldTab.value = 'map'
        }
      }
    }
  }
  ready.value = true
}

onMounted(reload)
</script>

<template>
  <div class="lineage-page">
    <div class="lineage-toolbar">
      <div class="seg">
        <button :class="{ on: level === 'table' }" @click="level = 'table'">表级血缘</button>
        <button :class="{ on: level === 'field' }" @click="level = 'field'">字段级血缘</button>
      </div>
      <!-- Task 5 来源筛选（下推 /lineage/graph source 参数；追溯深链模式无来源语义故隐藏） -->
      <div v-if="level === 'table' && !traceMode" class="seg">
        <button :class="{ on: sourceFilter === 'all' }" @click="setSource('all')">全部来源</button>
        <button :class="{ on: sourceFilter === 'design' }" @click="setSource('design')">设计态</button>
        <button :class="{ on: sourceFilter === 'runtime' }" @click="setSource('runtime')">运行态</button>
      </div>
      <!-- trace 模式方向/深度/聚焦一并隐藏（Task 8 审查 I-1）：setDirection/setDepth 静默改值
           而 watcher 被拦截无反馈，控件不可见才与「参数无语义」一致 -->
      <template v-if="level === 'table' && selected && !traceMode">
        <span class="sep" />
        <!-- Task 7：方向/深度下推服务端裁剪（重拉）；一键聚焦=全链参数 + dep_focus 高亮 -->
        <div class="seg">
          <button :class="{ on: direction === 'down' }" @click="setDirection('down')">下游</button>
          <button :class="{ on: direction === 'up' }" @click="setDirection('up')">上游</button>
          <button :class="{ on: direction === 'both' }" @click="setDirection('both')">全连通</button>
        </div>
        <div class="seg">
          <button v-for="d in [1, 2, 3]" :key="d" :class="{ on: depth === d && !focusMode }" @click="setDepth(d)">{{ d }}层</button>
          <button :class="{ on: depth === 0 && !focusMode }" title="不限层数（depth=0 全链）" @click="setDepth(0)">∞ 全链</button>
        </div>
        <div class="seg">
          <button :class="{ on: focusMode === 'impact' }" title="以下游全链重查并高亮" @click="runFocus('impact')">⚡ 影响分析</button>
          <button :class="{ on: focusMode === 'source' }" title="以上游全链重查并高亮" @click="runFocus('source')">源头追踪</button>
        </div>
        <span class="hint">当前：{{ selected }}</span>
      </template>
      <span v-else-if="level === 'table'" class="hint">点击画布节点查看上/下游 N 层与影响分析</span>
      <span v-else class="hint">字段级血缘：选择中心表查看字段映射图与映射明细</span>
      <span v-if="graphTruncated && level === 'table'" class="hint trunc-hint">⚠ 结果超上限已截断</span>
      <span class="sep" />
      <input
        v-model="searchKw"
        class="search-in mono"
        placeholder="中心表搜索（回车定位）"
        @keyup.enter="applySearch"
      >
    </div>

    <!-- 实例追溯上下文条（Task 8）：常驻直到「回到全量」或切级退出；
         工作流/节点名来自追溯行与实例详情（缺失按 '-' 呈现，不硬造） -->
    <div v-if="traceMode" class="trace-bar">
      <span class="tb-cap">实例追溯</span>
      <span class="pill" :class="traceState.cls">{{ traceState.label }}</span>
      <span class="tb-kv">工作流 <b>{{ traceWfLabel }}</b></span>
      <span class="tb-kv">节点 <b class="mono">{{ traceNodeLabel }}</b></span>
      <span v-if="traceInstanceId" class="tb-kv">实例 <b class="mono" :title="traceInstanceId">{{ traceInstanceId.slice(0, 18) }}</b></span>
      <span class="tb-kv">开始 <b class="mono">{{ traceInfo?.startTime || '-' }}</b></span>
      <span class="tb-kv">结束 <b class="mono">{{ traceInfo?.endTime || '-' }}</b></span>
      <span class="tb-flex" />
      <button class="tb-back" @click="exitTrace(true)">回到全量</button>
    </div>

    <!-- 来源图例（Task 5，表级常驻；字段级 /lineage/fields 无来源语义故隐藏） -->
    <div v-if="level === 'table'" class="lineage-legend">
      <div class="lg-title">来源图例</div>
      <span class="lg-item"><i class="lg-line lg-run" />运行事实（实线）</span>
      <span class="lg-item"><i class="lg-line lg-design" />设计推导（虚线）</span>
      <span class="lg-item"><i class="lg-line lg-run" />双源佐证<i class="lg-dual">双源</i></span>
      <span class="lg-item"><i class="lg-unv-mark">未验</i>未验证（仅设计）</span>
    </div>

    <!-- 表级画布（trace 追溯同为表级；字段级渲染映射图面板，避免空 doc 回退拉 seed）；
         center-node：双击/右键「以此为中心」重拉（Task 7） -->
    <GraphWorkbench
      v-if="level === 'table'"
      :profile="lineageProfile"
      doc-id="lineage_global"
      :doc="doc"
      @select="onSelect"
      @center-node="centerOn"
    />

    <!-- 最近浏览面包屑（Task 7）：>1 项才显示；末项为当前中心表不可点 -->
    <div v-if="level === 'table' && !traceMode && crumbs.length > 1" class="crumb-bar">
      <span class="crumb-label">最近浏览：</span>
      <template v-for="(c, i) in crumbs" :key="`${c}-${i}`">
        <button
          v-if="i < crumbs.length - 1"
          class="crumb mono"
          :title="`以此为中心：${c}`"
          @click="centerOn(c)"
        >{{ c }}</button>
        <span v-else class="crumb cur mono">{{ c }}</span>
        <span v-if="i < crumbs.length - 1" class="crumb-sep">›</span>
      </template>
    </div>

    <!-- 字段级面板（Task 6）：中心表下拉 + 「映射图 / 映射明细」页签 -->
    <div v-else-if="level === 'field'" class="field-panel">
      <div class="fp-head">
        <select :value="selected ?? ''" class="fp-select mono" aria-label="中心表选择" @change="onFieldTablePick(($event.target as HTMLSelectElement).value)">
          <option value="" disabled>选择中心表（{{ fieldTables.length }}）</option>
          <option v-for="t in fieldTables" :key="t.name" :value="t.name">{{ t.name }}（{{ t.count }} 项映射）</option>
        </select>
        <div class="seg">
          <button :class="{ on: fieldTab === 'map' }" @click="fieldTab = 'map'">映射图</button>
          <button :class="{ on: fieldTab === 'detail' }" @click="fieldTab = 'detail'">映射明细</button>
        </div>
        <span v-if="selected" class="hint">{{ fieldRows.length }} 条字段映射</span>
      </div>
      <div v-if="!selected" class="fp-empty">请选择中心表（下拉或顶部搜索）查看字段映射</div>
      <div v-else-if="!fieldRows.length" class="fp-empty">该表暂无字段级映射（可能未采集字段级血缘）</div>
      <FieldLineageMap v-else-if="fieldTab === 'map'" :rows="fieldRows" :highlight="fieldKw" />
      <!-- 映射明细（原字段转换弹层平铺）：映射行 + transform + 语句/实例溯源 -->
      <div v-else class="fp-detail">
        <div class="fp-sec">
          <div class="sec-title">字段映射（{{ fieldRows.length }}）</div>
          <div v-for="(r, i) in fieldRows" :key="i" class="tr-row">
            <div class="tr-map mono"><b>{{ r.target }}</b> ← {{ r.from }}</div>
            <div v-if="r.transform" class="tr-expr mono">{{ r.transform }}</div>
          </div>
        </div>
        <div v-if="fieldStmtRow" class="fp-sec tr-src">
          <div class="sec-title">采集溯源</div>
          <div class="tr-stmt mono">{{ fieldStmtRow.stmt }}</div>
          <div class="tr-meta">
            <span>实例 {{ fieldStmtRow.instanceId }}</span>
            <span>{{ fieldStmtRow.wf }} / {{ fieldStmtRow.task }}</span>
            <span v-if="fieldStmtRow.dsName">数据源 {{ fieldStmtRow.dsName }}</span>
          </div>
        </div>
        <div v-else class="fp-empty">本表无语句溯源信息（可能来自设计态推导或历史数据）</div>
      </div>
    </div>

    <!-- 影响分析面板（表级 + 选中表） -->
    <div v-if="impact && impactOpen" class="impact-card">
      <div class="impact-head">
        <b>影响分析 · {{ impact.table }}</b>
        <button class="impact-close" @click="impactOpen = false">×</button>
      </div>
      <div class="impact-summary">{{ impactSummary(impact) }}</div>
      <div v-if="impact.downTables.length" class="impact-sec">
        <div class="sec-title">下游表</div>
        <div v-for="t in impact.downTables" :key="t.name" class="sec-row">
          <span>{{ t.name }}</span><i>{{ t.task }}</i>
        </div>
      </div>
      <div v-if="impact.downTasks.length" class="impact-sec">
        <div class="sec-title">下游任务</div>
        <div v-for="t in impact.downTasks" :key="t.name" class="sec-row">
          <span>{{ t.name }}</span><i>{{ t.wf }} · {{ t.type }}</i>
        </div>
      </div>
      <div v-if="impact.downIndicators.length" class="impact-sec">
        <div class="sec-title">受影响指标</div>
        <div v-for="m in impact.downIndicators" :key="m.code" class="sec-row">
          <span>{{ m.name }}</span><i>{{ m.code }}</i>
        </div>
      </div>
      <div v-if="impact.reports.length" class="impact-sec">
        <div class="sec-title">关联报表</div>
        <div v-for="r in impact.reports" :key="r" class="sec-row"><span>{{ r }}</span></div>
      </div>
      <div
        v-if="!impact.downTables.length && !impact.downTasks.length && !impact.downIndicators.length && !impact.reports.length"
        class="impact-empty"
      >暂无血缘（该表无下游影响对象）</div>
    </div>
  </div>
</template>

<style scoped>
.lineage-page{position:relative;height:100%;display:flex;flex-direction:column}
.lineage-toolbar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);background:#fff;z-index:5}
.seg{display:flex;gap:2px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:2px}
.seg button{border:none;background:transparent;padding:5px 14px;font-size:12px;cursor:pointer;color:var(--text-2);border-radius:var(--radius-sm);transition:all var(--dur-base) var(--ease);min-height:28px}
.seg button:hover{color:var(--text)}
.seg button.on{background:#fff;color:var(--primary);font-weight:600;box-shadow:0 1px 3px rgba(16,24,40,.14)}
.sep{width:1px;height:18px;background:var(--border)}
.hint{font-size:11.5px;color:var(--text-3)}
.trunc-hint{color:#d97706}
/* 实例追溯上下文条（Task 8）：工具栏下方常驻，同白底描边视觉；状态 pill 复用全局 .pill.ok/err/info */
.trace-bar{display:flex;align-items:center;gap:10px;padding:6px 12px;border-bottom:1px solid var(--border);background:var(--primary-light,#e8f1ff);font-size:12px;z-index:5}
.tb-cap{font-weight:700;color:var(--primary);font-size:12px}
.tb-kv{color:var(--text-3)}
.tb-kv b{color:var(--text);font-weight:600}
.tb-flex{flex:1}
.tb-back{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:3px 10px;font-size:11.5px;cursor:pointer;color:var(--text-2)}
.tb-back:hover{border-color:var(--primary);color:var(--primary);background:#fff}
/* 来源图例（常驻左下角，避让 Controls 左上 / MiniMap 右下 / impact-card 右下） */
.lineage-legend{position:absolute;left:48px;bottom:16px;z-index:15;display:flex;flex-direction:column;gap:5px;background:rgba(255,255,255,.94);border:1px solid var(--border);border-radius:var(--radius);padding:8px 12px;font-size:11px;color:var(--text-2);box-shadow:0 2px 8px rgba(15,23,42,.08);pointer-events:none}
.lg-title{font-size:10.5px;font-weight:600;color:var(--text-3);margin-bottom:1px}
.lg-item{display:flex;align-items:center;gap:6px;line-height:1.5}
.lg-line{display:inline-block;width:22px;border-top:2px solid}
.lg-run{border-color:#1668dc}
.lg-design{border-color:#d97706;border-top-style:dashed}
.lg-dual{font-style:normal;font-size:9px;font-weight:700;background:var(--primary-light,#e8f1ff);color:#1668dc;border:1px solid #1668dc;border-radius:999px;padding:0 4px;line-height:1.5}
.lg-unv-mark{font-style:normal;font-size:9px;font-weight:700;background:#d97706;color:#fff;border-radius:999px;padding:0 4px;line-height:1.5}
.impact-card{position:absolute;right:16px;bottom:16px;width:320px;max-height:60%;overflow:auto;background:#fff;border:1px solid var(--border-strong);border-radius:var(--radius-lg);box-shadow:0 8px 24px rgba(15,23,42,.12);z-index:20;font-size:12px}
.impact-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border);background:var(--primary-light)}
.impact-head b{font-size:12.5px;color:var(--primary)}
.impact-close{border:none;background:none;font-size:16px;cursor:pointer;color:var(--text-3);line-height:1}
.impact-summary{padding:8px 12px;color:var(--text-2);border-bottom:1px dashed var(--border)}
.impact-sec{padding:8px 12px 2px}
.sec-title{font-size:11px;color:var(--text-3);margin-bottom:4px;font-weight:600}
.sec-row{display:flex;justify-content:space-between;gap:8px;padding:3px 0;border-bottom:1px solid var(--bg)}
.sec-row span{color:var(--text)}
.sec-row i{font-style:normal;font-size:10.5px;color:var(--text-3);white-space:nowrap}
.impact-empty{padding:16px 12px;text-align:center;color:var(--text-3)}
.search-in{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:4px 10px;font-size:12px;width:180px;outline:none;background:#fff;color:var(--text);transition:border-color var(--dur-base) var(--ease)}
.search-in:focus{border-color:var(--primary)}
.search-in::placeholder{color:var(--text-3)}
/* 最近浏览面包屑（Task 7）：画布顶部悬浮条，避让工具栏与图例 */
.crumb-bar{position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:15;display:flex;align-items:center;gap:4px;max-width:70%;overflow:auto;background:rgba(255,255,255,.95);border:1px solid var(--border);border-radius:999px;padding:3px 10px;font-size:11px;box-shadow:0 2px 8px rgba(15,23,42,.08)}
.crumb-label{color:var(--text-3);white-space:nowrap}
.crumb{border:1px solid var(--border);background:#fff;border-radius:999px;padding:1px 8px;font-size:11px;cursor:pointer;color:var(--primary);white-space:nowrap}
.crumb:hover{border-color:var(--primary);background:var(--primary-light)}
.crumb.cur{border-color:transparent;background:none;color:var(--text);font-weight:600;cursor:default}
.crumb-sep{color:var(--text-3)}
.tr-row{padding:4px 0;border-bottom:1px solid var(--bg)}
.tr-map{font-size:11.5px;color:var(--text-2)}
.tr-map b{color:var(--primary);font-weight:600}
.tr-expr{margin:2px 0 4px;padding:4px 8px;background:var(--bg);border-radius:var(--radius-sm);font-size:10.5px;color:var(--text-2);white-space:pre-wrap;word-break:break-all}
.tr-src{border-top:1px dashed var(--border)}
.tr-stmt{margin-bottom:6px;padding:6px 8px;background:var(--bg);border-radius:var(--radius-sm);font-size:10.5px;color:var(--text-2);white-space:pre-wrap;word-break:break-all;max-height:120px;overflow:auto}
.tr-meta{display:flex;flex-wrap:wrap;gap:10px;font-size:10.5px;color:var(--text-3)}
/* 字段级面板（Task 6 映射图/明细页签） */
.field-panel{flex:1;min-height:0;display:flex;flex-direction:column;background:var(--bg)}
.fp-head{display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid var(--border);background:#fff}
.fp-select{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:4px 8px;font-size:12px;max-width:320px;background:#fff;color:var(--text);outline:none}
.fp-empty{flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-3);font-size:12.5px;padding:24px}
.fp-detail{flex:1;min-height:0;overflow:auto;margin:12px;background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:6px 0}
.fp-sec{padding:8px 12px 2px}
</style>