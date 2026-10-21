<script setup lang="ts">
/**
 * Palette 双 Tab（INC4-FE-3，4.2c）：组件库 / 工作流。
 *
 * 蓝本 datara-web/src/graph/workbench/Palette.vue 双 Tab 框架照抄（§5A.1）：
 * PalTab（组件/工作流）/.pal-tabs/.pal-tab.on、搜索框、分组折叠（folded/arrow▼）、
 * 拖拽 setData('datara/node-type') + effectAllowed=copy、.p-ico/.p-name/.p-code、
 * 空态「无匹配组件」。
 *
 * §5A.3 组件规格一源零私设：组件库数据 = loadComponentSpecs()
 * （/api/v1/rebuild/components/spec；ETag/304/last-success 回落、首载 fail-closed
 * 均在 API 层）。paletteVisible===false 项按 normalizeSpec 契约过滤
 * （D1 闸门 §13-5：executionModel=runtime-only 显式 false），非本组件私设。
 *
 * 缺位降级（接驳点逐处注释声明）：
 *  - ViewProfile/resolveSchema/activeTags 通道归 INC4-FE-6/7 画布内核：
 *    分组改由 spec description.category 派生（键 = 全路径，组名 = 末段，
 *    空类别归「通用」）；无 disabled/phase 灰置与行级分类徽标（p-cat）通道；
 *
 * 工作流目录树（INC4-FE-4，4.2d，蓝本 L74-258 逻辑、L307-388 模板、L392-429 样式
 * 照抄 + §5A.2 三分类收窄）：目录树、勾选载入、删除、移动、新建分类全量在位。
 *  - 数据源 = listWorkflowDefinitions(projectId)（真端点 /rebuild/workflows；
 *    wire 缺 code、tags 字段容错 tags??[]、code undefined——候裁披露）；
 *  - projectId prop 缺位（/dag 过渡路由无项目上下文）→ 空态降级
 *    「候选池待项目上下文接驳」；宿主传入即活（行操作门控同源 hasProject）；
 *  - categories 系（新建分类、移动分类 setWfTags）新后端端点缺位 → RED 哨兵
 *    WF_CATEGORIES_NOT_WIRED（workflowCategories notWired）：UI 照抄在位，
 *    调用时 catch 哨兵给提示，后端补端点即活；
 *  - 蓝本 bus 事件 wf-definitions-changed 不引（新前端无 eventBus 基建，
 *    行操作后 buildPool 直调重拉等价）；
 *  - load-tasks 事件契约在位（DagPickItem[] 同名同载荷；wire id number
 *    → DagPickItem.id string 桥接 String(id)）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { loadComponentSpecs, type ComponentSpecItem } from '../services/rebuild/componentSpecApi'
import {
  deleteWorkflowDefinition,
  listWorkflowDefinitions,
  WF_CATEGORIES_NOT_WIRED,
  workflowCategories,
} from '../services/rebuild/workflowApi'
import type { DagPickItem } from '../stores/dagTabs'

const props = defineProps<{ defaultTab?: 'palette' | 'wf'; projectId?: number }>()
const emit = defineEmits<{ 'load-tasks': [{ items: DagPickItem[] }] }>()

interface PalRow { type: string; label: string; desc: string; icon: string; color: string; code: string; cat: string }

const kw = ref('')
const folded = ref<Record<string, boolean>>({})
const rows = ref<PalRow[]>([])
const loaded = ref(false)

/* ---------- 顶部 Tab：组件库 + 工作流（蓝本照抄） ---------- */
type PalTab = 'palette' | 'wf'
/** 宿主可指定初始 Tab；任务中心空态默认「工作流」目录，GraphWorkbench 常规不传保持「组件」 */
const tab = ref<PalTab>(props.defaultTab ?? 'palette')
const tabs: { k: PalTab; label: string }[] = [
  { k: 'palette', label: '组件' },
  { k: 'wf', label: '工作流' },
]

/* ---------- 组件库行：spec → PalRow（§5A.3 零私设映射） ---------- */
/** identity.code 字符串探测（旧 NodeSchema.code 通道；spec badge 是 {key,colorMap}
 *  状态徽标对象非 code 字符串，不直出） */
function codeOf(identity: Record<string, unknown>): string {
  return typeof identity.code === 'string' ? identity.code : ''
}

function rowOf(it: ComponentSpecItem): PalRow | null {
  const identity = it.identity ?? {}
  const description = it.description ?? {}
  const visual = it.visual ?? {}
  // normalizeSpec 契约（D1 闸门 §13-5）：runtime-only 组件显式 paletteVisible=false → 调色板过滤
  if (visual.paletteVisible === false) return null
  return {
    type: it.type,
    label: String(identity.displayName ?? it.type),
    desc: String(description.summary ?? ''),
    icon: String(visual.icon ?? ''),
    color: String(visual.color ?? ''),
    code: codeOf(identity),
    cat: String(description.category ?? ''),
  }
}

/** 规格目录加载：失败 console.warn + 空态（last-success 回落在 API 层；首载
 *  fail-closed 不阻断宿主渲染） */
onMounted(async () => {
  buildPool() // 工作流候选池初始拉取（无 projectId 置空池降级；蓝本 onMounted 调 buildPool 同构）
  try {
    const snap = await loadComponentSpecs()
    rows.value = snap.items.map(rowOf).filter((r): r is PalRow => r !== null)
  } catch (e) {
    console.warn('[Palette] component specs load failed:', e)
  } finally {
    loaded.value = true
  }
})

/* ---------- 分组（蓝本 cats 结构：kw 过滤 + 折叠 + 计数） ---------- */
const GENERIC_LABEL = '通用'

/** spec description.category 为分组路径（如「批处理与同步/数据源」）：
 *  键 = 全路径，组名 = 末段；空类别归「通用」。无 ViewProfile.palette
 *  分组通道（INC4-FE-6/7 接驳），一级平铺沿用蓝本单层目录结构 */
const groups = computed(() => {
  const k = kw.value.trim().toLowerCase()
  const match = (r: PalRow) =>
    !k ||
    r.label.toLowerCase().includes(k) ||
    r.desc.toLowerCase().includes(k) ||
    r.type.toLowerCase().includes(k)
  const map = new Map<string, { key: string; label: string; rows: PalRow[] }>()
  for (const r of rows.value) {
    if (!match(r)) continue
    const key = r.cat || GENERIC_LABEL
    let g = map.get(key)
    if (!g) {
      const segs = key.split('/')
      g = { key, label: segs[segs.length - 1] || key, rows: [] }
      map.set(key, g)
    }
    g.rows.push(r)
  }
  return [...map.values()]
})

function onDragStart(e: DragEvent, row: PalRow) {
  e.dataTransfer?.setData('datara/node-type', row.type)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

/* ---------- 工作流目录树（INC4-FE-4，蓝本 L74-258 照抄 + §5A.2 三分类收窄） ---------- */
interface DefRow { id: number; name: string; tags: string[]; code?: number }
interface CatRow { name: string; builtin: boolean }

/** 三分类收窄（§5A.2）：同步、流（蓝本 BUILTIN_LABELS 含 ETL——存量 ETL 降级映射 wf
 *  已候裁上呈，本票不引 ETL 通道；数据侧 tags 仅含 ETL 时落根目录） */
const BUILTIN_LABELS = ['同步', '流']
/** 根目录名（无标签普通工作流平铺） */
const ROOT_LABEL = '根目录'

const defPool = ref<DefRow[]>([])
/** 后端分类目录（builtin=false 为自定义；categories RED 期恒 []，端点接驳即活） */
const catsAll = ref<CatRow[]>([])
/** 行操作门控（蓝本 !isMock 等价）：projectId 有值 = 真项目上下文 */
const hasProject = computed(() => props.projectId !== undefined)

/** 某任务的分类目录：内置标签优先，其次自定义目录名，兜底根目录 */
function categoryOf(d: DefRow): string {
  const t = d.tags ?? []
  if (t.includes('同步')) return '同步'
  if (t.includes('流')) return '流'
  const custom = catsAll.value.find((c) => !c.builtin && t.includes(c.name))
  return custom?.name ?? ROOT_LABEL
}

/** 分类目录展示顺序（不含根）：同步 → 流 → 自定义（listCategories 顺序，RED 期仅内置） */
const groupOrder = computed<string[]>(() => [
  ...BUILTIN_LABELS,
  ...catsAll.value.filter((c) => !c.builtin).map((c) => c.name),
])

/** 目录树折叠态：默认收起（蓝本 fold: !wfFolded[name] 反转语义照抄；根目录固定展开） */
const wfFolded = ref<Record<string, boolean>>({})
function toggleWfDir(name: string) {
  const s = { ...wfFolded.value }
  s[name] = !s[name]
  wfFolded.value = s
}

/** 目录树：root = 无标签普通工作流平铺，dirs = 分类目录（含 kw 过滤 + groupOrder 序） */
const wfTree = computed(() => {
  const k = kw.value.trim().toLowerCase()
  const rowList = defPool.value.filter((d) => !k || d.name.toLowerCase().includes(k))
  const root: DefRow[] = []
  const map = new Map<string, DefRow[]>()
  for (const d of rowList) {
    const g = categoryOf(d)
    if (g === ROOT_LABEL) { root.push(d); continue }
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(d)
  }
  const dirs = groupOrder.value.filter((g) => map.has(g)).map((g) => ({ name: g, rows: map.get(g)! }))
  return { root, dirs }
})

/** 移动下拉选项：分类目录 + 根目录（移回根 = 清除 tags） */
const moveOptions = computed<string[]>(() => [...groupOrder.value, ROOT_LABEL])

/** 任务类型推导（三分类收窄：sync、stream，兜底 wf；无 seed 体系不设 seedTypeOf） */
function typeOf(d: DefRow): DagPickItem['type'] {
  const t = d.tags ?? []
  if (t.includes('同步')) return 'sync'
  if (t.includes('流')) return 'stream'
  return 'wf'
}

/** 候选池构建（蓝本 buildPool 去 mock 分支）：无 projectId = 过渡态空池；
 *  categories RED——loadCats 内部 catch 哨兵，内置目录照常渲染 */
function buildPool() {
  if (!hasProject.value) {
    defPool.value = []
    catsAll.value = []
    return
  }
  void loadDefPool()
  void loadCats()
}

/** projectId 变化（项目路由切换复用实例）重拉候选池 */
watch(() => props.projectId, () => buildPool())

async function loadDefPool() {
  try {
    defPool.value = await listWorkflowDefinitions(props.projectId as number)
  } catch { /* 后端未就绪时留空 */ }
}

async function loadCats() {
  try {
    catsAll.value = await workflowCategories.listCategories()
  } catch { /* 分类端点未接驳（RED 哨兵）或失败不阻断 */ }
}

/* ---------- 行操作（蓝本照抄；categories 系 catch RED 哨兵降级提示） ---------- */
function isCategoriesNotWired(e: unknown): boolean {
  return e instanceof Error && e.message === WF_CATEGORIES_NOT_WIRED
}

async function deleteRow(d: DefRow) {
  try {
    await ElMessageBox.confirm(`删除任务「${d.name}」及其画布？该操作不可恢复。`, '删除任务', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  try {
    await deleteWorkflowDefinition(props.projectId as number, d.id)
    ElMessage.success(`已删除「${d.name}」`)
    buildPool()
  } catch { ElMessage.error('删除失败') }
}

/** 移动分类 = setWfTags 整体替换 tags 为 [目标目录名]（根目录传空数组 = 普通工作流） */
async function moveTo(d: DefRow, cat: string) {
  if (cat === categoryOf(d)) return
  try {
    await workflowCategories.setWfTags(d.id, cat === ROOT_LABEL ? [] : [cat])
    ElMessage.success(`已移动「${d.name}」到「${cat}」`)
    buildPool()
  } catch (e) {
    ElMessage.error(isCategoriesNotWired(e) ? '分类系端点未接驳（候裁中），移动暂不可用' : '移动分类失败')
  }
}

async function newCategory() {
  let name = ''
  try {
    const r = await ElMessageBox.prompt('输入新分类目录名称（将显示在工作流列表分组中）', '新建分类', {
      confirmButtonText: '创建', cancelButtonText: '取消', inputPlaceholder: '目录名称',
      inputValidator: (v: string) => (v.trim() ? true : '目录名称不能为空'),
    })
    name = r.value.trim()
  } catch { return }
  if (BUILTIN_LABELS.includes(name) || name === ROOT_LABEL) {
    ElMessage.warning(`「${name}」为内置、根目录，无需新建`)
    return
  }
  try {
    await workflowCategories.createCategory(name)
    ElMessage.success(`已创建分类「${name}」`)
    void loadCats()
  } catch (e) {
    ElMessage.error(isCategoriesNotWired(e) ? '分类系端点未接驳（候裁中），新建暂不可用' : '创建分类失败')
  }
}

/* ---------- 勾选多选（载入后清空，跨分组保留） ---------- */
const picked = ref<Set<number>>(new Set())
function togglePick(id: number) {
  const s = new Set(picked.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  picked.value = s
}

/** 目录、根目录一键全选（再次点击取消全选） */
function toggleAll(ids: number[]) {
  const s = new Set(picked.value)
  const allPicked = ids.length > 0 && ids.every((id) => s.has(id))
  for (const id of ids) {
    if (allPicked) s.delete(id)
    else s.add(id)
  }
  picked.value = s
}

/** 载入选中 → 宿主 openTab（wire id number → DagPickItem.id string 桥接） */
function onLoad() {
  if (!picked.value.size || tab.value === 'palette') return
  const items: DagPickItem[] = [...picked.value].map((id) => {
    const d = defPool.value.find((x) => x.id === id)
    return {
      id: String(id),
      name: d?.name ?? String(id),
      type: d ? typeOf(d) : 'wf',
      code: d?.code,
    }
  })
  emit('load-tasks', { items })
  picked.value = new Set()
}
</script>

<template>
  <aside class="wb-palette" data-palette>
    <div class="pal-tabs">
      <button
        v-for="t in tabs" :key="t.k"
        class="pal-tab" :class="{ on: tab === t.k }"
        @click="tab = t.k"
      >{{ t.label }}</button>
    </div>

    <!-- 组件库：拖拽（数据一源 loadComponentSpecs，§5A.3 零私设） -->
    <template v-if="tab === 'palette'">
      <div class="pal-search">
        <input v-model="kw" placeholder="搜索组件" style="width:100%;border:1px solid var(--border-color,#d3d9e3);border-radius:var(--radius-sm,6px);padding:6px 9px;font-size:12.5px;outline:none" />
      </div>
      <div class="pal-list">
        <div v-for="g in groups" :key="g.key" class="pal-cat" :class="{ fold: folded[g.key] }">
          <div class="pal-cat-head" @click="folded[g.key] = !folded[g.key]">
            <span class="arrow">▼</span>{{ g.label }}
            <span class="cnt">{{ g.rows.length }}</span>
          </div>
          <div class="pal-items">
            <div
              v-for="row in g.rows" :key="row.type"
              class="pal-item"
              :title="row.desc"
              :draggable="true"
              @dragstart="onDragStart($event, row)"
            >
              <div class="p-ico" :style="{ background: row.color }">{{ row.icon }}</div>
              <div style="min-width:0">
                <div class="p-name">
                  {{ row.label }}
                  <span v-if="row.code" class="p-code">{{ row.code }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- 空态（蓝本原文「无匹配组件」；规格未加载完成前不闪空态） -->
        <div v-if="loaded && groups.length === 0" style="padding:20px;text-align:center;color:var(--text-3,#94a3b8);font-size:12px">无匹配组件</div>
      </div>
    </template>

    <!-- 工作流目录树：根目录（普通工作流平铺）+ 分类目录（同步/流/自定义，默认收起），行可删除/移动，顶部可新建分类（蓝本 L307-388 照抄；!isMock → hasProject；空态加项目上下文分支） -->
    <template v-else>
      <div class="pal-bar">
        <button class="pal-mini" @click="newCategory">＋ 新建分类</button>
        <span class="pal-hint">已选 <b>{{ picked.size }}</b></span>
        <button class="pal-load" :disabled="picked.size === 0" @click="onLoad">
          载入选中 ({{ picked.size }})
        </button>
      </div>
      <div class="pal-search">
        <input v-model="kw" placeholder="搜索工作任务" style="width:100%;border:1px solid var(--border-color,#d3d9e3);border-radius:var(--radius-sm,6px);padding:6px 9px;font-size:12.5px;outline:none" />
      </div>
      <div class="pal-list pal-tasks">
        <!-- 分类目录：默认收起，点击表头展开 -->
        <div v-for="g in wfTree.dirs" :key="g.name" class="pal-cat" :class="{ fold: !wfFolded[g.name] }">
          <div class="pal-cat-head" @click="toggleWfDir(g.name)">
            <span class="arrow">▼</span>{{ g.name }}
            <span class="cnt">{{ g.rows.length }}</span>
            <label class="pal-all" title="全选本目录" @click.stop>
              <input type="checkbox" :checked="g.rows.length > 0 && g.rows.every((r) => picked.has(r.id))" @change="toggleAll(g.rows.map((r) => r.id))" />全选
            </label>
          </div>
          <div class="pal-items">
            <div
              v-for="d in g.rows" :key="d.id"
              class="pal-task" :class="{ on: picked.has(d.id) }"
              @click="togglePick(d.id)"
            >
              <input type="checkbox" :checked="picked.has(d.id)" @click.stop="togglePick(d.id)" />
              <span class="pt-name" :title="d.name">
                <span v-if="d.code != null" class="p-code mono">#{{ d.code }}</span>{{ d.name }}
              </span>
              <!-- 真项目行操作：移动分类（下拉替换 tags）+ 删除；projectId 缺位（/dag 过渡路由）不支持 -->
              <template v-if="hasProject">
                <select
                  class="pt-move"
                  :value="categoryOf(d)"
                  :title="`移动「${d.name}」到分类`"
                  @click.stop
                  @change="moveTo(d, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="g2 in moveOptions" :key="g2" :value="g2">{{ g2 }}</option>
                </select>
                <span class="pt-del" title="删除任务" @click.stop="deleteRow(d)">✕</span>
              </template>
            </div>
          </div>
        </div>
        <!-- 根目录与分类目录之间的分段线：仅当两部分都非空时显示 -->
        <div v-if="wfTree.root.length > 0 && wfTree.dirs.length > 0" class="wf-root-sep"></div>
        <!-- 根目录：无标签普通工作流直接平铺（非目录分组） -->
        <div v-if="wfTree.root.length > 0" class="pal-cat-head pal-root-head">
          <span class="arrow">▼</span>{{ ROOT_LABEL }}
          <span class="cnt">{{ wfTree.root.length }}</span>
          <label class="pal-all" title="全选根目录" @click.stop>
            <input type="checkbox" :checked="wfTree.root.length > 0 && wfTree.root.every((r) => picked.has(r.id))" @change="toggleAll(wfTree.root.map((r) => r.id))" />全选
          </label>
        </div>
        <div v-for="d in wfTree.root" :key="d.id" class="pal-task wf-root-item" :class="{ on: picked.has(d.id) }" @click="togglePick(d.id)">
          <input type="checkbox" :checked="picked.has(d.id)" @click.stop="togglePick(d.id)" />
          <span class="pt-name" :title="d.name">
            <span v-if="d.code != null" class="p-code mono">#{{ d.code }}</span>{{ d.name }}
          </span>
          <!-- 真项目行操作：移动分类（下拉替换 tags）+ 删除；projectId 缺位（/dag 过渡路由）不支持 -->
          <template v-if="hasProject">
            <select
              class="pt-move"
              :value="categoryOf(d)"
              :title="`移动「${d.name}」到分类`"
              @click.stop
              @change="moveTo(d, ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="g2 in moveOptions" :key="g2" :value="g2">{{ g2 }}</option>
            </select>
            <span class="pt-del" title="删除任务" @click.stop="deleteRow(d)">✕</span>
          </template>
        </div>
        <div v-if="wfTree.root.length === 0 && wfTree.dirs.length === 0" class="pal-empty">
          {{ kw ? '无匹配任务' : (hasProject ? '暂无工作任务（后端定义未就绪）' : '候选池待项目上下文接驳') }}
        </div>
      </div>
    </template>
  </aside>
</template>

<style scoped>
/* 蓝本样式合并（旧 theme.css 全局系 + Palette.vue scoped 系，仅组件库分支；
   wf 系 .pal-task、.pt-* 通配、.pal-bar、.pal-load 等归 FE-4）。CSS 变量沿新前端惯例
   （var(--x, fallback)，无全局 token 定义）；旧主色 #1668dc 系 rgba 按新主色
   #2563eb 换算。 */
.wb-palette{width:232px;background:#fff;border-right:1px solid var(--border-color,#e2e8f0);display:flex;flex-direction:column;flex-shrink:0}
.pal-tabs{display:flex;gap:2px;padding:6px 8px 0;border-bottom:1px solid var(--border-color,#e2e8f0);flex-shrink:0}
.pal-tab{border:none;background:none;padding:5px 8px;font-size:12px;color:var(--text-secondary,#64748b);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.pal-tab:hover{color:var(--primary-color,#2563eb)}
.pal-tab.on{color:var(--primary-color,#2563eb);border-bottom-color:var(--primary-color,#2563eb);font-weight:600}
.pal-search{padding:6px 8px;border-bottom:1px solid var(--border-color,#e2e8f0);flex-shrink:0}
.pal-list{flex:1;overflow-y:auto;padding:6px}
.pal-cat{margin-bottom:2px}
.pal-cat-head{display:flex;align-items:center;gap:6px;padding:7px 8px;cursor:pointer;color:var(--text-secondary,#64748b);font-size:12.5px;font-weight:600;border-radius:var(--radius-sm,6px);user-select:none}
.pal-cat-head:hover{background:var(--bg-secondary,#f8fafc)}
.pal-cat-head .cnt{margin-left:auto;font-size:10.5px;color:var(--text-3,#94a3b8);background:var(--bg-secondary,#f8fafc);border-radius:8px;padding:0 7px}
.pal-cat-head .arrow{transition:transform .15s;font-size:10px}
.pal-cat.fold .pal-cat-head .arrow{transform:rotate(-90deg)}
.pal-cat.fold .pal-items{display:none}
.pal-item{display:flex;align-items:center;gap:9px;padding:5px 8px;border-radius:var(--radius-sm,6px);cursor:grab;border:1px solid transparent;user-select:none}
.pal-item:hover{background:var(--primary-light,#eff6ff);border-color:rgba(37,99,235,.25)}
.pal-item .p-ico{width:26px;height:26px;border-radius:var(--radius-sm,6px);display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;flex-shrink:0}
.pal-item .p-name{font-size:12.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pal-item .p-code{font-size:9.5px;font-weight:700;color:var(--text-3,#94a3b8);background:var(--bg-secondary,#f8fafc);border-radius:4px;padding:0 4px;margin-left:2px}
.pal-empty{padding:20px;text-align:center;color:var(--text-3,#94a3b8);font-size:12px}

/* ---------- 工作流目录树（INC4-FE-4，蓝本 L392-429 照抄、CSS 变量 fallback 化） ---------- */
/* .pal-empty、.pal-search、.pal-cat-head 本体、.pal-cat.fold 折叠规则已由组件库分支定义（两分支共用），不重复 */
.pal-tasks{flex:1}
.pal-task{display:flex;align-items:center;gap:6px;padding:6px 8px;cursor:pointer;border-radius:var(--radius-sm,6px);font-size:12.5px}
.pal-task:hover{background:var(--primary-light,#eff6ff)}
.pal-task.on{background:var(--primary-light,#eff6ff);color:var(--primary-color,#2563eb)}
.pal-task input{accent-color:var(--primary-color,#2563eb);cursor:pointer;flex-shrink:0}
.pt-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.p-code{font-size:11px;background:var(--primary-light,#eff6ff);color:var(--primary-color,#2563eb);border-radius:4px;padding:0 4px;margin-right:5px}
/* 旧前端全局 .mono 类不在新前端基建，就地补（蓝本 #编号 等宽通道） */
.p-code.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.pt-move{border:1px solid var(--border-color,#e2e8f0);border-radius:var(--radius-sm,6px);font-size:11px;color:var(--text-secondary,#64748b);background:#fff;padding:1px 3px;cursor:pointer;flex-shrink:0;max-width:74px}
.pt-move:hover{border-color:var(--primary-color,#2563eb);color:var(--primary-color,#2563eb)}
.pt-del{color:var(--text-4,#cbd5e1);font-size:12px;line-height:1;padding:1px 3px;border-radius:3px;flex-shrink:0;cursor:pointer}
.pt-del:hover{color:var(--danger,#dc2626);background:var(--danger-bg,#fef2f2)}
/* 根目录（普通工作流）平铺项 */
.wf-root-item{border-radius:0}
.wf-root-item:hover{background:var(--primary-light,#eff6ff)}
/* 根目录与分类目录分段线 */
.wf-root-sep{border-top:1px dashed var(--border-color,#e2e8f0);margin:4px 8px}
/* 目录头内「全选」标签（wf 分支专用；目录头本体沿用组件库版定义） */
.pal-cat-head .pal-all{margin-left:auto;display:inline-flex;align-items:center;gap:3px;font-size:11.5px;color:var(--text-3,#94a3b8);cursor:pointer;font-weight:400}
.pal-cat-head .pal-all input{accent-color:var(--primary-color,#2563eb);cursor:pointer;margin:0}
.pal-root-head{margin-top:2px;color:var(--text-secondary,#64748b)}
/* 列表操作条（置顶：新建分类、已选计数、载入选中） */
.pal-bar{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 8px;border-bottom:1px solid var(--border-color,#e2e8f0);flex-shrink:0}
.pal-hint{font-size:11.5px;color:var(--text-3,#94a3b8)}
.pal-hint b{color:var(--primary-color,#2563eb)}
.pal-mini{border:1px solid var(--border-color,#e2e8f0);background:#fff;border-radius:var(--radius-sm,6px);padding:3px 8px;font-size:11.5px;color:var(--text-secondary,#64748b);cursor:pointer;white-space:nowrap}
.pal-mini:hover{border-color:var(--primary-color,#2563eb);color:var(--primary-color,#2563eb)}
.pal-load{border:1px solid var(--primary-color,#2563eb);background:var(--primary-color,#2563eb);color:#fff;border-radius:var(--radius-sm,6px);padding:4px 10px;font-size:12px;cursor:pointer;white-space:nowrap}
.pal-load:disabled{border-color:var(--border-color,#e2e8f0);background:var(--bg-2,#f1f5f9);color:var(--text-3,#94a3b8);cursor:not-allowed}
</style>
