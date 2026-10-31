<template>
  <main class="pg" aria-label="监控中心">
    <header class="pg-head">
      <h1 class="sec-head">监控中心</h1>
      <p class="pg-desc">
        海豚任务运行监控（任务/工作流实例状态、工作流定义按用户）+ 海豚 master / worker / 数据库连接池 + datara 运行时节点。
        只读观测面，不提供海豚监控大盘的任何写操作；海豚首页 /home 不进 iframe。
      </p>
    </header>

    <div class="toolbar">
      <DepOpsSubNav />
      <span
        class="pill"
        :class="snapshot && snapshot.zkAvailable ? 'ok' : 'err'"
        :data-zk="snapshot ? String(snapshot.zkAvailable) : undefined"
      >
        ZK：{{ snapshot ? (snapshot.zkAvailable ? '可用' : '不可用') : '—' }}
      </span>
      <span class="spacer"></span>
      <span class="hint" data-generated>生成时间：{{ snapshot?.generatedAt || '—' }}</span>
      <button type="button" class="op-btn" data-refresh :disabled="anyBusy" @click="reloadAll">刷新</button>
    </div>

    <!-- ① 任务运行监控：海豚首页 /home 的三张统计卡，由 datara 自有图表渲染（§10.11） -->
    <section class="panel" data-analysis-section>
      <div class="panel-hd">
        <span class="sec-head">任务运行监控</span>
        <span class="pill info">任务运行总览</span>
        <span class="spacer"></span>
        <span class="hint">只读统计；时间区间留空时默认当天 0 点至当前</span>
      </div>
      <div class="toolbar">
        <label class="field">项目
          <select v-model="selectedProject" data-analysis-project>
            <option value="">请选择项目</option>
            <option v-for="project in projects" :key="project.id" :value="String(project.id)">{{ project.name }}</option>
          </select>
        </label>
        <label class="field">起始 <input v-model="startDate" data-analysis-start type="date"></label>
        <label class="field">结束 <input v-model="endDate" data-analysis-end type="date"></label>
        <button type="button" class="op-btn" data-analysis-query :disabled="analysisBusy || !projectId" @click="loadAnalysis">查询</button>
      </div>
      <div v-if="analysisError" class="err-box" role="alert" data-analysis-error>
        <span>{{ analysisError }}</span>
        <button type="button" class="op-btn retry" :disabled="analysisBusy" @click="loadAnalysis">重试</button>
      </div>
      <p v-if="!projectId" class="hint" data-analysis-hint>请先选择项目</p>
      <p v-else-if="analysisBusy && !analysis" class="loading" role="status">正在读取任务运行监控…</p>
      <div v-else-if="analysis" class="board-grid" data-analysis-cards>
        <div class="card mon-card" data-analysis-task>
          <div class="sub-hd">任务实例状态</div>
          <div class="donut-wrap">
            <div class="donut" :style="{ background: taskDonut }">
              <div class="donut-center"><b>{{ analysis.task.totalCount }}</b><span>任务实例</span></div>
            </div>
            <div class="legend">
              <div v-for="item in taskDist" :key="item.state" class="legend-line">
                <span class="dot" :style="{ background: item.color }"></span>
                <span>{{ item.label }}</span>
                <span class="legend-val">{{ item.count }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="card mon-card" data-analysis-workflow>
          <div class="sub-hd">工作流实例状态</div>
          <div class="donut-wrap">
            <div class="donut" :style="{ background: workflowDonut }">
              <div class="donut-center"><b>{{ analysis.workflow.totalCount }}</b><span>工作流实例</span></div>
            </div>
            <div class="legend">
              <div v-for="item in workflowDist" :key="item.state" class="legend-line">
                <span class="dot" :style="{ background: item.color }"></span>
                <span>{{ item.label }}</span>
                <span class="legend-val">{{ item.count }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="card mon-card" data-analysis-define>
          <div class="sub-hd">工作流定义统计（按用户）</div>
          <p v-if="!defineUsers.length" class="hint">暂无工作流定义</p>
          <div v-else class="bar-list">
            <div v-for="user in defineUsers" :key="user.name" class="bar-row">
              <span class="bar-name" :title="user.name">{{ user.name }}</span>
              <span class="bar-track"><span class="bar-fill" :style="{ width: barWidth(user.count) }"></span></span>
              <span class="bar-val">{{ user.count }}</span>
            </div>
          </div>
        </div>
      </div>
      <p v-else-if="!analysisBusy" class="hint" data-analysis-empty>暂无统计数据</p>
    </section>

    <!-- ② 运行时节点（datara 自有 ZK 注册节点，保留原状） -->
    <section class="panel" data-node-section>
      <div class="panel-hd">
        <span class="sec-head">运行时节点</span>
        <span class="pill info">datara 自有</span>
        <span class="spacer"></span>
        <span class="hint">master / worker / ssh 三类节点的心跳与指标快照，非实时值</span>
      </div>

      <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时表格须保留 -->
      <div v-if="error" class="err-box" role="alert" data-error>
        <span>{{ error }}</span>
        <button type="button" class="op-btn retry" :disabled="busy" @click="reloadNodes">重试</button>
      </div>

      <div v-if="busy" class="skeleton-wrap" aria-hidden="true">
        <div class="skeleton sk-row" style="width:28%"></div>
        <div class="skeleton sk-row" style="width:66%"></div>
        <div class="skeleton sk-row" style="width:48%"></div>
      </div>

      <div v-else-if="!snapshot && !error" class="panel empty" data-empty>
        <div class="e-title">暂无监控数据</div>
        <div class="e-hint">还没有任何节点上报心跳或指标快照。</div>
      </div>

      <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
      <div v-else-if="snapshot && snapshot.nodes.length === 0 && !error" class="panel empty" data-empty>
        <div class="e-title">暂无节点上报</div>
        <div class="e-hint">当前没有节点上报指标快照。</div>
      </div>

      <template v-else-if="snapshot && snapshot.nodes.length > 0">
        <div class="tbl-toolbar">
          <span class="pill info">{{ visibleNodes.length }}</span>
          <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索节点、模块或标签">
          <span class="spacer"></span>
        </div>
        <table class="tbl" data-node-list>
          <thead>
            <tr>
              <th>模块</th><th>节点</th><th>CPU</th><th>内存 %</th><th>内存 MB</th><th>磁盘</th>
              <th>心跳</th><th>指标态</th><th>最近上报</th><th>标签</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in visibleNodes" :key="`${row.module}:${row.node}`" :data-node="`${row.module}:${row.node}`">
              <td data-module>{{ moduleLabel(row.module) }}</td>
              <td data-node-name>{{ row.node }}</td>
              <td data-cpu>{{ percent(row.cpu) }}</td>
              <td data-mem>{{ percent(row.mem) }}</td>
              <td data-mem-mb>{{ memMb(row.memUsedMb, row.memTotalMb) }}</td>
              <td data-disk>{{ percent(row.disk) }}</td>
              <td :data-heartbeat="row.heartbeat">{{ heartbeatLabel(row.heartbeat) }}</td>
              <td :data-metric-state="row.metricState">{{ metricStateLabel(row.metricState) }}</td>
              <td data-last-seen>{{ row.lastSeen || '—' }}</td>
              <td data-tags>{{ row.tags.join('、') || '—' }}</td>
            </tr>
            <tr v-if="visibleNodes.length === 0"><td colspan="10">无匹配节点</td></tr>
          </tbody>
        </table>
      </template>
    </section>

    <!-- ③ Master 节点（海豚 MonitorController；点击下钻运行中工作流实例） -->
    <section class="panel" data-master-section>
      <div class="panel-hd">
        <span class="sec-head">Master 节点</span>
        <span class="pill info" :data-master-count="serverRows.MASTER?.length ?? 0">{{ serverRows.MASTER?.length ?? 0 }}</span>
        <span class="spacer"></span>
        <span class="hint">心跳超时由后端判定（默认 30s，可配），超时标记离线</span>
      </div>
      <div v-if="serverErrors.MASTER" class="err-box" role="alert" data-master-error>
        <span>{{ serverErrors.MASTER }}</span>
        <button type="button" class="op-btn retry" :disabled="serversLoading" @click="loadServers('MASTER')">重试</button>
      </div>
      <p v-else-if="serverRows.MASTER === null" class="hint" data-master-empty>暂无 master 节点数据</p>
      <template v-else>
        <table class="tbl" data-master-list>
          <thead>
            <tr>
              <th>地址</th><th>心跳</th><th>最近心跳</th><th>CPU</th><th>内存</th><th>磁盘</th>
              <th>负载</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in serverRows.MASTER" :key="serverKey(row)" :data-master="serverKey(row)">
              <td data-addr>{{ row.host }}:{{ row.port }}</td>
              <td :data-heartbeat="row.heartbeatState">{{ dsHeartbeatLabel(row.heartbeatState) }}</td>
              <td data-last-heartbeat>{{ row.lastHeartbeatTime || '—' }}</td>
              <td data-cpu>{{ percent(row.cpuUsage) }}</td>
              <td data-mem>{{ percent(row.memoryUsage) }}</td>
              <td data-disk>{{ percent(row.diskUsage) }}</td>
              <td data-load>{{ percent(row.loadAverage) }}</td>
              <td data-server-status>{{ row.serverStatus || '—' }}</td>
              <td>
                <button type="button" class="op-btn" data-drill @click="toggleDrill('master', serverKey(row))">运行中实例</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="drill && drill.kind === 'master'" class="drill" data-drill-panel data-drill-kind="master">
          <div class="sub-hd">
            <span>Master {{ drill.address }} · 运行中工作流实例</span>
            <button type="button" class="op-btn" data-drill-close @click="closeDrill">收起</button>
          </div>
          <p v-if="drillBusy" class="loading" role="status">正在读取运行中实例…</p>
          <div v-else-if="drillError" class="err-box" role="alert" data-drill-error>{{ drillError }}</div>
          <p v-else-if="!drillRows.length" class="hint" data-drill-empty>当前没有运行中的工作流实例</p>
          <table v-else class="tbl" data-drill-list>
            <thead><tr><th>名称</th><th>工作流定义</th><th>状态</th><th>开始时间</th><th>运行次数</th></tr></thead>
            <tbody>
              <tr v-for="(row, index) in drillRows" :key="index" :data-drill-row="index">
                <td data-executor-name>{{ text(row.name) }}</td>
                <td data-executor-definition>{{ text(row.workflowDefinitionCode) }}</td>
                <td data-executor-state>{{ text(row.state) }}</td>
                <td data-executor-start>{{ text(row.startTime) }}</td>
                <td data-executor-run-times>{{ text(row.runTimes) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>

    <!-- ④ Worker 节点（海豚 MonitorController；点击下钻运行中任务实例） -->
    <section class="panel" data-worker-section>
      <div class="panel-hd">
        <span class="sec-head">Worker 节点</span>
        <span class="pill info" :data-worker-count="serverRows.WORKER?.length ?? 0">{{ serverRows.WORKER?.length ?? 0 }}</span>
        <span class="spacer"></span>
        <span class="hint">运行位置由 worker 分组决定（部署运维 → Worker 分组）</span>
      </div>
      <div v-if="serverErrors.WORKER" class="err-box" role="alert" data-worker-error>
        <span>{{ serverErrors.WORKER }}</span>
        <button type="button" class="op-btn retry" :disabled="serversLoading" @click="loadServers('WORKER')">重试</button>
      </div>
      <p v-else-if="serverRows.WORKER === null" class="hint" data-worker-empty>暂无 worker 节点数据</p>
      <template v-else>
        <table class="tbl" data-worker-list>
          <thead>
            <tr>
              <th>地址</th><th>Worker 分组</th><th>心跳</th><th>最近心跳</th><th>CPU</th>
              <th>内存</th><th>磁盘</th><th>负载</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in serverRows.WORKER" :key="serverKey(row)" :data-worker="serverKey(row)">
              <td data-addr>{{ row.host }}:{{ row.port }}</td>
              <td data-worker-group>{{ row.workerGroup || '—' }}</td>
              <td :data-heartbeat="row.heartbeatState">{{ dsHeartbeatLabel(row.heartbeatState) }}</td>
              <td data-last-heartbeat>{{ row.lastHeartbeatTime || '—' }}</td>
              <td data-cpu>{{ percent(row.cpuUsage) }}</td>
              <td data-mem>{{ percent(row.memoryUsage) }}</td>
              <td data-disk>{{ percent(row.diskUsage) }}</td>
              <td data-load>{{ percent(row.loadAverage) }}</td>
              <td data-server-status>{{ row.serverStatus || '—' }}</td>
              <td>
                <button type="button" class="op-btn" data-drill @click="toggleDrill('worker', serverKey(row))">运行中实例</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="drill && drill.kind === 'worker'" class="drill" data-drill-panel data-drill-kind="worker">
          <div class="sub-hd">
            <span>Worker {{ drill.address }} · 运行中任务实例</span>
            <button type="button" class="op-btn" data-drill-close @click="closeDrill">收起</button>
          </div>
          <p v-if="drillBusy" class="loading" role="status">正在读取运行中实例…</p>
          <div v-else-if="drillError" class="err-box" role="alert" data-drill-error>{{ drillError }}</div>
          <p v-else-if="!drillRows.length" class="hint" data-drill-empty>当前没有运行中的任务实例</p>
          <table v-else class="tbl" data-drill-list>
            <thead><tr><th>名称</th><th>任务类型</th><th>工作流实例</th><th>开始时间</th></tr></thead>
            <tbody>
              <tr v-for="(row, index) in drillRows" :key="index" :data-drill-row="index">
                <td data-executor-name>{{ text(row.name) }}</td>
                <td data-executor-task-type>{{ text(row.taskType) }}</td>
                <td data-executor-workflow>{{ text(row.workflowInstanceName) }}</td>
                <td data-executor-start>{{ text(row.startTime) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>

    <!-- ⑤ 数据库连接池（海豚元数据库，非 dbx 业务库） -->
    <section class="panel" data-db-section>
      <div class="panel-hd">
        <span class="sec-head">数据库连接池</span>
        <span class="pill info">任务元数据库</span>
        <span class="spacer"></span>
        <span class="hint">展示任务元数据库（t_ds_ 所在库）连接池状态，不含业务数据连接</span>
      </div>
      <div v-if="dbError" class="err-box" role="alert" data-db-error>
        <span>{{ dbError }}</span>
        <button type="button" class="op-btn retry" :disabled="dbLoading" @click="loadDatabases">重试</button>
      </div>
      <p v-else-if="databases === null" class="hint" data-db-empty>暂无数据库监控数据</p>
      <table v-else class="tbl" data-db-list>
        <thead>
          <tr><th>类型</th><th>状态</th><th>最大连接</th><th>最大已用</th><th>当前连接</th><th>活跃连接</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in databases" :key="index" :data-db-type="row.dbType">
            <td data-db-type-name>{{ row.dbType }}</td>
            <td :data-db-state="row.state">{{ row.state === 'YES' ? '正常' : '异常' }}</td>
            <td data-max-connections>{{ row.maxConnections ?? '—' }}</td>
            <td data-max-used>{{ row.maxUsedConnections ?? '—' }}</td>
            <td data-threads-connections>{{ row.threadsConnections ?? '—' }}</td>
            <td data-threads-running>{{ row.threadsRunningConnections ?? '—' }}</td>
            <td data-db-date>{{ row.date || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- ⑥ 告警服务（可选：仅展示存活状态；告警能力由 datara 承担，见 10.10 R6） -->
    <section class="panel" data-alert-section>
      <div class="panel-hd">
        <span class="sec-head">告警服务</span>
        <span class="pill info">可选</span>
        <span class="spacer"></span>
        <span class="hint">仅展示告警服务存活状态；告警规则与发送由平台统一承载</span>
      </div>
      <div v-if="serverErrors.ALERT_SERVER" class="err-box" role="alert" data-alert-error>
        <span>{{ serverErrors.ALERT_SERVER }}</span>
        <button type="button" class="op-btn retry" :disabled="serversLoading" @click="loadServers('ALERT_SERVER')">重试</button>
      </div>
      <p v-else-if="serverRows.ALERT_SERVER === null" class="hint" data-alert-empty>暂无告警服务数据</p>
      <table v-else class="tbl" data-alert-list>
        <thead><tr><th>地址</th><th>心跳</th><th>最近心跳</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="row in serverRows.ALERT_SERVER" :key="serverKey(row)" :data-alert="serverKey(row)">
            <td data-addr>{{ row.host }}:{{ row.port }}</td>
            <td :data-heartbeat="row.heartbeatState">{{ dsHeartbeatLabel(row.heartbeatState) }}</td>
            <td data-last-heartbeat>{{ row.lastHeartbeatTime || '—' }}</td>
            <td data-server-status>{{ row.serverStatus || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <p class="lock-tip" role="note" data-metric-note>
      口径：空指标如实显示 —；heartbeat=unknown 表示无法判定在线状态（ZK 不可用或海豚未上报）；指标态 过期=上报时间超出 90s TTL，不支持=该模块（ssh）不上报指标；
      海豚 master/worker 心跳三态由后端按超时阈值（默认 30s，可配）判定；海豚首页 /home 不进 iframe，三张统计卡由 datara 自有图表渲染。手动刷新，不做轮询。
    </p>
  </main>
</template>

<script setup lang="ts">
/**
 * 监控中心（部署运维 → /dep/monitor）组件段。
 *
 * §10.11：在 datara 自有运行时节点监控之上，合并展示海豚 master / worker / DB
 * 与海豚首页 /home 的三张统计卡。监控数据**只读**，不暴露海豚监控大盘的任何写操作。
 *
 * 契约面：
 *  - `createMonitorContract().fetchMonitorNodes()`（B3 monitorApi，datara 自有节点）；
 *  - `orchestrationApi.fetchMonitorServers/fetchMonitorDatabases/fetch*Executors`（海豚 MonitorController）；
 *  - `orchestrationApi.fetchTaskStateCount/fetchWorkflowStateCount/fetchDefineUserCount`（海豚 DataAnalysisController）。
 *
 * 数据红线：
 *  - 仅经契约层取数，禁直连 fetch/axios；
 *  - 空指标如实显示 —，心跳三态给可辨识文案，不虚构实时性；
 *  - 各区块独立 busy/error，一处失败不空白其他区块；
 *  - 手动刷新，不做高频轮询；
 *  - projectCode 由后端按 datara 项目解析，前端只传 projectId，不接受任意 projectCode。
 */
import { computed, onMounted, ref } from 'vue'
import DepOpsSubNav from '../../components/DepOpsSubNav.vue'
import { createMonitorContract, type MonitorHeartbeat, type MonitorMetricState, type MonitorSnapshot } from '../../services/rebuild/monitorApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'
import {
  orchestrationApi,
  type OrchestrationDatabaseRow,
  type OrchestrationExecutorRow,
  type OrchestrationNodeType,
  type OrchestrationServerRow,
  type OrchestrationStateCountRow,
  type OrchestrationTaskStateCount,
  type OrchestrationWorkflowStateCount,
} from '../../services/rebuild/orchestrationApi'

const monitor = createMonitorContract()

/* ---------- ② 运行时节点（datara 自有） ---------- */

const snapshot = ref<MonitorSnapshot | null>(null)
const busy = ref(false)
const error = ref('')

/** D13 列表搜索：前端过滤节点行，不触发后端。 */
const filterKeyword = ref('')
const visibleNodes = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  const nodes = snapshot.value?.nodes ?? []
  if (keyword === '') return nodes
  return nodes.filter(
    (row) =>
      row.module.toLowerCase().includes(keyword) ||
      row.node.toLowerCase().includes(keyword) ||
      row.tags.join('、').toLowerCase().includes(keyword),
  )
})

/* ---------- ③④⑥ 海豚 master / worker / alert server ---------- */

type DrillKind = 'master' | 'worker'

const serverRows = ref<Record<OrchestrationNodeType, OrchestrationServerRow[] | null>>({
  MASTER: null,
  WORKER: null,
  ALERT_SERVER: null,
})
const serverErrors = ref<Record<OrchestrationNodeType, string>>({ MASTER: '', WORKER: '', ALERT_SERVER: '' })
const serversLoading = ref(false)

const drill = ref<{ kind: DrillKind; address: string } | null>(null)
const drillRows = ref<OrchestrationExecutorRow[]>([])
const drillError = ref('')
const drillBusy = ref(false)

/* ---------- ⑤ 海豚元数据库连接池 ---------- */

const databases = ref<OrchestrationDatabaseRow[] | null>(null)
const dbError = ref('')
const dbLoading = ref(false)

/* ---------- ① 任务运行监控（海豚首页 /home） ---------- */

interface AnalysisSnapshot {
  task: OrchestrationTaskStateCount
  workflow: OrchestrationWorkflowStateCount
  define: { count: number; userList: Record<string, unknown>[] }
}

const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const startDate = ref('')
const endDate = ref('')
const analysis = ref<AnalysisSnapshot | null>(null)
const analysisBusy = ref(false)
const analysisError = ref('')

const projectId = computed(() => Number(selectedProject.value) || null)

interface StateMeta {
  state: string
  label: string
  color: string
}

/** 合并海豚返回计数后的行（固定顺序，count=0 也保留）。 */
interface StateCountMeta extends StateMeta {
  count: number
}

/** 海豚状态全集固定顺序（实测）；count=0 也不丢项。 */
const TASK_STATE_META: StateMeta[] = [
  { state: 'SUBMITTED_SUCCESS', label: '已提交', color: 'var(--primary)' },
  { state: 'RUNNING_EXECUTION', label: '运行中', color: 'var(--success)' },
  { state: 'PAUSE', label: '暂停', color: 'var(--warn)' },
  { state: 'FAILURE', label: '失败', color: 'var(--danger)' },
  { state: 'SUCCESS', label: '成功', color: 'var(--cyan)' },
  { state: 'NEED_FAULT_TOLERANCE', label: '待容错', color: 'var(--purple)' },
  { state: 'KILL', label: '已停止', color: 'var(--text-3)' },
  { state: 'DELAY_EXECUTION', label: '延迟执行', color: 'var(--primary-dark)' },
  { state: 'FORCED_SUCCESS', label: '强制成功', color: 'var(--info)' },
  { state: 'DISPATCH', label: '分发中', color: 'var(--primary)' },
]

const WORKFLOW_STATE_META: StateMeta[] = [
  { state: 'SUBMITTED_SUCCESS', label: '已提交', color: 'var(--primary)' },
  { state: 'RUNNING_EXECUTION', label: '运行中', color: 'var(--success)' },
  { state: 'READY_PAUSE', label: '准备暂停', color: 'var(--warn)' },
  { state: 'PAUSE', label: '暂停', color: 'var(--warn)' },
  { state: 'READY_STOP', label: '准备停止', color: 'var(--purple)' },
  { state: 'STOP', label: '停止', color: 'var(--text-3)' },
  { state: 'FAILURE', label: '失败', color: 'var(--danger)' },
  { state: 'SUCCESS', label: '成功', color: 'var(--cyan)' },
  { state: 'SERIAL_WAIT', label: '串行等待', color: 'var(--primary-dark)' },
  { state: 'FAILOVER', label: '失败重试', color: 'var(--info)' },
]

/** 按固定顺序合并海豚返回的状态计数；未返回的状态补 0，不丢项。 */
function withMeta(meta: StateMeta[], rows: OrchestrationStateCountRow[] | undefined): StateCountMeta[] {
  const counts = new Map((rows ?? []).map((row) => [row.state, row.count]))
  return meta.map((item) => ({ ...item, count: counts.get(item.state) ?? 0 }))
}

const taskDist = computed(() => withMeta(TASK_STATE_META, analysis.value?.task.taskInstanceStatusCounts))
const workflowDist = computed(() => withMeta(WORKFLOW_STATE_META, analysis.value?.workflow.workflowInstanceStatusCounts))

/** conic-gradient 环形图（对标 IndBoardView 的 donut 范式）。 */
function donutGradient(dist: StateCountMeta[]): string {
  const total = dist.reduce((sum, item) => sum + item.count, 0) || 1
  let acc = 0
  const segs = dist.map((item) => {
    const from = (acc / total) * 100
    acc += item.count
    const to = (acc / total) * 100
    return `${item.color} ${from.toFixed(2)}% ${to.toFixed(2)}%`
  })
  return `conic-gradient(${segs.join(',')})`
}

const taskDonut = computed(() => donutGradient(taskDist.value))
const workflowDonut = computed(() => donutGradient(workflowDist.value))

const defineUsers = computed(() =>
  (analysis.value?.define.userList ?? []).map((row) => ({
    name: String(row.userName ?? ''),
    count: Number(row.count ?? 0),
  })),
)
const defineMax = computed(() => Math.max(1, ...defineUsers.value.map((row) => row.count)))
const barWidth = (count: number): string => `${Math.round((count / defineMax.value) * 100)}%`

/* ---------- 展示辅助 ---------- */

const MODULE_LABEL: Record<string, string> = { master: 'master', worker: 'worker', ssh: 'ssh' }
const moduleLabel = (m: string): string => MODULE_LABEL[m] ?? m

/** 心跳：unknown 须可辨识（ZK 不可用、无法判定），不虚构在线状态；后端 ssh 行的心跳串如实透出。 */
const heartbeatLabel = (h: MonitorHeartbeat): string => {
  if (h === 'online') return '在线'
  if (h === 'offline') return '离线'
  if (h === 'unknown') return '未知（无法判定）'
  return h
}

/** 海豚节点心跳三态：与 datara 自有节点统一文案。 */
const dsHeartbeatLabel = (h: string): string => {
  if (h === 'online') return '在线'
  if (h === 'offline') return '离线'
  if (h === 'unknown') return '未知（无法判定）'
  return h
}

/** 指标态：stale / unsupported 须可辨识，不与 fresh 混排。 */
const metricStateLabel = (s: MonitorMetricState): string => {
  if (s === 'fresh') return '新鲜'
  if (s === 'stale') return '过期'
  if (s === 'unsupported') return '不支持'
  return s
}

const percent = (v: number | null | undefined): string => (v === null || v === undefined ? '—' : `${v}%`)
const memMb = (used: number | null, total: number | null): string =>
  used === null && total === null ? '—' : `${used ?? '—'} / ${total ?? '—'}`
const text = (v: unknown): string => (v === null || v === undefined ? '—' : String(v))
const serverKey = (row: OrchestrationServerRow): string => `${row.host}:${row.port}`

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 非 0 包络码须随错误信息透出（契约层经 preserveEnvelopeCode 保码）。 */
const errorText = (e: unknown): string => {
  const code = (e as { code?: number | string } | null)?.code
  return code !== undefined && code !== 0 ? `加载失败（code ${code}）：${message(e)}` : message(e)
}

/* ---------- 取数 ---------- */

const anyBusy = computed(() => busy.value || serversLoading.value || dbLoading.value || analysisBusy.value)

/** 刷新按钮统一重载全部区块；各区块独立失败，互不空白。 */
async function reloadAll(): Promise<void> {
  await Promise.allSettled([reloadNodes(), loadServers('MASTER'), loadServers('WORKER'), loadServers('ALERT_SERVER'), loadDatabases()])
}

async function reloadNodes(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    snapshot.value = await monitor.fetchMonitorNodes()
  } catch (e) {
    // 刷新失败保留上一次快照，不空白表格。
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

async function loadServers(nodeType: OrchestrationNodeType): Promise<void> {
  serversLoading.value = true
  serverErrors.value[nodeType] = ''
  try {
    serverRows.value[nodeType] = await orchestrationApi.fetchMonitorServers(nodeType)
    if (drill.value && drill.value.kind === (nodeType === 'WORKER' ? 'worker' : 'master') && !serverRows.value[nodeType]?.some((row) => serverKey(row) === drill.value?.address)) {
      closeDrill()
    }
  } catch (e) {
    serverErrors.value[nodeType] = errorText(e)
  } finally {
    serversLoading.value = false
  }
}

async function loadDatabases(): Promise<void> {
  dbLoading.value = true
  dbError.value = ''
  try {
    databases.value = await orchestrationApi.fetchMonitorDatabases()
  } catch (e) {
    dbError.value = errorText(e)
  } finally {
    dbLoading.value = false
  }
}

async function toggleDrill(kind: DrillKind, address: string): Promise<void> {
  if (drill.value?.kind === kind && drill.value.address === address) {
    closeDrill()
    return
  }
  drill.value = { kind, address }
  drillRows.value = []
  drillError.value = ''
  drillBusy.value = true
  try {
    drillRows.value =
      kind === 'master'
        ? await orchestrationApi.fetchMasterWorkflowExecutors(address)
        : await orchestrationApi.fetchWorkerTaskExecutors(address)
  } catch (e) {
    drillError.value = errorText(e)
  } finally {
    drillBusy.value = false
  }
}

function closeDrill(): void {
  drill.value = null
  drillRows.value = []
  drillError.value = ''
}

/** 项目下拉：默认取第一项；projectCode 由后端解析，前端只传 projectId。 */
async function loadProjects(): Promise<void> {
  try {
    projects.value = (await listProjects()).list
    selectedProject.value = String(projects.value[0]?.id ?? '')
  } catch (e) {
    analysisError.value = errorText(e)
  }
}

async function loadAnalysis(): Promise<void> {
  if (!projectId.value) return
  analysisBusy.value = true
  analysisError.value = ''
  try {
    const [task, workflow, define] = await Promise.all([
      orchestrationApi.fetchTaskStateCount(projectId.value, startDate.value || undefined, endDate.value || undefined),
      orchestrationApi.fetchWorkflowStateCount(projectId.value, startDate.value || undefined, endDate.value || undefined),
      orchestrationApi.fetchDefineUserCount(projectId.value),
    ])
    analysis.value = { task, workflow, define }
  } catch (e) {
    // 失败保留上一次统计，仅透出错误。
    analysisError.value = errorText(e)
  } finally {
    analysisBusy.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  await reloadAll()
  if (projectId.value) await loadAnalysis()
})
</script>

<style scoped>
/* 仅保留语义化状态着色与本页私有版式；通用版式/令牌一律走全局设计系统 */
td[data-heartbeat='unknown'] { color: var(--warn); }
td[data-heartbeat='offline'] { color: var(--danger); }
td[data-metric-state='stale'] { color: var(--warn); }
td[data-metric-state='unsupported'] { color: var(--text-3); }
td[data-db-state]:not([data-db-state='YES']) { color: var(--danger); }

.skeleton-wrap { display: grid; gap: 10px; }

/* 统计卡：环形图 + 图例（对标 IndBoardView 的 donut 范式） */
.mon-card { display: grid; gap: 10px; align-content: start; }
.donut-wrap { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.donut { width: 132px; height: 132px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.donut-center {
  width: 88px; height: 88px; border-radius: 50%; background: var(--card);
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px;
}
.donut-center b { font-size: 16px; }
.donut-center span { font-size: 10px; color: var(--text-3); }
.legend { flex: 1; min-width: 150px; display: flex; flex-direction: column; gap: 6px; }
.legend-line { display: flex; align-items: center; gap: 7px; font-size: 12px; }
.legend-line .dot { width: 9px; height: 9px; border-radius: 3px; flex-shrink: 0; }
.legend-val { margin-left: auto; color: var(--text-2); font-size: 11.5px; }

/* 工作流定义按用户柱状 */
.bar-list { display: grid; gap: 7px; }
.bar-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.bar-name { width: 96px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.bar-track { flex: 1; height: 8px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.bar-fill { display: block; height: 100%; background: var(--primary); border-radius: 4px; }
.bar-val { width: 34px; text-align: right; color: var(--text-2); font-size: 11.5px; }

/* 下钻运行中实例 */
.drill { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 10px; }
.drill .sub-hd { justify-content: space-between; }
</style>
