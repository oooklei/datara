<script setup lang="ts">
/**
 * 任务中心（/dag）—— 唯一任务流入口，严格两层结构：本页（视角页签 + 画布多 Tab）→ GraphWorkbench（统一图工作台）。
 *
 * G2 结构调整：删除中间壳组件 DagDesignView/EtlDesignView/StreamDesignView；
 * 任务类型不再各占顶部页签，收敛为 Palette「工作流」Tab 内按分类分组（同步 / ETL / 流 / 自定义 / 普通）。
 *
 * I11 多 Tab（用户裁定）：同一个画布同时只能编辑一个工作流；多个工作流用 tab 切换（VueFlow 页），
 * 每个 tab 可关闭（点 X 时若有未保存修改 → 三选：保存并关闭 / 放弃修改 / 取消），同时最多打开 5 个；
 * 每载入一个工作流增加 1 个画布 Tab（Palette「载入选中」逐项 open，同一工作流重复载入仅激活现有 Tab）。
 * 画布切换实现：GraphWorkbench 单实例以 :key="activeTab.key"（=docId）重挂载；旧实例 onBeforeUnmount
 * 把草稿存 snap（I11 起 snapKey 由任务类型改为 docId：datara.dag.snap.{docId}），新实例 load 后 restoreSnap。
 *
 * 顶部仅保留「任务编排 / 运行监控 / 告警与SLA」三个视角页签（运行监控、告警与SLA 非任务画布）。
 * 旧路径 /dag/design/:id、/stream/design/:id 由路由 redirect 落回本页（?tab=edit&type=…&doc=…）保书签。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isMock, listDefinitions, listCategories, SYNC_TAG, ETL_TAG, STREAM_TAG } from '../services'
import { listSeedTaskDocs } from '../services/mock/seed'
import { dagProfile, etlProfile, streamProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
import Palette from '../graph/workbench/Palette.vue'
import InstanceRunsView from './dag/InstanceRunsView.vue'
import DagAlarmView from './dag/DagAlarmView.vue'
import { useDagTabsStore, MAX_DAG_TABS } from '../stores/dagTabs'
import type { DagPickItem, DagProfileType, DagTab } from '../stores/dagTabs'
import { useGraphStore } from '../stores/graph'

const route = useRoute()
const router = useRouter()

/* ---- 视角页签：任务编排（画布）+ 运行监控 + 告警与SLA ---- */
type TabKey = 'edit' | 'runs' | 'alarm'
const tabs: { k: TabKey; label: string; icon: string }[] = [
  { k: 'edit', label: '任务编排', icon: '⑃' },
  { k: 'runs', label: '运行监控', icon: '▶' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂' },
]
const qtab = String(route.query.tab ?? '')
const tab = ref<TabKey>(tabs.some((t) => t.k === qtab) ? (qtab as TabKey) : 'edit')

function switchTab(k: TabKey) {
  tab.value = k
  router.replace({ query: { ...route.query, tab: k } }).catch(() => {})
}

/* ---- 画布多 Tab（I11）—— 宿主接 dagTabs store ---- */
const dagTabs = useDagTabsStore()
const graphStore = useGraphStore()
const activeTab = computed(() => dagTabs.activeTab)

/** 画布 Profile：由当前激活 Tab 类型决定（工作流/同步共用 DAG 编排；ETL / 流 各自专用节点库） */
const profileOf = computed(() => {
  const t = activeTab.value?.type
  return t === 'etl' ? etlProfile : t === 'stream' ? streamProfile : dagProfile
})

function lsGet(key: string): string {
  try { return localStorage.getItem(key) ?? '' } catch { return '' }
}
function lsSet(key: string, v: string) {
  try { localStorage.setItem(key, v) } catch { /* 忽略隐私模式 */ }
}

/* ---- 任务池（画布「#code / 目录 / 名称」与打开优先级需要 code / tags / 分类） ---- */
interface PoolMeta { id: string; name: string; tags: string[]; code?: number }
const defPool = ref<PoolMeta[]>([])
/** 自定义分类目录名（listCategories 中 builtin=false 项；builtin 分类按固定内置名渲染） */
const catNames = ref<string[]>([])

async function loadDefPool() {
  try {
    const defs = await listDefinitions({ pageNo: 1, pageSize: 500 })
    defPool.value = defs.map((d) => ({ id: d.id, name: d.name, tags: d.tags ?? [], code: d.code }))
  } catch { /* 后端未就绪时留空（画布区显示空态） */ }
}

async function loadCatNames() {
  try {
    const cats = await listCategories()
    catNames.value = cats.filter((c) => !c.builtin).map((c) => c.name)
  } catch { /* 分类列表失败不阻断 */ }
}

const isTaskType = (v: unknown): v is DagProfileType =>
  v === 'wf' || v === 'sync' || v === 'etl' || v === 'stream'

/** 类型由定义 tags 推导；mock 用 seed type（batch → wf） */
function typeOf(meta?: PoolMeta | null, seedType?: string): DagProfileType {
  if (isMock) {
    return seedType === 'sync' ? 'sync' : seedType === 'etl' ? 'etl' : seedType === 'stream' ? 'stream' : 'wf'
  }
  const t = meta?.tags ?? []
  if (t.includes(SYNC_TAG)) return 'sync'
  if (t.includes(ETL_TAG)) return 'etl'
  if (t.includes(STREAM_TAG)) return 'stream'
  return 'wf'
}

/** 画布标题分类：内置优先（同步 > ETL > 流 > 自定义目录名 > 普通） */
function categoryOf(meta?: PoolMeta | null, seedType?: string): string {
  if (isMock) return seedType === 'sync' ? '同步' : seedType === 'etl' ? 'ETL' : seedType === 'stream' ? '流' : '普通'
  const t = meta?.tags ?? []
  if (t.includes(SYNC_TAG)) return '同步'
  if (t.includes(ETL_TAG)) return 'ETL'
  if (t.includes(STREAM_TAG)) return '流'
  const custom = catNames.value.find((n) => t.includes(n))
  return custom ?? '普通'
}

const TYPE_LABEL: Record<DagProfileType, string> = { wf: '工作流', sync: '同步', etl: 'ETL', stream: '流' }

/** GraphWorkbench 标题副元数据 */
function docMetaOf(tabItem: DagTab): { code?: number; category?: string } {
  const meta = defPool.value.find((d) => d.id === tabItem.docId)
  const seed = isMock ? listSeedTaskDocs().find((d) => d.id === tabItem.docId) : undefined
  return { code: meta?.code ?? tabItem.code, category: categoryOf(meta, seed?.type) }
}

/** 打开一个工作流 Tab（含默认打开与 Palette 载入共用）；返回 store.open 结果 */
function openTab(docId: string, meta?: PoolMeta | null, seedType?: string): 'ok' | 'dup' | 'full' {
  const seed = isMock ? listSeedTaskDocs().find((s) => s.id === docId) : undefined
  return dagTabs.open({
    docId,
    name: meta?.name ?? seed?.name ?? docId,
    type: typeOf(meta, seedType ?? seed?.type),
    code: meta?.code,
  })
}

/** Palette 勾选载入（多选）：逐项开为独立画布 Tab，最多 5 个，重复项仅激活 */
function onPickTasks(p: { items: DagPickItem[] }) {
  const items = p.items.filter((i) => i.id)
  if (!items.length) return
  for (const [idx, it] of items.entries()) {
    const meta = defPool.value.find((d) => d.id === it.id)
    const r = openTab(it.id, meta ?? { id: it.id, name: it.name, tags: [] }, undefined)
    if (r === 'full') {
      ElMessage.warning(`最多同时打开 ${MAX_DAG_TABS} 个画布 Tab，后续 ${items.length - idx} 项未载入`)
      break
    }
    if (r !== 'dup') {
      lsSet(it.type === 'wf' ? 'datara.dag.last' : `datara.dag.last.${it.type}`, it.id)
      lsSet('datara.dag.lastType', it.type)
    }
  }
  switchTab('edit')
}

/** 快照草稿是否存在（关闭非激活 Tab 时确认丢弃的依据） */
function hasSnapDraft(docId: string): boolean {
  try {
    const s = JSON.parse(localStorage.getItem(`datara.dag.snap.${docId}`) ?? 'null')
    return !!s && !!s.draft
  } catch { return false }
}
function clearSnap(docId: string) {
  try { localStorage.removeItem(`datara.dag.snap.${docId}`) } catch { /* 忽略隐私模式 */ }
}

/**
 * 关闭画布 Tab（用户裁定：点 X 时提示保存）：
 * - 激活 Tab 且画布有未保存修改 → 三选：保存并关闭 / 放弃修改 / 取消（X/ESC = 取消）；
 * - 非激活 Tab 存在快照草稿 → 确认丢弃后关闭，否则直接关；
 * 关闭后清理该 docId 的草稿快照（等旧实例卸载回写完成后 nextTick 清理）。
 */
async function onCloseTab(t: DagTab) {
  const isActive = t.key === dagTabs.activeKey
  if (isActive && graphStore.doc?.id === t.docId && graphStore.dirty) {
    let action: 'save' | 'discard' | null = null
    try {
      await ElMessageBox.confirm('当前画布有未保存的修改，关闭前要保存吗？', '关闭画布', {
        confirmButtonText: '保存并关闭',
        cancelButtonText: '放弃修改',
        distinguishCancelAndClose: true,
        type: 'warning',
        closeOnClickModal: false,
      })
      action = 'save'
    } catch (e) {
      action = e === 'cancel' ? 'discard' : null
    }
    if (action === null) return // X / ESC 关闭弹窗 = 取消关闭
    if (action === 'save') {
      try {
        await graphStore.save()
      } catch {
        ElMessage.error('保存失败，画布未关闭')
        return
      }
    }
  } else if (!isActive && hasSnapDraft(t.docId)) {
    try {
      await ElMessageBox.confirm(`「${t.name}」存在未保存的修改草稿，关闭将丢弃草稿。确定关闭吗？`, '关闭画布', {
        confirmButtonText: '仍要关闭',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch { return }
  }
  dagTabs.remove(t.key)
  await nextTick() // 等旧实例 onBeforeUnmount saveSnap 回写完成再清理
  clearSnap(t.docId)
}

onMounted(async () => {
  if (isMock) {
    // 候选池 = seed 文档池（无需后端）
  } else {
    await Promise.all([loadDefPool(), loadCatNames()])
  }
  /* 打开优先级：?doc= 直达（旧 /dag/design/:id、/stream/design/:id 重定向落此）
     > 上次类型 last（datara.dag.last[.type]）> 无（画布空态，Palette 载入后才有 Tab） */
  const qdoc = String(route.query.doc ?? '')
  if (qdoc) {
    const meta = defPool.value.find((d) => d.id === qdoc)
    openTab(qdoc, meta ?? null)
    // ?doc= 直达也更新「上次打开」落盘（按推导类型写对应 key），下次直达用
    const t = typeOf(meta ?? null, undefined)
    lsSet(t === 'wf' ? 'datara.dag.last' : `datara.dag.last.${t}`, qdoc)
    lsSet('datara.dag.lastType', t)
    return
  }
  const lastType = isTaskType(lsGet('datara.dag.lastType')) ? (lsGet('datara.dag.lastType') as DagProfileType) : 'wf'
  const last = lsGet(lastType === 'wf' ? 'datara.dag.last' : `datara.dag.last.${lastType}`)
  if (last) {
    const meta = defPool.value.find((d) => d.id === last)
    // 目标仍存在时打开；缺失（已删除）则清掉陈旧 last（空态已渲染 Palette 可手动找回，不再每次重载都落空态）
    if (isMock || meta) openTab(last, meta ?? null, undefined)
    else lsSet(lastType === 'wf' ? 'datara.dag.last' : `datara.dag.last.${lastType}`, '')
  }
})
</script>

<template>
  <div class="tc">
    <!-- 顶部视角页签栏（任务类型页签已移除：类型切换走 Palette 工作流 Tab 分类） -->
    <div class="tc-tabs">
      <button
        v-for="t in tabs" :key="t.k"
        class="tc-tab" :class="{ on: tab === t.k }"
        @click="switchTab(t.k)"
      ><span class="tc-ic">{{ t.icon }}</span>{{ t.label }}</button>
      <span class="spacer" />
      <span v-if="tab === 'edit'" class="tc-view">{{ profileOf.name }}</span>
    </div>

    <!-- 视角内容区：任务编排 = 画布 Tab 条 + 统一图工作台（两层结构，无中间壳） -->
    <div class="tc-body">
      <template v-if="tab === 'edit'">
        <!-- I11 画布 Tab 条：每载入一个工作流增加 1 个 Tab，X 关闭（关闭时提示保存），最多 5 个 -->
        <div v-if="dagTabs.tabs.length" class="tc-dagbar">
          <button
            v-for="t in dagTabs.tabs" :key="t.key"
            class="tc-dag" :class="{ on: t.key === dagTabs.activeKey }"
            :title="t.name"
            @click="dagTabs.activate(t.key)"
          >
            <span v-if="t.code != null" class="tcd-code mono">#{{ t.code }}</span>
            <span class="tcd-name">{{ t.name }}</span>
            <span class="tcd-type">{{ TYPE_LABEL[t.type] }}</span>
            <span class="tcd-x" title="关闭画布" @click.stop="onCloseTab(t)">×</span>
          </button>
          <span class="tc-daghint">{{ dagTabs.count }}/{{ MAX_DAG_TABS }}</span>
        </div>
        <div v-if="activeTab" class="tc-canvas">
          <GraphWorkbench
            :key="activeTab.key"
            :profile="profileOf"
            :doc-id="activeTab.docId"
            :snap-key="activeTab.docId"
            :doc-meta="docMetaOf(activeTab)"
            :host-managed="true"
            @pick-tasks="onPickTasks"
          />
        </div>
        <div v-else class="tc-empty">
          <!-- I12b：空态也渲染 Palette（默认「工作流」目录）：无 last/无 ?doc 时用户仍可勾选任务载入，不再无入口死路 -->
          <Palette :profile="dagProfile" default-tab="wf" @load-tasks="onPickTasks" />
          <div class="tc-empty-hint">
            <div>暂无打开的画布</div>
            <div>在左侧 Palette「工作流」中勾选任务后点「载入选中」，每个任务开一个画布 Tab。</div>
          </div>
        </div>
      </template>

      <template v-else-if="tab === 'runs'">
        <!-- F56d：运行实例接引擎真数据（InstanceRunsView），纯 mock 演示页 DagRunsView 已删除 -->
        <InstanceRunsView />
      </template>

      <div v-else-if="tab === 'alarm'" class="tc-alarm-wrap">
        <!-- F56e：告警与SLA 为演示模块，页签内容顶部主动提示（与顶栏「演示数据」标识同规则） -->
        <div class="tc-demo-tip">演示数据 · 告警与SLA 为本期范围外模块，页面数据为演示样例</div>
        <DagAlarmView />
      </div>
    </div>
  </div>
</template>

<style scoped>
.tc{display:flex;flex-direction:column;height:100%}
.tc-tabs{display:flex;align-items:center;gap:2px;padding:0 14px;background:#fff;border-bottom:1px solid var(--border);flex-shrink:0}
.tc-tab{border:none;background:none;padding:11px 16px;font-size:13px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:6px;transition:color var(--dur-base) var(--ease),border-color var(--dur-base) var(--ease)}
.tc-tab:hover{color:var(--primary)}
.tc-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.tc-ic{font-size:12px;opacity:.75}
.tc-tab.on .tc-ic{opacity:1}
.spacer{flex:1}
/* 当前画布视角（Profile 名）：类型页签移除后，此处与画布标题徽标一同标识当前视角 */
.tc-view{font-size:11.5px;color:var(--text-3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:2px 10px}
.tc-body{flex:1;min-height:0;display:flex;flex-direction:column;overflow:auto}
/* I11 画布 Tab 条 */
.tc-dagbar{display:flex;align-items:center;gap:6px;padding:6px 12px;background:#fff;border-bottom:1px solid var(--border);flex-shrink:0;overflow-x:auto}
.tc-dag{display:flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg, #f8fafc);padding:5px 8px;font-size:12.5px;color:var(--text-2);cursor:pointer;max-width:260px;white-space:nowrap;transition:all var(--dur-base) var(--ease)}
.tc-dag:hover{border-color:var(--primary);color:var(--primary)}
.tc-dag.on{border-color:var(--primary);background:var(--primary-light);color:var(--primary);font-weight:600}
.tcd-code{font-size:11px;background:var(--primary-light);color:var(--primary);border-radius:4px;padding:0 4px}
.tcd-name{overflow:hidden;text-overflow:ellipsis;flex-shrink:1;min-width:0}
.tcd-type{font-size:10.5px;color:var(--text-3);border:1px solid var(--border);border-radius:9px;padding:0 6px;flex-shrink:0}
.tc-dag.on .tcd-type{color:var(--primary);border-color:var(--primary)}
.tcd-x{color:var(--text-4);font-size:13px;line-height:1;padding:0 1px;border-radius:3px;flex-shrink:0;cursor:pointer}
.tcd-x:hover{color:var(--danger);background:var(--danger-bg, #fef2f2)}
.tc-daghint{font-size:11px;color:var(--text-4);margin-left:2px}
.tc-canvas{flex:1;min-height:0;display:flex;flex-direction:column}
.tc-empty{flex:1;min-height:0;display:flex;align-items:stretch;overflow:hidden}
/* I12b：空态右侧提示（Palette 占左侧 232px，全局 .wb-palette 已定宽高由父容器撑满） */
.tc-empty-hint{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px;color:var(--text-3);font-size:13px;text-align:center}
/* F56e：演示页签顶部提示条（低饱和描边，不做警告色） */
.tc-alarm-wrap{display:flex;flex-direction:column;min-height:0}
.tc-demo-tip{margin:10px 14px 0;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius-lg);font-size:12px;color:var(--text-3);background:var(--bg)}
</style>