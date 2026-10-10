<script setup lang="ts">
/**
 * GraphWorkbench：统一图工作台内核。
 * 左 Palette(edit) + 中 VueFlow 画布 + 右 Inspector + FloatLayer 浮窗 + 顶部工具栏。
 * 视角差异全部由注入的 ViewProfile 决定（菜单即视角）。
 */
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import type { Connection, EdgeChange, EdgeMouseEvent, NodeChange, NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

import type { ClipboardNode, DocGroup, EdgePartialDep, GraphDocument, GEdge, GEdgeKind, GNode, GNodeData, Issue, AlignDir, DistributeAxis } from '../model'
import { cloneDoc, uid, resolveNodeSchema, alignNodes, distributeNodes, pasteSelection } from '../model' // Task 11（§3.5）：批量对齐/分布/复制粘贴纯函数
import { connectionRejectReason } from '../model/connectionGuard'
import type { ConnSpec, PortTypesHint } from '../model/connectionGuard'
import { collectDocErrors, issuesToSources } from '../model/docErrors' // Task 10（§3.3）：错误聚合模型
import type { DocError } from '../model/docErrors'
import { portTypesMatch } from '../model/portTypes'
import { applyLayout } from '../layout'
import type { NodeSchema, ViewProfile } from '../profiles'
import type { ComponentCategory } from '../profiles/types' // I12 R1：doc 推导组件库置顶标签用
import { onEdgeCreated, onEdgeRemoved, decideDrop, prefillFromUpstream, prefillDeclaredFromUpstream, applyInitTemplate } from '../profiles/formLinkage' // 拖边即引用（端点合一 §3.3）+ F1 拖入闸门 + M5 initTemplate 落图合入
import { createTemplateStage, selectTemplateSteps, stagedUpstreamOf } from '../profiles/templateStaging'
import type { TemplateStage } from '../profiles/templateStaging'
import { useGraphStore } from '../../stores/graph'
import { patchById } from './syncFromDoc'
import { useAuthStore } from '../../stores/auth'
import { useRunStore } from '../../stores/run'
import { useFloatStore } from '../../stores/float'
import { useComponentStore } from '../../stores/componentStore' // Task 5（§2.3）：spec 规格缓存，两源并存 schema 解析
import { graphService, isMock } from '../../services'
import type { DagPickItem } from '../../stores/dagTabs'
import { canvasOnlyRenderVisible } from './canvasFlags' // Task 12（§3.6）：视口裁剪开关（localStorage datara.wb.flags）
import { loadCanvasState, saveCanvasState, type CanvasState } from '../../composables/useCanvasState' // Task 14（§3.7）：画布状态持久化（canvas-state:{docId}）

import DataNode from './DataNode.vue'
import RerouteNode from './RerouteNode.vue'
import EdgeDataFloat from './EdgeDataFloat.vue'
import { edgeDataClass, EDGE_DATA_TYPE_VISUALS, resolveEdgeDataType } from './edgeData'
import Palette from './Palette.vue'
import Inspector from './Inspector.vue'
import DropConfigDialog from './DropConfigDialog.vue'
import FloatLayer from './FloatLayer.vue'
import ErrorPanel from './panels/ErrorPanel.vue' // Task 10（§3.3）：错误聚合面板（底部抽屉，替代 IssuePanel 浮窗入口；IssuePanel.vue 文件保留）
import ShortcutHelp from './panels/ShortcutHelp.vue' // Task 11（§3.5）：快捷键帮助浮窗（`?` 唤起）
import LogPanel from './panels/LogPanel.vue'
import WfVarPanel from './panels/WfVarPanel.vue'
import AiPanel from './panels/AiPanel.vue'
import VersionPanel from './panels/VersionPanel.vue'
import RunDialog from './RunDialog.vue'
import { Search, FullScreen, RefreshLeft, RefreshRight, Operation, Grid, Refresh, Warning } from '@element-plus/icons-vue'

const props = defineProps<{
  profile: ViewProfile
  docId: string
  doc?: GraphDocument | null
  snapKey?: string
  /** I11：画布标题副元数据（#code / 目录 / 名称）；宿主由 dagTabs 激活项推导 */
  docMeta?: { code?: number; category?: string }
  /** 宿主托管载入（任务中心统一画布）：Palette 载入请求上抛宿主，由宿主决定视角/文档，本组件不自行合并 */
  hostManaged?: boolean
  /** 宿主切换文档后要并入的其余选中任务 id（首屏合并一次，配合 :key 强刷） */
  mergeIds?: string[]
  /** Analysis-only canvases, such as lineage, do not have a workflow-definition context. */
  hideVars?: boolean
}>()
const emit = defineEmits<{
  select: [id: string | null]
  'pick-tasks': [{ items: DagPickItem[] }]
  /** Task 7 血缘交互：profile.nodeCenter 视角下，节点双击/右键「以此为中心」上抛宿主重拉 */
  'center-node': [id: string]
}>()

const graphStore = useGraphStore()
const run = useRunStore()
const floatStore = useFloatStore()
const auth = useAuthStore()
const router = useRouter()
/** 组件治理入口（M0 目录 / M1 设计器）：顶栏按钮进入，不占用左侧导航 */
function gotoCatalog() { void router.push('/meta/components') }
/** 基线化工作台（M-B0 组件基线化）：顶栏按钮进入，与组件目录并列 */
function gotoBaseline() { void router.push('/meta/baseline') }
/** 系统权限降级（M15）：只读角色（analyst/viewer）强制进入 view 模式 */
const effMode = computed(() => (props.profile.mode === 'edit' && !auth.canEdit ? 'view' : props.profile.mode))
const { screenToFlowCoordinate, fitView, fitViewOnInitDone, viewport, setViewport, findNode } = useVueFlow() // Task 11（§3.5）：findNode 取画布实测尺寸/同步 position

/* Task 12（§3.6）视口裁剪：仅渲染可视区元素（大图拖拽/缩放帧开销大头），setup 取一次成常量；
 * 默认开，canvasFlags（localStorage datara.wb.flags）可手动关闭排查渲染问题 */
const onlyRenderVisible = canvasOnlyRenderVisible()

/** N15 快照恢复的视口（首屏 fit 完成后回放；无快照时为 null → 走 0.8 收敛） */
const restoredViewport = ref<{ x: number; y: number; zoom: number } | null>(null)

/* F56c：首屏构图——vue-flow 内部 fit-view-on-init 是无参调用（默认 padding），在节点尺寸测量后
   触发，晚于 onMounted 里的任何 fitView 并将其覆盖（实测 0.8 被打回 0.57）。因此等 fitViewOnInitDone
   翻转（init fit 完成）后再执行：有快照视口则回放（N15，保证还原上次编辑位置），否则 maxZoom 0.8
   只封顶不抬底——大屏把过大的自然适配统一收敛到 0.8 可读档位并居中；窄画布保持自然适配，绝不裁切节点。 */
watch(fitViewOnInitDone, (done) => {
  if (done) nextTick(() => {
    if (restoredViewport.value) setViewport({ ...restoredViewport.value })
    else fitView({ padding: 0, maxZoom: 0.8 })
  })
})

const FALLBACK_SCHEMA: NodeSchema = { type: 'unknown', label: '未知', icon: '?', color: '#94a3b8', form: [] }

/* ---------- Task 5（方案§2.3，R1 对策）：spec 驱动渲染 + profile 兜底降级 ----------
   两源并存：profile 仍是主数据源；spec 规格已加载且未降级时，命中类型的组件由 spec 视图驱动
   （画布节点/Inspector 表单、拖入弹窗、palette 行），未命中回落 profile，其余 nodeTypes 读取点不动。 */
const componentStore = useComponentStore()
/** spec 规格可用闸门：已加载（200/304 往返成功）且未降级（服务不可用 → 强制 profile 兜底） */
const specEnabled = computed(() => componentStore.loaded && !componentStore.degraded)
/** 两源并存 schema 解析：spec 命中 → specToSchema 适配视图；否则 profile（可 undefined） */
function schemaFor(type: string): NodeSchema | undefined {
  return resolveNodeSchema(type, props.profile, componentStore.specMap, specEnabled.value)
}
/* spec 规格异步到位（晚于画布首装）后重装配渲染数组，画布节点/Inspector 表单切换到 spec 视图。
   双源：specEnabled 翻转（到位/降级回落）与 specMap 引用替换（失效重拉 200 重建）均重装配；
   304 沿用不动 specMap 引用不触发；从未启用（首拉即降级）无需装配 */
watch([specEnabled, () => componentStore.specMap], ([on], [prevOn]) => {
  if (on || prevOn) syncFromDoc()
})

// vue-flow 深层泛型实例化易触发 TS2589，渲染数组放宽为 any（数据契约仍是 GraphDocument）
/* eslint-disable @typescript-eslint/no-explicit-any */
const flowNodes = ref<any[]>([])
const flowEdges = ref<any[]>([])
const selectedId = ref<string | null>(null)
const autoRefresh = ref(false)

/* ---------- F56b 画布交互增强状态 ---------- */
/** N5 多选集（框选 / Ctrl 点选；节点与边分开维护，Del 批删） */
const selectedIds = ref<Set<string>>(new Set())
const selectedEdgeIds = ref<Set<string>>(new Set())
/** N12 面板收放（持久化 datara.wb.panels） */
const leftOpen = ref(true)
const rightOpen = ref(true)
/** I11 侧窗拖拽调宽：初始宽度随面板样式（Palette 232 / wb-right 288），拖拽期间实时更新并持久化 */
const leftWidth = ref(232)
const rightWidth = ref(288)
const PANEL_MIN_W = 140
const PANEL_MAX_W = 520
let resizeSide: 'left' | 'right' | null = null
let resizeStartX = 0
let resizeStartW = 0
function startResize(side: 'left' | 'right', e: MouseEvent) {
  resizeSide = side
  resizeStartX = e.clientX
  resizeStartW = side === 'left' ? leftWidth.value : rightWidth.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', stopResize)
  e.preventDefault()
}
function onResizeMove(e: MouseEvent) {
  if (!resizeSide) return
  const dx = e.clientX - resizeStartX
  const w = Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, resizeStartW + (resizeSide === 'left' ? dx : -dx)))
  if (resizeSide === 'left') leftWidth.value = w
  else rightWidth.value = w
}
function stopResize() {
  resizeSide = null
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', stopResize)
}
/** N15 右侧边窗双 Tab：属性(Inspector) / 变量（日志已按 I11 移入「更多」浮窗，LogPanel 仍由更多菜单复用） */
const rightTab = ref<'inspector' | 'vars'>('inspector')
const rightTabs = computed<{ k: 'inspector' | 'vars'; label: string; icon: string }[]>(() => {
  const tabs: { k: 'inspector' | 'vars'; label: string; icon: string }[] = [
    { k: 'inspector', label: '属性', icon: '☰' },
  ]
  if (!props.hideVars) tabs.push({ k: 'vars', label: '变量', icon: '$' })
  return tabs
})
watch(() => props.hideVars, (hide) => {
  if (hide && rightTab.value === 'vars') rightTab.value = 'inspector'
}, { immediate: true })
/** N7 类型过滤（视图态，不落 doc） */
const hiddenTypes = ref<Set<string>>(new Set())
/** N6 折叠组（视图态；组元数据存 doc.groups 随版本保存） */
const collapsedGroups = ref<Set<string>>(new Set())
/** 导航面板（图例过滤 / 大纲 / 组管理） */
const navOpen = ref(false)
/** N8 搜索 */
const searchOpen = ref(false)
const searchKw = ref('')
const lastKw = ref('')
const searchHit = ref<string | null>(null)
const searchList = ref<string[]>([])
const searchIdx = ref(0)
const searchInput = ref<HTMLInputElement | null>(null)
/** N1 拖入高亮 */
const dropHot = ref(false)
let dragDepth = 0

const doc = computed(() => props.doc ?? graphStore.doc)
const selectedNode = computed<GNode | null>(() =>
  doc.value?.nodes.find((n) => n.id === selectedId.value) ?? null)

/** I12 R1：由当前 doc 节点分类推导组件库置顶标签（仅决定分组置顶，不过滤组件）：
 *  含专属 etl 类节点→['ETL']、含 stream→['流']、含专属 sync→['同步']、否则 ['普通']。
 *  「专属」= 节点分类只含此任务类与 general——控制类节点同时归属 sync+etl 不作判据，
 *  以免任何 dag 文档都误判为 ETL；优先序沿用任务书：etl → stream → sync → 普通。 */
const paletteActiveTags = computed<string[]>(() => {
  const nodes = doc.value?.nodes
  if (!nodes?.length) return ['普通']
  /* I12 R1（Nit 修复）：单次遍历收集各专属类存在性，替代 has() 三次全量遍历 + kindOf 重复推导 */
  const seen: Partial<Record<ComponentCategory, true>> = {}
  for (const n of nodes) {
    const cs = props.profile.nodeTypes[n.type]?.categories
    if (!cs) continue
    const kinds = cs.filter((c) => c !== 'general')
    // 「专属」= 分类只含单一任务类与 general——控制类节点同时归属 sync+etl 不作判据
    if (kinds.length === 1) seen[kinds[0]] = true
  }
  if (seen.etl) return ['ETL']
  if (seen.stream) return ['流']
  if (seen.sync) return ['同步']
  return ['普通']
})

/* ---------- doc ↔ flow 同步 ---------- */

function toFlowNode(g: GNode): any {
  return {
    id: g?.id ?? `node_fallback_${Math.random().toString(36).slice(2, 8)}`,
    type: 'gn',
    position: g?.position ?? { x: 0, y: 0 },
    data: { gnode: g, schema: schemaFor(g?.type ?? '') ?? FALLBACK_SCHEMA }, // Task 5：spec 命中 → spec 视图，否则 profile
  }
}

function toFlowEdge(e: GEdge, nodeMap?: Map<string, GNode>): any {
  // 防御：边数据缺少 id/source/target 时生成占位边（避免 VueFlow setEdges 内部 toString() 崩溃）
  // VueFlow setEdges 内部会对 edge 的多个字段调用 toString()，undefined/null 会抛 TypeError
  const rawId = e?.id ?? `edge_fallback_${Math.random().toString(36).slice(2, 8)}`
  const rawSource = e?.source ?? 'node_unknown'
  const rawTarget = e?.target ?? 'node_unknown'
  const k = props.profile.edgeKinds[e?.kind ?? props.profile.defaultEdge]
    ?? Object.values(props.profile.edgeKinds)[0]
  // 防御：edgeKinds 配置缺失时提供默认样式
  // 全量同步传 nodeMap（O(1) 查找，避免 O(E×N)）；单边增量调用点缺省时退回线性查找，行为一致
  const sourceNode = nodeMap
    ? (e?.source != null ? nodeMap.get(e.source) : undefined)
    : doc.value?.nodes.find((node) => node.id === e?.source)
  const sourceSpec = sourceNode && specEnabled.value ? componentStore.specMap.get(sourceNode.type) : undefined
  const dataType = resolveEdgeDataType(e?.sourceHandle, sourceSpec)
  const color = EDGE_DATA_TYPE_VISUALS[dataType].color
  const edgeType = k?.edgeType ?? 'default'
  const dashed = k?.dashed ?? false
  const animated = k?.animated ?? false
  return {
    id: String(rawId),
    source: String(rawSource),
    target: String(rawTarget),
    sourceHandle: e?.sourceHandle != null ? String(e.sourceHandle) : '',
    targetHandle: e?.targetHandle != null ? String(e.targetHandle) : '',
    type: edgeType,
    class: edgeDataClass(dataType),
    data: { dataType },
    label: e?.label != null ? String(e.label) : '',
    labelStyle: { fill: color, fontSize: 9.5 },
    labelBgPadding: [4, 2],
    labelBgBorderRadius: 3,
    labelBgStyle: { fill: '#fff', fillOpacity: 0.85, stroke: color, strokeWidth: 0.5 },
    style: { stroke: color, strokeWidth: 1.6, strokeDasharray: dashed ? '6 4' : '' },
    markerEnd: { type: MarkerType.ArrowClosed, color },
    animated,
  }
}

/**
 * Prefer an id-based patch so routine draft updates keep Vue Flow's transient
 * state.  The complete rebuild is deliberately retained as a safe P0 fallback
 * for malformed legacy documents or an unexpected projector failure.
 */
function syncFromDoc() {
  if (!doc.value) return
  const nodeMap = new Map(doc.value.nodes.map((n) => [n.id, n])) // 一次建 Map，全量边同步 O(1) 查节点
  try {
    flowNodes.value = patchById(flowNodes.value, doc.value.nodes, toFlowNode)
      .items
      .filter((node) => node.type !== 'gbadge')
    flowEdges.value = patchById(flowEdges.value, doc.value.edges, (e) => toFlowEdge(e, nodeMap)).items
  } catch (error) {
    console.warn('Incremental graph sync failed; rebuilding canvas state.', error)
    flowNodes.value = doc.value.nodes.map(toFlowNode)
    flowEdges.value = doc.value.edges.map((e) => toFlowEdge(e, nodeMap))
  }
  applyVisibility()
}

/* ---------- F56b：可见性（N7 类型过滤 + N6 组折叠）与合成徽标 ---------- */

/** 折叠组徽标拖放位（会话级，不入 doc；键 = 组 id） */
const badgePos: Record<string, { x: number; y: number }> = {}

/** 类型过滤/折叠组成员 → hidden 标记；折叠组生成合成徽标节点（仅渲染层，绝不入 doc） */
function applyVisibility() {
  const d = doc.value
  if (!d) return
  const hid = new Set<string>()
  ;(d.groups ?? []).forEach((g) => {
    if (collapsedGroups.value.has(g.id)) g.nodeIds.forEach((id) => hid.add(id))
  })
  flowNodes.value.forEach((fn) => {
    if (fn.type === 'gbadge') return
    const g = fn.data?.gnode as GNode | undefined
    fn.hidden = !!g && (hiddenTypes.value.has(g.type) || hid.has(g.id))
    if (fn.hidden) hid.add(fn.id)
  })
  flowEdges.value.forEach((fe) => { fe.hidden = hid.has(fe.source) || hid.has(fe.target) })
  const badges = (d.groups ?? [])
    .filter((g) => collapsedGroups.value.has(g.id))
    .map((g) => {
      const members = g.nodeIds
        .map((id) => d.nodes.find((n) => n.id === id))
        .filter((n): n is GNode => !!n)
      const cx = members.length ? members.reduce((s, n) => s + n.position.x, 0) / members.length : 0
      const cy = members.length ? members.reduce((s, n) => s + n.position.y, 0) / members.length : 0
      return {
        id: `grp:${g.id}`,
        type: 'gbadge',
        position: badgePos[g.id] ?? { x: cx, y: cy },
        data: { name: g.name, count: members.length },
      }
    })
  if (badges.length || flowNodes.value.some((fn) => fn.type === 'gbadge')) {
    flowNodes.value = flowNodes.value.filter((fn) => fn.type !== 'gbadge').concat(badges)
  }
}

/** 复位失效选中（删除/撤销/回滚后节点或边已不存在） */
function pruneSelection() {
  const d = doc.value
  const ids = new Set(d?.nodes.map((n) => n.id) ?? [])
  const eids = new Set(d?.edges.map((e) => e.id) ?? [])
  selectedIds.value = new Set([...selectedIds.value].filter((id) => ids.has(id)))
  selectedEdgeIds.value = new Set([...selectedEdgeIds.value].filter((id) => eids.has(id)))
  if (selectedId.value && !ids.has(selectedId.value)) selectedId.value = null
}

onMounted(async () => {
  /* N12 面板收放持久化恢复 */
  try {
    const p = JSON.parse(localStorage.getItem('datara.wb.panels') ?? '{}') as { left?: boolean; right?: boolean; rightTab?: string; leftW?: number; rightW?: number }
    if (typeof p.left === 'boolean') leftOpen.value = p.left
    if (typeof p.right === 'boolean') rightOpen.value = p.right
    if (p.rightTab === 'inspector' || (!props.hideVars && p.rightTab === 'vars')) rightTab.value = p.rightTab
    if (typeof p.leftW === 'number' && p.leftW >= PANEL_MIN_W && p.leftW <= PANEL_MAX_W) leftWidth.value = p.leftW
    if (typeof p.rightW === 'number' && p.rightW >= PANEL_MIN_W && p.rightW <= PANEL_MAX_W) rightWidth.value = p.rightW
  } catch { /* 忽略隐私模式 */ }
  window.addEventListener('keydown', onKeydown)
  if (!props.doc) await graphStore.load(props.docId)
  syncFromDoc()
  /* N15 快照恢复（面板/视口/未保存草稿）；须在首屏 fit 前设置 restoredViewport 供上方 watch 回放 */
  restoreSnap()
  /* Task 14（§3.7）：canvas-state 恢复（视口/选区/浮窗开合）——在快照恢复后执行，
     确保草稿替换与 flowNodes 就绪后再恢复选区；视口以 canvas-state（move-end 级新鲜度）为准 */
  restoreCanvasState()
  /* 宿主切换视角后要并入的其余选中任务（首个已在 :key 中作为画布文档加载） */
  if (props.mergeIds?.length) await onLoadTasks(props.mergeIds)
  /* 首屏构图见 setup 顶部 fitViewOnInitDone watch（等内部 init fit 完成后再收敛/回放视口） */
})

/* Task 14 审查修复：归位链中止旗标（plain 变量，非响应式）。必须是每实例私有——script setup 体
 * 随实例执行，KeepAlive 下多画布缓存实例共存时各持一份；若提升为模块级共享，其他实例的
 * 激活/休眠会冲掉本实例的判定（误放行已休眠实例挂起的归位链）。 */
let wbActive = true

onBeforeUnmount(() => {
  wbActive = false // Task 14 审查修复：卸载即失活——挂起的归位链 await 恢复后据此中止
  window.removeEventListener('keydown', onKeydown)
  stopResize()
  /* N15 离开时落快照（面板收展/右Tab + 视口 + 未保存草稿）；keep-alive 复活场景由 onDeactivated 提前落，此处保留双保险 */
  saveSnap()
})

/* Task 14（§4.5）：KeepAlive 缓存复活/休眠钩子（仅宿主包 <KeepAlive> 时触发，如任务中心画布 Tab）。
 * graphStore 为全局单例（doc/undo 栈/dirty 跨 Tab 共享），后台 Tab 被其他画布 load 过后
 * 本实例的 doc 计算值会指向他人文档——复活时按 docId 归位重载 + 草稿快照找回，防跨 Tab 串扰。 */
onActivated(async () => {
  /* keydown 监听重挂：与 onMounted 的添加幂等（本组件另有非 KeepAlive 宿主——血缘/运行详情/拓扑，
     仅依赖 activated 会导致那些宿主永不挂监听），keep-alive 场景由 onDeactivated 卸下、此处补回 */
  window.addEventListener('keydown', onKeydown)
  wbActive = true
  if (props.doc || graphStore.doc?.id === props.docId) return // 外部注入文档不归位；仍持有本文档则免重载
  try { await graphStore.load(props.docId) } catch { return } // 文档已被删除等：保持现状不中断
  /* Task 14 审查修复：await 期间实例可能已被再次休眠/卸载（快速切 Tab），或 store 单例已被
     其他 Tab 的 load 重指向——两种情况都中止归位链，防旧实例把他人文档/过期状态刷进画布 */
  if (!wbActive) return
  if (graphStore.doc?.id !== props.docId) return
  syncFromDoc()
  restoreSnap() // 取回休眠前 saveSnap 落的未保存草稿（与首次挂载同序：load → sync → restoreSnap）
  /* Task 14 审查修复：复用挂载恢复函数全量恢复（视口+选区+浮窗开合），不再只回放视口；
     时机仍在 syncFromDoc 之后（flowNodes 已就绪），与首次挂载链路一致 */
  restoreCanvasState()
})

/* 休眠：卸下 keydown 监听（防后台缓存实例响应方向键微移/粘贴等键盘操作——多实例共存时重复触发的硬性问题），
 * 并落 canvas-state 与草稿快照（onBeforeUnmount 保留双保险） */
onDeactivated(() => {
  wbActive = false // Task 14 审查修复：休眠即失活——挂起的归位链 await 恢复后据此中止
  window.removeEventListener('keydown', onKeydown)
  persistCanvasState()
  saveSnap()
})

watch([leftOpen, rightOpen, rightTab, leftWidth, rightWidth], ([l, r, t, lw, rw]) => {
  try { localStorage.setItem('datara.wb.panels', JSON.stringify({ left: l, right: r, rightTab: t, leftW: lw, rightW: rw })) } catch { /* 忽略隐私模式 */ }
})

/* 外部注入文档（血缘等只读视图）：重建渲染数组 + 复位失效选中 + 适配视图 */
watch(() => props.doc, (d) => {
  if (!d) return
  syncFromDoc()
  pruneSelection()
  nextTick(() => fitView({ padding: 0.15 }))
})

/* store.doc 引用变更（版本回滚/保存后替换/撤销重做 N14）时重同步渲染数组；外部注入文档以 props 为准 */
watch(() => graphStore.doc, (d) => {
  if (props.doc || !d) return
  syncFromDoc()
  pruneSelection()
})

/* ---------- N15 快照四合一：docId + 面板收展/右Tab + 未保存草稿 + 视口 ---------- */

/** 快照命名空间（按 snapKey 隔离；未传则按 profile.id，独立路由天然按视角隔离） */
const snapNs = computed(() => `datara.dag.snap.${props.snapKey ?? props.profile.id}`)

/** 离开工作台时落快照：外部注入 doc（血缘等只读视图）不保存；无文档不保存；
 *  keep-alive 后台实例（graphStore 单例已被其他 Tab 归位为他人文档）不写——其自身草稿已由 onDeactivated 落盘 */
function saveSnap() {
  if (props.doc || !doc.value || doc.value.id !== props.docId) return
  try {
    localStorage.setItem(snapNs.value, JSON.stringify({
      docId: doc.value.id,
      panels: { left: leftOpen.value, right: rightOpen.value, rightTab: rightTab.value, leftW: leftWidth.value, rightW: rightWidth.value },
      draft: graphStore.dirty ? cloneDoc(doc.value) : null, // 仅未保存草稿（已保存版本无需快照）
      viewport: { x: viewport.value.x, y: viewport.value.y, zoom: viewport.value.zoom },
    }))
  } catch { /* 忽略隐私模式 */ }
}

/** 打开工作台时恢复快照：面板收展/右Tab、视口（交首屏 watch 回放）、未保存草稿 */
function restoreSnap() {
  if (props.doc) return
  try {
    const s = JSON.parse(localStorage.getItem(snapNs.value) ?? 'null') as
      | { docId?: string; panels?: { left?: boolean; right?: boolean; rightTab?: string; leftW?: number; rightW?: number }; draft?: GraphDocument | null; viewport?: { x: number; y: number; zoom: number } }
      | null
    if (!s || s.docId !== props.docId) return
    if (typeof s.panels?.left === 'boolean') leftOpen.value = s.panels.left
    if (typeof s.panels?.right === 'boolean') rightOpen.value = s.panels.right
    if (s.panels?.rightTab === 'inspector' || (!props.hideVars && s.panels?.rightTab === 'vars')) rightTab.value = s.panels.rightTab
    if (typeof s.panels?.leftW === 'number' && s.panels.leftW >= PANEL_MIN_W && s.panels.leftW <= PANEL_MAX_W) leftWidth.value = s.panels.leftW
    if (typeof s.panels?.rightW === 'number' && s.panels.rightW >= PANEL_MIN_W && s.panels.rightW <= PANEL_MAX_W) rightWidth.value = s.panels.rightW
    if (s.viewport && Number.isFinite(s.viewport.x) && Number.isFinite(s.viewport.y) && Number.isFinite(s.viewport.zoom)) {
      restoredViewport.value = { x: s.viewport.x, y: s.viewport.y, zoom: s.viewport.zoom }
    }
    /* 未保存草稿恢复：仅同文档且含节点数组（覆盖已落库版本，续编不丢改动） */
    if (s.draft && s.draft.id === props.docId && Array.isArray(s.draft.nodes)) {
      graphStore.replace(s.draft)
      syncFromDoc()
    }
  } catch { /* 忽略损坏快照 */ }
}

/* ---------- 工具栏动作 ---------- */

/** Task 8（§3.1）：全图边类型复检（保存闸门）——portTypesMatch 逐边判，错误并入现有 issues 展示链路；
 *  断链/重复/成环由既有校验器负责不重复报（聚合校验模型 Task 10 再做，本轮不另造） */
function edgeTypeIssues(d: GraphDocument): Issue[] {
  const out: Issue[] = []
  const ids = new Set(d.nodes.map((n) => n.id))
  for (const e of d.edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue
    const pt = connPortTypes(d, e)
    if (!portTypesMatch(pt.src, pt.dst)) {
      out.push({
        level: 'error',
        msg: `类型不匹配：源 ${pt.src ?? 'any'} → 目标 ${pt.dst ?? 'any'}（边 ${e.source}→${e.target}）`,
        edgeId: e.id,
        nodeId: e.source,
      })
    }
  }
  return out
}

/* ---------- Task 10（§3.3）：错误聚合模型（computed 实时聚合 + onConnect 瞬时拒绝） ---------- */

/** 瞬时错误（onConnect 拒绝，如成环）：doc 引用/结构变化或下次校验时清空，合并进最终错误列表 */
const transientErrors = ref<DocError[]>([])
/** 实时校验错误：validators（轻量纯函数）+ Task 8 边类型复检 → 分类映射 → 统一列表；修复后自动消失 */
const validatorErrors = computed<DocError[]>(() => {
  const d = doc.value
  if (!d) return []
  const issues: Issue[] = []
  props.profile.validators.forEach((v) => issues.push(...v(d)))
  issues.push(...edgeTypeIssues(d)) // Task 8（§3.1）：全图边类型复检兜底
  return collectDocErrors(d, issuesToSources(issues))
})
/** 最终错误模型：ErrorPanel / 工具栏 Badge / 红描边 / Inspector 卡片的统一数据源 */
const docErrors = computed<DocError[]>(() => [...validatorErrors.value, ...transientErrors.value])
/** 有 node 类错误的节点 id 集（DataNode 红描边 st-error）——只认 error 级，warn 不误描红 */
const errorNodeIds = computed(() => {
  const s = new Set<string>()
  for (const e of docErrors.value) if (e.level === 'error' && e.kind === 'node' && e.nodeId) s.add(e.nodeId)
  return s
})
/** 选中节点的 node 类错误 message 列表（Inspector 错误卡片）——同样只认 error 级 */
const selectedNodeErrors = computed(() =>
  selectedId.value
    ? docErrors.value.filter((e) => e.level === 'error' && e.kind === 'node' && e.nodeId === selectedId.value).map((e) => e.message)
    : [])
/** 工具栏 Badge 口径：只统计 error 级（warn 进面板琥珀提示，不计入红色总数） */
const errBadgeCount = computed(() => docErrors.value.reduce((n, e) => (e.level === 'error' ? n + 1 : n), 0))

/** 错误抽屉开关（工具栏 Badge / onValidate / onSave 闸门共用） */
const errPanelOpen = ref(false)
/** 定位高亮节点 id（error-focus 类挂载点，2s 自动移除；连续定位重置旧 timer 防泄漏） */
const focusNodeId = ref<string | null>(null)
let focusTimer: number | null = null
onBeforeUnmount(() => { if (focusTimer !== null) window.clearTimeout(focusTimer) })

/* ---------- Task 14（§3.7）：画布状态持久化（localStorage canvas-state:{docId}，写侧 500ms 防抖） ---------- */

/** 组装并防抖落盘当前画布状态（视口 + 选区 + 浮窗开合）；外部注入文档（血缘等只读视图）不落 */
function persistCanvasState() {
  /* Task 14 审查修复：归属守卫（与 saveSnap 同款）——自管模式下 store 单例可能已被其他 Tab 归位为
     他人文档（如后台实例 pruneSelection 清空选区触发 watch → 把清空选区写回本 docId 的 canvas-state），
     doc 非本文档时直接不落；props.doc 注入宿主本就不落盘，维持豁免。 */
  if (props.doc || !doc.value || doc.value.id !== props.docId) return
  saveCanvasState(props.docId, {
    version: 1,
    viewport: { x: viewport.value.x, y: viewport.value.y, zoom: viewport.value.zoom },
    selectedIds: [...selectedIds.value],
    activeTab: '', // 右侧面板 Tab 已有全局持久化（datara.wb.panels），本工作台不重复落
    floats: { nav: navOpen.value, errors: errPanelOpen.value },
  })
}

/** canvas-state 视口回放：zoom 夹取 [0.3,2]（下界与模板 min-zoom 一致）防脏数据；首屏交 restoredViewport 延迟回放，已挂载实例（keep-alive 复活/草稿恢复）直接 setViewport */
function applyCanvasStateViewport(st: CanvasState) {
  const v = st.viewport
  if (!v || !Number.isFinite(v.x) || !Number.isFinite(v.y) || !Number.isFinite(v.zoom)) return
  const zoom = Math.min(2, Math.max(0.3, v.zoom))
  restoredViewport.value = { x: v.x, y: v.y, zoom }
  if (fitViewOnInitDone.value) setViewport({ x: v.x, y: v.y, zoom })
}

/** 挂载与 keep-alive 复活共用恢复（Task 14 审查修复：复活路径不再只回放视口）：视口 + 选区（仅 edit 模式，过滤 doc 中已不存在的 id）+ 浮窗（导航/错误面板）开合 */
function restoreCanvasState() {
  if (props.doc) return
  const st = loadCanvasState(props.docId)
  if (!st) return
  applyCanvasStateViewport(st)
  if (effMode.value === 'edit' && st.selectedIds?.length && doc.value) {
    const ids = new Set(doc.value.nodes.map((n) => n.id))
    const valid = st.selectedIds.filter((id) => ids.has(id))
    if (valid.length) {
      selectedIds.value = new Set(valid)
      selectedId.value = valid[0]!
      flowNodes.value.forEach((f) => { if (f.type !== 'gbadge') f.selected = valid.includes(f.id) })
      emit('select', selectedId.value)
    }
  }
  if (typeof st.floats?.nav === 'boolean') navOpen.value = st.floats.nav
  if (typeof st.floats?.errors === 'boolean') errPanelOpen.value = st.floats.errors
}

/** 画布拖拽/缩放结束 → 防抖落盘视口（连同选区/浮窗最新态一次写入） */
function onCanvasMoveEnd() { persistCanvasState() }

/* 选区 / 浮窗开合变更 → 防抖落盘 */
watch(selectedIds, () => persistCanvasState())
watch([navOpen, errPanelOpen], () => persistCanvasState())

/* doc 引用/结构变化 → 清空瞬时拒绝（增删会替换 nodes/edges 数组引用；原地 push 由下次校验兜底清空） */
watch(
  () => [doc.value, doc.value?.nodes, doc.value?.edges],
  () => { transientErrors.value = [] },
)

/** ErrorPanel「定位」：node → fitView 该节点；edge → fitView source/target 并高亮 target；gate 无锚点不显示按钮 */
function locateError(err: DocError) {
  const d = doc.value
  if (!d) return
  let ids: string[] = []
  if (err.kind === 'node' && err.nodeId) ids = [err.nodeId]
  else if (err.kind === 'edge' && err.edgeId) {
    const e = d.edges.find((x) => x.id === err.edgeId)
    if (e) ids = [e.source, e.target]
  }
  const visible = ids.filter((id) => flowNodes.value.some((f: { id: string }) => f.id === id))
  if (!visible.length) return
  fitView({ nodes: visible, padding: 0.35, duration: 300, maxZoom: 1.4 })
  focusNodeId.value = visible[visible.length - 1]! // node 取自身；edge 取 target（末位）
  if (focusTimer) window.clearTimeout(focusTimer)
  focusTimer = window.setTimeout(() => { focusNodeId.value = null; focusTimer = null }, 2000)
}

async function onSave() {
  if (!doc.value) return
  /* W1 保存闸门：先跑视角校验器；存在 error（成环/缺源缺汇/混编等）时确认后才保存（warn 不阻断，保持草稿语义） */
  const pre: Issue[] = []
  props.profile.validators.forEach((v) => pre.push(...v(doc.value!)))
  pre.push(...edgeTypeIssues(doc.value!)) // Task 8（§3.1）：全图边类型复检兜底
  const errs = pre.filter((i) => i.level === 'error')
  if (errs.length) {
    errPanelOpen.value = true // Task 10（§3.3）：闸门发现 error 自动打开错误面板（错误模型与 pre 同源实时聚合）
    try {
      await ElMessageBox.confirm(
        `当前画布存在 ${errs.length} 个校验错误，如「${errs[0]!.msg}」。仍要保存吗？（可先点「校验」查看全部问题）`,
        '保存前校验',
        { confirmButtonText: '仍要保存', cancelButtonText: '返回修改', type: 'warning' },
      )
    } catch { return }
  }
  try {
    const { value } = await ElMessageBox.prompt('版本备注（可选）', '保存新版本', {
      confirmButtonText: '保存', cancelButtonText: '取消', inputPlaceholder: '如：新增质检节点',
    })
    try {
      const version = await graphStore.save(value || undefined)
      ElMessage.success(`已保存 v${version}（已落库，刷新后仍在）`)
    } catch (e) {
      /* I12-D2 保存并发冲突（后端 409/code 2005）：提示刷新加载最新版本；其余错误原样透出 */
      const code = (e as { code?: number }).code
      const msg = e instanceof Error ? e.message : String(e)
      if (code === 2005) ElMessage.error(`${msg}（请刷新画布，以最新版本为基础重新编辑保存）`)
      else ElMessage.error(`保存失败: ${msg}`)
    }
  } catch { /* 取消 */ }
}

function onValidate() {
  if (!doc.value) return
  /* Task 10（§3.3）：校验即刷新错误模型（computed 已按 doc 实时聚合）并打开错误面板抽屉，
     替代原 IssuePanel 浮窗（panels/IssuePanel.vue 保留由其它链路复用）；瞬时拒绝一并清空重检 */
  transientErrors.value = []
  errPanelOpen.value = true
  const n = validatorErrors.value.length
  if (n === 0) ElMessage.success('校验通过')
  else ElMessage.warning(`发现 ${n} 个问题`)
}

const WORKER_LAYOUT_THRESHOLD = 200
let layoutWorker: Worker | null = null
let layoutRequestId = 0

function terminateLayoutWorker() {
  layoutWorker?.terminate()
  layoutWorker = null
}

function layoutInWorker(doc: GraphDocument): Promise<GraphDocument> {
  const requestId = ++layoutRequestId
  if (!layoutWorker) layoutWorker = new Worker(new URL('./layoutWorker.ts', import.meta.url), { type: 'module' })
  return new Promise((resolve, reject) => {
    const worker = layoutWorker!
    const onMessage = (event: MessageEvent<{ id: number; doc?: GraphDocument; error?: string }>) => {
      if (event.data.id !== requestId) return
      cleanup()
      if (event.data.error || !event.data.doc) reject(new Error(event.data.error ?? '布局 Worker 未返回结果'))
      else resolve(event.data.doc)
    }
    const onError = () => { cleanup(); reject(new Error('布局 Worker 异常退出')) }
    const cleanup = () => {
      worker.removeEventListener('message', onMessage)
      worker.removeEventListener('error', onError)
    }
    worker.addEventListener('message', onMessage)
    worker.addEventListener('error', onError)
    worker.postMessage({ id: requestId, doc, dir: props.profile.layoutDir ?? 'TB' })
  })
}

onBeforeUnmount(terminateLayoutWorker)

async function onLayout() {
  if (!doc.value) return
  const before = cloneDoc(doc.value)
  const beforeJson = JSON.stringify(before)
  let laidOut: GraphDocument
  if (before.nodes.length > WORKER_LAYOUT_THRESHOLD && props.profile.layout !== 'lane' && props.profile.layout !== 'force' && props.profile.layout !== 'er') {
    ElMessage.info(`正在后台布局 ${before.nodes.length} 个节点…`)
    try {
      laidOut = await layoutInWorker(before)
    } catch (error) {
      console.warn('Worker layout failed; falling back to main thread.', error)
      laidOut = applyLayout(before, props.profile)
    }
  } else {
    laidOut = applyLayout(before, props.profile)
  }
  // Never replace edits made while a large graph was being calculated.
  if (!doc.value || JSON.stringify(doc.value) !== beforeJson) {
    ElMessage.warning('布局期间画布已更新，已保留最新编辑')
    return
  }
  graphStore.replace(laidOut)
  syncFromDoc()
  ElMessage.success('已自动布局')
}

/* ---------- F56b N14 撤销/重做 + N10 适配 ---------- */
function onUndo() { graphStore.undo() }
function onRedo() { graphStore.redo() }
function onFit() { fitView({ padding: 0.15, duration: 220 }) }

/* ---------- N15 任务载入（B 复制合并）：勾选任务 → 复制其节点/边原样合并进当前画布 ---------- */

/** Palette 载入请求：宿主托管时上抛（宿主切换视角/文档），否则本地合并（独立路由/只读视图用法） */
function onPaletteLoad(p: { items: DagPickItem[] }) {
  if (props.hostManaged) { emit('pick-tasks', p); return }
  void onLoadTasks(p.items.map((i) => i.id))
}

async function onLoadTasks(ids: string[]) {
  if (!ids.length || !doc.value || props.doc || effMode.value !== 'edit') return
  let added = 0
  for (const [idx, id] of ids.entries()) {
    let src: GraphDocument | null = null
    try { src = await graphService.get(id) } catch { /* 单个任务失败不中断其余载入 */ }
    if (!src || !src.nodes.length) continue
    /* B 语义：节点/边原样复制，全部重映射新 uid（节点 id + 边两端同步替换），并按序级联偏移错开 */
    const idMap = new Map<string, string>()
    src.nodes.forEach((n) => idMap.set(n.id, uid('nd')))
    const ox = 80 + idx * 60
    const oy = 120 + idx * 120
    src.nodes.forEach((n) => {
      const g: GNode = { ...n, id: idMap.get(n.id)!, position: { x: n.position.x + ox, y: n.position.y + oy } }
      doc.value!.nodes.push(g)
    })
    src.edges.forEach((e) => {
      if (!idMap.has(e.source) || !idMap.has(e.target)) return
      const g: GEdge = { ...e, id: uid('e'), source: idMap.get(e.source)!, target: idMap.get(e.target)! }
      doc.value!.edges.push(g)
    })
    added += src.nodes.length
  }
  if (!added) { ElMessage.warning('所选任务暂无可载入的节点'); return }
  /* 必须整档重同步渲染数组：Vue Flow 的 v-model:nodes 按引用同步，原地 push 不会写入其内部 store（新节点不渲染） */
  syncFromDoc()
  graphStore.markDirty()
  ElMessage.success(`已载入 ${ids.length} 个任务（复制合并 ${added} 个节点）`)
  nextTick(() => fitView({ padding: 0.15, duration: 250 }))
}

/** N11 MiniMap 节点着色（按类型色） */
function miniColor(n: any): string {
  return n?.data?.schema?.color ?? '#94a3b8'
}

/* ---------- F56b N7 类型过滤 + N9 大纲（导航面板数据） ---------- */

const typeStats = computed(() => {
  const m = new Map<string, number>()
  doc.value?.nodes.forEach((n) => m.set(n.type, (m.get(n.type) ?? 0) + 1))
  return [...m.entries()].map(([type, count]) => {
    const s = props.profile.nodeTypes[type] ?? FALLBACK_SCHEMA
    return { type, label: s.label, color: s.color, count }
  })
})

function toggleType(type: string) {
  const next = new Set(hiddenTypes.value)
  if (next.has(type)) next.delete(type)
  else next.add(type)
  hiddenTypes.value = next
  applyVisibility()
}

const outlineTree = computed(() =>
  typeStats.value.map((t) => ({
    ...t,
    nodes: (doc.value?.nodes ?? []).filter((n) => n.type === t.type),
  })),
)

/** 选中并居中定位（大纲/搜索共用） */
function selectAndCenter(id: string) {
  if (!flowNodes.value.some((f) => f.id === id)) return
  flowNodes.value.forEach((f) => { if (f.type !== 'gbadge') f.selected = f.id === id })
  selectedIds.value = new Set([id])
  selectedId.value = id
  emit('select', id)
  fitView({ nodes: [id], padding: 0.35, duration: 250, maxZoom: 1.4 })
}

function locateNode(id: string) {
  searchHit.value = null
  selectAndCenter(id)
}

/* ---------- F56b N6 成组 ---------- */

const groups = computed<DocGroup[]>(() => doc.value?.groups ?? [])

function groupSelected() {
  const ids = [...selectedIds.value]
  if (!doc.value || ids.length < 2) {
    ElMessage.warning('请先框选（Shift 拖框）或 Ctrl 点选至少 2 个节点')
    return
  }
  const g: DocGroup = { id: uid('grp'), name: `组 ${(doc.value.groups?.length ?? 0) + 1}`, nodeIds: ids }
  doc.value.groups = [...(doc.value.groups ?? []), g]
  graphStore.markDirty()
  ElMessage.success(`已将 ${ids.length} 个节点成组「${g.name}」（导航面板可折叠/解组）`)
}

function toggleGroupCollapse(gid: string) {
  const next = new Set(collapsedGroups.value)
  if (next.has(gid)) next.delete(gid)
  else next.add(gid)
  collapsedGroups.value = next
  applyVisibility()
}

async function renameGroup(g: DocGroup) {
  try {
    const { value } = await ElMessageBox.prompt('组名称', '重命名组', {
      inputValue: g.name, confirmButtonText: '确定', cancelButtonText: '取消',
    })
    const v = value.trim()
    if (v && v !== g.name) { g.name = v; graphStore.markDirty() }
  } catch { /* 取消 */ }
}

function ungroup(gid: string) {
  if (!doc.value) return
  const next = new Set(collapsedGroups.value)
  next.delete(gid)
  collapsedGroups.value = next
  doc.value.groups = (doc.value.groups ?? []).filter((g) => g.id !== gid)
  applyVisibility()
  graphStore.markDirty()
}

/** 选中组成员并居中（展开态）——拖动任一成员即整体移动（vue-flow 多选拖拽原生支持） */
function focusGroup(g: DocGroup) {
  if (collapsedGroups.value.has(g.id)) { toggleGroupCollapse(g.id); return }
  if (!g.nodeIds.length) return
  flowNodes.value.forEach((f) => { if (f.type !== 'gbadge') f.selected = g.nodeIds.includes(f.id) })
  selectedIds.value = new Set(g.nodeIds)
  fitView({ nodes: g.nodeIds, padding: 0.3, duration: 250, maxZoom: 1.3 })
  ElMessage.info('已选中组全部成员，拖动任一成员即可整体移动')
}

/* ---------- F56b N8 搜索 ---------- */

function onSearchEnter() {
  const kw = searchKw.value.trim()
  if (kw && kw === lastKw.value && searchList.value.length) {
    searchIdx.value += 1
    gotoSearchHit()
    return
  }
  lastKw.value = kw
  runSearch()
}

function runSearch() {
  const kw = searchKw.value.trim().toLowerCase()
  const d = doc.value
  if (!kw || !d) { searchList.value = []; searchHit.value = null; return }
  /* 折叠/过滤掉的节点不参与匹配（画布上不可见） */
  const folded = new Set<string>()
  ;(d.groups ?? []).forEach((g) => {
    if (collapsedGroups.value.has(g.id)) g.nodeIds.forEach((id) => folded.add(id))
  })
  searchList.value = d.nodes
    .filter((n) => !hiddenTypes.value.has(n.type) && !folded.has(n.id))
    .filter((n) =>
      String(n.data.name ?? '').toLowerCase().includes(kw) ||
      n.id.toLowerCase().includes(kw) ||
      n.type.toLowerCase().includes(kw))
    .map((n) => n.id)
  searchIdx.value = 0
  gotoSearchHit()
}

function gotoSearchHit() {
  if (!searchList.value.length) {
    searchHit.value = null
    ElMessage.info('无匹配节点')
    return
  }
  searchIdx.value = ((searchIdx.value % searchList.value.length) + searchList.value.length) % searchList.value.length
  const id = searchList.value[searchIdx.value]!
  searchHit.value = id
  selectAndCenter(id)
}

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (!searchOpen.value) {
    searchKw.value = ''
    lastKw.value = ''
    searchList.value = []
    searchHit.value = null
  } else {
    nextTick(() => searchInput.value?.focus())
  }
}

/* ---------- F56b N1 拖入高亮（dragenter/leave 计数防子元素抖动） ---------- */

function onDragEnter() { dragDepth += 1; dropHot.value = true }
function onDragLeave() { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) dropHot.value = false }
function onDropWrap(e: DragEvent) { dragDepth = 0; dropHot.value = false; onDrop(e) }

/* ---------- F56b 键盘：Ctrl+F 搜索 / Ctrl+Z·Y 撤销重做 / Del 批删（编辑态） ---------- */

function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null
  if (!el) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable
}

function onKeydown(e: KeyboardEvent) {
  if (isTypingTarget(e.target)) return
  /* Task 14 审查修复：归属拦截——自管模式下 store 单例可能正指向其他 Tab 的文档（如 onActivated
     归位 load 的 await 窗口期），此时本实例的键盘动作（Del 批删/撤销重做/粘贴等）会误伤他人文档；
     仅 props.doc 注入宿主（血缘等只读视图，文档自持不经过 store）豁免。 */
  if (!props.doc && doc.value?.id !== props.docId) return
  const k = e.key.toLowerCase()
  if ((e.ctrlKey || e.metaKey) && k === 'f') {
    e.preventDefault()
    searchOpen.value = true
    nextTick(() => searchInput.value?.focus())
    return
  }
  /* Task 11（§3.5）：`?` 快捷键帮助（任意模式可用，紧挨 Ctrl+F 之后、edit 闸门之前） */
  if (e.key === '?') {
    e.preventDefault()
    openFloat('shortcut-help', '快捷键帮助', ShortcutHelp, 560, 440)
    return
  }
  if (effMode.value !== 'edit') return
  if ((e.ctrlKey || e.metaKey) && k === 'z' && !e.shiftKey) { e.preventDefault(); graphStore.undo(); return }
  if ((e.ctrlKey || e.metaKey) && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); graphStore.redo(); return }
  /* Task 11（§3.5）：Ctrl+A 全选 / Ctrl+C 复制 / Ctrl+V 粘贴 / Ctrl+D 原位复制 */
  if ((e.ctrlKey || e.metaKey) && k === 'a') { e.preventDefault(); selectAllNodes(); return }
  if ((e.ctrlKey || e.metaKey) && k === 'c') { e.preventDefault(); copySelection(); return }
  if ((e.ctrlKey || e.metaKey) && k === 'v') { e.preventDefault(); pasteClip(24); return }
  if ((e.ctrlKey || e.metaKey) && k === 'd') { e.preventDefault(); pasteClip(0); return }
  /* Task 11（§3.5）：方向键微移选中节点（Shift = 10px 网格步长），无选中不拦截 */
  if (e.key.startsWith('Arrow') && selectedIds.value.size) {
    e.preventDefault()
    nudgeSelection(e.key, e.shiftKey ? ARROW_GRID_STEP : 1)
    return
  }
  /* Task 11（§3.5）：F2 重命名恰好一个选中节点 */
  if (e.key === 'F2' && selectedIds.value.size === 1) { e.preventDefault(); renameSelected(); return }
  if (e.key === 'Delete' || e.key === 'Backspace') {
    const nodes = [...selectedIds.value]
    const edges = [...selectedEdgeIds.value]
    if (!nodes.length && !edges.length) return
    e.preventDefault()
    if (nodes.length) void removeNodes(nodes)
    if (edges.length) void removeEdges(edges)
  }
}

/* ---------- Task 11（§3.5）批量操作：全选/复制/粘贴/原位复制/微移/重命名/对齐/分布 ---------- */

/** 方向键 Shift 档网格步长（px） */
const ARROW_GRID_STEP = 10

/** 对齐/分布节点尺寸兜底（px）：画布未挂载/实测尺寸未知时使用 */
const NODE_SIZE_FALLBACK = 160

/** 多选剪贴板快照（Ctrl+C 落，Ctrl+V/D 消费）：节点深拷贝、内部边仅存粘贴所需字段（partial 深拷贝防引用共享） */
type ClipSnapshot = {
  nodes: ClipboardNode<GNodeData>[]
  edges: { source: string; target: string; kind?: GEdgeKind; label?: string; sourceHandle?: string; targetHandle?: string; partial?: EdgePartialDep }[]
}
let copiedSnapshot: ClipSnapshot | null = null

/** Ctrl+A：全选节点（排除不可见节点：类型过滤命中 + 折叠组成员，与 applyVisibility 的 hidden 判定同源） */
function selectAllNodes() {
  const d = doc.value
  if (!d) return
  const folded = new Set<string>()
  ;(d.groups ?? []).forEach((g) => {
    if (collapsedGroups.value.has(g.id)) g.nodeIds.forEach((id) => folded.add(id))
  })
  selectedIds.value = new Set(
    d.nodes.filter((n) => !hiddenTypes.value.has(n.type) && !folded.has(n.id)).map((n) => n.id),
  )
}

/** Ctrl+C：快照选中节点（深拷贝）与两端均在选集内的内部边（浅拷贝）；跨组件连线不复制 */
function copySelection() {
  const d = doc.value
  const sel = selectedIds.value
  if (!d || !sel.size) return
  copiedSnapshot = {
    nodes: d.nodes.filter((n) => sel.has(n.id)).map((n) => ({
      id: n.id, type: n.type, position: { ...n.position }, data: structuredClone(n.data),
    })),
    edges: d.edges.filter((e) => sel.has(e.source) && sel.has(e.target)).map((e) => ({
      source: e.source, target: e.target, kind: e.kind, label: e.label,
      sourceHandle: e.sourceHandle, targetHandle: e.targetHandle,
      partial: e.partial ? structuredClone(e.partial) : undefined,
    })),
  }
}

/** Ctrl+V（offset=24）/ Ctrl+D（offset=0 原位）粘贴：节点/边落 doc + 渲染数组，选区切到新节点 */
function pasteClip(offset: number) {
  const d = doc.value
  if (!d || !copiedSnapshot) return
  const r = pasteSelection(copiedSnapshot, () => uid('nd'), offset)
  r.nodes.forEach((n) => {
    const g: GNode = { id: n.id, type: n.type, position: { ...n.position }, data: n.data }
    d.nodes.push(g)
    flowNodes.value.push(toFlowNode(g))
  })
  r.edges.forEach((e) => {
    const g: GEdge = {
      id: e.id, source: e.source, target: e.target, kind: e.kind, label: e.label,
      sourceHandle: e.sourceHandle, targetHandle: e.targetHandle,
      partial: e.partial ? structuredClone(e.partial) : undefined, // 再次深拷贝：防与剪贴板快照共享引用
    }
    d.edges.push(g)
    flowEdges.value.push(toFlowEdge(g))
  })
  graphStore.markDirty()
  selectedIds.value = new Set(r.nodes.map((n) => n.id))
  /* 清空边选区：防紧接 Delete 误删粘贴前选中的旧边 */
  selectedEdgeIds.value = new Set()
  applyVisibility()
  ElMessage.success(`已粘贴 ${r.nodes.length} 个节点`)
}

/* 微移撤销合并窗口（ms）：连发方向键若每键 markDirty，600ms 内即挤爆 50 步 undo 栈；
 * 窗口内不重复入栈，整段 burst 只产生一个撤销检查点——仿拖拽合并窗口思路 */
let lastNudgeMark = 0
/** 正确性：窗口内被跳过的键不更新 store.lastSnap，下一次任何 markDirty 自然把 burst 前状态压栈；
 *  burst 首键必触发（lastNudgeMark 已过期），故 redoStack 不残留脏项 */
function nudgeMarkDirty() {
  const now = Date.now()
  if (now - lastNudgeMark > 600) { graphStore.markDirty(); lastNudgeMark = now }
}

/** 方向键微移：doc 节点与 flow 渲染节点 position 同步 ±step，nudgeMarkDirty 合并入栈（不整树 syncFromDoc） */
function nudgeSelection(key: string, step: number) {
  const d = doc.value
  if (!d) return
  const dx = key === 'ArrowLeft' ? -step : key === 'ArrowRight' ? step : 0
  const dy = key === 'ArrowUp' ? -step : key === 'ArrowDown' ? step : 0
  d.nodes.forEach((n) => {
    if (!selectedIds.value.has(n.id)) return
    n.position = { x: n.position.x + dx, y: n.position.y + dy }
    const fn = findNode(n.id)
    if (fn) fn.position = { ...n.position }
  })
  nudgeMarkDirty()
}

/** F2：重命名唯一选中节点（非空校验；改 data.name 后 syncFromDoc 传播渲染 + markDirty） */
function renameSelected() {
  const id = [...selectedIds.value][0]
  const n = doc.value?.nodes.find((x) => x.id === id)
  if (!n) return
  void ElMessageBox.prompt('节点名称', '重命名', {
    inputValue: String(n.data.name ?? ''), inputPattern: /\S/, inputErrorMessage: '名称不能为空',
    confirmButtonText: '确定', cancelButtonText: '取消',
  }).then(({ value }) => {
    const v = String(value ?? '').trim()
    if (v && v !== n.data.name) { n.data.name = v; syncFromDoc(); graphStore.markDirty() }
  }).catch(() => { /* 取消 */ })
}

/** 对齐/分布尺寸回调：画布实测尺寸优先，未挂载/未知兜底 NODE_SIZE_FALLBACK */
function canvasWidthOf(n: GNode): number { return findNode(n.id)?.dimensions?.width ?? NODE_SIZE_FALLBACK }
function canvasHeightOf(n: GNode): number { return findNode(n.id)?.dimensions?.height ?? NODE_SIZE_FALLBACK }

/** 新位置写回：doc 节点与 flow 渲染节点同步（避免整树 syncFromDoc 重建） */
function writeBackPosition(id: string, position: { x: number; y: number }) {
  const g = doc.value?.nodes.find((x) => x.id === id)
  if (g) g.position = { ...position }
  const fn = findNode(id)
  if (fn) fn.position = { ...position }
}

/** 工具条对齐（选中 ≥2）：纯函数以选集包围盒为基准计算新位置后写回 */
function applyAlign(dir: AlignDir) {
  const d = doc.value
  if (!d || selectedIds.value.size < 2) return
  const sel = d.nodes.filter((n) => selectedIds.value.has(n.id))
  alignNodes(sel, dir, canvasWidthOf, canvasHeightOf).forEach((n) => writeBackPosition(n.id, n.position))
  graphStore.markDirty()
}

/** 工具条分布（选中 ≥3）：排序后相邻等间隙，写回同上 */
function applyDistribute(axis: DistributeAxis) {
  const d = doc.value
  if (!d || selectedIds.value.size < 3) return
  const sel = d.nodes.filter((n) => selectedIds.value.has(n.id))
  distributeNodes(sel, axis, canvasWidthOf, canvasHeightOf).forEach((n) => writeBackPosition(n.id, n.position))
  graphStore.markDirty()
}

/** 运行：mock 走本地 execService 演示链路；real 弹运行对话框（手工/补数页签，I3 §13） */
const runDlgVisible = ref(false)
async function onRun() {
  if (!doc.value) return
  if (run.running) { await run.stop(); return }
  if (effMode.value !== 'edit') return
  if (isMock) { await run.start(doc.value); return }
  runDlgVisible.value = true
}
function onRunSubmitted() {
  // 提交成功后日志面板留痕（实例在「运行实例（引擎）」页跟踪）
  run.log('运行命令已提交（real：实例在 /dag/instances 跟踪）', 'ok')
}

/** 工作台工具条「刷新」（P2 欠账补齐）：重拉当前画布文档，同步他人改动/后端数据变更。
 *  仅自管加载模式（宿主未传 doc prop）显示；有未保存改动先确认丢弃。 */
const isManaged = computed(() => !!props.doc)
async function onRefreshDoc() {
  if (graphStore.dirty) {
    try {
      await ElMessageBox.confirm('画布有未保存改动，刷新将丢弃这些改动。确定刷新？', '刷新画布', {
        type: 'warning', confirmButtonText: '丢弃并刷新', cancelButtonText: '取消',
      })
    } catch { return }
  }
  try {
    await graphStore.load(props.docId)
    ElMessage.success('画布已刷新')
  } catch (e) {
    ElMessage.error(e instanceof Error ? `刷新失败：${e.message}` : '刷新失败')
  }
}

/** 质检类视角：运行检查（提交即返回，边结果异步翻转后重渲染） */
const checking = ref(false)
async function onRunCheck() {
  if (!doc.value || !props.profile.onRunCheck || checking.value) return
  checking.value = true
  run.log('提交质量检查（显示/运行分离：异步推送边结果翻转）')
  try {
    const summary = await props.profile.onRunCheck(doc.value)
    syncFromDoc()
    graphStore.markDirty()
    if (summary) { run.log(summary, 'ok'); ElMessage.success(summary) }
  } finally {
    checking.value = false
  }
}

function onEdgeClick(e: { edge?: { id: string } }) {
  if (!doc.value || !e.edge) return
  const g = doc.value.edges.find((x) => x.id === e.edge!.id)
  if (!g) return
  props.profile.onEdgeClick?.(g, doc.value)
  const upstream = doc.value.nodes.find((node) => node.id === g.source)
  if (!upstream) return
  const spec = specEnabled.value ? componentStore.specMap.get(upstream.type) : undefined
  const dataType = resolveEdgeDataType(g.sourceHandle, spec)
  const outputs = spec?.outputs ?? spec?.ports.outputs.map((port) => ({ name: port.name, type: port.type })) ?? []
  openFloat(`edge-data:${g.id}`, `边数据 · ${upstream.data.name || upstream.id}`, EdgeDataFloat, 680, 430, {
    doc: doc.value, edge: g, upstream, outputs, dataType,
    previewLimit: spec?.extensions?.capabilities?.previewLimit ?? 100,
    workflowCode: props.docMeta?.code,
  })
}

/** 节点渲染组件：profile 可注入自定义（如 ER 实体卡片），缺省 DataNode */
const nodeComp = computed(() => props.profile.nodeComp ?? DataNode)

/** profile 预置浮窗（按当前模式过滤） */
const extraFloats = computed(() =>
  (props.profile.floats ?? []).filter((f) => !f.mode || f.mode === effMode.value))

function openFloat(id: string, title: string, comp: unknown, w: number, h: number, extra?: Record<string, unknown>) {
  floatStore.open({
    /* Task 14：id 加 docId 前缀 + owner 标记所属画布——keep-alive 后各 Tab 浮窗互不串扰/复用 */
    id: `${props.docId}:${id}`,
    owner: props.docId,
    title, w, h,
    x: 320 + (floatStore.floats.length % 3) * 30,
    y: 90 + (floatStore.floats.length % 3) * 30,
    minimized: false,
    comp: comp as never,
    props: extra,
  })
}

/** 工具栏「更多 ⋯」：低频入口收敛（profile 预置浮窗 + 日志 + 版本），主操作保持前置 */
type MoreItem = { id: string; label: string; run: () => void }
const moreItems = computed<MoreItem[]>(() => {
  const logItem: MoreItem = { id: 'logs', label: '运行日志', run: () => openFloat('logs', '运行日志', LogPanel, 460, 320) }
  const floats: MoreItem[] = extraFloats.value.map((f) => ({
    id: f.id, label: f.label,
    run: () => openFloat(f.id, f.label, f.comp, f.w, f.h, f.propsOf?.({ selectedId: selectedId.value ?? null })),
  }))
  return effMode.value === 'edit'
    ? [...floats, logItem, { id: 'versions', label: '版本管理', run: () => openFloat('versions', '版本管理', VersionPanel, 440, 300, { docId: props.docId }) }]
    : [...floats, logItem]
})
function runMore(it: MoreItem) { it.run() }

/* ---------- view 模式周期刷新（topo 健康翻转） ---------- */

let timer: number | null = null
watch(autoRefresh, (on) => {
  if (on && props.profile.onTick) {
    timer = window.setInterval(() => {
      if (doc.value) {
        props.profile.onTick?.(doc.value)
        syncFromDoc() // 强制重建渲染数组，确保健康状态传播到画布
      }
    }, 3000)
  } else if (timer) {
    window.clearInterval(timer)
    timer = null
  }
})
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })

/* ---------- 画布交互 ---------- */

/** Task 8（§3.1）：端口类型解析（两源并存宽进口径）——spec 命中 → SpecPort.type（首次接入消费链路）；
 *  profile 形态 NodePort 仅 {id,label} 无类型声明、handle 匹配不到或缺省 → undefined = any（不误拦） */
function connPortType(d: GraphDocument, nodeId: string | undefined, handle: string | null | undefined, side: 'source' | 'target'): string | undefined {
  const g = d.nodes.find((n) => n.id === nodeId)
  if (!g) return undefined
  const spec = specEnabled.value ? componentStore.specMap.get(g.type) : undefined
  if (spec) {
    const list = side === 'source' ? spec.ports.outputs : spec.ports.inputs
    return (handle ? list.find((p) => p.name === handle) : undefined)?.type || undefined
  }
  return undefined
}

/** Task 8（§3.1）：连线两端端口类型 → 四道闸类型道入参（缺省键 = any） */
function connPortTypes(d: GraphDocument, conn: ConnSpec): PortTypesHint {
  return {
    src: connPortType(d, conn.source, conn.sourceHandle, 'source'),
    dst: connPortType(d, conn.target, conn.targetHandle, 'target'),
  }
}

/** Task 8（§8.2）：拒绝连线时源/目标端口红色闪烁 1s（Handle DOM：.vue-flow__handle[data-nodeid][data-handleid]；DOM 缺失静默跳过，toast 兜底） */
function flashPortsReject(conn: ConnSpec) {
  const flash = (nodeId: string | undefined, handleId: string | null | undefined) => {
    if (!nodeId) return
    const id = CSS.escape(nodeId)
    const sel = handleId
      ? `.vue-flow__handle[data-nodeid="${id}"][data-handleid="${CSS.escape(handleId)}"]`
      : `.vue-flow__handle[data-nodeid="${id}"]`
    document.querySelectorAll(sel).forEach((el) => {
      el.classList.add('port-flash-red')
      window.setTimeout(() => el.classList.remove('port-flash-red'), 1000)
    })
  }
  flash(conn.source, conn.sourceHandle)
  flash(conn.target, conn.targetHandle)
}

function onConnect(conn: Connection) {
  if (effMode.value !== 'edit') return
  if (!doc.value || !conn.source || !conn.target) return
  /* 四道闸收敛（方案§3.1，Task 8）：自连→重复边→成环（仅 DAG 布局，行为不变）→类型交集（新增） */
  const reason = connectionRejectReason(doc.value, conn, connPortTypes(doc.value, conn), { checkCycle: props.profile.layout === 'dagre' })
  if (reason) {
    ElMessage.warning(reason)
    flashPortsReject(conn)
    /* Task 10（§3.3）：拒绝原因入错误模型（瞬时 gate 错误）；同原因去重，doc 变化/下次校验清空 */
    if (!transientErrors.value.some((e) => e.code === 'CONNECT_REJECTED' && e.message === reason)) {
      transientErrors.value = [...transientErrors.value, { kind: 'gate', level: 'error', code: 'CONNECT_REJECTED', message: reason }]
    }
    return
  }
  /* 分支/具名输出口连线：边标注端口名并使用 branch 语义（不同分支可指向同一目标；
     端点合一：endpoint_select 静态 outputs（sourceRef/targetRef）与动态 ports 归一按端口解析） */
  transientErrors.value = [] // Task 10（§3.3）：连线成功即清瞬时拒绝（原地 push 不触发 watch，须显式清理）
  const srcNode = doc.value.nodes.find((n) => n.id === conn.source)
  const srcSchema = srcNode ? props.profile.nodeTypes[srcNode.type] : undefined
  const port = (srcNode && conn.sourceHandle)
    ? (srcSchema?.ports?.(srcNode.data) ?? srcSchema?.outputs)?.find((p) => p.id === conn.sourceHandle)
    : undefined
  const edge: GEdge = {
    id: uid('e'),
    source: conn.source,
    target: conn.target,
    kind: port ? 'branch' : props.profile.defaultEdge,
    label: port?.label,
    sourceHandle: conn.sourceHandle ?? undefined,
    targetHandle: conn.targetHandle ?? undefined,
  }
  doc.value.edges.push(edge)
  onEdgeCreated(doc.value, edge) // 拖边即引用（§3.3）：同步向目标节点 inputs 追加 `${source}:${sourceHandle ?? ''}` 引用
  flowEdges.value.push(toFlowEdge(edge))
  applyVisibility()
  graphStore.markDirty()
  if (port) ElMessage.success(`已连接分支「${port.label}」`)
}

/* Task 8（§3.1）：拖线实时预判（:is-valid-connection）。
   已存在边按 id 豁免——vue-flow 的 setEdges/addEdges 对存量边也会回调本函数（createGraphEdges
   校验失败即丢边），按 id 放行保证历史文档遗留边（成环/重复/类型不匹配）不被静默清除；
   拖线新连线则走四道闸类型道（不跑 topoSort，成环道留待 onConnect 拦，与旧行为一致）。
   拒绝时 vue-flow 不吸附目标端点且不触发 onConnect，toast + 端口红闪各 1s 内同连线组合去重。 */
let lastRejectKey = ''
let lastRejectAt = 0
function isValidConnection(conn: Connection): boolean {
  if (!doc.value || !conn.source || !conn.target) return true
  if ('id' in conn && typeof conn.id === 'string' && doc.value.edges.some((e) => e.id === conn.id)) return true
  const reason = connectionRejectReason(doc.value, conn, connPortTypes(doc.value, conn), { checkCycle: false })
  if (!reason) return true
  const key = `${conn.source}|${conn.sourceHandle ?? ''}|${conn.target}|${conn.targetHandle ?? ''}`
  const now = Date.now()
  if (key !== lastRejectKey || now - lastRejectAt > 1000) {
    lastRejectKey = key
    lastRejectAt = now
    ElMessage.warning(reason)
    flashPortsReject(conn)
  }
  return false
}

function onNodesChange(changes: NodeChange[]) {
  // view 模式只读：忽略拖拽/删除等变更（回滚/保存等外部替换由 store.doc watch 重同步）
  if (!doc.value || effMode.value !== 'edit') return
  changes.forEach((c) => {
    if (c.type === 'position' && c.position && !c.dragging) {
      if (c.id.startsWith('grp:')) { badgePos[c.id.slice(4)] = { ...c.position }; return } // 组徽标拖位（会话级）
      const g = doc.value!.nodes.find((n) => n.id === c.id)
      if (g) { g.position = { ...c.position }; graphStore.markDirty() }
    } else if (c.type === 'remove') {
      if (!c.id.startsWith('grp:')) void removeNodes([c.id])
    } else if (c.type === 'select') {
      // N5 多选集维护（单选/框选/Ctrl 点选统一经此）
      const next = new Set(selectedIds.value)
      if (c.selected) next.add(c.id)
      else next.delete(c.id)
      selectedIds.value = next
    }
  })
}

function onEdgesChange(changes: EdgeChange[]) {
  if (!doc.value || effMode.value !== 'edit') return
  changes.forEach((c) => {
    if (c.type === 'remove') {
      void removeEdges([c.id])
    } else if (c.type === 'select') {
      const next = new Set(selectedEdgeIds.value)
      if (c.selected) next.add(c.id)
      else next.delete(c.id)
      selectedEdgeIds.value = next
    }
  })
}

/** N4：删除节点（断边确认 + 组清理 + toast；未保存前可 Ctrl+Z 撤销） */
async function removeNodes(ids: string[], opts?: { silent?: boolean }) {
  const d = doc.value
  if (!d || !ids.length) return
  const set = new Set(ids)
  const targets = d.nodes.filter((n) => set.has(n.id))
  if (!targets.length) return
  const cutEdges = d.edges.filter((e) => set.has(e.source) || set.has(e.target))
  const linked = cutEdges.length
  if (!opts?.silent && linked > 0) {
    const label = targets.length === 1 ? `「${String(targets[0]!.data.name ?? targets[0]!.id)}」` : `${targets.length} 个节点`
    try {
      await ElMessageBox.confirm(
        `删除${label}将同时断开 ${linked} 条连线。删除后（未保存前）可 Ctrl+Z 撤销。`,
        '删除节点',
        { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
      )
    } catch { return }
  }
  cutEdges.forEach((e) => onEdgeRemoved(d, e)) // 拖边即引用（§3.3）：被断开的边同步从目标节点 inputs 移除引用（目标节点已删时为空操作）
  d.nodes = d.nodes.filter((n) => !set.has(n.id))
  d.edges = d.edges.filter((e) => !set.has(e.source) && !set.has(e.target))
  if (d.groups?.length) {
    d.groups = d.groups
      .map((g) => ({ ...g, nodeIds: g.nodeIds.filter((id) => !set.has(id)) }))
      .filter((g) => g.nodeIds.length > 0)
  }
  flowNodes.value = flowNodes.value.filter((n) => !set.has(n.id) && n.type !== 'gbadge')
  flowEdges.value = flowEdges.value.filter((e) => !set.has(e.source) && !set.has(e.target))
  selectedIds.value = new Set([...selectedIds.value].filter((id) => !set.has(id)))
  if (selectedId.value && set.has(selectedId.value)) { selectedId.value = null; emit('select', null) }
  graphStore.markDirty()
  ElMessage.success(`已删除 ${targets.length} 个节点${linked ? `（断开 ${linked} 条连线）` : ''}`)
  applyVisibility()
}

/** Inspector 删除按钮入口 */
function deleteOne(id: string) { void removeNodes([id]) }

/** N3：删除连线（toast 反馈；hover 高亮与右键见模板/CSS） */
function removeEdges(ids: string[]) {
  const d = doc.value
  if (!d || !ids.length) return
  const set = new Set(ids)
  d.edges.filter((e) => set.has(e.id)).forEach((e) => onEdgeRemoved(d, e)) // 拖边即引用（§3.3）：同步从目标节点 inputs 移除引用
  d.edges = d.edges.filter((e) => !set.has(e.id))
  flowEdges.value = flowEdges.value.filter((e) => !set.has(e.id))
  selectedEdgeIds.value = new Set([...selectedEdgeIds.value].filter((x) => !set.has(x)))
  graphStore.markDirty()
  ElMessage.success(set.size === 1 ? '已删除连线' : `已删除 ${set.size} 条连线`)
}

function onNodeClick(ev: NodeMouseEvent) {
  /* N6 折叠组徽标：点击 = 展开成员 */
  if (ev.node.id.startsWith('grp:')) { toggleGroupCollapse(ev.node.id.slice(4)); return }
  selectedId.value = ev.node.id
  emit('select', ev.node.id)
}

/** W1 查询增强：双击节点直接打开页面化浮窗（运行详情/实时数据/看板），免先选中再点「页面」；
 * Task 7：无页面且 profile.nodeCenter（血缘分析）→ 上抛 center-node 宿主以此节点为中心重拉 */
function onNodeDblClick(ev: NodeMouseEvent) {
  if (ev.node.id.startsWith('grp:')) return
  const n = doc.value?.nodes.find((x) => x.id === ev.node.id)
  const p = n ? props.profile.nodeTypes[n.type]?.page : undefined
  if (!n || !p) {
    if (n && props.profile.nodeCenter) emit('center-node', n.id)
    return
  }
  if (p.mode && p.mode !== effMode.value) return
  openFloat(`page_${n.id}`, p.title, p.comp, p.w ?? 540, p.h ?? 400, { node: n, doc: graphStore.doc })
}

function onPaneClick() {
  selectedId.value = null
  selectedIds.value = new Set()
  selectedEdgeIds.value = new Set()
  emit('select', null)
}

/* ---------- 拖拽添加 ---------- */

function onDrop(e: DragEvent) {
  if (!doc.value || effMode.value !== 'edit') return
  const type = e.dataTransfer?.getData('datara/node-type')
  if (!type) return
  const schema = schemaFor(type) // Task 5：spec 命中 → spec 视图，否则 profile（可 undefined 拒拖）
  if (!schema) return
  const pos = screenToFlowCoordinate({ x: e.clientX, y: e.clientY })
  /* F63 模板组件：先弹模式选择，build 物化为普通节点链（聚合占位不保留，引擎零改动） */
  if (schema.template) {
    materializeTemplate(schema, pos)
    return
  }
  /* F1 configure-first（§12.1）：前置裁决（灰置/runtimeOnly/maxInstances 拦截）→ 一律必弹配置弹窗
     （含 form: [] 的 C1/C2/C6/C7——六区块即其配置面；无 direct-add 旁路） */
  const decision = decideDrop(schema, { sameTypeCount: doc.value.nodes.filter((n) => n.type === type).length, paletteDisabled: paletteDisabledOf(type) })
  if (decision.action === 'intercept') { ElMessage.warning(decision.reason); return }
  const g: GNode = {
    id: uid('nd'),
    type,
    position: pos,
    /* M5：initTemplate.props 浅合入（defaults < 模板）；applyInitTemplate 返回等价副本，
       name 恒保留 → 收窄回 GNodeData 安全（extra 键由 GNodeData 索引签名承载） */
    data: applyInitTemplate({ name: schema.label, ...(schema.defaults ?? {}) }, schema) as GNodeData,
  }
  /* §11 划界语义：逻辑上游 = 当前选中节点优先，否则 drop 点最近节点。
     同一取法两处消费：prefill 一次性快照预填 + dropUpstream 传弹窗（虚拟节点无 doc.edges 入边，
     弹窗期 ①输入候选 / dataScope 上游两域 / 悬空引用判定均需它才能与落画布后同源）
     落图默认值优先级（低 → 高）：defaults < initTemplate.props（applyInitTemplate 已合入）
     < 上游快照 prefillFromUpstream —— 上游非空同名值最后落笔，覆盖模板与通用默认 */
  const up = pickPrefillUpstream(pos)
  prefillFromUpstream(g.data, up?.data ?? null, schema.dropPolicy?.prefillFromUpstream)
  prefillDeclaredFromUpstream(g.data, up?.data ?? null, schema.behaviors?.prefillFromUpstream)
  dropSchema.value = schema
  dropNode.value = g
  dropUpstream.value = up ? [up] : []
  dropDlg.value = true
}

/** F1：确认弹窗 → 节点落画布（「已配置」态）；取消/ESC → dropNode 丢弃，画布无痕。
 *  模板展开期（tplStage 激活）：确认 = 下一步 / 末步原子提交，取消 = 整链放弃。 */
function confirmDrop() {
  if (tplStage.value) { advanceTplStep(); return }
  const g = dropNode.value
  dropDlg.value = false
  dropNode.value = null
  dropSchema.value = null
  dropUpstream.value = []
  if (!g) return
  addNodeToCanvas(g)
  ElMessage.success(`已添加「${props.profile.nodeTypes[g.type]?.label ?? g.type}」`)
}
function cancelDrop() {
  if (tplStage.value) { abortTemplate(); return }
  dropDlg.value = false
  dropNode.value = null
  dropSchema.value = null
  dropUpstream.value = []
}

/** F1：预填逻辑上游——当前选中节点优先（显式接续意图）；否则取 drop 点欧氏距离最近节点 */
function pickPrefillUpstream(pos: { x: number; y: number }): GNode | null {
  const d = doc.value
  if (!d) return null
  if (selectedId.value) {
    const sel = d.nodes.find((n) => n.id === selectedId.value)
    if (sel) return sel
  }
  let best: GNode | null = null
  let bd = Infinity
  for (const n of d.nodes) {
    const dx = n.position.x - pos.x
    const dy = n.position.y - pos.y
    const dist = dx * dx + dy * dy
    if (dist < bd) { bd = dist; best = n }
  }
  return best
}

/** F1：palette 灰置态查询（灰置行 draggable=false 正常拖不出，此处为 dataTransfer 伪造的防御层） */
function paletteDisabledOf(type: string): boolean {
  for (const c of props.profile.palette) {
    if (c.items) {
      const it = c.items.find((i) => i.type === type)
      if (it) return !!it.disabled
    } else if (c.types?.includes(type)) return false
  }
  return false
}

/** F1：节点落画布公共尾（弹窗确认后统一收口） */
function addNodeToCanvas(g: GNode) {
  if (!doc.value) return
  doc.value.nodes.push(g)
  flowNodes.value.push(toFlowNode(g))
  selectedId.value = g.id
  applyVisibility()
  graphStore.markDirty()
}

/* ---------- F1 拖入配置弹窗状态 ---------- */
const dropDlg = ref(false)
const dropNode = ref<GNode | null>(null)
const dropSchema = ref<NodeSchema | null>(null)
/** 本次拖入的逻辑上游快照（虚拟节点无 doc.edges 入边，弹窗期配置上下文唯一来源；确认/取消均清空） */
const dropUpstream = ref<GNode[]>([])

/* ---------- F63 模板物化（§10.1） ---------- */

const tplDlg = ref(false)
const tplSchema = ref<NodeSchema | null>(null)
const tplPos = ref<{ x: number; y: number }>({ x: 0, y: 0 })
const tplModeKey = ref('')

function materializeTemplate(schema: NodeSchema, pos: { x: number; y: number }) {
  const modes = schema.template?.modes ?? []
  if (!modes.length) return
  if (modes.length === 1) { applyTemplate(schema, modes[0]!.key, pos); return }
  tplSchema.value = schema
  tplPos.value = pos
  tplModeKey.value = modes[0]!.key
  tplDlg.value = true
}

function confirmTemplate() {
  const s = tplSchema.value
  tplDlg.value = false
  if (!s) return
  applyTemplate(s, tplModeKey.value, tplPos.value)
}

function applyTemplate(schema: NodeSchema, modeKey: string, pos: { x: number; y: number }) {
  const mode = schema.template?.modes.find((m) => m.key === modeKey)
  if (!mode || !doc.value) return
  let built: { nodes: GNode[]; edges: GEdge[] }
  try {
    built = mode.build({ doc: doc.value, pos })
  } catch (err) {
    ElMessage.error(`模板展开失败：${err instanceof Error ? err.message : String(err)}`)
    return
  }
  if (!built.nodes.length) return
  /* configure-first（§12.1）：模板不再直接物化——先暂存（不写画布），再逐节点过配置闸门，
     全部通过后原子提交；任一步取消则整链丢弃，画布无痕。
     纯装饰节点（form 空且六区块无值，如 C1 开始 / C2 结束）自动跳过，不索取无意义输入。 */
  const steps = selectTemplateSteps(built.nodes, (t) => props.profile.nodeTypes[t])
  if (!steps.length) { commitTemplate(mode.label, built.nodes, built.edges); return }
  tplStage.value = { ...createTemplateStage(mode.label, built.nodes, built.edges), steps }
  openTplStep()
}

/** 模板暂存区（未落画布） */
const tplStage = ref<TemplateStage | null>(null)

/** 弹窗步骤态（普通拖入为 null → 弹窗标题/按钮走缺省文案） */
const dropStep = computed(() => {
  const st = tplStage.value
  return st ? { index: st.step, total: st.steps.length, chainLabel: st.chainLabel } : null
})
const dropConfirmText = computed(() => {
  const st = tplStage.value
  if (!st) return undefined
  return st.step === st.steps.length - 1 ? '完成展开' : '下一步'
})

/** 打开当前步骤的配置弹窗（复用普通拖入的同一弹窗实例，虚拟节点不落画布） */
function openTplStep() {
  const st = tplStage.value
  if (!st) return
  const g = st.steps[st.step]
  const s = g ? props.profile.nodeTypes[g.type] ?? null : null
  if (!g || !s) { abortTemplate(); return }
  dropNode.value = g
  dropSchema.value = s
  dropUpstream.value = stagedUpstreamOf(st, g.id)
  dropDlg.value = true
}

/** 步骤确认 → 下一步；末步确认 → 原子提交整链（一次性写 doc，画布不会出现半成品） */
function advanceTplStep() {
  const st = tplStage.value
  if (!st) return
  if (st.step < st.steps.length - 1) {
    st.step += 1
    openTplStep()
    return
  }
  const done = tplStage.value
  tplStage.value = null
  clearDropState()
  if (done) commitTemplate(done.chainLabel, done.nodes, done.edges)
}

/** 放弃展开：整链丢弃（staged 本就未写 doc，故画布无痕） */
function abortTemplate() {
  const label = tplStage.value?.chainLabel
  tplStage.value = null
  clearDropState()
  if (label) ElMessage.info(`已放弃模板「${label}」展开，画布未变更`)
}

function clearDropState() {
  dropDlg.value = false
  dropNode.value = null
  dropSchema.value = null
  dropUpstream.value = []
}

/** 原子提交：整链一次写入 doc + 画布，随后统一标脏/选中/可见性 */
function commitTemplate(chainLabel: string, nodes: GNode[], edges: GEdge[]) {
  if (!doc.value) return
  nodes.forEach((n) => { doc.value!.nodes.push(n); flowNodes.value.push(toFlowNode(n)) })
  edges.forEach((e2) => { doc.value!.edges.push(e2); flowEdges.value.push(toFlowEdge(e2)) })
  selectedId.value = nodes[0]!.id
  applyVisibility()
  graphStore.markDirty()
  const total = nodes.length
  ElMessage.success(`模板「${chainLabel}」已展开为 ${total} 个普通节点（配置已通过，可再编辑/增删插节点）`)}

/* ---------- 右键菜单（节点 / 连线 / 画布） ---------- */

const ctx = ref<{ show: boolean; x: number; y: number; nodeId?: string; edgeId?: string }>({ show: false, x: 0, y: 0 })

function onNodeCtx(e: NodeMouseEvent) {
  e.event.preventDefault()
  const me = e.event as MouseEvent
  ctx.value = { show: true, x: me.clientX, y: me.clientY, nodeId: e.node.id }
}
/** N3 连线右键：删除连线 */
function onEdgeCtx(e: EdgeMouseEvent) {
  e.event.preventDefault()
  const me = e.event as MouseEvent
  ctx.value = { show: true, x: me.clientX, y: me.clientY, edgeId: e.edge.id }
}
function onPaneCtx(e: MouseEvent) {
  if (effMode.value !== 'edit') return
  e.preventDefault()
  ctx.value = { show: true, x: e.clientX, y: e.clientY }
}
function closeCtx() { ctx.value.show = false }

function ctxCopy() {
  if (!doc.value || !ctx.value.nodeId) return
  const src = doc.value.nodes.find((n) => n.id === ctx.value.nodeId)
  const copy: GNode = {
    id: uid('nd'), type: src!.type,
    position: { x: src!.position.x + 40, y: src!.position.y + 40 },
    data: { ...src!.data, name: `${src!.data.name} 副本` },
  }
  doc.value.nodes.push(copy)
  flowNodes.value.push(toFlowNode(copy))
  applyVisibility()
  graphStore.markDirty()
  closeCtx()
}
/** N16 重命名 */
function ctxRename() {
  const n = doc.value?.nodes.find((x) => x.id === ctx.value.nodeId)
  closeCtx()
  if (!n) return
  void ElMessageBox.prompt('节点名称', '重命名', {
    inputValue: String(n.data.name ?? ''), confirmButtonText: '确定', cancelButtonText: '取消',
  }).then(({ value }) => {
    const v = value.trim()
    if (v && v !== n.data.name) { n.data.name = v; graphStore.markDirty() }
  }).catch(() => { /* 取消 */ })
}
function ctxGroup() { groupSelected(); closeCtx() }
/** Task 7 血缘「以此为中心」（profile.nodeCenter 视角右键菜单项） */
function ctxCenter() {
  const id = ctx.value.nodeId
  closeCtx()
  if (id) emit('center-node', id)
}
function ctxDelete() {
  if (ctx.value.nodeId) void removeNodes([ctx.value.nodeId])
  closeCtx()
}
function ctxDeleteSelected() {
  const ids = [...selectedIds.value]
  closeCtx()
  void removeNodes(ids)
}
function ctxDeleteEdge() {
  if (ctx.value.edgeId) removeEdges([ctx.value.edgeId])
  closeCtx()
}
function ctxLayout() { onLayout(); closeCtx() }
</script>

<template>
  <div class="wb" @click="closeCtx">
    <!-- 顶部工具栏 -->
    <div class="wb-header">
      <div class="wb-title">
        <template v-if="docMeta?.code != null || docMeta?.category">
          <span v-if="docMeta?.code != null" class="mono wb-code">#{{ docMeta.code }}</span>
          <span v-if="docMeta?.category" class="wb-cat">{{ docMeta.category }}</span>
          <span class="wb-sep">/</span>
        </template>
        {{ doc?.name ?? '加载中…' }}
        <span class="badge">{{ profile.name }}</span>
        <span v-if="doc" class="mono" style="font-size:11px;color:var(--text-3)">v{{ doc.version }}</span>
        <span v-if="graphStore.dirty" class="pill warn" style="margin-left:4px">未保存</span>
      </div>
      <span class="spacer" style="flex:1" />
      <!-- Task 10（§3.3）：错误指示按钮（Badge 只计 error 级总数），点击开/关错误面板抽屉 -->
      <el-badge :value="errBadgeCount" :hidden="!errBadgeCount" type="danger" class="tb-badge">
        <button class="tb-ico" :class="{ on: errPanelOpen }" title="错误面板：聚合节点/边/闸门校验错误，一键定位" @click="errPanelOpen = !errPanelOpen">
          <el-icon><Warning /></el-icon>
        </button>
      </el-badge>
      <template v-if="effMode === 'edit'">
        <button class="tb-btn primary" :disabled="graphStore.saving" @click="onSave">保存</button>
        <button class="tb-btn run" :class="{ running: run.running }" @click="onRun">{{ run.running ? '停止' : '试运行' }}</button>
        <span class="tb-sep" />
        <button class="tb-btn" @click="onValidate">校验</button>
        <button class="tb-btn" @click="onLayout">自动布局</button>
        <!-- Task 11（§3.5）：多选对齐/分布工具组（edit 块内，选中 ≥2 显；分布需 ≥3） -->
        <div v-if="selectedIds.size >= 2" class="tb-multisel">
          <button class="tb-ico" title="左对齐（选集包围盒为基准）" @click="applyAlign('left')">左</button>
          <button class="tb-ico" title="右对齐" @click="applyAlign('right')">右</button>
          <button class="tb-ico" title="上对齐" @click="applyAlign('top')">上</button>
          <button class="tb-ico" title="下对齐" @click="applyAlign('bottom')">下</button>
          <button class="tb-ico" title="水平居中" @click="applyAlign('hcenter')">横中</button>
          <button class="tb-ico" title="垂直居中" @click="applyAlign('vcenter')">纵中</button>
          <button class="tb-ico" :disabled="selectedIds.size < 3" title="水平分布（相邻等间隙，需选 ≥3）" @click="applyDistribute('h')">横距</button>
          <button class="tb-ico" :disabled="selectedIds.size < 3" title="垂直分布（相邻等间隙，需选 ≥3）" @click="applyDistribute('v')">纵距</button>
        </div>
        <span class="tb-sep" />
        <button class="tb-btn tb-catalog" title="打开组件目录：查看内置/用户组件、新建设计、版本与发布治理" @click="gotoCatalog">
          <el-icon><Grid /></el-icon><span>组件目录</span>
        </button>
        <button class="tb-btn tb-catalog" title="打开基线化工作台：组件八段 DSL 底稿编辑/体检/认可发 v1" @click="gotoBaseline">
          <el-icon><Grid /></el-icon><span>基线化工作台</span>
        </button>
        <button v-if="!isManaged" class="tb-ico" title="刷新（重新加载当前画布）" @click="onRefreshDoc"><el-icon><Refresh /></el-icon></button>
        <button class="tb-ico" title="适配视图（全部节点居中）" @click="onFit"><el-icon><FullScreen /></el-icon></button>
        <button class="tb-ico" :class="{ on: searchOpen }" title="搜索节点（Ctrl+F）" @click="toggleSearch"><el-icon><Search /></el-icon></button>
        <button class="tb-ico" :disabled="!graphStore.canUndo" title="撤销（Ctrl+Z）" @click="onUndo"><el-icon><RefreshLeft /></el-icon></button>
        <button class="tb-ico" :disabled="!graphStore.canRedo" title="重做（Ctrl+Y）" @click="onRedo"><el-icon><RefreshRight /></el-icon></button>
        <button class="tb-ico" :class="{ on: navOpen }" title="图例过滤 / 大纲 / 节点组" @click="navOpen = !navOpen"><el-icon><Operation /></el-icon></button>
        <span class="tb-sep" />
        <button class="tb-btn" @click="openFloat('ai', 'AI 助手', AiPanel, 380, 420)">AI</button>
        <el-dropdown trigger="click" @command="runMore">
          <button class="tb-btn" title="更多工具（日志 / 版本等）">更多 ⋯</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="it in moreItems" :key="it.id" :command="it">{{ it.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <div v-if="searchOpen" class="wb-search" @click.stop>
          <input ref="searchInput" v-model="searchKw" placeholder="按名称/ID/类型搜节点" @keydown.enter.prevent="onSearchEnter" @keydown.esc.prevent="toggleSearch" />
          <span v-if="searchList.length" class="s-cnt mono">{{ searchIdx + 1 }}/{{ searchList.length }}</span>
          <button class="s-x" title="关闭搜索" @click="toggleSearch">×</button>
        </div>
      </template>
      <template v-else>
        <label v-if="profile.onTick" style="display:flex;align-items:center;gap:5px;font-size:12px;color:var(--text-2);cursor:pointer">
          <input v-model="autoRefresh" type="checkbox" /> {{ profile.tickLabel ?? '健康状态自动刷新(3s)' }}
        </label>
        <button class="tb-btn tb-catalog" title="打开组件目录：查看内置/用户组件、新建设计、版本与发布治理" @click="gotoCatalog">
          <el-icon><Grid /></el-icon><span>组件目录</span>
        </button>
        <button class="tb-btn tb-catalog" title="打开基线化工作台：组件八段 DSL 底稿编辑/体检/认可发 v1" @click="gotoBaseline">
          <el-icon><Grid /></el-icon><span>基线化工作台</span>
        </button>
        <button v-if="!isManaged" class="tb-ico" title="刷新（重新加载当前画布）" @click="onRefreshDoc"><el-icon><Refresh /></el-icon></button>
        <button class="tb-ico" title="适配视图（全部节点居中）" @click="onFit"><el-icon><FullScreen /></el-icon></button>
        <button class="tb-ico" :class="{ on: searchOpen }" title="搜索节点（Ctrl+F）" @click="toggleSearch"><el-icon><Search /></el-icon></button>
        <button class="tb-ico" :class="{ on: navOpen }" title="图例过滤 / 大纲" @click="navOpen = !navOpen"><el-icon><Operation /></el-icon></button>
        <div v-if="searchOpen" class="wb-search" @click.stop>
          <input ref="searchInput" v-model="searchKw" placeholder="按名称/ID/类型搜节点" @keydown.enter.prevent="onSearchEnter" @keydown.esc.prevent="toggleSearch" />
          <span v-if="searchList.length" class="s-cnt mono">{{ searchIdx + 1 }}/{{ searchList.length }}</span>
          <button class="s-x" title="关闭搜索" @click="toggleSearch">×</button>
        </div>
        <span class="tb-sep" />
        <button v-if="profile.onRunCheck" class="tb-btn" :class="{ running: checking }" @click="onRunCheck">
          {{ checking ? '检查中…' : '运行检查' }}
        </button>
        <button class="tb-btn" @click="onValidate">结构检查</button>
        <span class="tb-sep" />
        <el-dropdown trigger="click" @command="runMore">
          <button class="tb-btn" title="更多工具（日志等）">更多 ⋯</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="it in moreItems" :key="it.id" :command="it">{{ it.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </div>

    <div class="wb-body">
      <!-- 左侧元件库（可收放，状态持久化）：组件 + 任务候选池多 Tab 勾选载入 -->
      <template v-if="effMode === 'edit' && profile.palette.length">
        <Palette v-show="leftOpen" :style="{ width: leftWidth + 'px' }" :profile="profile" :active-tags="paletteActiveTags" :resolve-schema="schemaFor" @load-tasks="onPaletteLoad" />
        <div v-if="leftOpen" class="wb-split wb-split-l" title="拖拽调整宽度" @mousedown="startResize('left', $event)" />

      </template>

      <!-- 导航面板（图例过滤 / 大纲 / 节点组） -->
      <div v-if="navOpen" class="wb-nav" @click.stop>
        <div class="nav-sec">
          <div class="nav-cap">图例过滤（勾选 = 显示）</div>
          <label v-for="t in typeStats" :key="t.type" class="nav-row">
            <input type="checkbox" :checked="!hiddenTypes.has(t.type)" @change="toggleType(t.type)" />
            <span class="nav-dot" :style="{ background: t.color }" />
            <span class="nav-label">{{ t.label }}</span>
            <span class="nav-cnt">{{ t.count }}</span>
          </label>
        </div>
        <div class="nav-sec">
          <div class="nav-cap">大纲（按类型分组 · 点击定位）</div>
          <template v-for="t in outlineTree" :key="t.type">
            <div class="nav-row nav-bold">
              <span class="nav-dot" :style="{ background: t.color }" />{{ t.label }}（{{ t.nodes.length }}）
            </div>
            <div
              v-for="n in t.nodes" :key="n.id"
              class="nav-row nav-leaf" :title="String(n.data.name ?? n.id)"
              @click="locateNode(n.id)"
            >{{ String(n.data.name ?? n.id) }}</div>
          </template>
        </div>
        <div v-if="groups.length" class="nav-sec">
          <div class="nav-cap">节点组</div>
          <div v-for="g in groups" :key="g.id" class="nav-row nav-group">
            <button class="nav-mini" :title="collapsedGroups.has(g.id) ? '展开成员' : '折叠为徽标'" @click="toggleGroupCollapse(g.id)">
              {{ collapsedGroups.has(g.id) ? '展开' : '折叠' }}
            </button>
            <span class="nav-gname" title="点击选中成员并居中" @click="focusGroup(g)">{{ g.name }}（{{ g.nodeIds.length }}）</span>
            <button class="nav-mini" @click="renameGroup(g)">改名</button>
            <button class="nav-mini" title="解散组（不影响节点）" @click="ungroup(g.id)">解组</button>
          </div>
        </div>
      </div>

      <!-- 中央画布 -->
      <div
        class="wb-canvas"
        :class="{ 'drop-hot': dropHot, 'has-lanes': !!profile.lanes }"
        @dragenter.prevent="onDragEnter"
        @dragover.prevent
        @dragleave="onDragLeave"
        @drop="onDropWrap"
        @contextmenu="onPaneCtx"
      >
        <!-- 泳道图例（topo 等分层视角） -->
        <div v-if="profile.lanes" style="position:absolute;top:8px;left:12px;z-index:10;display:flex;gap:6px;pointer-events:none;flex-wrap:wrap">
          <span
            v-for="(l, i) in profile.lanes" :key="l.key"
            class="pill" style="background:rgba(255,255,255,.85);border:1px solid var(--border)"
          >{{ i + 1 }}. {{ l.name }}</span>
        </div>
        <!-- Task 12（§3.6）视口裁剪：仅渲染可视区元素（onlyRenderVisible 默认开，localStorage 可关排查） -->
        <VueFlow
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          :fit-view-on-init="true"
          :min-zoom="0.3"
          :max-zoom="2"
          :delete-key-code="null"
          :only-render-visible-elements="onlyRenderVisible"
          :nodes-draggable="effMode === 'edit'"
          :nodes-connectable="effMode === 'edit'"
          :is-valid-connection="isValidConnection"
          @connect="onConnect"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          @node-click="onNodeClick"
          @node-double-click="onNodeDblClick"
          @node-contextmenu="onNodeCtx"
          @edge-click="onEdgeClick"
          @edge-contextmenu="onEdgeCtx"
          @pane-click="onPaneClick"
          @move-end="onCanvasMoveEnd"
        >
          <Background :gap="18" />
          <Controls position="top-left" />
          <MiniMap pannable zoomable :node-color="miniColor" node-stroke-color="#ffffff" :node-border-radius="2" mask-color="rgba(203,213,225,.5)" />
          <template #node-gn="nodeProps">
            <div :class="{ 'gn-hit': nodeProps.id === searchHit }">
              <component
                :is="nodeProps.data.gnode.type === 'reroute' ? RerouteNode : nodeComp"
                :id="nodeProps.id"
                :gnode="nodeProps.data.gnode"
                :schema="nodeProps.data.schema"
                :selected="nodeProps.selected"
                :has-error="errorNodeIds.has(nodeProps.id)"
                :focus="focusNodeId === nodeProps.id"
              />
            </div>
          </template>
          <!-- 折叠组徽标（合成渲染节点，点击展开成员） -->
          <template #node-gbadge="nProps">
            <div class="gbadge" title="点击展开组成员">
              <span class="gbadge-ico">▣</span>
              <span class="gbadge-name">{{ nProps.data.name }}</span>
              <span class="gbadge-cnt">{{ nProps.data.count }}</span>
            </div>
          </template>
        </VueFlow>
      </div>

      <!-- 右侧边窗（可收放，状态持久化）：属性 / 日志 / 变量 三 Tab 同级（N15） -->
      <div v-if="rightOpen" class="wb-split wb-split-r" title="拖拽调整宽度" @mousedown="startResize('right', $event)" />
      <div v-show="rightOpen" class="wb-right" :style="{ width: rightWidth + 'px' }">
        <div class="wb-right-head">
          <button
            v-for="t in rightTabs" :key="t.k"
            class="wb-right-tab" :class="{ on: rightTab === t.k }"
            @click="rightTab = t.k"
          ><span class="wbt-ic">{{ t.icon }}</span>{{ t.label }}</button>
        </div>
        <Inspector v-show="rightTab === 'inspector'" :node="selectedNode" :profile="profile" :node-errors="selectedNodeErrors" :doc-id="docId" @delete="deleteOne" />
        <div v-if="!hideVars && rightTab === 'vars'" class="wb-right-body"><WfVarPanel :doc-id="docId" /></div>
      </div>
    </div>

    <!-- 右键菜单（节点 / 连线 / 画布） -->
    <div v-if="ctx.show" class="ctx-menu" :style="{ left: ctx.x + 'px', top: ctx.y + 'px' }" @click.stop>
      <template v-if="ctx.edgeId">
        <div class="ctx-item danger" @click="ctxDeleteEdge">删除连线</div>
      </template>
      <template v-else-if="ctx.nodeId">
        <div class="ctx-item" @click="selectedId = ctx.nodeId; closeCtx()">属性面板</div>
        <div v-if="profile.nodeCenter" class="ctx-item" @click="ctxCenter">以此为中心</div>
        <template v-if="effMode === 'edit'">
          <div v-if="selectedIds.size > 1 && selectedIds.has(ctx.nodeId)" class="ctx-item" @click="ctxGroup">成组（{{ selectedIds.size }} 个节点）</div>
          <div class="ctx-item" @click="ctxRename">重命名</div>
          <div class="ctx-item" @click="ctxCopy">复制节点</div>
          <div v-if="selectedIds.size > 1 && selectedIds.has(ctx.nodeId)" class="ctx-item danger" @click="ctxDeleteSelected">删除所选（{{ selectedIds.size }}）</div>
          <div v-else class="ctx-item danger" @click="ctxDelete">删除节点</div>
        </template>
      </template>
      <template v-else>
        <div v-if="effMode === 'edit' && selectedIds.size > 1" class="ctx-item" @click="ctxGroup">成组（{{ selectedIds.size }} 个节点）</div>
        <div class="ctx-item" @click="ctxLayout">自动布局</div>
      </template>
    </div>

    <!-- Task 10（§3.3）：错误聚合面板（底部抽屉 · 三页签 · 一键定位） -->
    <ErrorPanel :open="errPanelOpen" :errors="docErrors" @update:open="errPanelOpen = $event" @locate="locateError" />

    <!-- 浮窗层（Task 14：owner 按画布隔离——keep-alive 多画布共存时后台 Tab 浮窗不泄漏到前台） -->
    <FloatLayer :owner="docId" />

    <!-- I3 运行对话框（real 模式试运行：手工/补数页签 + env_group，§13） -->
    <RunDialog v-model="runDlgVisible" :wf="docId" :wf-name="doc?.name" @submitted="onRunSubmitted" />

    <!-- F63 模板模式选择（拖入 template 组件时弹出，确认后物化为普通节点链） -->
    <el-dialog v-model="tplDlg" :title="`展开模板：${tplSchema?.label ?? ''}`" width="420px" append-to-body>
      <div style="display:flex;flex-direction:column;gap:8px">
        <div
          v-for="m in tplSchema?.template?.modes ?? []" :key="m.key"
          class="tpl-mode" :class="{ on: tplModeKey === m.key }"
          @click="tplModeKey = m.key"
        >
          <div style="font-weight:600;font-size:13px">{{ m.label }}</div>
          <div v-if="m.desc" style="font-size:11.5px;color:var(--text-3)">{{ m.desc }}</div>
        </div>
      </div>
      <div style="font-size:10.5px;color:var(--text-3);margin-top:8px">选定模式后按设计时物化展开为普通节点链（不保留聚合占位节点），展开后可继续编辑。</div>
      <template #footer>
        <el-button @click="tplDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmTemplate">展开</el-button>
      </template>
    </el-dialog>

    <!-- F1 configure-first 拖入配置弹窗（§12.1 三段式；确认落画布，取消不落） -->
    <DropConfigDialog :visible="dropDlg" :node="dropNode" :schema="dropSchema" :profile="profile" :upstream="dropUpstream" :step="dropStep" :confirm-text="dropConfirmText" @confirm="confirmDrop" @cancel="cancelDrop" />
  </div>
</template>

<style scoped>
.tb-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:5px 12px;font-size:12.5px;cursor:pointer;color:var(--text);transition:all .15s}
.tb-sep{width:1px;height:18px;background:var(--border-strong);margin:0 4px;flex:none}
/* F56c R5：视图类操作图标化（tooltip 保留文字语义），进一步压缩工具栏视觉宽度 */
.tb-ico{width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;border:1px solid transparent;background:transparent;border-radius:var(--radius-sm);cursor:pointer;color:var(--text-2);font-size:16px;transition:all .15s;flex:none}
/* Task 10（§3.3）：错误指示 Badge 与内部图标按钮的弹性对齐 */
.tb-badge{display:inline-flex;align-items:center;flex:none}
.tb-ico:hover{background:var(--bg);color:var(--primary)}
/* Task 11（§3.5）：多选对齐/分布工具组（文字缩写按钮，与 .tb-ico 同风格；分布 <3 置灰） */
.tb-multisel{display:inline-flex;align-items:center;gap:2px;margin:0 4px;flex:none}
.tb-multisel .tb-ico{width:auto;min-width:28px;height:30px;padding:0 5px;font-size:11px}
.tb-multisel .tb-ico:disabled{opacity:.4;cursor:not-allowed;background:transparent;color:var(--text-3)}
.tb-ico.on{border-color:var(--primary);background:var(--primary-light);color:var(--primary)}
.tb-ico:disabled{opacity:.4;cursor:not-allowed}
/* F56c：头部工具栏降噪——次级操作幽灵化，仅主操作（保存/试运行）保持实体 */
.wb-header .tb-btn:not(.primary):not(.run){border-color:transparent;background:transparent;color:var(--text-2)}
.wb-header .tb-btn:not(.primary):not(.run):not(.on):hover{border-color:transparent;background:var(--bg);color:var(--primary)}
.wb-header .tb-btn.run{border-color:rgba(22,104,220,.25);color:var(--primary);background:#fff}
.wb-header .tb-btn.run:hover{border-color:var(--primary);background:var(--primary-light);color:var(--primary)}
.wb-header .tb-btn.run.running{border-color:var(--danger);color:var(--danger);background:var(--danger-bg)}
.wb-header .tb-btn.on:not(.primary):not(.run){border-color:var(--primary);background:var(--primary-light);color:var(--primary)}
/* 组件治理入口：常驻带文字按钮（不用纯图标，避免与布局/搜索等 tb-ico 混淆而"看不见"） */
.wb-header .tb-catalog{display:inline-flex;align-items:center;gap:5px;border-color:var(--primary)!important;background:var(--primary-light)!important;color:var(--primary)!important;font-weight:600}
.wb-header .tb-catalog:hover{background:var(--primary)!important;color:#fff!important;border-color:var(--primary)!important}
.tb-btn:hover{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
.tb-btn.running{border-color:var(--danger);color:var(--danger);background:var(--danger-bg)}
.tb-btn.primary{background:var(--primary);border-color:var(--primary);color:#fff;font-weight:600}
.tb-btn.primary:hover{background:var(--primary);color:#fff;opacity:.88}
.tb-btn.on{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
.tb-btn:disabled{opacity:.4;cursor:not-allowed}
.tb-btn:disabled:hover{border-color:var(--border-strong);color:var(--text);background:#fff}
/* 工具栏搜索框（Ctrl+F） */
.wb-search{display:flex;align-items:center;gap:5px;border:1px solid var(--primary);border-radius:var(--radius-sm);padding:2px 4px 2px 8px;background:#fff}
.wb-search input{border:none;outline:none;font-size:12px;width:150px;background:transparent;color:var(--text)}
.wb-search .s-cnt{font-size:10.5px;color:var(--text-3);white-space:nowrap}
.wb-search .s-x{border:none;background:none;cursor:pointer;color:var(--text-3);font-size:13px;line-height:1;padding:2px 4px}
.wb-search .s-x:hover{color:var(--danger)}
/* 导航面板（图例/大纲/组） */
.wb-nav{position:absolute;top:8px;right:10px;z-index:60;width:256px;max-height:calc(100% - 20px);overflow:auto;background:var(--card);border:1px solid var(--border-strong);border-radius:var(--radius-sm);box-shadow:var(--shadow-lg);padding:9px}
.nav-sec+.nav-sec{margin-top:9px;border-top:1px solid var(--border);padding-top:8px}
.nav-cap{font-size:10.5px;font-weight:700;color:var(--text-3);margin-bottom:5px}
.nav-row{display:flex;align-items:center;gap:6px;font-size:12px;padding:2.5px 5px;border-radius:5px;color:var(--text-2);cursor:default}
label.nav-row{cursor:pointer}
.nav-row:hover{background:var(--bg)}
.nav-dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.nav-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav-cnt{margin-left:auto;color:var(--text-3);font-size:10.5px}
.nav-bold{font-weight:600;color:var(--text-1)}
.nav-leaf{padding-left:21px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav-leaf:hover{color:var(--primary)}
.nav-group{gap:4px}
.nav-gname{cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.nav-gname:hover{color:var(--primary)}
.nav-mini{border:1px solid var(--border-strong);background:#fff;border-radius:4px;font-size:10px;padding:1.5px 5px;cursor:pointer;color:var(--text-2);flex-shrink:0}
.nav-mini:hover{border-color:var(--primary);color:var(--primary)}
/* I11 侧窗拖拽调宽：分隔把手（5px 热区，hover/拖拽高亮） */
.wb-split{width:5px;flex-shrink:0;cursor:col-resize;background:transparent;transition:background .12s;position:relative;z-index:30}
.wb-split:hover,.wb-split.drag{background:var(--primary);opacity:.55}
.wb-split-l{border-right:1px solid transparent}
.wb-split-r{border-left:1px solid transparent}
/* 拖入高亮（N1） */
.wb-canvas.drop-hot{outline:2px dashed var(--primary);outline-offset:-3px;background:var(--primary-light)}
.tpl-mode{border:1px solid var(--border);border-radius:var(--radius-sm);padding:9px 11px;cursor:pointer;transition:all .15s}
.tpl-mode:hover{border-color:var(--primary)}
.tpl-mode.on{border-color:var(--primary);background:var(--primary-light)}
/* N15 右侧边窗三 Tab（属性/日志/变量）：面板头 + 显式折叠按钮 */
.wb-right{width:288px;background:var(--card);border-left:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;min-width:0}
.wb-right .wb-inspector{width:100%;border-left:none;flex:1;min-height:0}
.wb-right-head{display:flex;align-items:center;gap:2px;padding:6px 8px 0;border-bottom:1px solid var(--border);flex-shrink:0}
.wb-right-tab{border:none;background:none;padding:6px 10px;font-size:12.5px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:5px;margin-bottom:-1px}
.wb-right-tab:hover{color:var(--primary)}
.wb-right-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.wb-right-tab .wbt-ic{font-size:11px}
.wb-right-body{flex:1;min-height:0;overflow:auto}
</style>

<style>
/* F56b：vue-flow 画布层增强（需全局作用于 .vue-flow__*，不可 scoped） */
/* N2 端口 hover 放大 */
.vue-flow__handle{transition:transform .12s ease}
.vue-flow__handle:hover{transform:scale(1.45)}
/* N3 连线 hover 加粗 / 选中红色高亮 */
.vue-flow__edge{cursor:pointer}
.vue-flow__edge:hover .vue-flow__edge-path{stroke-width:3}
.vue-flow__edge.selected .vue-flow__edge-path{stroke:#e11d48 !important;stroke-width:2.6 !important}
.vue-flow__edge.selected .vue-flow__edge-textbg{stroke:#e11d48}
/* N10 Controls / N11 MiniMap 观感；N15 控件移顶（横向排布，置于画布左上） */
.wb-canvas .vue-flow__controls{border-radius:8px;overflow:hidden;border:1px solid var(--border);box-shadow:0 2px 10px rgba(15,23,42,.12);display:flex;flex-direction:row;margin:8px 0 0 10px}
.wb-canvas .vue-flow__controls-button{border-bottom:none;border-right:1px solid var(--border);background:#fff}
.wb-canvas .vue-flow__controls-button:last-child{border-right:none}
/* N15 泳道图例占左上（topo 等分层视角）时 Controls 让位右上 */
.wb-canvas.has-lanes .vue-flow__controls{left:auto;right:12px;margin:8px 12px 0 0}
.vue-flow__minimap{border:1px solid var(--border);border-radius:8px;overflow:hidden;box-shadow:0 2px 10px rgba(15,23,42,.12);background:rgba(255,255,255,.92)}
/* N8 搜索命中脉冲 */
.gn-hit{animation:gnPulse 1.1s ease-in-out 2}
@keyframes gnPulse{
  0%,100%{filter:drop-shadow(0 0 0 rgba(225,29,72,0))}
  50%{filter:drop-shadow(0 0 7px rgba(225,29,72,.9))}
}
/* Task 8（§8.2）：拒绝连线端口红色闪烁（isValidConnection/onConnect 拒绝时挂类，1s 后 JS 移除） */
.vue-flow__handle.port-flash-red{animation:portFlashRed 1s ease-in-out}
@keyframes portFlashRed{
  0%,100%{box-shadow:0 0 0 0 rgba(225,29,72,0)}
  20%,60%{box-shadow:0 0 0 5px rgba(225,29,72,.75);background:#e11d48;border-color:#e11d48}
  40%,80%{box-shadow:0 0 0 2px rgba(225,29,72,.3);background:#fecdd3;border-color:#e11d48}
}
/* N6 折叠组徽标 */
.gbadge{display:flex;align-items:center;gap:7px;background:#fff;border:1.5px dashed var(--primary);border-radius:10px;padding:8px 12px;box-shadow:0 2px 8px rgba(15,23,42,.10);cursor:pointer;font-size:12px;user-select:none}
.gbadge:hover{background:var(--primary-light)}
.gbadge-ico{color:var(--primary);font-size:13px;line-height:1}
.gbadge-name{font-weight:600;color:var(--text);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gbadge-cnt{font-size:10px;background:var(--primary-light);color:var(--primary);border-radius:999px;padding:0 6px;line-height:1.6}
</style>
