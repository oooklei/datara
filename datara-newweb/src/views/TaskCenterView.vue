<script setup lang="ts">
/**
 * 任务中心（/dag 承载，s260 派令）。
 *
 * §10.4 嵌入机制（docs/designs/2026-10-29-dbx-unified-target-design.md）：
 * 「任务编排」主视角 = 海豚（DolphinScheduler）单页画布 iframe（embed 模式）。
 * E1 裁定只取海豚的「编排可视化 DAG 画布 + 运行后台底座」，门户外壳/身份/
 * 数据源/审计由 datara + dbx 承担，故这里不再挂载自研画布内核
 * （WorkflowGraphWorkbench / dagTabs 退役，组件文件保留备查）。
 *
 * 宿主职责（§10.4 / §10.5 B）：
 *  - 项目上下文（datara 项目 → 海豚 projectCode，由编排网关 ensure_project 映射）
 *  - 免登凭证下发（postMessage `datara:ds-session`，DS 侧据此切内部信任头）
 *  - 工作流定义列表与筛选（datara 自建页，不进 iframe）
 *  - 画布路由切换（打开哪个 DAG / 新建工作流）
 *
 * 画布内配套元素（节点侧栏/节点表单/试运行弹窗/定时弹窗/版本下拉/日志抽屉）
 * 随画布一起在 iframe 内闭环，不拆到 datara（§10.4「画布内的配套元素留在画布内」）。
 *
 * 视角页签：任务编排 / 运行监控 / 工作流定时 / 告警与SLA，
 * ?tab= query 驱动 + router.replace 保书签，默认 edit，非法 ?tab= 回落 edit。
 * 运行监控 = datara 自建页（§10.5 B，调海豚实例 API，不进 iframe）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import VariableManagerDrawer from './variables/VariableManagerDrawer.vue'
import WorkflowRunMonitor from '../components/WorkflowRunMonitor.vue'
// §10.5 B / §10.10 R7：海豚实例页不进 datara iframe → datara 自建实例页
import DsRunMonitor from '../components/DsRunMonitor.vue'
import WorkflowScheduleList from '../components/WorkflowScheduleList.vue'
// §10.10 R6：告警桥接（datara 项目级规则 + 触发记录）
import OrchestrationAlarmPanel from '../components/OrchestrationAlarmPanel.vue'
import { authAccount } from '../services/rebuild/authApi'
import { roleHasPermission } from '../services/rebuild/rolePermissions'
import {
  getOrchestrationSession,
  getUnifiedEmbedSession,
  orchestrationApi,
  type OrchestrationSession,
  type WorkflowDefinitionRow,
} from '../services/rebuild/orchestrationApi'
import { dsEmbedUrl, listenDsReady, sendSessionToDs } from '../services/rebuild/dsBridge'
import { useEnvironmentContext } from '../services/rebuild/environmentContext'
import { sanitizeEmbeddedBranding } from '../services/rebuild/embeddedBranding'

/* ---- 视角页签（蓝本照抄：TabKey / tabs 数组 / ?tab= 同步 / 默认 edit） ---- */
type TabKey = 'edit' | 'runs' | 'schedules' | 'alarm'
const tabs: { k: TabKey; label: string; icon: string }[] = [
  { k: 'edit', label: '任务编排', icon: '⑃' },
  { k: 'runs', label: '运行监控', icon: '▶' },
  { k: 'schedules', label: '工作流定时', icon: '◷' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂' },
]
const route = useRoute()
const router = useRouter()
const qtab = String(route.query.tab ?? '')
const tab = ref<TabKey>(tabs.some((t) => t.k === qtab) ? (qtab as TabKey) : 'edit')
const variablesVisible = ref(false)
const variableWorkflowId = ref<number | undefined>()

function openProjectVariables() {
  variableWorkflowId.value = undefined
  variablesVisible.value = true
}

/**
 * B5-d-3 四角色判定链接线：变量抽屉写操作按钮由冻结矩阵 task:write 判定
 * （viewer/operator 无 task:write → 抽屉只读态「当前角色仅可查看变量」；
 * 后端 authorize() 仍是最终裁决，此处仅收敛 UI 可用性）。
 */
const canEditVariables = computed(() => {
  const role = authAccount.value?.role
  return !!role && roleHasPermission(role, 'task:write')
})

/**
 * Keep the active view in sync with browser history/deep links.  Clicking a
 * tab updates local state immediately and writes `?tab=`; however, back/forward
 * navigation changes the route without going through switchTab.  Watching the
 * route query makes those navigation paths deterministic and falls back to the
 * edit view for stale/invalid bookmarks.
 */
watch(
  () => route.query.tab,
  (value) => {
    const next = String(value ?? '')
    tab.value = tabs.some((t) => t.k === next) ? (next as TabKey) : 'edit'
  },
)

function switchTab(k: TabKey) {
  tab.value = k
  router.replace({ query: { ...route.query, tab: k } }).catch(() => {})
}

/* ---- D8 下钻契约（G02）：工作台 KPI/最近实例写入 ?status=/?runId=，本页透传运行监控。
 * 词形 = 后端 run-stats 状态机（SUCCEEDED/FAILED/RUNNING/PENDING/CANCELLED）；
 * runId 仅接受正整数（非法值回落列表态，不假设）。 ---- */
const drillStatus = computed<string | undefined>(() => {
  const raw = route.query.status
  const value = Array.isArray(raw) ? String(raw[0] ?? '') : String(raw ?? '')
  return value || undefined
})
const drillRunId = computed<number | undefined>(() => {
  const raw = route.query.runId
  const value = Array.isArray(raw) ? String(raw[0] ?? '') : String(raw ?? '')
  const n = Number(value)
  return Number.isInteger(n) && n > 0 ? n : undefined
})

/** 运行监控子视图：海豚实例监控（默认，§10.5 B）/ 自研 execution 域运行记录。
 *  D8 下钻（?status=/?runId=）来自工作台 KPI/最近实例，目标即自研运行记录，
 *  故带下钻参数进入时直接落 native 视图。 */
type RunsViewKey = 'dolphin' | 'native'
const hasDrilldown = (): boolean => drillRunId.value !== undefined || drillStatus.value !== undefined
const runsView = ref<RunsViewKey>(hasDrilldown() ? 'native' : 'dolphin')
watch([drillStatus, drillRunId], () => {
  if (hasDrilldown()) runsView.value = 'native'
})

/** 项目上下文（route.params.projectId 承接；/dag 过渡路由无项目段 → undefined，
 *  工作流定义列表与编排画布均降级为「先选项目」空态） */
const projectId = computed<number | undefined>(() => {
  const raw = route.params.projectId
  const n = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(n) && n > 0 ? n : undefined
})
const {
  options: environmentOptions,
  selectedId: environmentGroupId,
  selected: selectedEnvironment,
  error: environmentError,
  refresh: refreshEnvironments,
} = useEnvironmentContext(projectId)

function sessionWithEnvironment(session: OrchestrationSession): OrchestrationSession {
  const environment = selectedEnvironment.value
  return environment?.id != null && environment.code
    ? { ...session, environmentGroupId: environment.id, environmentCode: environment.code }
    : session
}

/* ---- §10.5 B：工作流定义列表（datara 自建页；画布本体才进 iframe） ---- */

const wfRows = ref<WorkflowDefinitionRow[]>([])
const wfLoading = ref(false)
const wfError = ref('')
/** 输入框草稿；`wfAppliedKeyword` 才是已生效的查询词（回车/点查询才生效）。 */
const wfKeyword = ref('')
const wfAppliedKeyword = ref('')
const wfPageNo = ref(1)
const WF_PAGE_SIZE = 10
const wfTotal = ref(0)
const wfRange = computed(() => {
  if (wfTotal.value === 0) return '0 / 0'
  const from = (wfPageNo.value - 1) * WF_PAGE_SIZE + 1
  const to = Math.min(wfPageNo.value * WF_PAGE_SIZE, wfTotal.value)
  return `${from}–${to} / ${wfTotal.value}`
})
/** 列表请求代际：项目切换/翻页竞态时丢弃迟到响应。 */
let wfGeneration = 0

async function loadWorkflowDefinitions() {
  const pid = projectId.value
  wfGeneration += 1
  const generation = wfGeneration
  if (pid === undefined) {
    wfRows.value = []
    wfTotal.value = 0
    wfError.value = ''
    wfLoading.value = false
    return
  }
  wfLoading.value = true
  try {
    const result = await orchestrationApi.listWorkflowDefinitions(
      pid,
      wfPageNo.value,
      WF_PAGE_SIZE,
      wfAppliedKeyword.value,
    )
    if (generation !== wfGeneration) return
    wfRows.value = result.list
    wfTotal.value = result.total
    wfError.value = ''
  } catch (reason) {
    if (generation !== wfGeneration) return
    wfRows.value = []
    wfTotal.value = 0
    wfError.value = reason instanceof Error ? reason.message : '工作流定义加载失败'
  } finally {
    if (generation === wfGeneration) wfLoading.value = false
  }
}

function onSearchWorkflows() {
  wfAppliedKeyword.value = wfKeyword.value.trim()
  wfPageNo.value = 1
  void loadWorkflowDefinitions()
}

function onPrevWfPage() {
  if (wfPageNo.value <= 1) return
  wfPageNo.value -= 1
  void loadWorkflowDefinitions()
}

function onNextWfPage() {
  if (wfPageNo.value * WF_PAGE_SIZE >= wfTotal.value) return
  wfPageNo.value += 1
  void loadWorkflowDefinitions()
}

async function onToggleRelease(row: WorkflowDefinitionRow) {
  const pid = projectId.value
  if (row.code === null || pid === undefined) return
  const next = row.releaseState === 'ONLINE' ? 'OFFLINE' : 'ONLINE'
  try {
    await orchestrationApi.releaseWorkflowDefinition(row.code, pid, next)
    ElMessage.success(next === 'ONLINE' ? '工作流已上线' : '工作流已下线')
    void loadWorkflowDefinitions()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '上下线操作失败')
  }
}

async function onDeleteWorkflow(row: WorkflowDefinitionRow) {
  const pid = projectId.value
  if (row.code === null || pid === undefined) return
  try {
    await ElMessageBox.confirm(`确认删除工作流「${row.name ?? row.code}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await orchestrationApi.deleteWorkflowDefinition(row.code, pid)
    ElMessage.success('工作流已删除')
    void loadWorkflowDefinitions()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败')
  }
}

/* ---- §10.4：海豚 iframe embed 宿主（画布态） ---- */

/** 编辑视角两态：list（datara 自建列表）/ canvas（海豚单页画布 iframe）。 */
const editMode = ref<'list' | 'canvas'>('list')
/** 当前画布对应的定义行；null = 新建工作流。 */
const activeDefinition = ref<Pick<WorkflowDefinitionRow, 'code' | 'name'> | null>(null)

const dsFrameEl = ref<HTMLIFrameElement | null>(null)
let disposeEmbeddedBranding: (() => void) | undefined
/** iframe src：必须等编排会话返回 projectCode 后再设（后端 ensure_project 生成）。 */
const dsFrameUrl = ref<string | null>(null)
const activeCanvasPath = ref<string | null>(null)
const dsEmptyReason = ref('正在获取编排会话…')
const dsSession = ref<OrchestrationSession | null>(null)
let disposeDsReady: (() => void) | null = null
let dsRefreshTimer: ReturnType<typeof setInterval> | null = null

function stopDsRefresh() {
  if (dsRefreshTimer !== null) clearInterval(dsRefreshTimer)
  dsRefreshTimer = null
}

/** 会话惰性加载：只在真正要开画布时取，列表态不发无用请求。 */
async function ensureDsSession(): Promise<OrchestrationSession | null> {
  const pid = projectId.value
  if (pid === undefined) {
    dsEmptyReason.value = '请先选择项目以加载编排画布'
    return null
  }
  if (dsSession.value) return dsSession.value
  dsEmptyReason.value = '正在获取编排会话…'
  try {
    // Migration seam is advisory during rollout; retain the existing
    // orchestration session fallback until every deployed frontend has it.
    try { await getUnifiedEmbedSession(pid) } catch { /* legacy session below */ }
    const session = await getOrchestrationSession(pid)
    if (!session.projectCode) {
      dsEmptyReason.value = '编排会话缺少海豚项目编码'
      return null
    }
    dsSession.value = session
    return session
  } catch {
    dsEmptyReason.value = '编排会话获取失败（datara 编排网关或海豚未就绪）'
    return null
  }
}

/**
 * 装载画布：取会话 → 设 iframe src（单个 DAG 画布路由 + embed=1）→ 下发免登凭证。
 *
 * 时序要点：海豚帧 boot 后立即发 `datara:ds-ready`，宿主监听后下发会话；
 * 另发一次兜底，覆盖「ready 先于本监听挂载」的竞态。DS 侧在会话到达前不 mount，
 * 因此首屏 API 不会带空凭证打 401。
 */
async function mountCanvas(path: string) {
  stopDsRefresh()
  disposeDsReady?.()
  disposeDsReady = null
  dsFrameUrl.value = null
  const session = await ensureDsSession()
  if (session === null) return
  dsFrameUrl.value = dsEmbedUrl(session.projectCode, path)
  await nextTick()
  disposeDsReady = listenDsReady(dsFrameEl.value, () => sendSessionToDs(dsFrameEl.value, sessionWithEnvironment(session)))
  sendSessionToDs(dsFrameEl.value, sessionWithEnvironment(session))
  // Embed bearer expires after 15 minutes; renew while the canvas stays open.
  dsRefreshTimer = setInterval(() => {
    const pid = projectId.value
    if (pid === undefined || editMode.value !== 'canvas' || tab.value !== 'edit') return
    void getOrchestrationSession(pid).then((fresh) => {
      if (projectId.value !== pid || editMode.value !== 'canvas') return
      dsSession.value = fresh
      sendSessionToDs(dsFrameEl.value, sessionWithEnvironment(fresh))
    }).catch(() => ElMessage.error('编排会话续期失败，请重新打开工作流'))
  }, 10 * 60 * 1000)
}

watch(environmentGroupId, () => {
  if (dsSession.value && editMode.value === 'canvas') {
    sendSessionToDs(dsFrameEl.value, sessionWithEnvironment(dsSession.value))
  }
})

/** 从列表打开某个工作流 → 海豚画布路由 `/projects/:code/workflow/definitions/:code`。 */
function openWorkflow(row: WorkflowDefinitionRow) {
  if (row.code === null) return
  activeDefinition.value = row
  activeCanvasPath.value = `/projects/{code}/workflow/definitions/${row.code}`
  editMode.value = 'canvas'
  void mountCanvas(activeCanvasPath.value)
}

function openScheduledWorkflow(code: number, name: string) {
  activeDefinition.value = { code, name }
  activeCanvasPath.value = `/projects/{code}/workflow/definitions/${code}`
  editMode.value = 'canvas'
  switchTab('edit')
  void mountCanvas(activeCanvasPath.value)
}

/** 宿主驱动的画布路由切换（§10.4）：新建工作流 → 海豚新建定义路由。 */
function onOpenCreateWf() {
  if (projectId.value === undefined) {
    ElMessage.warning('请先选择项目以新建工作流')
    return
  }
  activeDefinition.value = null
  activeCanvasPath.value = '/projects/{code}/workflow/definitions/create'
  editMode.value = 'canvas'
  void mountCanvas(activeCanvasPath.value)
}

/** 顶部刷新只重载当前嵌入画布，不退出工作流或丢失项目上下文。 */
function refreshCanvas(): void {
  if (activeCanvasPath.value === null || editMode.value !== 'canvas') return
  void mountCanvas(activeCanvasPath.value)
}

/** 卸下画布（保留列表数据，避免返回时闪空）。 */
function resetCanvas() {
  stopDsRefresh()
  disposeDsReady?.()
  disposeDsReady = null
  dsFrameUrl.value = null
  activeDefinition.value = null
  activeCanvasPath.value = null
  editMode.value = 'list'
}

function backToWorkflowList() {
  resetCanvas()
  void loadWorkflowDefinitions()
}

function onDsOpenVariables(event: MessageEvent) {
  if (event.origin !== window.location.origin || event.source !== dsFrameEl.value?.contentWindow) return
  const payload = event.data as { type?: string; projectCode?: string; workflowCode?: number } | null
  if (payload?.type !== 'datara:open-variables' || payload.projectCode !== dsSession.value?.projectCode) return
  if (!Number.isSafeInteger(payload.workflowCode) || (payload.workflowCode ?? 0) < 1) return
  variableWorkflowId.value = payload.workflowCode
  variablesVisible.value = true
}

function onDsFrameLoad(): void {
  disposeEmbeddedBranding?.()
  try {
    const document = dsFrameEl.value?.contentDocument
    disposeEmbeddedBranding = document ? sanitizeEmbeddedBranding(document) : undefined
  } catch {
    disposeEmbeddedBranding = undefined
  }
}

onMounted(() => {
  window.addEventListener('message', onDsOpenVariables)
  void loadWorkflowDefinitions()
})

// 项目上下文变化（进入/切换项目）→ 会话失效 + 回列表重载
watch(projectId, () => {
  dsSession.value = null
  backToWorkflowList()
})

// 离开编辑视角时卸下 iframe：避免监听挂在已销毁的 frame 上
watch(tab, (value) => {
  if (value !== 'edit') resetCanvas()
})

onUnmounted(() => {
  disposeEmbeddedBranding?.()
  disposeEmbeddedBranding = undefined
})

onUnmounted(() => {
  window.removeEventListener('message', onDsOpenVariables)
  stopDsRefresh()
  disposeDsReady?.()
  disposeDsReady = null
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
      <label v-if="projectId !== undefined" class="tc-environment">环境组
        <select v-model.number="environmentGroupId" data-tc-environment>
          <option :value="null">未选择</option>
          <option v-for="row in environmentOptions" :key="row.id!" :value="row.id!">{{ row.name }}</option>
        </select>
      </label>
      <button v-if="environmentError" data-tc-environment-retry @click="refreshEnvironments">{{ environmentError }}；重试</button>
      <button
        v-if="tab === 'edit'"
        class="tc-variable-management"
        data-testid="variable-management"
        :disabled="projectId === undefined"
        @click="openProjectVariables"
      >变量管理</button>
      <button v-if="tab === 'edit'" class="tc-new-workflow" data-testid="new-workflow" @click="onOpenCreateWf">＋ 新建工作流</button>
      <span v-if="tab === 'edit'" class="tc-view">DAG 编排</span>
    </div>

    <!-- 视角内容区（内容门控 §5A.1） -->
    <div class="tc-body" data-tc-body>
      <!-- 任务编排 = datara 自建工作流定义列表（§10.5 B）→ 选中后进海豚单页画布 iframe（§10.4） -->
      <template v-if="tab === 'edit'">
        <div v-if="editMode === 'list'" class="tc-wf" data-tc-wf-list>
          <header class="tc-wf-head">
            <div>
              <h3 class="tc-wf-title">工作流定义</h3>
              <p class="tc-wf-sub">列表与筛选由平台承载；打开后进入任务编排画布</p>
            </div>
            <div class="tc-wf-filters">
              <input v-model.trim="wfKeyword" data-wf-keyword placeholder="按名称搜索" @keyup.enter="onSearchWorkflows" />
              <button :disabled="wfLoading || projectId === undefined" data-wf-search @click="onSearchWorkflows">查询</button>
            </div>
          </header>
          <p v-if="projectId === undefined" class="tc-wf-hint" data-tc-wf-empty>请先选择项目以查看工作流定义</p>
          <p v-else-if="wfLoading" class="tc-wf-hint" data-wf-loading>加载中…</p>
          <p v-else-if="wfError" class="tc-wf-hint" data-wf-error>{{ wfError }}</p>
          <p v-else-if="!wfRows.length" class="tc-wf-hint" data-wf-empty>暂无工作流定义</p>
          <table v-else class="tc-wf-table" data-wf-table>
            <thead>
              <tr><th>名称</th><th>上线状态</th><th>创建人</th><th>更新时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in wfRows" :key="String(row.code)" :data-wf-row="String(row.code)">
                <td>
                  <button class="tc-wf-open" data-wf-open @click="openWorkflow(row)">{{ row.name ?? `#${row.code}` }}</button>
                </td>
                <td>{{ row.releaseState === 'ONLINE' ? '已上线' : '未上线' }}</td>
                <td>{{ row.userName ?? '—' }}</td>
                <td>{{ row.updateTime ?? '—' }}</td>
                <td class="tc-wf-ops">
                  <button data-wf-schedule title="打开画布后使用定时操作" @click="openWorkflow(row)">配置定时</button>
                  <button data-wf-release @click="onToggleRelease(row)">{{ row.releaseState === 'ONLINE' ? '下线' : '上线' }}</button>
                  <button data-wf-delete @click="onDeleteWorkflow(row)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <nav v-if="wfTotal > WF_PAGE_SIZE" class="tc-wf-pagination" data-wf-pagination>
            <button :disabled="wfPageNo <= 1" data-wf-previous @click="onPrevWfPage">上一页</button>
            <span>{{ wfRange }}</span>
            <button :disabled="wfPageNo * WF_PAGE_SIZE >= wfTotal" data-wf-next @click="onNextWfPage">下一页</button>
          </nav>
        </div>
        <div v-else class="tc-embed" data-tc-embed>
          <div class="tc-embed-bar">
            <button class="tc-embed-back" data-tc-back-list @click="backToWorkflowList">← 返回列表</button>
            <span class="tc-embed-title">{{ activeDefinition ? (activeDefinition.name ?? `#${activeDefinition.code}`) : '新建工作流' }}</span>
            <button type="button" class="tc-embed-refresh" data-tc-embed-refresh :disabled="!dsFrameUrl" @click="refreshCanvas">刷新画布</button>
          </div>
          <iframe
            v-if="dsFrameUrl"
            ref="dsFrameEl"
            :src="dsFrameUrl"
            class="tc-embed-frame"
            data-tc-ds-frame
            allow="clipboard-write"
            @load="onDsFrameLoad"
          />
          <div v-else class="tc-empty" data-tc-empty>
            <p class="tc-slot-title">编排画布未就绪</p>
            <p class="tc-slot-sub">{{ dsEmptyReason }}</p>
          </div>
        </div>
      </template>
      <!-- 运行监控：datara 自建页（§10.5 B / §10.10 R7）。
           海豚实例页不进 datara iframe，故此处为 datara 自建实例页（DsRunMonitor，
           经编排网关读海豚实例/任务实例/甘特/日志/变量，含停止·暂停·恢复·失败重试·重跑）；
           自研 execution 域运行记录（WorkflowRunMonitor）为互补视图，二者可切换。 -->
      <template v-else-if="tab === 'runs'">
        <div class="tc-runs-head" data-tc-runs-head>
          <div class="tc-runs-switch" role="tablist">
            <button
              class="tc-runs-switch-btn"
              :class="{ on: runsView === 'dolphin' }"
              data-tc-runs-view-dolphin
              @click="runsView = 'dolphin'"
            >工作流实例监控</button>
            <button
              class="tc-runs-switch-btn"
              :class="{ on: runsView === 'native' }"
              data-tc-runs-view-native
              @click="runsView = 'native'"
            >自研运行记录</button>
          </div>
        </div>
        <DsRunMonitor v-if="runsView === 'dolphin' && projectId !== undefined" :project-id="projectId" />
        <WorkflowRunMonitor
          v-else-if="runsView === 'native' && projectId !== undefined"
          :project-id="projectId"
          :initial-status="drillStatus"
          :initial-run-id="drillRunId"
        />
        <div v-else class="tc-slot" data-tc-runs-slot><p class="tc-slot-sub">请先选择项目以查看运行记录</p></div>
      </template>
      <template v-else-if="tab === 'schedules'">
        <WorkflowScheduleList :project-id="projectId" @edit="openScheduledWorkflow" />
      </template>
      <!-- 告警与 SLA：§10.10 R6 告警桥接（datara 项目级规则 + 触发记录，
           海豚告警组/实例/插件不接入；失败由编排网关轮询实例状态感知）。 -->
      <template v-else-if="tab === 'alarm'">
        <OrchestrationAlarmPanel v-if="projectId !== undefined" :project-id="projectId" />
        <div v-else class="tc-slot" data-tc-alarm-slot><p class="tc-slot-sub">请先选择项目以配置告警</p></div>
      </template>
    </div>
    <VariableManagerDrawer v-model="variablesVisible" :project-id="projectId" :workflow-id="variableWorkflowId" :can-edit="canEditVariables" />
  </div>
</template>

<style scoped>
/* 运行监控子视图切换（§10.5 B 海豚实例监控 / 自研运行记录） */
.tc-runs-head{display:flex;align-items:center;padding:10px 14px 0;flex-shrink:0}
.tc-runs-switch{display:inline-flex;gap:2px;padding:2px;border-radius:var(--radius-sm, 6px);background:var(--fill-2, var(--bg-2))}
.tc-runs-switch-btn{border:none;background:none;padding:5px 12px;font-size:12.5px;border-radius:var(--radius-sm, 5px);color:var(--text-secondary, var(--text-2));cursor:pointer;transition:background .15s ease,color .15s ease}
.tc-runs-switch-btn:hover{color:var(--text, var(--text-1))}
.tc-runs-switch-btn.on{background:var(--card);color:var(--primary-color, var(--primary));font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.08)}
/* 蓝本 .tc/.tc-tabs/.tc-tab/.tc-ic/.tc-body 照抄；高度适配新壳（AppShell header 56px
   grid 行，主内容区无 height 上下文，蓝本 height:100% 改 min-height:calc(100vh - 56px)）。
   CSS 变量沿新前端惯例（var(--x, fallback)，无全局 token 定义）。 */
.tc{display:flex;flex-direction:column;min-height:calc(100vh - 56px)}
.tc-tabs{display:flex;align-items:center;gap:2px;padding:0 14px;background:var(--card);border-bottom:1px solid var(--border-color, var(--border));flex-shrink:0}
.tc-tab{border:none;background:none;padding:11px 16px;font-size:13px;color:var(--text-secondary, var(--text-2));cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:6px;transition:color .15s ease,border-color .15s ease}
.tc-tab:hover{color:var(--primary-color, var(--primary))}
.tc-tab.on{color:var(--primary-color, var(--primary));border-bottom-color:var(--primary-color, var(--primary));font-weight:600}
.tc-ic{font-size:12px;opacity:.75}
.tc-tab.on .tc-ic{opacity:1}
/* 右上专属操作（蓝本 .spacer/.tc-new-workflow/.tc-save-template/.tc-view 照抄） */
.spacer{flex:1}
.tc-new-workflow{background:var(--primary-color, var(--primary));color:var(--on-primary);border:none;border-radius:var(--radius-sm, 6px);padding:5px 12px;font-size:12.5px;cursor:pointer}
.tc-new-workflow:hover{opacity:.9}
.tc-variable-management{border:1px solid var(--border-color, var(--border));color:var(--primary-color, var(--primary));background:var(--card);border-radius:var(--radius-sm, 6px);padding:4px 12px;font-size:12.5px;cursor:pointer}
.tc-variable-management:hover:not(:disabled){border-color:var(--primary-color, var(--primary))}
.tc-variable-management:disabled{color:var(--text-4, var(--border-strong));cursor:not-allowed}
.tc-view{font-size:11.5px;color:var(--text-secondary, var(--text-2));border:1px solid var(--border-color, var(--border));border-radius:var(--radius-lg, 10px);padding:2px 10px}
.tc-body{flex:1;min-height:0;display:flex;flex-direction:column;overflow:auto}
/* B6 375 档修复：tab 行 + 右侧操作组 min-content 403px 撑破视口，<768 允许换行收缩 */
@media(max-width:768px){.tc-tabs{flex-wrap:wrap;padding:0 8px}.tc-tab{padding:10px 10px}}
/* §10.5 B 工作流定义列表（datara 自建；表格/筛选范式对齐 WorkflowRunMonitor） */
.tc-wf{flex:1;min-height:0;display:flex;flex-direction:column;padding:16px 18px;gap:12px;overflow:auto}
.tc-wf-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
.tc-wf-title{margin:0;font-size:15px;font-weight:600;color:var(--text-primary, var(--text))}
.tc-wf-sub{margin:4px 0 0;font-size:12.5px;color:var(--text-secondary, var(--text-2))}
.tc-wf-filters{display:flex;align-items:center;gap:8px}
.tc-wf-filters input{border:1px solid var(--border-color, var(--border));border-radius:var(--radius-sm, 6px);padding:5px 10px;font-size:12.5px;background:var(--card);color:var(--text-primary, var(--text));min-width:200px}
.tc-wf-filters button{border:1px solid var(--border-color, var(--border));background:var(--card);color:var(--primary-color, var(--primary));border-radius:var(--radius-sm, 6px);padding:5px 12px;font-size:12.5px;cursor:pointer}
.tc-wf-filters button:disabled{color:var(--text-4, var(--border-strong));cursor:not-allowed}
.tc-wf-hint{margin:0;padding:24px 0;text-align:center;font-size:13px;color:var(--text-secondary, var(--text-2))}
.tc-wf-table{width:100%;border-collapse:collapse;font-size:12.5px}
.tc-wf-table th,.tc-wf-table td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border-color, var(--border));color:var(--text-primary, var(--text))}
.tc-wf-table th{font-weight:600;color:var(--text-secondary, var(--text-2))}
.tc-wf-open{border:none;background:none;padding:0;font-size:12.5px;color:var(--primary-color, var(--primary));cursor:pointer;text-align:left}
.tc-wf-open:hover{text-decoration:underline}
.tc-wf-ops{display:flex;gap:6px}
.tc-wf-ops button{border:1px solid var(--border-color, var(--border));background:var(--card);color:var(--text-primary, var(--text));border-radius:var(--radius-sm, 6px);padding:3px 9px;font-size:12px;cursor:pointer}
.tc-wf-ops button:hover{border-color:var(--primary-color, var(--primary));color:var(--primary-color, var(--primary))}
.tc-wf-pagination{display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--text-secondary, var(--text-2))}
.tc-wf-pagination button{border:1px solid var(--border-color, var(--border));background:var(--card);border-radius:var(--radius-sm, 6px);padding:3px 10px;font-size:12px;cursor:pointer;color:var(--text-primary, var(--text))}
.tc-wf-pagination button:disabled{color:var(--text-4, var(--border-strong));cursor:not-allowed}
/* 画布态顶栏（返回列表 + 当前工作流名） */
.tc-embed-bar{display:flex;align-items:center;gap:10px;padding:6px 12px;background:var(--card);border-bottom:1px solid var(--border-color, var(--border));flex-shrink:0}
.tc-embed-back{border:1px solid var(--border-color, var(--border));background:var(--card);color:var(--primary-color, var(--primary));border-radius:var(--radius-sm, 6px);padding:3px 10px;font-size:12px;cursor:pointer}
.tc-embed-title{font-size:12.5px;color:var(--text-primary, var(--text));font-weight:600}
/* §10.4 海豚 iframe embed：占满内容区，无边框（同源反代，与宿主同域） */
.tc-embed{flex:1;min-height:0;display:flex;flex-direction:column}
.tc-embed-frame{flex:1;min-height:0;width:100%;border:none;background:var(--bg-secondary, var(--bg))}
/* 画布未就绪 / 运行监控无项目上下文空态；告警 SLA 空态共用 */
.tc-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px}
.tc-slot{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px}
.tc-slot-title{margin:0;font-size:15px;font-weight:600;color:var(--text-primary, var(--text))}
.tc-slot-sub{margin:0;font-size:13px;color:var(--text-secondary, var(--text-2));max-width:560px;text-align:center}
</style>
