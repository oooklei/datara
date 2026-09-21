<script setup lang="ts">
/**
 * I3 运行实例视图（§13「Workbench 运行实例视图」真实落地，/dag/instances）：
 * - 实例列表（run_mode/state 筛选，GET /instances 分页）；
 * - 行操作：详情 / 停止 / 整体重跑 / 失败重跑（run_instance 权限联动，均写命令由 master 消费）；
 * - 详情抽屉：只读 DAG（GraphWorkbench view 模式，任务状态染色 + attempt 徽标）
 *   + 任务表（loopIter/delayUntil/输出参数）+ 变量快照（variables.varSnapshot，§10.3 全明文）
 *   + 节点日志抽屉（GET /logs/task/{id} 2s 轮询增量）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listDefinitions, listInstancesPage, getInstanceDetail,
  stopInstance, rerunInstance, rerunFailedTasks, getTaskLog, graphService,
} from '../../services'
import type { InstanceRow, DefinitionMeta } from '../../services'
import { listTmpData } from '../../services/datasourceApi'
import type { TmpRow } from '../../services/datasourceApi'
import { cloneDoc } from '../../graph/model'
import type { GraphDocument } from '../../graph/model'
import { dagProfile } from '../../graph/profiles/dag'
import type { ViewProfile } from '../../graph/profiles'
import GraphWorkbench from '../../graph/workbench/GraphWorkbench.vue'
import { useRunStore } from '../../stores/run'
import { useAuthStore } from '../../stores/auth'

type TaskRow = NonNullable<InstanceRow['taskInstances']>[number]

const auth = useAuthStore()
const run = useRunStore()
const router = useRouter()
const canRun = computed(() => auth.hasPerm('run_instance'))

/* ---------- 字典 / 映射 ---------- */
const INSTANCE_STATES = [
  { v: 'running', t: '运行中' }, { v: 'success', t: '成功' },
  { v: 'failure', t: '失败' }, { v: 'kill', t: '已终止' },
  { v: 'submitted', t: '已提交' },
]
const RUN_MODES = [
  { v: 'manual', t: '手工' }, { v: 'schedule', t: '定时' }, { v: 'complement', t: '补数' },
]
function instCls(s?: string): string {
  if (s === 'success') return 'ok'
  if (s === 'failure' || s === 'kill') return 'bad'
  if (s === 'running' || s === 'submitted') return 'info'
  return 'gray'
}
function instLabel(s?: string): string {
  return INSTANCE_STATES.find((x) => x.v === s)?.t ?? (s ?? '-')
}
function modeLabel(m?: string): string {
  return m === 'schedule' ? '定时' : m === 'complement' ? '补数' : '手工'
}
const TASK_STATE_LABEL: Record<string, string> = {
  submitted: '已提交', waiting_dependency: '等待依赖', running: '运行中', success: '成功',
  failure: '失败', kill: '终止', skip: '跳过', fault_tolerance: '容错中', retry: '重试中',
}
function taskLabel(s?: string): string {
  return TASK_STATE_LABEL[s ?? ''] ?? (s ?? '-')
}
function taskPillCls(s?: string): string {
  if (s === 'success') return 'ok'
  if (s === 'failure' || s === 'kill') return 'bad'
  if (s && ['running', 'retry', 'fault_tolerance', 'submitted', 'waiting_dependency'].includes(s)) return 'info'
  return 'gray'
}
/** 任务状态 → DataNode 染色类（run.nodeStatus → DataNode 的 st- 前缀类） */
function taskSt(s?: string): string {
  switch (s) {
    case 'success': return 'success'
    case 'failure': return 'fail'
    case 'kill': return 'kill'
    case 'running': case 'retry': case 'fault_tolerance': return 'running'
    case 'skip': return 'skip'
    default: return 'queued'
  }
}

/* ---------- 工作流 code→定义 映射（名称展示 + 详情 doc 加载） ---------- */
const defMap = ref<Map<number, DefinitionMeta>>(new Map())

async function loadDefMap() {
  try {
    const defs = await listDefinitions()
    const m = new Map<number, DefinitionMeta>()
    defs.forEach((d) => {
      const code = (d as DefinitionMeta & { code?: number }).code
      if (code) m.set(code, d)
    })
    defMap.value = m
  } catch { /* 定义列表失败不阻断实例页 */ }
}

function wfName(code?: number): string {
  return defMap.value.get(code ?? -1)?.name ?? (code != null ? `#${code}` : '-')
}

/* ---------- 实例列表 ---------- */
const rows = ref<InstanceRow[]>([])
const total = ref(0)
const pageNo = ref(1)
const pageSize = 20
const loading = ref(false)
const fRunMode = ref('')
const fState = ref('')

async function reload() {
  loading.value = true
  try {
    const page = await listInstancesPage({
      pageNo: pageNo.value, pageSize,
      runMode: fRunMode.value || undefined,
      state: fState.value || undefined,
    })
    rows.value = page.list
    total.value = page.total ?? page.list.length
  } catch (e) {
    ElMessage.error('实例列表加载失败：' + errMsg(e))
  } finally {
    loading.value = false
  }
}
function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
watch([fRunMode, fState], () => { pageNo.value = 1; reload() })

onMounted(async () => {
  await loadDefMap()
  await reload()
})

/* ---------- 行操作：停止 / 整体重跑 / 失败重跑 ---------- */
const RUNNING = new Set(['submitted', 'running', 'fault_tolerance'])
const TERMINAL = new Set(['success', 'failure', 'kill'])

async function onStop(r: InstanceRow) {
  try {
    await ElMessageBox.confirm(`确认停止实例 ${r.instanceId}？运行中任务将被 kill，未启动任务不再执行。`, '停止实例', { type: 'warning' })
  } catch { return }
  try {
    await stopInstance(r.instanceId)
    ElMessage.success('停止命令已提交（master 2s 内消费置 kill）')
    await reload()
  } catch (e) { ElMessage.error(errMsg(e)) }
}
async function onRerun(r: InstanceRow) {
  try {
    await ElMessageBox.confirm(`确认整体重跑实例 ${r.instanceId}？将新建实例全量重算，复用原变量快照。`, '整体重跑', { type: 'warning' })
  } catch { return }
  try {
    await rerunInstance(r.instanceId)
    ElMessage.success('重跑命令已提交（新实例即将生成）')
    await reload()
  } catch (e) { ElMessage.error(errMsg(e)) }
}
async function onRerunFailed(r: InstanceRow) {
  try {
    await ElMessageBox.confirm(`确认失败节点重跑实例 ${r.instanceId}？仅重置 failure 任务及其下游，同实例续跑。`, '失败节点重跑', { type: 'info' })
  } catch { return }
  try {
    await rerunFailedTasks(r.instanceId)
    ElMessage.success('失败重跑命令已提交')
    await reload()
  } catch (e) { ElMessage.error(errMsg(e)) }
}

/* ---------- 详情抽屉：DAG + 任务表 + 变量快照 ---------- */
const detailVisible = ref(false)
const detail = ref<InstanceRow | null>(null)
const detailLoading = ref(false)
const detailDoc = ref<GraphDocument | null>(null)
const viewProfile: ViewProfile = { ...dagProfile, mode: 'view', palette: [], floats: [] }

/** 详情轮询（实例运行中 3s 刷新状态染色） */
let detailTimer: number | null = null
function stopDetailTimer() {
  if (detailTimer) { window.clearInterval(detailTimer); detailTimer = null }
}

async function openDetail(r: InstanceRow) {
  detail.value = r
  detailVisible.value = true
  await loadDetail()
  stopDetailTimer()
  if (RUNNING.has(detail.value?.state ?? '')) {
    detailTimer = window.setInterval(loadDetail, 3000)
  }
}
function closeDetail() {
  stopDetailTimer()
  run.nodeStatus = {}
  detailDoc.value = null
}

async function loadDetail() {
  if (!detail.value) return
  detailLoading.value = true
  try {
    const d = await getInstanceDetail(detail.value.instanceId)
    detail.value = d
    paintDag(d)
  } catch (e) {
    ElMessage.error('实例详情加载失败：' + errMsg(e))
  } finally {
    detailLoading.value = false
  }
}

/** 构建只读 doc 并按任务状态染色（nodeStatus 注入 DataNode；attempt 注入 data._attempt 徽标） */
async function paintDag(d: InstanceRow) {
  const defId = defMap.value.get(d.wfCode ?? -1)?.id
  if (!defId) { detailDoc.value = null; return }
  try {
    const doc = await graphService.get(defId)
    if (!doc) { detailDoc.value = null; return }
    const painted = cloneDoc(doc)
    const taskRows = d.taskInstances ?? []
    painted.nodes.forEach((n) => {
      const own = taskRows.filter((t) => t.nodeId === n.id)
      if (!own.length) return
      const last = own[own.length - 1]!
      n.data._attempt = Math.max(...own.map((t) => Number(t.attempt ?? 1)))
      run.nodeStatus[n.id] = taskSt(last.state)
    })
    detailDoc.value = painted
  } catch { detailDoc.value = null }
}

const tasks = computed<TaskRow[]>(() => detail.value?.taskInstances ?? [])

/* ---------- 变量快照（§10.3：{name:{value,source,resolved}}） ---------- */
const snapshot = computed<{ name: string; value: string; source: string; resolved: boolean }[]>(() => {
  const raw = (detail.value?.variables ?? {}) as { varSnapshot?: Record<string, { value?: unknown; source?: string; resolved?: boolean }> }
  const snap = raw.varSnapshot
  if (!snap || typeof snap !== 'object') return []
  return Object.entries(snap).map(([name, v]) => ({
    name,
    value: String(v?.value ?? ''),
    source: String(v?.source ?? '-'),
    resolved: v?.resolved !== false,
  }))
})
const snapshotText = computed(() => {
  const raw = (detail.value?.variables ?? {}) as { varSnapshot?: unknown }
  return raw.varSnapshot ? JSON.stringify(raw.varSnapshot, null, 2) : ''
})
const showSnapshotRaw = ref(false)

/* ---------- 节点日志抽屉（2s 轮询增量） ---------- */
const logVisible = ref(false)
const logTask = ref<TaskRow | null>(null)
const logContent = ref('')
const logLoading = ref(false)
let logTimer: number | null = null

function openLog(t: TaskRow) {
  logTask.value = t
  logContent.value = ''
  logVisible.value = true
  stopLogTimer()
  pollLog()
  logTimer = window.setInterval(pollLog, 2000)
}
function stopLogTimer() {
  if (logTimer) { window.clearInterval(logTimer); logTimer = null }
}
async function pollLog() {
  if (!logTask.value) return
  logLoading.value = true
  try {
    const r = await getTaskLog(logTask.value.id)
    const growing = r.content.length >= logContent.value.length
    logContent.value = r.content
    // 增量自动滚底
    requestAnimationFrame(() => {
      const el = document.querySelector('.log-pre') as HTMLElement | null
      if (el && growing) el.scrollTop = el.scrollHeight
    })
  } catch (e) {
    logContent.value = '日志读取失败：' + errMsg(e)
  } finally {
    logLoading.value = false
  }
}
watch(logVisible, (v) => { if (!v) { stopLogTimer(); logTask.value = null } })

/* ---------- C22 数据预览（设计 §5.1 第二入口：日志抽屉「数据预览」按钮） ---------- */
const tmpVisible = ref(false)
const tmpRows = ref<TmpRow[]>([])
const tmpErr = ref('')
async function openTmp() {
  const iid = String(detail.value?.instanceId ?? '')
  const nid = logTask.value?.nodeId ?? ''
  if (!iid || !nid) return
  tmpErr.value = ''
  try {
    const rows = await listTmpData(iid)
    tmpRows.value = rows.filter((r) => !r.nodeId || r.nodeId === nid)
    tmpVisible.value = true
  } catch (e) {
    tmpErr.value = errMsg(e)
    ElMessage.error('临时数据读取失败：' + tmpErr.value)
  }
}
/** preview.rows 与 columns 全等的首行为表头行，跳过避免重复展示 */
function tmpBody(r: TmpRow): string[][] {
  const rows = r.preview?.rows ?? []
  const cols = r.preview?.columns ?? []
  if (rows.length && cols.length && rows[0].every((v, i) => String(v ?? '') === cols[i])) return rows.slice(1)
  return rows
}

/** I5 F27 入口①：SQL/文件节点日志抽屉跳血缘视图（预置 instance+node 追溯过滤） */
function goLineage() {
  const iid = String(detail.value?.instanceId ?? '')
  const nid = logTask.value?.nodeId ?? ''
  if (!iid || !nid) return
  router.push({ path: '/meta/lineage', query: { instance: iid, node: nid } })
}

onBeforeUnmount(() => { stopDetailTimer(); stopLogTimer() })

function dur(s?: string | null, e?: string | null): string {
  if (!s || !e) return '-'
  const t = new Date(String(e).replace(' ', 'T')).getTime() - new Date(String(s).replace(' ', 'T')).getTime()
  if (!Number.isFinite(t) || t < 0) return '-'
  const m = Math.floor(t / 60000)
  const sec = Math.floor((t % 60000) / 1000)
  return m ? `${m}m${sec}s` : `${sec}s`
}
</script>

<template>
  <div class="page">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">运行实例</span>
        <span class="pill info">调度执行引擎 I3</span>
        <span class="spacer" />
        <select v-model="fRunMode" class="f-sel">
          <option value="">全部模式</option>
          <option v-for="m in RUN_MODES" :key="m.v" :value="m.v">{{ m.t }}</option>
        </select>
        <select v-model="fState" class="f-sel">
          <option value="">全部状态</option>
          <option v-for="s in INSTANCE_STATES" :key="s.v" :value="s.v">{{ s.t }}</option>
        </select>
        <button class="tb-refresh" @click="reload">刷新</button>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>实例 ID</th><th>工作流</th><th>模式</th><th>计划时间</th><th>状态</th>
            <th>开始</th><th>结束</th><th>主机</th><th style="width:250px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="9" style="text-align:center;color:var(--text-3);padding:18px">加载中…</td></tr>
          <tr v-for="r in rows" :key="r.instanceId">
            <td class="mono" style="font-size:11px" :title="r.instanceId">{{ r.instanceId.slice(0, 18) }}</td>
            <td style="font-weight:600">{{ wfName(r.wfCode) }}</td>
            <td>
              <span class="pill" :class="r.runMode === 'manual' ? '' : 'info'">{{ modeLabel(r.runMode) }}</span>
              <div v-if="r.runMode !== 'manual' && r.scheduleTime" class="mono" style="font-size:10.5px;color:var(--text-3)">{{ r.scheduleTime }}</div>
            </td>
            <td style="font-size:11.5px;color:var(--text-3)">{{ r.scheduleTime || '-' }}</td>
            <td><span class="pill" :class="instCls(r.state)">{{ instLabel(r.state) }}</span></td>
            <td style="font-size:11.5px">{{ r.startTime || '-' }}</td>
            <td style="font-size:11.5px">{{ r.endTime || '-' }}</td>
            <td style="font-size:11.5px;color:var(--text-3)">{{ r.host || '-' }}</td>
            <td>
              <button class="op-btn primary" @click="openDetail(r)">详情</button>
              <template v-if="canRun">
                <button v-if="RUNNING.has(r.state ?? '')" class="op-btn" style="color:var(--danger)" @click="onStop(r)">停止</button>
                <button v-if="TERMINAL.has(r.state ?? '')" class="op-btn" @click="onRerun(r)">整体重跑</button>
                <button v-if="r.state === 'failure'" class="op-btn" @click="onRerunFailed(r)">失败重跑</button>
              </template>
            </td>
          </tr>
          <tr v-if="!loading && rows.length === 0">
            <td colspan="9" style="text-align:center;color:var(--text-3);padding:18px">暂无实例（在工作流定义页「运行」或定时/补数产生）</td>
          </tr>
        </tbody>
      </table>
      <div v-if="total > pageSize" class="pg-bar">
        <button class="op-btn" :disabled="pageNo <= 1" @click="pageNo--; reload()">上一页</button>
        <span style="font-size:11.5px;color:var(--text-3)">第 {{ pageNo }} 页 / 共 {{ Math.ceil(total / pageSize) }} 页（{{ total }} 条）</span>
        <button class="op-btn" :disabled="pageNo >= Math.ceil(total / pageSize)" @click="pageNo++; reload()">下一页</button>
      </div>
    </div>

    <!-- 实例详情抽屉：只读 DAG + 任务表 + 变量快照 -->
    <el-drawer v-model="detailVisible" size="86%" :title="`实例详情 ${detail?.instanceId ?? ''}`" @close="closeDetail">
      <div v-if="detail" class="dt-body">
        <div class="dt-meta">
          <span class="pill" :class="instCls(detail.state)">{{ instLabel(detail.state) }}</span>
          <span class="pill" :class="detail.runMode === 'manual' ? '' : 'info'">{{ modeLabel(detail.runMode) }}</span>
          <span v-if="detail.scheduleTime" class="dt-kv">计划时间 <b class="mono">{{ detail.scheduleTime }}</b></span>
          <span class="dt-kv">开始 <b class="mono">{{ detail.startTime || '-' }}</b></span>
          <span class="dt-kv">结束 <b class="mono">{{ detail.endTime || '-' }}</b></span>
          <span class="dt-kv">时长 <b>{{ dur(detail.startTime, detail.endTime) }}</b></span>
          <span class="dt-kv">主机 <b class="mono">{{ detail.host || '-' }}</b></span>
          <span v-if="canRun && TERMINAL.has(detail.state ?? '')" style="margin-left:auto">
            <button class="op-btn" @click="onRerun(detail)">整体重跑</button>
            <button v-if="detail.state === 'failure'" class="op-btn" @click="onRerunFailed(detail)">失败重跑</button>
          </span>
          <span v-else-if="canRun && RUNNING.has(detail.state ?? '')" style="margin-left:auto">
            <button class="op-btn" style="color:var(--danger)" @click="onStop(detail)">停止</button>
          </span>
        </div>

        <div class="dt-split">
          <!-- 左：只读 DAG（任务状态染色 + attempt 徽标） -->
          <div class="dt-dag">
            <div v-if="detailLoading && !detailDoc" class="dt-empty">加载画布…</div>
            <div v-else-if="!detailDoc" class="dt-empty">
              画布加载失败（工作流定义可能已删除；wf_code={{ detail.wfCode ?? '-' }}）
            </div>
            <GraphWorkbench v-else :profile="viewProfile" :doc-id="detailDoc.id" :doc="detailDoc" />
          </div>

          <!-- 右：任务表 + 变量快照 -->
          <div class="dt-side">
            <div class="side-head">任务（{{ tasks.length }}）</div>
            <table class="tbl">
              <thead>
                <tr><th>节点</th><th>状态</th><th>attempt</th><th>迭代</th><th>时长</th><th>操作</th></tr>
              </thead>
              <tbody>
                <tr v-for="t in tasks" :key="t.id">
                  <td>
                    <div style="font-weight:600">{{ t.name }}</div>
                    <div class="mono" style="font-size:10px;color:var(--text-3)">{{ t.nodeType }}</div>
                  </td>
                  <td>
                    <span class="pill" :class="taskPillCls(t.state)">{{ taskLabel(t.state) }}</span>
                    <div v-if="t.delayUntil" class="mono" style="font-size:10px;color:var(--text-3)">至 {{ t.delayUntil }}</div>
                  </td>
                  <td><span class="pill" :class="t.attempt > 1 ? 'warn' : ''">#{{ t.attempt }}</span></td>
                  <td>{{ t.loopIter || 0 }}</td>
                  <td style="font-size:11px">{{ dur(t.startTime, t.endTime) }}</td>
                  <td>
                    <button class="op-btn" @click="openLog(t)">日志</button>
                    <div v-if="t.outputs && Object.keys(t.outputs).length" style="margin-top:3px">
                      <span v-for="(v, k) in t.outputs" :key="k" class="pill info" style="margin:1px 2px 1px 0;font-size:10px">{{ k }}={{ String(v).slice(0, 24) }}</span>
                    </div>
                  </td>
                </tr>
                <tr v-if="tasks.length === 0"><td colspan="6" class="dt-empty">暂无任务行</td></tr>
              </tbody>
            </table>

            <div class="side-head" style="margin-top:12px">
              变量快照（{{ snapshot.length }}）
              <button class="op-btn" style="margin-left:8px" @click="showSnapshotRaw = !showSnapshotRaw">{{ showSnapshotRaw ? '表格' : '原文' }}</button>
            </div>
            <div v-if="showSnapshotRaw" class="mono snap-raw">{{ snapshotText || '（无快照）' }}</div>
            <table v-else-if="snapshot.length" class="tbl">
              <thead><tr><th>变量</th><th>值</th><th>来源</th><th>解析</th></tr></thead>
              <tbody>
                <tr v-for="s in snapshot" :key="s.name">
                  <td class="mono" style="font-size:11px">{{ s.name }}</td>
                  <td class="mono" style="font-size:11px;word-break:break-all">{{ s.value }}</td>
                  <td style="font-size:11px;color:var(--text-3)">{{ s.source }}</td>
                  <td><span class="pill" :class="s.resolved ? 'ok' : 'warn'">{{ s.resolved ? '已解析' : '未解析' }}</span></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="dt-empty">实例暂无变量快照（实例运行后由 master 汇总写入）</div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 节点日志抽屉（F47：2s 轮询增量滚动；I4 C22 节点附「数据预览」入口） -->
    <el-drawer v-model="logVisible" size="55%" :title="`节点日志 - ${logTask?.name ?? ''}（attempt #${logTask?.attempt ?? 1}）`">
      <div class="log-wrap">
        <div class="log-bar">
          <span class="pill" :class="taskPillCls(logTask?.state)">{{ taskLabel(logTask?.state) }}</span>
          <span class="mono" style="font-size:11px;color:var(--text-3)">task_id={{ logTask?.id }}</span>
          <span style="flex:1" />
          <button v-if="logTask && ['sql', 'file'].includes(logTask.nodeType ?? '')" class="op-btn" @click="goLineage">查看血缘</button>
          <button v-if="logTask?.nodeType === 'file'" class="op-btn" @click="openTmp">数据预览</button>
          <span v-if="logLoading" style="font-size:11px;color:var(--text-3)">轮询中（2s）…</span>
        </div>
        <!-- C22 临时数据预览检验网格（抽样 + 字段类型推断 + 空值统计） -->
        <div v-if="tmpVisible" class="tmp-panel">
          <div class="tmp-bar">
            <span class="tmp-cap">临时数据预览（{{ tmpRows.length }} 条）</span>
            <span style="flex:1" />
            <button class="op-btn" @click="tmpVisible = false">收起</button>
          </div>
          <div v-if="!tmpRows.length" class="tmp-empty">本节点未注册临时数据</div>
          <div v-for="r in tmpRows" :key="r.id" class="tmp-item">
            <div class="tmp-meta">
              <span class="pill info mono">{{ r.name }}</span>
              <span class="pill">{{ r.kind === 'table' ? '临时表' : r.kind === 'resultset' ? '结果集引用' : '文件登记' }}</span>
              <span class="pill">{{ r.rowsCount ?? 0 }} 行</span>
              <span class="mono" style="font-size:10.5px;color:var(--text-3)">{{ r.retention }}</span>
            </div>
            <table v-if="r.schema?.columns?.length" class="tmp-tbl">
              <thead><tr><th>字段</th><th>类型</th><th>空值率</th></tr></thead>
              <tbody>
                <tr v-for="c in r.schema.columns" :key="c.name">
                  <td class="mono">{{ c.name }}</td><td>{{ c.type }}</td><td class="mono">{{ c.nullRate }}%</td>
                </tr>
              </tbody>
            </table>
            <table v-if="tmpBody(r).length" class="tmp-tbl">
              <thead><tr><th>#</th><th v-for="(c, j) in r.preview?.columns" :key="j">{{ c }}</th></tr></thead>
              <tbody>
                <tr v-for="(row, i) in tmpBody(r).slice(0, 20)" :key="i">
                  <td class="mono" style="color:var(--text-3)">{{ i + 1 }}</td>
                  <td v-for="(_, j) in r.preview?.columns" :key="j" class="mono">{{ row[j] ?? '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <pre class="log-pre mono">{{ logContent || '（暂无日志内容）' }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.f-sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:5px 8px;font-size:12px;margin-right:6px;background:#fff}
/* C22 临时数据预览面板（日志抽屉内） */
.tmp-panel{display:flex;flex-direction:column;gap:8px;border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;margin-bottom:8px;max-height:45%;overflow:auto}
.tmp-bar{display:flex;align-items:center;gap:8px}
.tmp-cap{font-size:11.5px;font-weight:600;color:var(--text-2)}
.tmp-empty{font-size:11.5px;color:var(--text-3);text-align:center;padding:8px}
.tmp-item{display:flex;flex-direction:column;gap:5px;border-top:1px dashed var(--border);padding-top:6px}
.tmp-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tmp-tbl{width:100%;border-collapse:collapse;font-size:11px}
.tmp-tbl th{text-align:left;font-weight:600;color:var(--text-3);padding:2px 5px;border-bottom:1px solid var(--border)}
.tmp-tbl td{padding:2px 5px;border-bottom:1px dashed var(--border)}
.tb-refresh{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:5px 12px;font-size:12px;cursor:pointer}
.tb-refresh:hover{border-color:var(--primary);color:var(--primary)}
.pg-bar{display:flex;align-items:center;gap:10px;margin-top:10px}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:3px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
.op-btn:disabled{opacity:.4;cursor:not-allowed}
.dt-body{display:flex;flex-direction:column;height:100%}
.dt-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-bottom:10px;border-bottom:1px solid var(--border)}
.dt-kv{font-size:12px;color:var(--text-3)}
.dt-kv b{color:var(--text);font-weight:600}
.dt-split{display:flex;gap:12px;flex:1;min-height:0;padding-top:10px}
.dt-dag{flex:1.4;min-width:0;min-height:420px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;position:relative}
.dt-dag :deep(.wb){height:100%}
.dt-side{flex:1;min-width:340px;overflow:auto;padding-bottom:20px}
.side-head{font-size:12.5px;font-weight:700;margin-bottom:6px}
.dt-empty{text-align:center;color:var(--text-3);font-size:12px;padding:18px 6px}
.snap-raw{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;font-size:11px;max-height:220px;overflow:auto;white-space:pre-wrap;word-break:break-all}
.log-wrap{display:flex;flex-direction:column;height:100%}
.log-bar{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.log-pre{flex:1;background:#0b1020;color:#c8d3f5;border-radius:var(--radius-sm);padding:12px;font-size:11.5px;line-height:1.65;overflow:auto;white-space:pre-wrap;word-break:break-all;margin:0}
</style>
