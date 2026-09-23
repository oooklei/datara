<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { NodeSchema, ViewProfile } from '../profiles/types'
import { catLabelsOf, pinnedRank } from './palettePinning' // I12 R1：分类徽标 + 分组置顶纯逻辑
import {
  isMock, listDefinitions, deleteDefinition, createCategory, listCategories, setWfTags,
  SYNC_TAG, ETL_TAG, STREAM_TAG,
} from '../../services'
import type { DagPickItem, DagProfileType } from '../../stores/dagTabs'
import { listSeedTaskDocs } from '../../services/mock/seed'

/** I12 R1：activeTags = 当前文档推导的分类标签（如 ['同步']），仅决定分组置顶，不过滤组件 */
const props = defineProps<{ profile: ViewProfile; activeTags?: string[]; defaultTab?: 'palette' | 'wf' }>()
/** 载入请求带逐项明细（id/name/type/code）：任务中心据此逐项开画布 Tab（B 语义合并已移除，I11 多 Tab） */
const emit = defineEmits<{ 'load-tasks': [{ items: DagPickItem[] }] }>()

interface PalRow { schema: NodeSchema; disabled: boolean; phase?: string; cats: string[] }

const kw = ref('')
const folded = ref<Record<string, boolean>>({})

/* ---------- 顶部 Tab：组件库 + 工作流（I11：同步/ETL/流 不再各占 Tab，收敛为分类分组） ---------- */
type PalTab = 'palette' | 'wf'
/** I12b：宿主可指定初始 Tab；任务中心空态默认「工作流」目录（无画布时组件库无意义），GraphWorkbench 常规用法不传保持「组件」 */
const tab = ref<PalTab>(props.defaultTab ?? 'palette')
const tabs: { k: PalTab; label: string }[] = [
  { k: 'palette', label: '组件' },
  { k: 'wf', label: '工作流' },
]

/* palette 分组兼容两种写法：types: string[]（老）与 items: PaletteItem[]（新，支持灰置 phase） */
/* I12 R1：activeTags 命中的置顶组名次（缓存计算，activeTags 不变不重复计算） */
const rank = computed(() => pinnedRank(props.activeTags))
const cats = computed(() => {
  // I12 R1（Nit 修复）：k/match 只随 kw 变化，上提到 .map 外，避免按分组重复创建闭包
  const k = kw.value.trim().toLowerCase()
  const match = (s: NodeSchema) =>
    !k ||
    s.label.toLowerCase().includes(k) ||
    (s.desc ?? '').toLowerCase().includes(k) ||
    s.type.toLowerCase().includes(k)
  return props.profile.palette.map((c) => {
    const fromItems = (c.items ?? []).map((i) => ({ type: i.type, disabled: !!i.disabled, phase: i.phase }))
    const fromTypes = (c.types ?? []).map((t) => ({ type: t, disabled: false, phase: undefined as string | undefined }))
    const seen = new Set<string>()
    const rows: PalRow[] = []
    for (const it of [...fromItems, ...fromTypes]) {
      if (seen.has(it.type)) continue
      seen.add(it.type)
      const s = props.profile.nodeTypes[it.type]
      if (s && match(s)) rows.push({ schema: s, disabled: it.disabled, phase: it.phase, cats: catLabelsOf(s.categories) }) // I12 R1：行级分类徽标
    }
    return { name: c.name, rows }
  }).filter((c) => c.rows.length > 0)
    // I12 R1：强关联分组置顶（稳定排序，未命中组保持原序；只重排不过滤，组件全量渲染）
    .sort((a, b) => (rank.value.get(a.name) ?? Number.POSITIVE_INFINITY) - (rank.value.get(b.name) ?? Number.POSITIVE_INFINITY))
})

function onDragStart(e: DragEvent, row: PalRow) {
  if (row.disabled) return
  e.dataTransfer?.setData('datara/node-type', row.schema.type)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

/* ---------- 工作流目录树（I11：同步 > ETL > 流 > 自定义分类 为可收起目录，无标签任务归根目录） ---------- */
interface DefRow { id: string; name: string; tags: string[]; code?: number }
interface CatRow { name: string; builtin: boolean }

const defPool = ref<DefRow[]>([])
/** 后端分类目录（builtin=false 为自定义；顺序即展示顺序） */
const catsAll = ref<CatRow[]>([])

const BUILTIN_LABELS = ['同步', 'ETL', '流']
/** 根目录名（无标签任务 = 普通工作流，I11 去掉「普通」标签分类，默认归根目录） */
const ROOT_LABEL = '根目录'

/** 某任务的分类目录：内置标签优先，其次自定义目录名，兜底根目录（普通） */
function categoryOf(d: DefRow): string {
  const t = d.tags ?? []
  if (t.includes(SYNC_TAG)) return '同步'
  if (t.includes(ETL_TAG)) return 'ETL'
  if (t.includes(STREAM_TAG)) return '流'
  const custom = catsAll.value.find((c) => !c.builtin && t.includes(c.name))
  return custom?.name ?? ROOT_LABEL
}

/** 分类目录展示顺序（不含根）：同步 → ETL → 流 → 自定义（listCategories 顺序） */
const groupOrder = computed<string[]>(() => [
  ...BUILTIN_LABELS,
  ...catsAll.value.filter((c) => !c.builtin).map((c) => c.name),
])

/** 工作流 Tab 目录树折叠态：仅分类目录可折叠，默认收起（根目录固定展开） */
const wfFolded = ref<Record<string, boolean>>({})
function toggleWfDir(name: string) {
  const s = { ...wfFolded.value }
  s[name] = !s[name]
  wfFolded.value = s
}

/** 工作流 Tab 目录树：root = 根目录任务（无标签普通工作流，平铺展示），dirs = 分类目录（默认收起，含 kw 过滤） */
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

/** 任务类型推导（画布 Profile 与载入载荷用）：内置标签 → sync/etl/stream，否则 wf */
function typeOf(d: DefRow): DagProfileType {
  const t = d.tags ?? []
  if (t.includes(SYNC_TAG)) return 'sync'
  if (t.includes(ETL_TAG)) return 'etl'
  if (t.includes(STREAM_TAG)) return 'stream'
  return 'wf'
}

/** mock = seed 文档池（无后端分类），real = 定义全量 + 分类目录 */
function buildPool() {
  if (isMock) {
    defPool.value = listSeedTaskDocs().map((d) => ({ id: d.id, name: d.name, tags: [] }))
    return
  }
  void loadDefPool()
  void loadCats()
}

async function loadDefPool() {
  try {
    const defs = await listDefinitions({ pageNo: 1, pageSize: 500 })
    defPool.value = defs.map((d) => ({ id: d.id, name: d.name, tags: d.tags ?? [], code: d.code }))
  } catch { /* 后端未就绪时留空 */ }
}

async function loadCats() {
  try {
    const r = await listCategories()
    catsAll.value = r.map((c) => ({ name: c.name, builtin: c.builtin }))
  } catch { /* 分类失败不阻断 */ }
}

/* ---------- 工作流 Tab 行操作（real 才可用：删除 / 移动分类 / 新建分类） ---------- */
async function deleteRow(d: DefRow) {
  try {
    await ElMessageBox.confirm(`删除任务「${d.name}」及其画布？该操作不可恢复。`, '删除任务', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  try {
    await deleteDefinition(d.id)
    ElMessage.success(`已删除「${d.name}」`)
    buildPool()
  } catch { ElMessage.error('删除失败') }
}

/** 移动分类 = setWfTags 整体替换 tags 为 [目标目录名]（根目录传空数组 = 普通工作流） */
async function moveTo(d: DefRow, cat: string) {
  if (cat === categoryOf(d)) return
  try {
    await setWfTags(d.id, cat === ROOT_LABEL ? [] : [cat])
    ElMessage.success(`已移动「${d.name}」到「${cat}」`)
    buildPool()
  } catch { ElMessage.error('移动分类失败') }
}

async function newCategory() {
  let name = ''
  try {
    const r = await ElMessageBox.prompt('输入新分类目录名称（将显示在工作流列表分组中）', '新建分类', {
      confirmButtonText: '创建', cancelButtonText: '取消', inputPlaceholder: '目录名称',
      inputValidator: (v) => (v.trim() ? true : '目录名称不能为空'),
    })
    name = r.value.trim()
  } catch { return }
  if (BUILTIN_LABELS.includes(name) || name === ROOT_LABEL) {
    ElMessage.warning(`「${name}」为内置/根目录，无需新建`)
    return
  }
  try {
    await createCategory(name)
    ElMessage.success(`已创建分类「${name}」`)
    void loadCats()
  } catch { ElMessage.error('创建分类失败') }
}

/* ---------- 勾选多选（载入后清空，跨分组保留） ---------- */
const picked = ref<Set<string>>(new Set())
function togglePick(id: string) {
  const s = new Set(picked.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  picked.value = s
}

/** 目录/根目录一键全选（再次点击取消全选） */
function toggleAll(ids: string[]) {
  const s = new Set(picked.value)
  const allPicked = ids.length > 0 && ids.every((id) => s.has(id))
  for (const id of ids) {
    if (allPicked) s.delete(id)
    else s.add(id)
  }
  picked.value = s
}

/** mock 载荷：type 由 seed type 映射（batch → wf） */
function seedTypeOf(id: string): DagProfileType {
  const s = listSeedTaskDocs().find((x) => x.id === id)
  return s?.type === 'sync' ? 'sync' : s?.type === 'etl' ? 'etl' : s?.type === 'stream' ? 'stream' : 'wf'
}

function onLoad() {
  if (!picked.value.size || tab.value === 'palette') return
  const items: DagPickItem[] = [...picked.value].map((id) => {
    const d = defPool.value.find((x) => x.id === id)
    return {
      id,
      name: d?.name ?? listSeedTaskDocs().find((x) => x.id === id)?.name ?? id,
      type: d ? typeOf(d) : seedTypeOf(id),
      code: d?.code,
    }
  })
  emit('load-tasks', { items })
  picked.value = new Set()
}

onMounted(buildPool)
</script>

<template>
  <aside class="wb-palette">
    <div class="pal-tabs">
      <button
        v-for="t in tabs" :key="t.k"
        class="pal-tab" :class="{ on: tab === t.k }"
        @click="tab = t.k"
      >{{ t.label }}</button>
    </div>

    <!-- 组件库：拖拽 / 点击添加 -->
    <template v-if="tab === 'palette'">
      <div class="pal-search">
        <input v-model="kw" placeholder="搜索组件" style="width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 9px;font-size:12.5px;outline:none" />
      </div>
      <div class="pal-list">
        <div v-for="cat in cats" :key="cat.name" class="pal-cat" :class="{ fold: folded[cat.name] }">
          <div class="pal-cat-head" @click="folded[cat.name] = !folded[cat.name]">
            <span class="arrow">▼</span>{{ cat.name }}
            <span class="cnt">{{ cat.rows.length }}</span>
          </div>
          <div class="pal-items">
            <div
              v-for="row in cat.rows" :key="row.schema.type"
              class="pal-item" :class="{ disabled: row.disabled }"
              :title="row.disabled ? `${row.schema.desc ?? row.schema.label}（${row.phase ?? '后续增量注册'}）` : row.schema.desc"
              :draggable="!row.disabled"
              @dragstart="onDragStart($event, row)"
            >
              <div class="p-ico" :style="{ background: row.schema.color }">{{ row.schema.icon }}</div>
              <div style="min-width:0">
                <div class="p-name">
                  {{ row.schema.label }}
                  <span v-if="row.schema.code" class="p-code">{{ row.schema.code }}</span>
                  <!-- I12 R1：分类徽标（多类并列小胶囊，仅标识不拦截） -->
                  <span v-for="lb in row.cats" :key="lb" class="p-cat">{{ lb }}</span>
                </div>
                <!-- F56c R5：常规项描述走 hover tooltip（title 已挂），仅灰置项保留说明行 -->
                <div v-if="row.disabled" class="p-desc">灰置 · {{ row.phase ?? '后续增量注册' }}</div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="cats.length === 0" style="padding:20px;text-align:center;color:var(--text-3);font-size:12px">无匹配组件</div>
      </div>
    </template>

    <!-- 工作流目录树：根目录（普通工作流平铺，默认即普通无标签）+ 分类目录（同步/ETL/流/自定义，默认收起），行可删除/移动，顶部可新建分类 -->
    <template v-else>
      <div class="pal-bar">
        <button class="pal-mini" @click="newCategory">＋ 新建分类</button>
        <span class="pal-hint">已选 <b>{{ picked.size }}</b></span>
        <button class="pal-load" :disabled="picked.size === 0" @click="onLoad">
          载入选中 ({{ picked.size }})
        </button>
      </div>
      <div class="pal-search">
        <input v-model="kw" placeholder="搜索工作任务" style="width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 9px;font-size:12.5px;outline:none" />
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
              <!-- real 行操作：移动分类（下拉替换 tags）+ 删除；mock 无后端不支持 -->
              <template v-if="!isMock">
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
          <!-- real 行操作：移动分类（下拉替换 tags）+ 删除；mock 无后端不支持 -->
          <template v-if="!isMock">
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
          {{ kw ? '无匹配任务' : '暂无工作任务（后端定义未就绪）' }}
        </div>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.pal-tabs{display:flex;gap:2px;padding:6px 8px 0;border-bottom:1px solid var(--border);flex-shrink:0}
.pal-tab{border:none;background:none;padding:5px 8px;font-size:12px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.pal-tab:hover{color:var(--primary)}
.pal-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.pal-search{padding:6px 8px;border-bottom:1px solid var(--border);flex-shrink:0}
.pal-tasks{flex:1}
.pal-task{display:flex;align-items:center;gap:6px;padding:6px 8px;cursor:pointer;border-radius:var(--radius-sm);font-size:12.5px}
.pal-task:hover{background:var(--primary-light)}
.pal-task.on{background:var(--primary-light);color:var(--primary)}
.pal-task input{accent-color:var(--primary);cursor:pointer;flex-shrink:0}
.pt-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.p-code{font-size:11px;background:var(--primary-light);color:var(--primary);border-radius:4px;padding:0 4px;margin-right:5px}
.pt-move{border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11px;color:var(--text-2);background:#fff;padding:1px 3px;cursor:pointer;flex-shrink:0;max-width:74px}
.pt-move:hover{border-color:var(--primary);color:var(--primary)}
.pt-del{color:var(--text-4);font-size:12px;line-height:1;padding:1px 3px;border-radius:3px;flex-shrink:0;cursor:pointer}
.pt-del:hover{color:var(--danger);background:var(--danger-bg, #fef2f2)}
.pal-empty{padding:20px;text-align:center;color:var(--text-3);font-size:12px}
/* 根目录（普通工作流）平铺项 */
.wf-root-item{border-radius:0}
.wf-root-item:hover{background:var(--primary-light)}
/* 根目录与分类目录分段线 */
.wf-root-sep{border-top:1px dashed var(--border);margin:4px 8px}
/* 目录头（分类 / 根目录共用）内的「全选」标签 */
.pal-cat-head{display:flex;align-items:center;gap:6px;padding:6px 8px;cursor:pointer;font-size:12.5px;border-radius:var(--radius-sm)}
.pal-cat-head:hover{background:var(--primary-light)}
.pal-cat-head .pal-all{margin-left:auto;display:inline-flex;align-items:center;gap:3px;font-size:11.5px;color:var(--text-3);cursor:pointer;font-weight:400}
.pal-cat-head .pal-all input{accent-color:var(--primary);cursor:pointer;margin:0}
.pal-root-head{margin-top:2px;color:var(--text-2)}
/* 列表操作条（置顶右对齐：全站规则，按钮不再挂底部） */
.pal-bar{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 8px;border-bottom:1px solid var(--border);flex-shrink:0}
.pal-hint{font-size:11.5px;color:var(--text-3)}
.pal-hint b{color:var(--primary)}
.pal-mini{border:1px solid var(--border);background:#fff;border-radius:var(--radius-sm);padding:3px 8px;font-size:11.5px;color:var(--text-2);cursor:pointer;white-space:nowrap}
.pal-mini:hover{border-color:var(--primary);color:var(--primary)}
.pal-load{border:1px solid var(--primary);background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:4px 10px;font-size:12px;cursor:pointer;white-space:nowrap}
.pal-load:disabled{border-color:var(--border);background:var(--bg-2, #f1f5f9);color:var(--text-3);cursor:not-allowed}
/* I12 R1：分类徽标（9px 胶囊，沿用既有 chip 风格） */
.p-cat{font-size:9px;line-height:1;color:var(--text-3);background:var(--bg,#f5f7fa);border:1px solid var(--border);border-radius:999px;padding:1.5px 5px;margin-left:4px;white-space:nowrap}
</style>