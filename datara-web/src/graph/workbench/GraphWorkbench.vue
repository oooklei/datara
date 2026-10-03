<script setup lang="ts">
/**
 * GraphWorkbench：统一图工作台内核。
 * 左 Palette(edit) + 中 VueFlow 画布 + 右 Inspector + FloatLayer 浮窗 + 顶部工具栏。
 * 视角差异全部由注入的 ViewProfile 决定（菜单即视角）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import type { Connection, EdgeChange, EdgeMouseEvent, NodeChange, NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

import type { DocGroup, GraphDocument, GEdge, GNode, GNodeData, Issue } from '../model'
import { cloneDoc, detectCycle, uid } from '../model'
import { applyLayout } from '../layout'
import type { NodeSchema, ViewProfile } from '../profiles'
import type { ComponentCategory } from '../profiles/types' // I12 R1：doc 推导组件库置顶标签用
import { onEdgeCreated, onEdgeRemoved, decideDrop, prefillFromUpstream, applyInitTemplate } from '../profiles/formLinkage' // 拖边即引用（端点合一 §3.3）+ F1 拖入闸门 + M5 initTemplate 落图合入
import { createTemplateStage, selectTemplateSteps, stagedUpstreamOf } from '../profiles/templateStaging'
import type { TemplateStage } from '../profiles/templateStaging'
import { useGraphStore } from '../../stores/graph'
import { useAuthStore } from '../../stores/auth'
import { useRunStore } from '../../stores/run'
import { useFloatStore } from '../../stores/float'
import { graphService, isMock } from '../../services'
import type { DagPickItem } from '../../stores/dagTabs'

import DataNode from './DataNode.vue'
import Palette from './Palette.vue'
import Inspector from './Inspector.vue'
import DropConfigDialog from './DropConfigDialog.vue'
import FloatLayer from './FloatLayer.vue'
import IssuePanel from './panels/IssuePanel.vue'
import LogPanel from './panels/LogPanel.vue'
import WfVarPanel from './panels/WfVarPanel.vue'
import AiPanel from './panels/AiPanel.vue'
import VersionPanel from './panels/VersionPanel.vue'
import RunDialog from './RunDialog.vue'
import { Search, FullScreen, RefreshLeft, RefreshRight, Operation, Grid, Refresh } from '@element-plus/icons-vue'

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
const { screenToFlowCoordinate, fitView, fitViewOnInitDone, viewport, setViewport } = useVueFlow()

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

// vue-flow 深层泛型实例化易触发 TS2589，渲染数组放宽为 any（数据契约仍是 GraphDocument）
/* eslint-disable @typescript-eslint/no-explicit-any */
const flowNodes = ref<any[]>([])
const flowEdges = ref<any[]>([])
const selectedId = ref<string | null>(null)
const lastIssues = ref<Issue[]>([])
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
    data: { gnode: g, schema: props.profile.nodeTypes[g?.type ?? ''] ?? FALLBACK_SCHEMA },
  }
}

function toFlowEdge(e: GEdge): any {
  // 防御：边数据缺少 id/source/target 时生成占位边（避免 VueFlow setEdges 内部 toString() 崩溃）
  // VueFlow setEdges 内部会对 edge 的多个字段调用 toString()，undefined/null 会抛 TypeError
  const rawId = e?.id ?? `edge_fallback_${Math.random().toString(36).slice(2, 8)}`
  const rawSource = e?.source ?? 'node_unknown'
  const rawTarget = e?.target ?? 'node_unknown'
  const k = props.profile.edgeKinds[e?.kind ?? props.profile.defaultEdge]
    ?? Object.values(props.profile.edgeKinds)[0]
  // 防御：edgeKinds 配置缺失时提供默认样式
  const color = k?.color ?? '#64748b'
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

function syncFromDoc() {
  if (!doc.value) return
  flowNodes.value = doc.value.nodes.map(toFlowNode)
  flowEdges.value = doc.value.edges.map(toFlowEdge)
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
  /* 宿主切换视角后要并入的其余选中任务（首个已在 :key 中作为画布文档加载） */
  if (props.mergeIds?.length) await onLoadTasks(props.mergeIds)
  /* 首屏构图见 setup 顶部 fitViewOnInitDone watch（等内部 init fit 完成后再收敛/回放视口） */
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  stopResize()
  /* N15 离开时落快照（面板收展/右Tab + 视口 + 未保存草稿） */
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

/** 离开工作台时落快照：外部注入 doc（血缘等只读视图）不保存；无文档不保存 */
function saveSnap() {
  if (props.doc || !doc.value) return
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

async function onSave() {
  if (!doc.value) return
  /* W1 保存闸门：先跑视角校验器；存在 error（成环/缺源缺汇/混编等）时确认后才保存（warn 不阻断，保持草稿语义） */
  const pre: Issue[] = []
  props.profile.validators.forEach((v) => pre.push(...v(doc.value!)))
  const errs = pre.filter((i) => i.level === 'error')
  if (errs.length) {
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
  const issues: Issue[] = []
  props.profile.validators.forEach((v) => issues.push(...v(doc.value!)))
  lastIssues.value = issues
  floatStore.open({
    id: 'issues', title: `校验结果（${props.profile.name}）`,
    x: window.innerWidth - 560, y: 90, w: 420, h: 300,
    minimized: false, comp: IssuePanel, props: { issues },
  })
  if (issues.length === 0) ElMessage.success('校验通过')
  else ElMessage.warning(`发现 ${issues.length} 个问题`)
}

function onLayout() {
  if (!doc.value) return
  graphStore.replace(applyLayout(cloneDoc(doc.value), props.profile))
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
  const k = e.key.toLowerCase()
  if ((e.ctrlKey || e.metaKey) && k === 'f') {
    e.preventDefault()
    searchOpen.value = true
    nextTick(() => searchInput.value?.focus())
    return
  }
  if (effMode.value !== 'edit') return
  if ((e.ctrlKey || e.metaKey) && k === 'z' && !e.shiftKey) { e.preventDefault(); graphStore.undo(); return }
  if ((e.ctrlKey || e.metaKey) && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); graphStore.redo(); return }
  if (e.key === 'Delete' || e.key === 'Backspace') {
    const nodes = [...selectedIds.value]
    const edges = [...selectedEdgeIds.value]
    if (!nodes.length && !edges.length) return
    e.preventDefault()
    if (nodes.length) void removeNodes(nodes)
    if (edges.length) void removeEdges(edges)
  }
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
  if (g) props.profile.onEdgeClick?.(g, doc.value)
}

/** 节点渲染组件：profile 可注入自定义（如 ER 实体卡片），缺省 DataNode */
const nodeComp = computed(() => props.profile.nodeComp ?? DataNode)

/** profile 预置浮窗（按当前模式过滤） */
const extraFloats = computed(() =>
  (props.profile.floats ?? []).filter((f) => !f.mode || f.mode === effMode.value))

function openFloat(id: string, title: string, comp: unknown, w: number, h: number, extra?: Record<string, unknown>) {
  floatStore.open({
    id, title, w, h,
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

function onConnect(conn: Connection) {
  if (effMode.value !== 'edit') return
  if (!doc.value || !conn.source || !conn.target) return
  if (conn.source === conn.target) { ElMessage.warning('不允许自连'); return }
  const dup = (sh: string) => doc.value!.edges.some(
    (e) => e.source === conn.source && e.target === conn.target && (e.sourceHandle ?? '') === sh)
  if (dup(conn.sourceHandle ?? '')) { ElMessage.warning('依赖边已存在'); return }
  /* 分支/具名输出口连线：边标注端口名并使用 branch 语义（不同分支可指向同一目标；
     端点合一：endpoint_select 静态 outputs（sourceRef/targetRef）与动态 ports 归一按端口解析） */
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
  const next: GraphDocument = { ...doc.value, edges: [...doc.value.edges, edge] }
  if (props.profile.layout === 'dagre' && detectCycle(next).length) {
    ElMessage.error('该连接将形成环，已拒绝（DAG 不允许成环）')
    return
  }
  doc.value.edges.push(edge)
  onEdgeCreated(doc.value, edge) // 拖边即引用（§3.3）：同步向目标节点 inputs 追加 `${source}:${sourceHandle ?? ''}` 引用
  flowEdges.value.push(toFlowEdge(edge))
  applyVisibility()
  graphStore.markDirty()
  if (port) ElMessage.success(`已连接分支「${port.label}」`)
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
  const schema = props.profile.nodeTypes[type]
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
      <template v-if="effMode === 'edit'">
        <button class="tb-btn primary" :disabled="graphStore.saving" @click="onSave">保存</button>
        <button class="tb-btn run" :class="{ running: run.running }" @click="onRun">{{ run.running ? '停止' : '试运行' }}</button>
        <span class="tb-sep" />
        <button class="tb-btn" @click="onValidate">校验</button>
        <button class="tb-btn" @click="onLayout">自动布局</button>
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
        <Palette v-show="leftOpen" :style="{ width: leftWidth + 'px' }" :profile="profile" :active-tags="paletteActiveTags" @load-tasks="onPaletteLoad" />
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
        <VueFlow
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          :fit-view-on-init="true"
          :min-zoom="0.3"
          :max-zoom="2"
          :delete-key-code="null"
          :nodes-draggable="effMode === 'edit'"
          :nodes-connectable="effMode === 'edit'"
          @connect="onConnect"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          @node-click="onNodeClick"
          @node-double-click="onNodeDblClick"
          @node-contextmenu="onNodeCtx"
          @edge-click="onEdgeClick"
          @edge-contextmenu="onEdgeCtx"
          @pane-click="onPaneClick"
        >
          <Background :gap="18" />
          <Controls position="top-left" />
          <MiniMap pannable zoomable :node-color="miniColor" node-stroke-color="#ffffff" :node-border-radius="2" mask-color="rgba(203,213,225,.5)" />
          <template #node-gn="nodeProps">
            <div :class="{ 'gn-hit': nodeProps.id === searchHit }">
              <component
                :is="nodeComp"
                :id="nodeProps.id"
                :gnode="nodeProps.data.gnode"
                :schema="nodeProps.data.schema"
                :selected="nodeProps.selected"
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
        <Inspector v-show="rightTab === 'inspector'" :node="selectedNode" :profile="profile" @delete="deleteOne" />
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

    <!-- 浮窗层 -->
    <FloatLayer />

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
.tb-ico:hover{background:var(--bg);color:var(--primary)}
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
/* N6 折叠组徽标 */
.gbadge{display:flex;align-items:center;gap:7px;background:#fff;border:1.5px dashed var(--primary);border-radius:10px;padding:8px 12px;box-shadow:0 2px 8px rgba(15,23,42,.10);cursor:pointer;font-size:12px;user-select:none}
.gbadge:hover{background:var(--primary-light)}
.gbadge-ico{color:var(--primary);font-size:13px;line-height:1}
.gbadge-name{font-weight:600;color:var(--text);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gbadge-cnt{font-size:10px;background:var(--primary-light);color:var(--primary);border-radius:999px;padding:0 6px;line-height:1.6}
</style>
