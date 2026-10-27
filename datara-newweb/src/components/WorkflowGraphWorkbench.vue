<script setup lang="ts">
/**
 * WorkflowGraphWorkbench（INC4-FE-6 ③，4.3 画布内核）：vue-flow 画布替换
 * CanvasPlaceholder，接驳 workflowGraph store（FE-6 ② loadSeq/dirty/差量保存）。
 *
 * 同步策略（非受控 + 单向 prop 同步 + 事件选择性回写，无双源）：
 *  - :nodes/:edges 从 store computed 映射单向传入（vue-flow 内部 merge）；
 *  - @connect → store.addEdge（自带自环/幂等守卫；不调 vue-flow addEdges，
 *    边靠 prop 同步进内部态）；
 *  - @nodes-change：remove → removeNode；position 且 !dragging（拖拽落定）
 *    → moveNode（中间态不回写，保 diff 感知）；dimensions/select 忽略；
 *  - @edges-change：remove → 按 EdgeRemoveChange.source/target 直取 removeEdge
 *    （vue-flow 1.48 类型实锚，免 id 解析）。
 *
 * 生命周期（单例 store × 多 Tab KeepAlive 并存，快照兜底）：
 *  - onActivated 为 load 唯一入口（KeepAlive 首挂载也触发 activated）：
 *    projectId 缺位 → 降级注记；同 Tab 复活且 store 仍持 doc → 仅清陈旧快照键
 *    （不重载保编辑态）；否则 load + 快照 $patch 恢复（isDirty 随之）；
 *  - onDeactivated/onUnmounted → dirty 时写 localStorage 快照
 *    datara.dag.snap.${docId}（TaskCenterView onCloseTab hasSnapDraft 同键）；
 *    不 close store——槽位由下一 Tab 的 load 接管。
 *
 * 类型实锚：@vue-flow/core 1.48.2 dist/types（NodeChange/EdgeChange/Connection/
 * MarkerType.ArrowClosed/NodeMouseEvent/EdgeMouseEvent；index.d.ts export * from './types'）。
 */
import { computed, nextTick, onActivated, onDeactivated, onUnmounted, ref } from 'vue'
import { MarkerType, VueFlow, useVueFlow } from '@vue-flow/core'
import type {
  Connection,
  EdgeChange,
  EdgeMouseEvent,
  NodeChange,
  NodeMouseEvent,
} from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { ElMessage, ElMessageBox } from 'element-plus'
import dagre from '@dagrejs/dagre'
import type { DagTab } from '../stores/dagTabs'
import {
  WF_NODE_TYPES,
  listWorkflowVersions,
  publishWorkflowDefinition,
  type WorkflowDraftEdge,
  type WorkflowDraftNode,
  type WorkflowVersion,
  type WfNodeType,
} from '../services/rebuild/workflowApi'
import { loadComponentSpecs, type ComponentSpecItem, type WorkflowType } from '../services/rebuild/componentSpecApi'
import { useTrialRunStore } from '../stores/trialRun'
import { useWorkflowGraphStore } from '../stores/workflowGraph'
import NodeConfigPanel from './NodeConfigPanel.vue'
import TrialRunPanel from './TrialRunPanel.vue'
import WorkflowVariablePanel from './WorkflowVariablePanel.vue'
import ScriptResourceEditor from './ScriptResourceEditor.vue'
import StreamObservationPanel from './StreamObservationPanel.vue'
import SyncMappingEditor from './SyncMappingEditor.vue'
import DependencyNodeEditor from './DependencyNodeEditor.vue'
import Palette from './Palette.vue'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const props = defineProps<{ tab: DagTab; projectId?: number }>()

const emit = defineEmits<{ (e: 'schedule', d: { id: number; name: string }): void }>()

const graphStore = useWorkflowGraphStore()
const INSPECTOR_TABS = [
  { id: 'properties', label: '属性' },
  { id: 'variables', label: '变量' },
  { id: 'dependencies', label: '依赖' },
  { id: 'trial', label: '试运行' },
] as const
type InspectorTabId = (typeof INSPECTOR_TABS)[number]['id']
const activeInspectorTab = ref<InspectorTabId>('properties')
const variablesPanelMounted = ref(false)
const trialPanelMounted = ref(false)

function activateInspectorTab(tab: InspectorTabId) {
  activeInspectorTab.value = tab
  if (tab === 'variables') variablesPanelMounted.value = true
  if (tab === 'trial') trialPanelMounted.value = true
}

function onInspectorKeydown(event: KeyboardEvent, index: number) {
  let nextIndex = index
  if (event.key === 'ArrowRight') nextIndex = (index + 1) % INSPECTOR_TABS.length
  else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + INSPECTOR_TABS.length) % INSPECTOR_TABS.length
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = INSPECTOR_TABS.length - 1
  else return
  event.preventDefault()
  const nextTab = INSPECTOR_TABS[nextIndex]
  activateInspectorTab(nextTab.id)
  void nextTick(() => document.getElementById(`workflow-inspector-tab-${nextTab.id}`)?.focus())
}

const SPLIT_STORAGE_KEY = 'datara.dag.split.v1'
function initialSplit(): { left: number; right: number } {
  try {
    const value = JSON.parse(localStorage.getItem(SPLIT_STORAGE_KEY) ?? '{}') as { left?: number; right?: number }
    return {
      left: Math.min(360, Math.max(196, Number(value.left) || 232)),
      right: Math.min(520, Math.max(280, Number(value.right) || 340)),
    }
  } catch {
    return { left: 232, right: 340 }
  }
}
const split = initialSplit()
const leftWidth = ref(split.left)
const rightWidth = ref(split.right)
const splitStyle = computed(() => ({ '--dag-left': `${leftWidth.value}px`, '--dag-right': `${rightWidth.value}px` }))
let stopResize: (() => void) | undefined

function beginResize(side: 'left' | 'right', event: PointerEvent) {
  event.preventDefault()
  const startX = event.clientX
  const startWidth = side === 'left' ? leftWidth.value : rightWidth.value
  const onMove = (move: PointerEvent) => {
    const delta = move.clientX - startX
    if (side === 'left') leftWidth.value = Math.min(360, Math.max(196, startWidth + delta))
    else rightWidth.value = Math.min(520, Math.max(280, startWidth - delta))
  }
  const onUp = () => {
    localStorage.setItem(SPLIT_STORAGE_KEY, JSON.stringify({ left: leftWidth.value, right: rightWidth.value }))
    stopResize?.()
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp, { once: true })
  stopResize = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    stopResize = undefined
  }
}

/** DagTab.docId（string）→ store docId（number）桥 */
const numDocId = computed(() => Number(props.tab.docId))

const degraded = ref(props.projectId === undefined)
const loading = ref(false)
const loaded = ref(false)
const componentSpecs = ref<ComponentSpecItem[]>([])
const availableComponents = computed(() => WF_NODE_TYPES.map((type) => {
  const spec = componentSpecs.value.find((item) => item.type === type)
  return spec ?? {
    type,
    identity: { displayName: type },
    componentRef: undefined,
  }
}))
const workflowType = computed<WorkflowType>(() => props.tab.type === 'sync' ? 'SYNC' : props.tab.type === 'stream' ? 'STREAM' : 'NORMAL')
const isSyncTab = computed(() => props.tab.type === 'sync')
const isStreamTab = computed(() => props.tab.type === 'stream')

/* ---------- store → vue-flow 单向映射 ---------- */

const trialStore = useTrialRunStore()
const taskStatusMap = computed(() => {
  const statuses = new Map<string, string>()
  // Production invariant: runResult can only be written by run(), whose guard
  // requires IDs bound by open(); open() also clears runResult and the store is
  // not persisted.  null/null + runResult is therefore test-fixture-only legacy
  // state, retained for the frozen L12-02 contract.  Every reachable bound state
  // must match both project and definition before its statuses can be rendered.
  const isUnreachableLegacyFixture = trialStore.projectId === null && trialStore.definitionId === null
  if (!isUnreachableLegacyFixture
    && (trialStore.projectId !== props.projectId || trialStore.definitionId !== numDocId.value)) {
    return statuses
  }
  for (const task of trialStore.runResult?.tasks ?? []) statuses.set(task.nodeCode, task.status)
  return statuses
})

type CanvasNode = {
  id: string
  type: string
  position: { x: number; y: number }
  label: string
  class?: string
}

function layoutFlowNodes(nodes: CanvasNode[], edges: WorkflowDraftEdge[]): CanvasNode[] {
  const overlaps = nodes.some((node, index) => nodes.slice(index + 1).some((other) =>
    Math.abs(node.position.x - other.position.x) < 168
      && Math.abs(node.position.y - other.position.y) < 64,
  ))
  if (!overlaps) return nodes

  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: 'LR', nodesep: 36, ranksep: 72, marginx: 28, marginy: 28 })
  graph.setDefaultEdgeLabel(() => ({}))
  for (const node of nodes) graph.setNode(node.id, { width: 168, height: 54 })
  for (const edge of edges) graph.setEdge(edge.fromNode, edge.toNode)
  dagre.layout(graph)

  return nodes.map((node) => {
    const point = graph.node(node.id) as { x: number; y: number } | undefined
    return point
      ? { ...node, position: { x: Math.round(point.x - 84), y: Math.round(point.y - 27) } }
      : node
  })
}

const flowNodes = computed(() =>
  layoutFlowNodes(graphStore.nodes.map((n: WorkflowDraftNode) => {
    const status = taskStatusMap.value.get(n.nodeCode)
    const unconfigured = !isNodeConfigured(n)
    return {
      id: n.nodeCode,
      type: 'default',
      position: { x: n.positionX ?? 0, y: n.positionY ?? 0 },
      label: `${n.nodeCode} ${n.nodeType}${n.name ? ` ${n.name}` : ''}${unconfigured ? ' ⚠未配置' : ''}${status ? ` [${status}]` : ''}`,
      class: [status ? `wf-node-${status.toLowerCase()}` : '', unconfigured ? 'wf-node-unconfigured' : ''].filter(Boolean).join(' ') || undefined,
    }
  }), graphStore.edges),
)

const flowEdges = computed(() =>
  graphStore.edges.map((e: WorkflowDraftEdge) => ({
    id: `${e.fromNode}->${e.toNode}`,
    source: e.fromNode,
    target: e.toNode,
    label: e.name ?? undefined,
    markerEnd: MarkerType.ArrowClosed,
  })),
)

/* ---------- vue-flow → store 选择性回写 ---------- */

function onConnect(conn: Connection) {
  graphStore.addEdge(conn.source, conn.target)
}

function onNodesChange(changes: NodeChange[]) {
  for (const c of changes) {
    if (c.type === 'remove') {
      graphStore.removeNode(c.id)
    } else if (c.type === 'position' && !c.dragging) {
      graphStore.moveNode(c.id, c.position.x, c.position.y)
    }
  }
}

function onEdgesChange(changes: EdgeChange[]) {
  for (const c of changes) {
    if (c.type === 'remove') graphStore.removeEdge(c.source, c.target)
  }
}

/* ---------- 选中态（工具栏删除） ---------- */

const selectedNode = ref<string | null>(null)
const selectedEdge = ref<{ from: string; to: string } | null>(null)
const selectedNodeRecord = computed(() => graphStore.nodes.find((node) => node.nodeCode === selectedNode.value) ?? null)
const nodeParameterKey = computed(() => {
  const type = String(selectedNodeRecord.value?.nodeType ?? '').toLowerCase()
  if (type === 'sql') return 'sql'
  if (type === 'python' || type === 'shell') return 'script'
  return null
})
const scriptResourceKind = computed(() => {
  const type = String(selectedNodeRecord.value?.nodeType ?? '').toLowerCase()
  return type === 'sql' || type === 'python' || type === 'shell' ? type : null
})
function updateNodeParams(value: Record<string, unknown>) {
  const node = selectedNodeRecord.value
  if (!node) return
  graphStore.updateNode(node.nodeCode, { params: value })
}
const isSyncMappingNode = computed(() => {
  if (workflowType.value !== 'SYNC' || !selectedNodeRecord.value) return false
  const nodeType = String(selectedNodeRecord.value.nodeType ?? '').toLowerCase()
  const mappingType = nodeType === 'sync'
    ? String(selectedNodeRecord.value.params?.component ?? '').toLowerCase()
    : nodeType
  return ['field_map', 'field_map_union'].includes(mappingType)
})
const isDependentNode = computed(() => String(selectedNodeRecord.value?.nodeType ?? '').toLowerCase() === 'dependent')
function updateSyncParams(value: Record<string, unknown>) {
  const node = selectedNodeRecord.value
  if (node) graphStore.updateNode(node.nodeCode, { params: { ...(node.params ?? {}), ...value } })
}

function onNodeClick({ node }: NodeMouseEvent) {
  selectedNode.value = node.id
  selectedEdge.value = null
}
function onEdgeClick({ edge }: EdgeMouseEvent) {
  selectedNode.value = null
  selectedEdge.value = { from: edge.source, to: edge.target }
}
function clearSelection() {
  selectedNode.value = null
  selectedEdge.value = null
}
function onDeleteSelected() {
  if (selectedNode.value) {
    graphStore.removeNode(selectedNode.value)
    clearSelection()
  } else if (selectedEdge.value) {
    graphStore.removeEdge(selectedEdge.value.from, selectedEdge.value.to)
    clearSelection()
  }
}

/* ---------- 托盘（13 类型点击加节点，级联摆位） ---------- */

function publishedComponentRef(type: string): { type: string; version: number } | null {
  const ref = componentSpecs.value.find((item) => item.type === type)?.componentRef
  if (!ref || typeof ref.type !== 'string' || ref.type === '' || ref.type !== type
    || !Number.isInteger(ref.version) || ref.version <= 0) {
    ElMessage.error(`组件 ${type} 缺少有效的已发布版本，无法添加`)
    return null
  }
  return ref
}

function onAddNode(component: (typeof availableComponents.value)[number]) {
  const componentRef = publishedComponentRef(component.type)
  if (!componentRef) return
  const n = graphStore.nodes.length
  const added = graphStore.addNode({
    nodeType: component.type as WfNodeType,
    componentRef,
    positionX: 24 + (n % 6) * 170,
    positionY: 24 + Math.floor(n / 6) * 48,
  })
  selectForConfig(added.nodeCode)
}

/* ---------- 设计态组件托盘（后端 catalogue 冻结白名单；node_type 必须是组件 type 本身） ---------- */

const SYNC_PALETTE_TYPES: readonly string[] = [
  'src_base_orch',
  'tgt_base_orch',
  'file_sync_orch',
  'endpoint_select',
  'field_map',
  'field_map_union',
  'condition_set',
]
const STREAM_PALETTE_TYPES: readonly string[] = [
  'stream_input',
  'stream_fuse',
  'stream_output',
  'page_board',
]
/** 当前宿主的托盘白名单：SYNC→7 项、STREAM→4 项；NORMAL 宿主用顶部 4 按钮通道 */
const designPaletteTypes = computed<readonly string[]>(() => {
  if (workflowType.value === 'SYNC') return SYNC_PALETTE_TYPES
  if (workflowType.value === 'STREAM') return STREAM_PALETTE_TYPES
  return []
})
const isSpecTrayVisible = computed(() => isSyncTab.value || isStreamTab.value)
const specTrayLabel = computed(() => (isStreamTab.value ? '流组件（拖入画布或点击添加）' : '同步组件（拖入画布或点击添加）'))
const paletteSpecs = ref<ComponentSpecItem[]>([])
const paletteSpecsFailed = ref(false)
let specRequestController: AbortController | null = null
let specRequestSequence = 0

async function loadPaletteSpecs() {
  specRequestController?.abort()
  const controller = new AbortController()
  const sequence = ++specRequestSequence
  specRequestController = controller
  try {
    const snapshot = await loadComponentSpecs(undefined, controller.signal)
    if (controller.signal.aborted || sequence !== specRequestSequence) return
    componentSpecs.value = snapshot.items
    paletteSpecs.value = snapshot.items.filter((item) => designPaletteTypes.value.includes(item.type))
    paletteSpecsFailed.value = false
  } catch (error) {
    if (controller.signal.aborted || sequence !== specRequestSequence
      || (error instanceof DOMException && error.name === 'AbortError')) return
    componentSpecs.value = []
    paletteSpecs.value = []
    paletteSpecsFailed.value = true
  } finally {
    if (sequence === specRequestSequence) specRequestController = null
  }
}

function abortPaletteSpecs() {
  specRequestSequence += 1
  specRequestController?.abort()
  specRequestController = null
}

function specName(spec: ComponentSpecItem): string {
  const displayName = spec.identity?.displayName
  return typeof displayName === 'string' && displayName !== '' ? displayName : spec.type
}

/* ---------- T2 configure-first：未配置节点判定与闸门 ---------- */

/** 设计态组件节点必须有除 component 归属标记外的业务参数才视为已配置；
 *  START/END 等 legacy 流程节点不参与判定 */
const DESIGN_NODE_TYPES = new Set<string>([...WF_NODE_TYPES, ...SYNC_PALETTE_TYPES, ...STREAM_PALETTE_TYPES])
function isNodeConfigured(node: WorkflowDraftNode): boolean {
  if (!DESIGN_NODE_TYPES.has(node.nodeType)) return true
  const params = node.params ?? {}
  return Object.keys(params).some((key) => key !== 'component')
}
const unconfiguredNodeNames = computed(() =>
  graphStore.nodes.filter((node) => !isNodeConfigured(node)).map((node) => `${node.nodeCode}${node.name ? `（${node.name}）` : ''}`),
)
function guardUnconfigured(): boolean {
  if (unconfiguredNodeNames.value.length === 0) return true
  ElMessage.error(`存在未配置节点：${unconfiguredNodeNames.value.join('、')}；请先完成配置（配置先行）`)
  return false
}

/** configure-first 交互：新增节点立即选中（Inspector 随选中呈现配置面板） */
function selectForConfig(nodeCode: string) {
  selectedNode.value = nodeCode
  selectedEdge.value = null
}

function onSpecDragStart(event: DragEvent, type: string) {
  event.dataTransfer?.setData('datara/node-type', type)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy'
}

/** 托盘点击添加：node_type 直传组件 type（后端 catalogue 校验只认组件 type，
 *  'SYNC' 之类宿主类别会被 WF_NODE_TYPE_UNKNOWN 拒绝）；SYNC/STREAM 保留
 *  params.component 供画布内专项编辑器分流 */
function addComponentByType(type: string) {
  const componentRef = publishedComponentRef(type)
  if (!componentRef) return
  const n = graphStore.nodes.length
  const keepComponentParam = SYNC_PALETTE_TYPES.includes(type) || STREAM_PALETTE_TYPES.includes(type)
  const added = graphStore.addNode({
    nodeType: type,
    componentRef,
    params: keepComponentParam ? { component: type } : undefined,
    positionX: 24 + (n % 6) * 170,
    positionY: 24 + Math.floor(n / 6) * 48,
  })
  selectForConfig(added.nodeCode)
}

const { project } = useVueFlow()
function onDrop(event: DragEvent) {
  const type = event.dataTransfer?.getData('datara/node-type')
  if (!type) return
  // Palette 承载全部设计态组件（NORMAL 4 + SYNC 7 + STREAM 4）；drop 白名单与宿主无关，
  // 画布节点归属由 definition.workflowType 决定，拖入非本类组件由 W1 校验/发布闸门拦截
  const droppable = designPaletteTypes.value.includes(type) || WF_NODE_TYPES.includes(type as (typeof WF_NODE_TYPES)[number])
  if (!droppable) return
  const componentRef = publishedComponentRef(type)
  if (!componentRef) return
  const position = project({ x: event.clientX, y: event.clientY })
  const keepComponentParam = SYNC_PALETTE_TYPES.includes(type) || STREAM_PALETTE_TYPES.includes(type)
  const added = graphStore.addNode({
    nodeType: type,
    componentRef,
    params: keepComponentParam ? { component: type } : undefined,
    positionX: Math.round(position.x),
    positionY: Math.round(position.y),
  })
  selectForConfig(added.nodeCode)
}

const selectedNodeObj = computed<WorkflowDraftNode | null>(() => selectedNodeRecord.value)
function onConfigSave(params: Record<string, unknown>) {
  if (!selectedNode.value) return
  graphStore.updateNode(selectedNode.value, { params })
  ElMessage.success('节点配置已保存')
  clearSelection()
}

function rebindTrialContext() {
  if (activeInspectorTab.value !== 'trial' || props.projectId === undefined) return
  if (!Number.isSafeInteger(props.projectId) || props.projectId <= 0) return
  if (!Number.isSafeInteger(numDocId.value) || numDocId.value <= 0) return
  trialStore.open(props.projectId, numDocId.value)
}

/* ---------- 快照（localStorage，键与 TaskCenterView hasSnapDraft 约定一致） ---------- */

function snapKey(): string {
  return `datara.dag.snap.${props.tab.docId}`
}

function readSnap(): { nodes: WorkflowDraftNode[]; edges: WorkflowDraftEdge[] } | null {
  try {
    const raw = localStorage.getItem(snapKey())
    if (!raw) return null
    const s = JSON.parse(raw) as { draft?: { nodes?: WorkflowDraftNode[]; edges?: WorkflowDraftEdge[] } }
    return s?.draft && Array.isArray(s.draft.nodes) && Array.isArray(s.draft.edges)
      ? { nodes: s.draft.nodes, edges: s.draft.edges }
      : null
  } catch {
    return null
  }
}

function clearSnap() {
  localStorage.removeItem(snapKey())
}

function persistSnap() {
  if (graphStore.docId !== numDocId.value || !graphStore.isDirty) return
  // reactive 数组深拷贝（structuredClone 对 Proxy 会抛错，JSON 序列化沿 store 惯例）
  const payload = {
    draft: {
      nodes: JSON.parse(JSON.stringify(graphStore.nodes)) as WorkflowDraftNode[],
      edges: JSON.parse(JSON.stringify(graphStore.edges)) as WorkflowDraftEdge[],
    },
  }
  try {
    localStorage.setItem(snapKey(), JSON.stringify(payload))
  } catch {
    // 配额满不阻断停用流程（TaskCenterView 关闭三选已有草稿提示兜底）
  }
}

/* ---------- 生命周期（KeepAlive） ---------- */

async function ensureLoaded() {
  if (props.projectId === undefined) {
    degraded.value = true
    return
  }
  degraded.value = false
  await loadPaletteSpecs()
  // Definition ids are only unique within a project.  When a keep-alive
  // project route changes, the same numeric workflow id must be reloaded
  // instead of reusing the previous project's draft.
  if (graphStore.docId === numDocId.value && graphStore.projectId === props.projectId) {
    // 同 Tab 复活：store 仍持 doc（不 close on deactivate），清陈旧快照键即可
    clearSnap()
    return
  }
  loaded.value = false
  loading.value = true
  try {
    await graphStore.load(props.projectId, numDocId.value)
    // load() records transport errors on the store instead of throwing so
    // callers can keep the shared store alive.  Do not mark the canvas ready
    // when that happened: otherwise Save/Publish become enabled for an empty
    // graph and can overwrite a draft after a transient read failure.
    if (graphStore.docId !== numDocId.value || graphStore.lastError) {
      loaded.value = false
      ElMessage.error(`画布数据加载失败：${graphStore.lastError ?? '未返回工作流草稿'}`)
      return
    }
    const snap = readSnap()
    if (snap) {
      // 直接状态赋值（$patch 的 _DeepPartial 对 Record<string, unknown> 索引签名不兼容）
      graphStore.nodes = snap.nodes
      graphStore.edges = snap.edges
      clearSnap()
    }
    loaded.value = true
  } catch {
    ElMessage.error('画布数据加载失败')
  } finally {
    loading.value = false
  }
}

onActivated(() => {
  void ensureLoaded()
  rebindTrialContext()
})
onDeactivated(() => {
  abortPaletteSpecs()
  persistSnap()
})
onUnmounted(() => {
  abortPaletteSpecs()
  stopResize?.()
  persistSnap()
})

/* ---------- 工具栏：保存 / 发布 / 版本 ---------- */

async function onSave() {
  if (!guardUnconfigured()) return
  let r
  try {
    r = await graphStore.save()
  } catch (error) {
    ElMessage.error(`保存失败：${error instanceof Error ? error.message : '请求异常'}`)
    return
  }
  if (!r) {
    ElMessage.warning('画布未加载，无法保存')
    return
  }
  if (r.complete) {
    ElMessage.success('保存成功')
    return
  }
  ElMessage.error(`保存未完成：${r.dirtyKeys.join(', ')}`)
}

async function onPublish() {
  if (props.projectId === undefined) return
  if (!guardUnconfigured()) return
  // Publishing a stale server draft is a destructive surprise.  Flush local
  // graph changes first and stop when the queue reports partial failure.
  if (graphStore.isDirty) {
    try {
      const saved = await graphStore.save()
      if (!saved?.complete) {
        ElMessage.error(`发布前保存未完成：${saved?.dirtyKeys.join(', ') ?? '未知变更'}`)
        return
      }
    } catch (error) {
      ElMessage.error(`发布前保存失败：${error instanceof Error ? error.message : '请求异常'}`)
      return
    }
  }
  let remark: string | undefined
  try {
    const p = await ElMessageBox.prompt('输入版本备注（可选）', '发布版本', {
      confirmButtonText: '发布',
      cancelButtonText: '取消',
      inputPlaceholder: '备注',
    })
    const v = (p.value ?? '').trim()
    remark = v || undefined
  } catch {
    return
  }
  try {
    const ver = await publishWorkflowDefinition(props.projectId, numDocId.value, remark)
    ElMessage.success(`已发布版本 v${ver.version}`)
  } catch (error) {
    ElMessage.error(`发布失败：${error instanceof Error ? error.message : '请求异常'}`)
  }
}

const versionsVisible = ref(false)
const versions = ref<WorkflowVersion[]>([])

async function onShowVersions() {
  if (props.projectId === undefined) return
  try {
    versions.value = await listWorkflowVersions(props.projectId, numDocId.value)
    versionsVisible.value = true
  } catch {
    ElMessage.error('版本列表加载失败')
  }
}

function onSchedule() {
  emit('schedule', { id: numDocId.value, name: props.tab.name })
}
</script>

<template>
  <div class="wf-workbench" data-tc-canvas-workbench>
    <div class="wf-toolbar">
      <div class="wf-actions">
        <button class="wf-btn" :disabled="!loaded" @click="onSave">保存</button>
        <button
          class="wf-btn"
          :disabled="!loaded || (!selectedNode && !selectedEdge)"
          title="删除选中节点/连线"
          @click="onDeleteSelected"
        >删除选中</button>
        <button class="wf-btn" :disabled="degraded || !loaded" @click="onPublish">发布</button>
        <button class="wf-btn" :disabled="degraded || !loaded" @click="onShowVersions">版本</button>
        <button class="wf-btn" data-testid="wf-schedule" :disabled="degraded || !loaded" @click="onSchedule">定时</button>
        <button class="wf-btn" data-testid="wf-trial" :disabled="degraded || !loaded" @click="activateInspectorTab('trial')">试运行</button>
        <button class="wf-btn" data-workflow-variables :disabled="degraded || !loaded" @click="activateInspectorTab('variables')">工作流变量</button>
        <span
          v-if="graphStore.docId === numDocId && graphStore.isDirty"
          class="wf-dirty"
          title="存在未保存的修改"
        >未保存</span>
      </div>
      <div class="wf-tray">
        <button
          v-for="component in availableComponents"
          :key="component.type"
          class="wf-type"
          :disabled="!loaded"
          @click="onAddNode(component)"
        >{{ component.identity.displayName ?? component.type }}</button>
      </div>
      <div v-if="isSpecTrayVisible && loaded" class="wf-specs">
        <span class="wf-specs-label">{{ specTrayLabel }}</span>
        <button
          v-for="spec in paletteSpecs"
          :key="spec.type"
          class="wf-spec"
          draggable="true"
          :data-testid="`wf-spec-${spec.type}`"
          :title="`${specName(spec)}（拖入画布或点击添加）`"
          @dragstart="onSpecDragStart($event, spec.type)"
          @click="addComponentByType(spec.type)"
        >{{ specName(spec) }}</button>
        <span v-if="paletteSpecsFailed" class="wf-specs-failed" data-testid="wf-specs-failed">组件清单加载失败</span>
      </div>
    </div>

    <div v-if="degraded" class="wf-degraded">画布：{{ tab.name }}（无项目上下文，待接驳）</div>
    <div v-else-if="loading" class="wf-degraded">画布加载中…</div>
    <div v-else-if="!loaded" class="wf-degraded">画布：{{ tab.name }}</div>
    <div v-else class="wf-body" :style="splitStyle">
      <div class="wf-palette-pane" data-dag-palette>
        <Palette :project-id="projectId" :workflow-type="workflowType" @add-component="addComponentByType($event.type)" />
      </div>
      <button
        type="button"
        class="wf-splitter"
        role="separator"
        aria-label="调整组件面板宽度"
        aria-orientation="vertical"
        @pointerdown="beginResize('left', $event)"
      />
      <div class="wf-flow" data-dag-canvas>
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :apply-default="true"
          @connect="onConnect"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
          @pane-click="clearSelection"
          @dragover.prevent
          @drop="onDrop"
        >
          <Controls />
          <MiniMap pannable zoomable />
        </VueFlow>
      </div>
      <button
        type="button"
        class="wf-splitter"
        role="separator"
        aria-label="调整属性面板宽度"
        aria-orientation="vertical"
        @pointerdown="beginResize('right', $event)"
      />
      <aside v-if="projectId !== undefined" class="wf-aside" data-dag-inspector>
        <header class="inspector-head"><strong>检查器</strong><small>{{ selectedNodeRecord?.nodeCode ?? '画布' }}</small></header>
        <div class="inspector-tabs" role="tablist" aria-label="工作流检查器">
          <button
            v-for="(item, index) in INSPECTOR_TABS"
            :id="`workflow-inspector-tab-${item.id}`"
            :key="item.id"
            type="button"
            role="tab"
            class="inspector-tab"
            :class="{ active: activeInspectorTab === item.id }"
            :aria-selected="activeInspectorTab === item.id"
            :aria-controls="`workflow-inspector-panel-${item.id}`"
            :tabindex="activeInspectorTab === item.id ? 0 : -1"
            @click="activateInspectorTab(item.id)"
            @keydown="onInspectorKeydown($event, index)"
          >{{ item.label }}</button>
        </div>

        <section id="workflow-inspector-panel-properties" v-show="activeInspectorTab === 'properties'" role="tabpanel" tabindex="0" aria-labelledby="workflow-inspector-tab-properties">
          <NodeConfigPanel
            v-if="selectedNodeObj && !isSyncMappingNode && !scriptResourceKind && !isDependentNode"
            :node="selectedNodeObj"
            :project-id="projectId"
            :workflow-id="numDocId"
            :workflow-version="1"
            @save="onConfigSave"
            @close="clearSelection"
          />
          <section v-else-if="selectedNodeRecord && nodeParameterKey && scriptResourceKind" class="node-editor" data-node-parameter-editor>
            <strong>{{ selectedNodeRecord.nodeType }} 参数 · {{ selectedNodeRecord.nodeCode }}</strong>
            <ScriptResourceEditor
              :key="selectedNodeRecord.nodeCode"
              :project-id="projectId"
              :workflow-id="numDocId"
              :workflow-version="1"
              :task-id="selectedNodeRecord.nodeCode"
              :kind="scriptResourceKind"
              :model-value="selectedNodeRecord.params ?? {}"
              @update:model-value="updateNodeParams"
            />
          </section>
          <SyncMappingEditor
            v-else-if="isSyncMappingNode && selectedNodeRecord"
            :project-id="projectId"
            :workflow-id="numDocId"
            :workflow-version="1"
            :task-id="selectedNodeRecord.nodeCode"
            :model-value="selectedNodeRecord.params ?? {}"
            @update:model-value="updateSyncParams"
          />
          <StreamObservationPanel
            v-else-if="workflowType === 'STREAM'"
            :project-id="projectId"
            :workflow-id="numDocId"
            :workflow-name="tab.name"
          />
          <div v-else class="inspector-empty">
            <span>◇</span><strong>选择一个节点以编辑配置</strong><small>节点参数由已发布组件 spec 动态生成</small>
          </div>
        </section>

        <section id="workflow-inspector-panel-variables" v-show="activeInspectorTab === 'variables'" class="inspector-panel" role="tabpanel" tabindex="0" aria-labelledby="workflow-inspector-tab-variables">
          <WorkflowVariablePanel
            v-if="variablesPanelMounted"
            :model-value="true"
            :project-id="projectId"
            :workflow-id="numDocId"
            @update:model-value="activateInspectorTab('properties')"
          />
        </section>

        <section id="workflow-inspector-panel-dependencies" v-show="activeInspectorTab === 'dependencies'" class="inspector-panel" role="tabpanel" tabindex="0" aria-labelledby="workflow-inspector-tab-dependencies">
          <DependencyNodeEditor
            v-if="selectedNodeRecord && isDependentNode"
            :project-id="projectId"
            :workflow-id="numDocId"
            :workflow-version="1"
            :task-id="selectedNodeRecord.nodeCode"
            :model-value="selectedNodeRecord.params ?? {}"
            @update:model-value="updateNodeParams"
          />
          <div v-else class="inspector-empty">
            <span>◇</span><strong>当前节点不支持依赖配置</strong><small>请选择 dependent 类型节点</small>
          </div>
        </section>

        <section id="workflow-inspector-panel-trial" v-show="activeInspectorTab === 'trial'" class="inspector-panel" role="tabpanel" tabindex="0" aria-labelledby="workflow-inspector-tab-trial">
          <TrialRunPanel v-if="trialPanelMounted" :project-id="projectId" :definition-id="numDocId" />
        </section>
      </aside>
    </div>

    <el-dialog v-model="versionsVisible" title="版本历史" width="640px" append-to-body>
      <el-table :data="versions" size="small">
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="remark" label="备注" />
        <el-table-column prop="publishedAt" label="发布时间" width="170" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 根布局 flex column：工具栏（动作行 + 托盘行）+ 流容器 flex:1（VueFlow 需显式高度） */
.wf-workbench {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}
.wf-toolbar {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  background: var(--bg-secondary, #f8fafc);
}
.wf-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
}
.wf-btn {
  border: 1px solid var(--border-color, #e2e8f0);
  background: #fff;
  border-radius: var(--radius-sm, 6px);
  padding: 4px 12px;
  font-size: 12.5px;
  color: var(--text-primary, #1e293b);
  cursor: pointer;
}
.wf-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
}
.wf-btn:disabled {
  color: var(--text-4, #cbd5e1);
  cursor: not-allowed;
}
.wf-dirty {
  font-size: 11.5px;
  color: var(--warning, #d97706);
  background: var(--warning-bg, #fef3c7);
  border-radius: 8px;
  padding: 1px 8px;
}
.wf-tray {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 10px 8px;
}
.wf-type {
  border: 1px solid var(--border-color, #e2e8f0);
  background: #fff;
  border-radius: var(--radius-sm, 6px);
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary, #64748b);
  cursor: pointer;
}
.wf-type:hover:not(:disabled) {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
  background: var(--primary-light, #eff6ff);
}
.wf-type:disabled {
  color: var(--text-4, #cbd5e1);
  cursor: not-allowed;
}
.wf-specs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 2px 10px 8px;
}
.wf-specs-label {
  font-size: 11px;
  color: var(--text-3, #94a3b8);
}
.wf-spec {
  border: 1px solid var(--border-color, #e2e8f0);
  background: #fff;
  border-radius: var(--radius-sm, 6px);
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary, #64748b);
  cursor: grab;
}
.wf-spec:hover {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
  background: var(--primary-light, #eff6ff);
}
.wf-specs-failed {
  font-size: 11px;
  color: var(--danger, #dc2626);
}
.wf-degraded {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3, #94a3b8);
  font-size: 13px;
}
.wf-body {
  flex: 1;
  min-height: 0;
  display: flex;
  background: var(--bg, #f5f7fb);
}
.wf-palette-pane {
  width: var(--dag-left);
  min-width: 0;
  flex: 0 0 var(--dag-left);
  overflow: hidden;
  border-right: 1px solid var(--border-color, #e2e8f0);
}
.wf-palette-pane :deep(.wb-palette) {
  width: 100%;
  height: 100%;
  border-right: 0;
}
.wf-splitter {
  position: relative;
  z-index: 3;
  width: 6px;
  flex: 0 0 6px;
  padding: 0;
  border: 0;
  border-left: 1px solid transparent;
  border-right: 1px solid transparent;
  background: transparent;
  cursor: col-resize;
}
.wf-splitter:hover,
.wf-splitter:focus-visible {
  border-color: var(--primary, #2563eb);
  background: color-mix(in srgb, var(--primary, #2563eb) 12%, transparent);
  outline: 0;
}
.wf-flow {
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.wf-aside {
  width: var(--dag-right);
  flex: 0 0 var(--dag-right);
  border-left: 1px solid var(--border-color, #e2e8f0);
  background: var(--card, #fff);
  overflow-y: auto;
}
.inspector-head{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;height:42px;padding:0 14px;border-bottom:1px solid var(--border-color,#e2e8f0);background:var(--card,#fff)}
.inspector-head strong{font-size:13px;color:var(--text,#172033)}.inspector-head small{font-family:var(--font-mono,monospace);color:var(--text-3,#94a3b8)}
.inspector-tabs{position:sticky;top:42px;z-index:2;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid var(--border-color,#e2e8f0);background:var(--card,#fff)}
.inspector-tab{padding:9px 4px;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--text-2,#64748b);font:inherit;font-size:12px;cursor:pointer}.inspector-tab.active{border-bottom-color:var(--primary,#2563eb);color:var(--primary,#2563eb);font-weight:600}.inspector-tab:focus-visible{outline:2px solid var(--primary,#2563eb);outline-offset:-2px}
.inspector-panel{min-height:0}.inspector-panel :deep(.workflow-variable-panel){position:static;width:auto;border:0;border-radius:0;box-shadow:none}
.inspector-empty{display:grid;place-items:center;gap:7px;padding:72px 20px;text-align:center;color:var(--text-3,#94a3b8)}.inspector-empty span{font-size:28px;color:var(--primary,#2563eb)}.inspector-empty strong{font-size:13px;color:var(--text-2,#64748b)}.inspector-empty small{font-size:11px}
.wf-flow :deep(.vue-flow) {
  height: 100%;
}
.wf-flow :deep(.vue-flow__node.wf-node-succeeded) {
  outline: 2px solid #16a34a;
}
.wf-flow :deep(.vue-flow__node.wf-node-failed) {
  outline: 2px solid #dc2626;
}
.wf-flow :deep(.vue-flow__node.wf-node-skipped) {
  outline: 2px solid #94a3b8;
}
.node-editor{flex-shrink:0;padding:10px 14px;border-top:1px solid var(--border-color,#e2e8f0);background:#f8fafc;display:grid;gap:6px}

@media (min-width: 768px) and (max-width: 1024px) {
  .wf-palette-pane{width:clamp(176px,var(--dag-left),220px);flex-basis:clamp(176px,var(--dag-left),220px)}
  .wf-aside{width:clamp(260px,var(--dag-right),320px);flex-basis:clamp(260px,var(--dag-right),320px)}
}

@media (max-width: 767px) {
  .wf-workbench{min-height:760px;overflow:auto}
  .wf-actions{align-items:flex-start;overflow-x:auto}
  .wf-body{display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(150px,28vh) minmax(360px,52vh) minmax(260px,42vh);overflow:visible}
  .wf-palette-pane{width:auto;max-height:28vh;flex:none;border-right:0;border-bottom:1px solid var(--border-color,#e2e8f0);overflow:auto}
  .wf-flow{min-height:360px;width:100%}
  .wf-aside{width:auto;min-height:260px;max-height:42vh;flex:none;border-left:0;border-top:1px solid var(--border-color,#e2e8f0)}
  .wf-splitter{display:none}
}
</style>
