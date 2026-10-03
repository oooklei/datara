<script setup lang="ts">
/**
 * 组件页面设计器 Task 13：页壳（三区域拼装 + 工具条 + 发布链）。
 *
 * 布局：顶栏（返回 + 名称 + 状态徽标 + 工具条，按钮置顶不滚动）+ 三区域
 * （左 PagePalette 232 可拖宽 140-520 / 中 PageCanvas flex + zoom 缩放壳 / 右 PageInspector 288 可拖宽）。
 * 面板拖宽与收放持久化同 GraphWorkbench（mousedown→window mousemove→mouseup 解绑，
 * localStorage datara.pd.panels）；画布尺寸持久化 datara.pd.canvas（canvasSize 事件落值 + 存档优先）。
 *
 * 状态：page（load 时 normalizePage）/ selectedIds 多选（主选中 = 首个）/ catalog（getResources）/
 * previewMap（preview 结果透传 PageCanvas）/ undo/redo 本地 JSON 快照栈（上限 50）。
 * 拖拽类高频事件（move/resize/canvasSize）合并撤销点（800ms 窗口），避免快照栈被单次拖拽挤爆。
 * 快捷键（GraphWorkbench 同款）：Ctrl/Cmd+Z 撤销、Ctrl+Y/Shift+Z 重做、Ctrl+C/V 复制粘贴、
 * Delete/Backspace 删除、Esc 退出预览；输入焦点（INPUT/TEXTAREA/SELECT/contentEditable）跳过。
 *
 * 发布链（§9 发布即刷新）：确认 → freeze 当前草稿 → publish 该 frozen 版本 →
 * 响应 data.refresh 存在则按 refreshed 出 toast；缺失（旧响应）兜底调 pageApi.refreshRefs。
 * 新建态（:type 缺省）：名称 + 4 页面模板卡 → createPageDraft（execution_model=page）→ replace 深链。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createPageDraft, freezeComponentVersion, getComponentDraft, listComponentVersions,
  publishComponentVersion, saveComponentDraft,
  type ComponentDraft, type ComponentVersionRow,
} from '../../../services/componentApi'
import { alignRects, distributeRects, normalizePage, genId, newWidget, reorderWidget, CANVAS_H, CANVAS_W, type BackgroundStyle, type PageDSL, type ReorderAction, type WidgetNode } from './designerModel'
import { pageTemplates } from './templates'
import type { ResourceCatalog } from './bindingCatalog'
import { pageApi, type PreviewQuery, type PreviewResult } from './pageApi'
import PagePalette from './palette/PagePalette.vue'
import PageCanvas from './canvas/PageCanvas.vue'
import PageInspector from './inspector/PageInspector.vue'

const route = useRoute()
const router = useRouter()

/* ================= 路由态与加载 ================= */
const typeParam = computed(() => (typeof route.params.type === 'string' && route.params.type ? route.params.type : ''))
const isCreate = computed(() => !typeParam.value)

const draft = ref<ComponentDraft | null>(null)
const versions = ref<ComponentVersionRow[]>([])
const page = ref<PageDSL>(normalizePage(null))
/** 多选集合（shift+点击累积）；主选中 = 首个（Inspector 与工具条 disabled 沿用单选语义，零改动） */
const selectedIds = ref<string[]>([])
const selectedId = computed<string | undefined>(() => selectedIds.value[0])
const EMPTY_CATALOG: ResourceCatalog = { datasources: [], workflows: [], globalParams: [], timeParams: [], components: [] }
const catalog = ref<ResourceCatalog>(EMPTY_CATALOG)
const previewMap = ref<Record<string, PreviewResult>>({})
const previewing = ref(false)
const zoom = ref(100)
const loading = ref(false)
const loadErr = ref('')
const saving = ref(false)
const publishing = ref(false)

const STATE_TEXT: Record<string, string> = { draft: '草稿', frozen: '冻结', published: '已发布', offline: '已下线' }
const stateText = computed(() => (draft.value ? STATE_TEXT[draft.value.state] ?? draft.value.state : ''))
const stateTagType = computed<'success' | 'warning' | 'info'>(() =>
  draft.value?.state === 'published' ? 'success' : draft.value?.state === 'offline' ? 'info' : 'warning')

function readCanvasStore(t: string): { w: number; h: number } | null {
  try {
    const s = JSON.parse(localStorage.getItem('datara.pd.canvas') ?? 'null') as { type?: string; w?: number; h?: number } | null
    if (s && s.type === t && typeof s.w === 'number' && typeof s.h === 'number') return { w: s.w, h: s.h }
  } catch { /* 忽略隐私模式 */ }
  return null
}

async function loadAll(t: string): Promise<void> {
  loading.value = true
  loadErr.value = ''
  try {
    const [d, v, res] = await Promise.all([getComponentDraft(t), listComponentVersions(t), pageApi.getResources()])
    draft.value = d
    versions.value = v.items
    const p = normalizePage(d.spec)
    const saved = readCanvasStore(t)
    if (saved) {
      // localStorage 旧持久化值可能落在旧口径（如高 2000），按 CANVAS_W/H 钳制后再赋值
      p.canvas.width = Math.min(CANVAS_W.max, Math.max(CANVAS_W.min, saved.w))
      p.canvas.height = Math.min(CANVAS_H.max, Math.max(CANVAS_H.min, saved.h))
    }
    page.value = p
    catalog.value = res
    selectedIds.value = []
    previewing.value = false
    previewMap.value = {}
    resetUndo()
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

watch(() => route.params.type, (t) => {
  const s = typeof t === 'string' ? t : ''
  if (s) void loadAll(s)
}, { immediate: true })

/* ================= undo/redo（本地 JSON 快照，上限 50） ================= */
const UNDO_LIMIT = 50
let undoStack: string[] = []
let redoStack: string[] = []
/** 快照栈为普通数组（内容不入响应式系统，避免深响应开销）；深度以 ref 供工具条禁用态 */
const undoDepth = ref(0)
const redoDepth = ref(0)
let lastDragPushAt = 0
const snapshot = (): string => JSON.stringify(page.value)
function resetUndo(): void {
  undoStack = [snapshot()]
  redoStack = []
  undoDepth.value = 0
  redoDepth.value = 0
}
function pushUndo(): void {
  undoStack.push(snapshot())
  if (undoStack.length > UNDO_LIMIT) undoStack.shift()
  redoStack = []
  undoDepth.value = undoStack.length - 1
  redoDepth.value = 0
}
/** 拖拽类高频事件（move/resize/canvasSize）合并撤销点：窗口内只记一次，避免单次拖拽挤爆快照栈 */
function pushUndoThrottled(): void {
  const now = Date.now()
  if (now - lastDragPushAt > 800) {
    pushUndo()
    lastDragPushAt = now
  }
}
function restore(s: string): void {
  try {
    page.value = JSON.parse(s) as PageDSL
  } catch { return }
  if (selectedId.value && !page.value.widgets.some((w) => w.id === selectedId.value)) selectedIds.value = []
}
function undo(): void {
  if (undoStack.length <= 1) return
  redoStack.push(undoStack.pop()!)
  restore(undoStack[undoStack.length - 1])
  undoDepth.value = undoStack.length - 1
  redoDepth.value = redoStack.length
}
function redo(): void {
  const s = redoStack.pop()
  if (!s) return
  undoStack.push(s)
  restore(s)
  undoDepth.value = undoStack.length - 1
  redoDepth.value = redoStack.length
}

/* ================= 画布事件（add/select/move/resize/canvasSize） ================= */
function onAdd(kind: string, x: number, y: number): void {
  pushUndo()
  const w = newWidget(kind, { x, y })
  page.value.widgets.push(w)
  selectedIds.value = [w.id]
}
/** 选中：additive（shift+点击）且未含 → 追加多选；否则重置单选 */
function onSelect(id: string, additive?: boolean): void {
  if (additive && !selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id]
  else selectedIds.value = [id]
}
/** 拖移：多选集内成员拖动时全体同步位移（同一撤销点）；否则单动 */
function onMove(id: string, dx: number, dy: number): void {
  const ids = selectedIds.value.includes(id) ? selectedIds.value : [id]
  const ws = ids
    .map((tid) => page.value.widgets.find((x) => x.id === tid))
    .filter((x): x is WidgetNode => !!x)
  if (ws.length === 0) return
  pushUndoThrottled()
  ws.forEach((w) => {
    w.rect.x += dx
    w.rect.y += dy
  })
}
function onResize(id: string, dw: number, dh: number): void {
  const w = page.value.widgets.find((x) => x.id === id)
  if (!w) return
  pushUndoThrottled()
  w.rect.w = Math.max(1, w.rect.w + dw)
  w.rect.h = Math.max(1, w.rect.h + dh)
}
function onCanvasSize(w: number, h: number): void {
  pushUndoThrottled()
  page.value.canvas.width = w
  page.value.canvas.height = h
  try { localStorage.setItem('datara.pd.canvas', JSON.stringify({ type: typeParam.value, w, h })) } catch { /* 忽略隐私模式 */ }
}

/* ================= Inspector 受控 patch ================= */
function onUpdateWidget(id: string, patch: Record<string, unknown>): void {
  const w = page.value.widgets.find((x) => x.id === id)
  if (!w) return
  pushUndo()
  Object.assign(w, patch)
}
/** 层级调整（D5/M6）：数组序 = z 序，靠后者在上层渲染（重排为纯函数，替换 widgets 数组） */
function onReorder(id: string, action: ReorderAction): void {
  pushUndo()
  page.value.widgets = reorderWidget(page.value.widgets, id, action)
}
function onUpdateCanvas(patch: Record<string, unknown>): void {
  pushUndo()
  if (typeof patch.width === 'number') page.value.canvas.width = patch.width
  if (typeof patch.height === 'number') page.value.canvas.height = patch.height
  if (patch.background && typeof patch.background === 'object') {
    page.value.canvas.background = { ...page.value.canvas.background, ...(patch.background as Partial<BackgroundStyle>) }
  }
}

/* ================= 工具条：复制 / 粘贴 / 删除 / 对齐 / 缩放 / 刷新 ================= */
const selWidget = (): WidgetNode | null => page.value.widgets.find((w) => w.id === selectedId.value) ?? null

/** 内部复制缓冲（复制时快照入缓冲，后续编辑不影响粘贴源；空缓冲粘贴禁用） */
const copyBuf = ref<WidgetNode | null>(null)
/** 深拷贝 + id 重生成（children 递归）+ 12px 偏移入画布（复制/粘贴共用） */
function pushClone(src: WidgetNode): void {
  pushUndo()
  const clone = JSON.parse(JSON.stringify(src)) as WidgetNode
  const reid = (n: WidgetNode): WidgetNode => ({ ...n, id: genId(n.kind), ...(n.children ? { children: n.children.map(reid) } : {}) })
  const c = reid(clone)
  c.rect = { ...c.rect, x: c.rect.x + 12, y: c.rect.y + 12 }
  page.value.widgets.push(c)
  selectedIds.value = [c.id]
}
function onCopy(): void {
  const w = selWidget()
  if (!w) return
  copyBuf.value = JSON.parse(JSON.stringify(w)) as WidgetNode
  pushClone(copyBuf.value)
}
function onPaste(): void {
  if (copyBuf.value) pushClone(copyBuf.value)
}
function onDelete(): void {
  const w = selWidget()
  if (!w) return
  pushUndo()
  page.value.widgets = page.value.widgets.filter((x) => x.id !== w.id)
  selectedIds.value = []
}
/** 对齐：多选（≥2）取最小坐标对齐；单选保持吸附 8 原语义 */
function onAlignLeft(): void {
  if (selectedIds.value.length >= 2) {
    pushUndo()
    page.value.widgets = alignRects(page.value.widgets, selectedIds.value, 'x')
    return
  }
  const w = selWidget()
  if (!w) return
  pushUndo()
  w.rect.x = 8
}
function onAlignTop(): void {
  if (selectedIds.value.length >= 2) {
    pushUndo()
    page.value.widgets = alignRects(page.value.widgets, selectedIds.value, 'y')
    return
  }
  const w = selWidget()
  if (!w) return
  pushUndo()
  w.rect.y = 8
}
/** 等距分布（≥3）：按轴升序首尾不动中间均匀（distributeRects 纯函数，替换 widgets 数组） */
function onDistribute(axis: 'x' | 'y'): void {
  if (selectedIds.value.length < 3) return
  pushUndo()
  page.value.widgets = distributeRects(page.value.widgets, selectedIds.value, axis)
}
const ZOOMS = [50, 75, 100, 125]
function onZoom(v: string | number | object): void {
  const n = Number(v)
  if (ZOOMS.includes(n)) zoom.value = n
}
const zoomStyle = computed<Record<string, string>>(() => ({
  transform: `scale(${zoom.value / 100})`,
  transformOrigin: 'top center',
}))

async function onRefresh(): Promise<void> {
  const t = typeParam.value
  if (t) await loadAll(t)
}

/* ================= 保存 / 预览 ================= */
async function onSave(): Promise<void> {
  const d = draft.value
  if (!d || saving.value) return
  saving.value = true
  try {
    const r = await saveComponentDraft(d.type, { draftRev: d.draftRev, spec: { page: page.value } })
    d.draftRev = r.draftRev
    ElMessage.success(`已保存（rev ${r.draftRev}）`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    saving.value = false
  }
}

async function onPreview(): Promise<void> {
  if (previewing.value) {
    previewing.value = false
    return
  }
  // 收集 query 绑定（bindings 中 kind='query' 项 → {id, datasourceId, sql}，children 递归）；
  // 仅 datasourceId 无 SQL 的数据源引用型绑定跳过（预览渲染模板样例数据）
  const queries: PreviewQuery[] = []
  const walk = (ws: WidgetNode[]): void => ws.forEach((w) => {
    Object.values(w.bindings ?? {}).forEach((b) => {
      if (b && b.kind === 'query' && b.datasourceId != null && b.query) {
        queries.push({
          id: w.id,
          datasourceId: b.datasourceId,
          sql: b.query ?? '',
          db: catalog.value.datasources.find((d) => d.id === b.datasourceId)?.db,
        })
      }
    })
    walk(w.children ?? [])
  })
  walk(page.value.widgets)
  if (queries.length === 0) {
    ElMessage.info('无查询绑定，仅样例预览')
    previewMap.value = {}
  } else {
    try {
      const r = await pageApi.preview(queries)
      previewMap.value = r.results
      // 失败组件汇总提示（首条 error 摘要 + 数量；不中断预览态，逐组件错误态仍由画布渲染）
      if (r.widgetErrors?.length) {
        ElMessage.warning(`${r.widgetErrors.length} 个组件预览失败：${r.widgetErrors[0].error}`)
      }
    } catch (e) {
      ElMessage.error(`预览失败：${e instanceof Error ? e.message : String(e)}`)
      return
    }
  }
  previewing.value = true
}

/* ================= 发布链（§9 发布即刷新） ================= */
async function onPublish(): Promise<void> {
  const d = draft.value
  if (!d || publishing.value) return
  try {
    await ElMessageBox.confirm(
      '发布以服务器已保存草稿为准（建议先保存），冻结为不可变版本并跑发布闸门，成功后自动刷新引用该组件的图。确认发布？',
      '发布页面组件',
      { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' },
    )
  } catch { return }
  publishing.value = true
  try {
    const fr = await freezeComponentVersion(d.type)
    const pub = await publishComponentVersion(d.type, { version: fr.frozenVersion, draftRev: fr.draftRev })
    let tail: string
    if (pub.refresh) {
      tail = pub.refresh.refreshed > 0 ? `已刷新 ${pub.refresh.refreshed} 个图引用` : '无引用需要刷新'
    } else {
      // 旧响应无 data.refresh → 兜底手动刷新引用（幂等）
      const r = await pageApi.refreshRefs(d.type)
      tail = r.refreshed > 0 ? `已刷新 ${r.refreshed} 个图引用` : '无引用需要刷新'
    }
    ElMessage.success(`已发布 v${pub.publishedVersion}，${tail}`)
    await loadAll(d.type)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    publishing.value = false
  }
}

/* ================= 面板拖宽 / 收放（GraphWorkbench 同款 + datara.pd.panels） ================= */
const leftOpen = ref(true)
const rightOpen = ref(true)
const leftWidth = ref(232)
const rightWidth = ref(288)
const PANEL_MIN_W = 140
const PANEL_MAX_W = 520
let resizeSide: 'left' | 'right' | null = null
let resizeStartX = 0
let resizeStartW = 0
function startPanelResize(side: 'left' | 'right', e: MouseEvent): void {
  resizeSide = side
  resizeStartX = e.clientX
  resizeStartW = side === 'left' ? leftWidth.value : rightWidth.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('mousemove', onPanelResizeMove)
  window.addEventListener('mouseup', stopPanelResize)
  e.preventDefault()
}
function onPanelResizeMove(e: MouseEvent): void {
  if (!resizeSide) return
  const dx = e.clientX - resizeStartX
  const w = Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, resizeStartW + (resizeSide === 'left' ? dx : -dx)))
  if (resizeSide === 'left') leftWidth.value = w
  else rightWidth.value = w
}
function stopPanelResize(): void {
  resizeSide = null
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('mousemove', onPanelResizeMove)
  window.removeEventListener('mouseup', stopPanelResize)
}

/* ================= 快捷键（GraphWorkbench 同款规格） ================= */
/** 输入焦点跳过（同 GraphWorkbench isTypingTarget） */
function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null
  if (!el) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable
}
/** 键位：Ctrl/Cmd+Z 撤销 / Ctrl+Y 或 Ctrl+Shift+Z 重做 / Ctrl+C 复制 / Ctrl+V 粘贴 / Delete 或 Backspace 删除 / Esc 退出预览 */
function onKeydown(e: KeyboardEvent): void {
  if (isCreate.value || loading.value) return
  if (isTypingTarget(e.target)) return
  const k = e.key.toLowerCase()
  const mod = e.ctrlKey || e.metaKey
  if (mod && k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return }
  if (mod && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); redo(); return }
  if (mod && k === 'c') { e.preventDefault(); onCopy(); return }
  if (mod && k === 'v') { e.preventDefault(); onPaste(); return }
  if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); onDelete(); return }
  if (e.key === 'Escape' && previewing.value) { e.preventDefault(); previewing.value = false }
}
onMounted(() => {
  try {
    const p = JSON.parse(localStorage.getItem('datara.pd.panels') ?? '{}') as { left?: boolean; right?: boolean; leftW?: number; rightW?: number }
    if (typeof p.left === 'boolean') leftOpen.value = p.left
    if (typeof p.right === 'boolean') rightOpen.value = p.right
    if (typeof p.leftW === 'number' && p.leftW >= PANEL_MIN_W && p.leftW <= PANEL_MAX_W) leftWidth.value = p.leftW
    if (typeof p.rightW === 'number' && p.rightW >= PANEL_MIN_W && p.rightW <= PANEL_MAX_W) rightWidth.value = p.rightW
  } catch { /* 忽略隐私模式 */ }
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  stopPanelResize()
  window.removeEventListener('keydown', onKeydown)
})
watch([leftOpen, rightOpen, leftWidth, rightWidth], ([l, r, lw, rw]) => {
  try { localStorage.setItem('datara.pd.panels', JSON.stringify({ left: l, right: r, leftW: lw, rightW: rw })) } catch { /* 忽略隐私模式 */ }
})

/* ================= 新建态（:type 缺省） ================= */
const newName = ref('')
const newTpl = ref(0)
const creating = ref(false)
/** 模板卡元数据（加载时算一次 widget 数，避免每次渲染调用 page() 工厂创建对象） */
const tplCards = pageTemplates.map((t) => ({ name: t.name, count: t.page().widgets.length }))
/** 中文名 slug 化后可能为空 → 兜底 'ui'；唯一性由时间戳段保证（后端 type 正则 [a-z][a-z0-9_]{1,63}） */
function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)
}
async function onCreate(): Promise<void> {
  const name = newName.value.trim()
  if (!name) {
    ElMessage.warning('请输入页面名称')
    return
  }
  const tpl = pageTemplates[newTpl.value]?.page() ?? pageTemplates[0].page()
  tpl.name = name
  const type = `page_${slugify(name) || 'ui'}_${Date.now().toString(36)}`
  creating.value = true
  try {
    await createPageDraft({ type, name, page: tpl })
    ElMessage.success('页面草稿已创建')
    void router.replace(`/meta/components/page-designer/${type}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="pd-view">
    <header class="pd-head">
      <div class="pd-head-l">
        <el-button size="small" @click="router.push('/meta/components')">← 目录</el-button>
        <h2>{{ isCreate ? '新建页面组件' : (draft ? draft.name : typeParam) }}</h2>
        <el-tag v-if="draft" size="small" :type="stateTagType">{{ stateText }}</el-tag>
        <span v-if="draft?.publishedVersion" class="pd-pubv">v{{ draft.publishedVersion }}</span>
      </div>
      <!-- 工具条（按钮置顶）：撤销 重做 | 复制 粘贴 删除 | 左对齐 上对齐 横分布 纵分布 | 缩放 | 刷新 | 保存 预览 发布 -->
      <div v-if="!isCreate" class="pd-toolbar">
        <el-button size="small" data-testid="tb-undo" title="撤销 Ctrl+Z" :disabled="undoDepth <= 0" @click="undo">撤销</el-button>
        <el-button size="small" data-testid="tb-redo" title="重做 Ctrl+Y" :disabled="redoDepth <= 0" @click="redo">重做</el-button>
        <span class="pd-sep" />
        <el-button size="small" data-testid="tb-copy" title="复制 Ctrl+C" :disabled="!selectedId" @click="onCopy">复制</el-button>
        <el-button size="small" data-testid="tb-paste" title="粘贴 Ctrl+V" :disabled="!copyBuf" @click="onPaste">粘贴</el-button>
        <el-button size="small" data-testid="tb-delete" title="删除 Delete" :disabled="!selectedId" @click="onDelete">删除</el-button>
        <span class="pd-sep" />
        <el-button size="small" data-testid="tb-align-left" :disabled="!selectedId" @click="onAlignLeft">左对齐</el-button>
        <el-button size="small" data-testid="tb-align-top" :disabled="!selectedId" @click="onAlignTop">上对齐</el-button>
        <el-button size="small" data-testid="tb-dist-h" title="横向等距分布（选中 ≥3）" :disabled="selectedIds.length < 3" @click="onDistribute('x')">横分布</el-button>
        <el-button size="small" data-testid="tb-dist-v" title="纵向等距分布（选中 ≥3）" :disabled="selectedIds.length < 3" @click="onDistribute('y')">纵分布</el-button>
        <span class="pd-sep" />
        <el-dropdown data-testid="tb-zoom" trigger="click" @command="onZoom">
          <el-button size="small">缩放 {{ zoom }}% ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="z in ZOOMS" :key="z" :command="z" :class="{ 'is-cur': z === zoom }">{{ z }}%</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="pd-sep" />
        <el-button size="small" data-testid="tb-refresh" :loading="loading" @click="onRefresh">刷新</el-button>
        <span class="pd-sep" />
        <el-button size="small" type="primary" plain data-testid="tb-save" :loading="saving" :disabled="!draft" @click="onSave">保存</el-button>
        <el-button size="small" :type="previewing ? 'success' : 'default'" data-testid="tb-preview" @click="onPreview">
          {{ previewing ? '退出预览' : '预览' }}
        </el-button>
        <el-button size="small" type="primary" data-testid="tb-publish" :loading="publishing" :disabled="!draft" @click="onPublish">发布</el-button>
      </div>
    </header>

    <el-alert v-if="loadErr" type="error" :closable="false" :title="`页面草稿加载失败：${loadErr}`" show-icon class="pd-err" />

    <!-- 新建态：名称 + 4 页面模板卡 + 创建 -->
    <section v-if="isCreate" class="pd-create">
      <div class="pd-create-title">新建页面组件</div>
      <div class="pd-create-row">
        <label class="pd-create-label">页面名称</label>
        <el-input v-model="newName" placeholder="如 销售看板（type 将自动生成 page_* 标识）" class="pd-create-name" />
      </div>
      <div class="pd-create-label" style="margin-top: 14px">页面模板</div>
      <div class="pd-tpl-grid">
        <button
          v-for="(t, i) in tplCards" :key="t.name" type="button" class="pd-tpl-card"
          :class="{ 'is-cur': newTpl === i }" @click="newTpl = i"
        >
          <span class="pd-tpl-name">{{ t.name }}</span>
          <span class="pd-tpl-sub">{{ t.count }} 个组件</span>
        </button>
      </div>
      <el-button type="primary" :loading="creating" class="pd-create-btn" @click="onCreate">创建</el-button>
    </section>

    <!-- 编辑态三区域 -->
    <div v-else class="pd-body" v-loading="loading">
      <aside v-show="leftOpen" class="pd-left" :style="{ width: `${leftWidth}px` }" data-testid="pd-palette">
        <PagePalette />
      </aside>
      <div
        class="pd-grip" title="拖拽调宽，双击收放" @mousedown="startPanelResize('left', $event)"
        @dblclick="leftOpen = !leftOpen"
      />
      <main class="pd-mid">
        <div class="pd-zoom" :style="zoomStyle" data-testid="pd-canvas-stage">
          <PageCanvas
            :page="page" :selected-id="selectedId" :selected-ids="selectedIds" :preview="previewing ? previewMap : undefined"
            @add="onAdd" @select="onSelect" @move="onMove" @resize="onResize" @canvas-size="onCanvasSize"
          />
        </div>
      </main>
      <div
        class="pd-grip" title="拖拽调宽，双击收放" @mousedown="startPanelResize('right', $event)"
        @dblclick="rightOpen = !rightOpen"
      />
      <aside v-show="rightOpen" class="pd-right" :style="{ width: `${rightWidth}px` }" data-testid="pd-inspector">
        <PageInspector
          :page="page" :selected-id="selectedId" :catalog="catalog"
          @update-widget="onUpdateWidget" @update-canvas="onUpdateCanvas" @reorder="onReorder"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
.pd-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0;
}
.pd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 14px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.pd-head-l {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.pd-head h2 {
  margin: 0;
  font-size: 16px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pd-pubv {
  font-size: 11px;
  color: var(--success);
  background: var(--success-bg);
  border-radius: var(--radius-sm);
  padding: 0 5px;
}
.pd-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.pd-sep {
  width: 1px;
  height: 16px;
  background: var(--border);
  margin: 0 2px;
}
.pd-toolbar :deep(.el-button + .el-button) {
  margin-left: 0;
}
.pd-err {
  margin: 8px 14px 0;
}

/* 三区域 */
.pd-body {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: stretch;
}
.pd-left,
.pd-right {
  flex: none;
  min-height: 0;
  overflow: hidden;
}
.pd-mid {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}
.pd-grip {
  flex: none;
  width: 5px;
  cursor: col-resize;
  background: transparent;
  transition: background var(--dur-fast) var(--ease);
}
.pd-grip:hover {
  background: var(--primary-light);
}
.pd-zoom {
  padding: 24px;
}

/* 新建态 */
.pd-create {
  flex: 1;
  overflow: auto;
  padding: 24px;
  max-width: 720px;
}
.pd-create-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 14px;
}
.pd-create-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pd-create-label {
  flex: none;
  width: 72px;
  font-size: 13px;
  color: var(--text-2);
}
.pd-create-name {
  max-width: 420px;
}
.pd-tpl-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 8px;
}
.pd-tpl-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px 8px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
}
.pd-tpl-card:hover {
  border-color: var(--primary);
}
.pd-tpl-card.is-cur {
  border-color: var(--primary);
  box-shadow: var(--shadow-primary);
}
.pd-tpl-name {
  font-size: 13px;
  color: var(--text);
}
.pd-tpl-sub {
  font-size: 11px;
  color: var(--text-3);
}
.pd-create-btn {
  margin-top: 18px;
}
</style>
