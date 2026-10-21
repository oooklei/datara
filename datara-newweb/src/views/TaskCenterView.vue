<script setup lang="ts">
/**
 * 任务中心（/dag 承载，s260 派令）。
 *
 * INC4-FE-1（4.2a）：顶部视角页签框架——四视角页签 = 任务编排 / 模板中心 /
 * 运行监控 / 告警与SLA（icon+label 照抄蓝本数组原文），?tab= query 驱动 +
 * router.replace 保书签，默认 edit，非法 ?tab= 回落 edit。
 *
 * INC4-FE-2（4.2b）：画布多 Tab（蓝本 TaskCenterView.vue 中段 L59-276 照抄，
 * §5A.1「照抄（交互机制与持久化键名一并继承）」）——dagTabs store
 * （MAX_DAG_TABS=5 上限 / 同 docId 单 Tab / 关闭三选 / KeepAlive +
 * localStorage 键名 datara.dag.last*、datara.dag.snap.{docId} 一并继承）+
 * edit 态右上专属操作三件（§7.3 布局蓝本一致性判据）。
 *
 * §5A.2 三分类收窄：DagProfileType 四类型收窄三类型（wf/sync/stream，删 etl），
 * TYPE_LABEL 去 etl 项；存量 ETL 降级映射 wf（执行前报监督线核对候批）。
 *
 * 缺位基建降级（接驳点逐处注释声明）：
 *  - GraphWorkbench 画布内核归 INC4-FE-6/7：画布区以占位组件承载 KeepAlive +
 *    :key 重挂载结构；onCloseTab dirty 信号 = 快照草稿（FE-6/7 替换
 *    graphStore.doc?.id === t.docId && graphStore.dirty）；
 *  - Palette 双 Tab（INC4-FE-3 组件库 + INC4-FE-4 候选池已接驳）：空态渲染
 *    <Palette default-tab="wf" :project-id="projectId"> @load-tasks=
 *    "onPickTasks"（事件同名同载荷直连）；组件库一源 loadComponentSpecs
 *    （§5A.3 零私设）；候选池 listWorkflowDefinitions（纯数组契约）；
 *  - 候选池接线（INC4-FE-4 已接驳）：defPool = listWorkflowDefinitions(projectId)
 *    （/api/v1/rebuild/workflows 纯数组契约）；?doc= 直达与 last 恢复查池取
 *    真名/类型（池不可用保底 name=docId 占位）；陈旧 last 清理沿蓝本
 *    L272-274（池非空才校验，目标已删清落盘键）；
 *  - projectId 承接 route.params.projectId：/dag 过渡路由无项目段 → undefined，
 *    Palette 空态降级「候选池待项目上下文接驳」；项目路由集成即活（候裁披露）；
 *  - auth store / WfCreateDialog / createTemplate 归画布内核批次：
 *    右上「＋新建工作流 / 另存为模板」入口在位，行为提示降级。
 */
import { computed, defineComponent, h, nextTick, onMounted, ref, type PropType } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MAX_DAG_TABS, useDagTabsStore, type DagPickItem, type DagTab, type DagProfileType } from '../stores/dagTabs'
import Palette from '../components/Palette.vue'
import { listWorkflowDefinitions, type WorkflowDefSummary } from '../services/rebuild/workflowApi'

/* ---- 视角页签（蓝本照抄：TabKey / tabs 数组 / ?tab= 同步 / 默认 edit） ---- */
type TabKey = 'edit' | 'templates' | 'runs' | 'alarm'
const tabs: { k: TabKey; label: string; icon: string }[] = [
  { k: 'edit', label: '任务编排', icon: '⑃' },
  { k: 'templates', label: '模板中心', icon: '▦' },
  { k: 'runs', label: '运行监控', icon: '▶' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂' },
]
const route = useRoute()
const router = useRouter()
const qtab = String(route.query.tab ?? '')
const tab = ref<TabKey>(tabs.some((t) => t.k === qtab) ? (qtab as TabKey) : 'edit')

function switchTab(k: TabKey) {
  tab.value = k
  router.replace({ query: { ...route.query, tab: k } }).catch(() => {})
}

/* ---- INC4-FE-2：画布多 Tab（蓝本照抄，见头注释降级声明） ---- */
const dagTabs = useDagTabsStore()
const activeTab = computed(() => dagTabs.activeTab)

/** 视角名（旧 taskCenterPolicy.workflowEditorProfile → dagProfile.name 'DAG 编排'；
 *  分类只影响目录/徽标/组件分组优先级，编辑内核始终是统一 DAG 工作流；
 *  ViewProfile 体系归 INC4-FE-6/7 接驳，本票以常量承载） */
const profileOf = computed(() => ({ name: 'DAG 编排' }))

function lsGet(key: string): string {
  try { return localStorage.getItem(key) ?? '' } catch { return '' }
}
function lsSet(key: string, v: string) {
  try { localStorage.setItem(key, v) } catch { /* 忽略隐私模式 */ }
}

/** 任务元数据载体（INC4-FE-4 接线：= WorkflowDefSummary wire 直通形状，wire id
 *  number 直通；Palette onLoad 出口 String(id) 桥接 DagPickItem.id string） */
type PoolMeta = WorkflowDefSummary

/** 项目上下文（route.params.projectId 承接；/dag 过渡路由无项目段 → undefined，
 *  候选池降级空态；项目路由集成即活，候裁披露） */
const projectId = computed<number | undefined>(() => {
  const raw = route.params.projectId
  const n = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(n) && n > 0 ? n : undefined
})

/** 候选池（INC4-FE-4 接线）：listWorkflowDefinitions 纯数组直存（纯数组非分页对象） */
const defPool = ref<WorkflowDefSummary[]>([])
async function loadDefPool() {
  if (projectId.value === undefined) return
  try {
    defPool.value = await listWorkflowDefinitions(projectId.value)
  } catch { /* 后端未就绪留空 */ }
}

/** 按字符串 docId 查候选池（wire id number → String 桥接比对） */
function poolFind(docId: string): PoolMeta | null {
  return defPool.value.find((d) => String(d.id) === docId) ?? null
}

const isTaskType = (v: unknown): v is DagProfileType =>
  v === 'wf' || v === 'sync' || v === 'stream'

/** 类型由定义 tags 推导（蓝本 L98-108 收窄）：tags 优先，seedType 兜底。
 *  tag 值 = 后端 tags 契约值（SYNC_TAG='同步' / STREAM_TAG='流'，旧
 *  services/graphApi.ts L21/L25）；§5A.2 删 ETL 分支，存量 etl 降级映射 wf
 *  （执行前报监督线核对候批）。 */
function typeOf(meta?: PoolMeta | null, seedType?: string): DagProfileType {
  const t = meta?.tags ?? []
  if (t.includes('同步')) return 'sync'
  if (t.includes('流')) return 'stream'
  if (seedType === 'sync' || seedType === 'stream') return seedType
  return 'wf'
}

/** 画布 Tab 类型徽标（§5A.2 三分类：去 etl） */
const TYPE_LABEL: Record<DagProfileType, string> = { wf: '工作流', sync: '同步', stream: '流' }

/** 打开一个工作流 Tab（默认打开与 Palette 载入共用）；返回 store.open 结果 */
function openTab(docId: string, meta?: PoolMeta | null, seedType?: string): 'ok' | 'dup' | 'full' {
  return dagTabs.open({
    docId,
    name: meta?.name ?? docId,
    type: typeOf(meta, seedType),
    code: meta?.code,
  })
}

/** Palette 勾选载入（多选，蓝本 L141-158 照抄）：逐项开为独立画布 Tab，最多 5 个，
 *  重复项仅激活；INC4-FE-4 接线——池命中走真名/tags 类型推导，miss 走 item 自带
 *  type 的 seedType 通道（Palette 与宿主池同 projectId 同源，正常恒命中）。 */
function onPickTasks(p: { items: DagPickItem[] }) {
  const items = p.items.filter((i) => i.id)
  if (!items.length) return
  for (const [idx, it] of items.entries()) {
    const r = openTab(it.id, poolFind(it.id), it.type)
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

/* ---- edit 态右上专属操作（蓝本 L288-291 照抄；auth.canEdit / WfCreateDialog /
   createTemplate 缺位降级见头注释，INC4-FE-6/7 画布内核批次归真） ---- */
function onOpenCreateWf() {
  // 蓝本：auth.canEdit 校验 → WfCreateDialog 对话框（auth store / 对话框组件随画布内核批次接驳）
  ElMessage.info('新建工作流对话框随后续批次（画布内核）接驳')
}

function saveActiveAsTemplate() {
  if (!activeTab.value) return
  // 蓝本：resolveTemplateSourceDoc → ElMessageBox.prompt('模板名称') → createTemplate（契约随画布内核批次接驳）
  ElMessage.info('另存为模板随后续批次（画布内核）接驳')
}

/** 快照草稿是否存在（关闭非激活 Tab 时确认丢弃的依据；键名 datara.dag.snap.{docId} 继承） */
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
 * 关闭画布 Tab（用户裁定：点 X 时提示保存；蓝本 L205-248 三选交互照抄）：
 * - 激活 Tab 且有未保存修改 → 三选：保存并关闭 / 放弃修改 / 取消（X/ESC = 取消）；
 * - 非激活 Tab 存在快照草稿 → 确认丢弃后关闭，否则直接关；
 * - 关闭后清理该 docId 的草稿快照（等旧实例卸载回写完成后 nextTick 清理）。
 *
 * FE-6/7 接驳点：画布内核（GraphWorkbench/graphStore）到位后，dirty 判定替换为
 * graphStore.doc?.id === t.docId && graphStore.dirty；「保存并关闭」分支接入
 * await graphStore.save()（失败 ElMessage.error('保存失败，画布未关闭') 后不关闭）。
 * 本票 dirty 信号 = 快照草稿（hasSnapDraft）；「保存并关闭」暂同放弃收尾
 * （无真保存能力，草稿随统一清理；本票无编辑内核，草稿仅测试种入可达）。
 */
async function onCloseTab(t: DagTab) {
  const isActive = t.key === dagTabs.activeKey
  if (isActive && hasSnapDraft(t.docId)) {
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
    // action === 'save'：graphStore.save() 归 INC4-FE-6/7（见上接驳点注释）
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
  /* 打开优先级（蓝本 L250-276 照抄）：候选池前置拉取 → ?doc= 直达（旧
     /dag/design/:id、/stream/design/:id 重定向落此）> 上次类型 last
     （datara.dag.last[.type]）> 无（画布空态，Palette 载入后才有 Tab）。
     INC4-FE-4 接线：?doc=/last 查池取真名/类型（池不可用保底 name=docId
     占位）；陈旧 last 清理沿蓝本 L272-274——池非空才校验，目标已删清落盘键
     （池空 = 后端未就绪/无项目上下文，不清理保底占位打开）。 */
  await loadDefPool()
  const qdoc = String(route.query.doc ?? '')
  if (qdoc) {
    const meta = poolFind(qdoc)
    openTab(qdoc, meta)
    // ?doc= 直达也更新「上次打开」落盘（按推导类型写对应 key），下次直达用
    const t = typeOf(meta, undefined)
    lsSet(t === 'wf' ? 'datara.dag.last' : `datara.dag.last.${t}`, qdoc)
    lsSet('datara.dag.lastType', t)
    return
  }
  const lastType = isTaskType(lsGet('datara.dag.lastType')) ? (lsGet('datara.dag.lastType') as DagProfileType) : 'wf'
  const lastKey = lastType === 'wf' ? 'datara.dag.last' : `datara.dag.last.${lastType}`
  const last = lsGet(lastKey)
  if (!last) return
  const meta = poolFind(last)
  if (meta) {
    openTab(last, meta)
  } else if (defPool.value.length > 0) {
    // 陈旧 last（目标已删）：清落盘键（lsGet 空串语义 = 删除）
    lsSet(lastKey, '')
    lsSet('datara.dag.lastType', '')
  } else {
    openTab(last, null) // 池不可用（未就绪/无项目上下文）：保底占位打开
  }
})

/** 画布占位组件（GraphWorkbench 本体归 INC4-FE-6/7）：承载蓝本 KeepAlive +
 *  :key 重挂载结构（§5A.1 照抄四要素），内核到位后替换为 GraphWorkbench。 */
const CanvasPlaceholder = defineComponent({
  name: 'CanvasPlaceholder',
  props: { tab: { type: Object as PropType<DagTab>, required: true } },
  setup(props) {
    return () =>
      h('div', { class: 'tc-canvas-slot', 'data-tc-canvas-slot': '' }, [
        h('p', { class: 'tc-canvas-slot-title' }, `画布：${props.tab.name}`),
        h('p', { class: 'tc-canvas-slot-sub' }, `docId ${props.tab.docId} · 画布内核随后续批次（INC4-FE-6/7）接驳`),
      ])
  },
})
</script>

<template>
  <div class="tc">
    <!-- 顶部视角页签栏（蓝本照抄：icon + label，.on 高亮态） -->
    <div class="tc-tabs" data-tc-tabs>
      <button
        v-for="t in tabs" :key="t.k"
        class="tc-tab" :class="{ on: tab === t.k }"
        :data-tab="t.k"
        @click="switchTab(t.k)"
      ><span class="tc-ic">{{ t.icon }}</span>{{ t.label }}</button>
      <!-- edit 态右上专属操作（蓝本 L288-291 照抄） -->
      <span class="spacer" />
      <button v-if="tab === 'edit'" class="tc-new-workflow" data-testid="new-workflow" @click="onOpenCreateWf">＋ 新建工作流</button>
      <button v-if="tab === 'edit' && activeTab" class="tc-save-template" @click="saveActiveAsTemplate">另存为模板</button>
      <span v-if="tab === 'edit'" class="tc-view">{{ profileOf.name }}</span>
    </div>

    <!-- 视角内容区（内容门控 §5A.1） -->
    <div class="tc-body" data-tc-body>
      <!-- 任务编排 = 主视角：画布 Tab 条 + 画布区（两层结构，蓝本 L294-337 照抄） -->
      <template v-if="tab === 'edit'">
        <!-- I11 画布 Tab 条：每载入一个工作流增加 1 个 Tab，X 关闭（关闭时提示保存），最多 5 个 -->
        <div v-if="dagTabs.tabs.length" class="tc-dagbar" data-tc-dagbar>
          <button
            v-for="t in dagTabs.tabs" :key="t.key"
            class="tc-dag" :class="{ on: t.key === dagTabs.activeKey }"
            :title="t.name"
            :data-dag-tab="t.key"
            @click="dagTabs.activate(t.key)"
          >
            <span v-if="t.code != null" class="tcd-code mono">#{{ t.code }}</span>
            <span class="tcd-name">{{ t.name }}</span>
            <span class="tcd-type">{{ TYPE_LABEL[t.type] }}</span>
            <span class="tcd-x" title="关闭画布" @click.stop="onCloseTab(t)">×</span>
          </button>
          <span class="tc-daghint">{{ dagTabs.count }}/{{ MAX_DAG_TABS }}</span>
        </div>
        <div v-if="activeTab" class="tc-canvas" data-tc-canvas>
          <!-- 蓝本 KeepAlive 缓存画布实例（切换 Tab 不销毁/重建，消除闪白与重复初始化）；
               GraphWorkbench 本体归 INC4-FE-6/7，本票以占位组件承载 KeepAlive + :key 结构 -->
          <KeepAlive>
            <CanvasPlaceholder :key="activeTab.key" :tab="activeTab" />
          </KeepAlive>
        </div>
        <div v-else class="tc-empty" data-tc-empty>
          <!-- 蓝本空态渲染 Palette（I12b，默认「工作流」目录）：INC4-FE-3 组件库
               + INC4-FE-4 候选池均已接驳，:project-id 承接项目上下文（缺位降级
               空态，候裁披露）；load-tasks 事件同名同载荷直连 onPickTasks；
               不加 .tc-newbtn（顶栏已有，避免双钮）；hint 两行文案保留 -->
          <Palette default-tab="wf" :project-id="projectId" @load-tasks="onPickTasks" />
          <div class="tc-empty-hint">
            <div>暂无打开的画布</div>
            <div>在左侧 Palette「工作流」中勾选任务后点「载入选中」，每个任务开一个画布 Tab。</div>
          </div>
        </div>
      </template>
      <!-- 运行监控 = 页签占位：内容归增量 8（§5A.10），本版不实现 -->
      <template v-else-if="tab === 'runs'">
        <div class="tc-slot" data-tc-runs-slot>
          <p class="tc-slot-sub">运行实例与日志随后续批次（增量 8）交付</p>
        </div>
      </template>
      <!-- 模板中心 / 告警与SLA：框架保留，本版不渲染占位内容（§5A.1） -->
    </div>
  </div>
</template>

<style scoped>
/* 蓝本 .tc/.tc-tabs/.tc-tab/.tc-ic/.tc-body 照抄；高度适配新壳（AppShell header 56px
   grid 行，主内容区无 height 上下文，蓝本 height:100% 改 min-height:calc(100vh - 56px)）。
   CSS 变量沿新前端惯例（var(--x, fallback)，无全局 token 定义）。 */
.tc{display:flex;flex-direction:column;min-height:calc(100vh - 56px)}
.tc-tabs{display:flex;align-items:center;gap:2px;padding:0 14px;background:#fff;border-bottom:1px solid var(--border-color, #e2e8f0);flex-shrink:0}
.tc-tab{border:none;background:none;padding:11px 16px;font-size:13px;color:var(--text-secondary, #64748b);cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:6px;transition:color .15s ease,border-color .15s ease}
.tc-tab:hover{color:var(--primary-color, #2563eb)}
.tc-tab.on{color:var(--primary-color, #2563eb);border-bottom-color:var(--primary-color, #2563eb);font-weight:600}
.tc-ic{font-size:12px;opacity:.75}
.tc-tab.on .tc-ic{opacity:1}
/* 右上专属操作（蓝本 .spacer/.tc-new-workflow/.tc-save-template/.tc-view 照抄） */
.spacer{flex:1}
.tc-new-workflow{background:var(--primary-color, #2563eb);color:#fff;border:none;border-radius:var(--radius-sm, 6px);padding:5px 12px;font-size:12.5px;cursor:pointer}
.tc-new-workflow:hover{opacity:.9}
.tc-save-template{border:1px solid var(--border-color, #e2e8f0);color:var(--primary-color, #2563eb);background:#fff;border-radius:var(--radius-sm, 6px);padding:4px 12px;font-size:12.5px;cursor:pointer}
.tc-save-template:hover{border-color:var(--primary-color, #2563eb)}
.tc-view{font-size:11.5px;color:var(--text-secondary, #64748b);border:1px solid var(--border-color, #e2e8f0);border-radius:var(--radius-lg, 10px);padding:2px 10px}
.tc-body{flex:1;min-height:0;display:flex;flex-direction:column;overflow:auto}
/* 画布 Tab 条（蓝本 .tc-dagbar、.tc-dag、.tcd-* 系列、.tc-daghint 照抄） */
.tc-dagbar{display:flex;align-items:center;gap:6px;padding:6px 12px;background:#fff;border-bottom:1px solid var(--border-color, #e2e8f0);flex-shrink:0;overflow-x:auto}
.tc-dag{display:flex;align-items:center;gap:6px;border:1px solid var(--border-color, #e2e8f0);background:var(--bg-secondary, #f8fafc);color:var(--text-secondary, #64748b);border-radius:var(--radius-sm, 6px);padding:4px 10px;font-size:12.5px;cursor:pointer;max-width:260px;white-space:nowrap}
.tc-dag.on{color:var(--primary-color, #2563eb);border-color:var(--primary-color, #2563eb);background:var(--primary-light, #eff6ff)}
.tcd-code{font-size:11px;background:var(--primary-light, #eff6ff);color:var(--primary-color, #2563eb);border-radius:4px;padding:0 4px}
.tcd-name{overflow:hidden;text-overflow:ellipsis;flex-shrink:1;min-width:0}
.tcd-type{font-size:10.5px;color:var(--text-3, #94a3b8);border:1px solid var(--border-color, #e2e8f0);border-radius:9px;padding:0 6px;flex-shrink:0}
.tcd-x{color:var(--text-4, #cbd5e1);border-radius:4px;padding:0 3px;font-size:13px;line-height:1}
.tcd-x:hover{color:var(--danger, #dc2626);background:var(--danger-bg, #fef2f2)}
.tc-daghint{font-size:11px;color:var(--text-4, #cbd5e1);margin-left:2px}
/* 画布区 / 空态（蓝本 .tc-canvas/.tc-empty/.tc-empty-hint 照抄） */
.tc-canvas{flex:1;min-height:0;display:flex;flex-direction:column}
.tc-canvas-slot{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px}
.tc-canvas-slot-title{margin:0;font-size:15px;font-weight:600;color:var(--text-primary, #0f172a)}
.tc-canvas-slot-sub{margin:0;font-size:13px;color:var(--text-secondary, #64748b)}
.tc-empty{flex:1;display:flex;align-items:center;justify-content:center;padding:24px}
.tc-empty-hint{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:13px;color:var(--text-secondary, #64748b);text-align:center}
/* 占位槽（runs 增量 8 注记保留） */
.tc-slot{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px}
.tc-slot-sub{margin:0;font-size:13px;color:var(--text-secondary, #64748b)}
</style>
