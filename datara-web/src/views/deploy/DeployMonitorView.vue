<script setup lang="ts">
/**
 * M16 集群监控（/dep/monitor · 原型 m16-deploy.js #/dep/monitor · 设计文档 U4）
 * 图为主：泳道拓扑工作台（GraphWorkbench + topoProfile）；卡片为辅：
 * 顶部统计条 + 资源明细折叠区（组件监控卡片 + 主机资源明细表 + CPU/内存趋势 + 服务清单）；
 * 主机「详情」弹窗：三环形仪表 + 承载组件 + 最近节点相关告警（deployAlarms）。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { isMock } from '../../services'
import type { Server, Component, DeployAlarm } from '../../services/types'
import { topoProfile } from '../../graph/profiles'
import GraphWorkbench from '../../graph/workbench/GraphWorkbench.vue'
import { fetchMonitorNodes, listRuntimeNodes, type MonitorNodeRow } from '../../services/graphApi'

/* ---- 拓扑区块折叠开关（默认展开，仅控制明细区显示，topoProfile 为常量直接传 prop） ---- */
const detailOpen = ref(true)

const router = useRouter()

const servers = ref<Server[]>([])
const comps = ref<Component[]>([])
const alarms = ref<DeployAlarm[]>([])

async function reload() {
  if (isMock) {
    // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用
    servers.value = [...((await dataStore.list<Server>('servers')) ?? [])]
    comps.value = [...((await dataStore.list<Component>('components')) ?? [])]
    alarms.value = [...((await dataStore.list<DeployAlarm>('deployAlarms')) ?? [])]
  } else {
    /* F56d real：主机节点走后端注册表 t_runtime_node；组件监控/告警为 mock 演示数据源，
       real 显示空态（组件安装/告警管理属后续迭代） */
    try {
      const nodes = await listRuntimeNodes()
      servers.value = nodes.map((n) => ({
        id: String(n.id),
        name: n.name,
        ip: n.host,
        cpu: '-',
        mem: '-',
        disk: '-',
        os: '-',
        role: n.kind || '-',
        status: n.status === 'offline' ? 'offline' : 'online',
      }))
    } catch { /* 后端未就绪时保留空态 */ }
    comps.value = []
    alarms.value = []
  }
  computeMetrics()
}
onMounted(reload)

/* ---- I7 F55 真实节点状态叠加：/monitor/nodes 30s 轮询（master/worker/ssh 实况徽标） ---- */
const realNodes = ref<MonitorNodeRow[]>([])
const realTimer = ref<number | null>(null)
async function reloadReal() {
  try {
    realNodes.value = (await fetchMonitorNodes()).nodes
  } catch { /* 后端未就绪保留上次数据 */ }
  realTimer.value = window.setTimeout(reloadReal, 30_000)
}
onMounted(reloadReal)
onBeforeUnmount(() => {
  if (realTimer.value != null) window.clearTimeout(realTimer.value)
})
const realStat = computed(() => {
  const by = (m: string) => realNodes.value.filter((n) => n.module === m)
  return {
    master: by('master'), worker: by('worker'), ssh: by('ssh'),
    onlineOf: (list: MonitorNodeRow[]) => list.filter((n) => n.heartbeat === 'online').length,
  }
})
function moduleLabel(m: string): string {
  return m === 'master' ? 'Master 主控' : m === 'worker' ? 'Worker 执行' : 'SSH 节点'
}

/* ---- 节点资源画像：基础值 + 渲染期微抖动（对齐原型 A._metricBase/_computeMetrics） ---- */
interface NodeMetric {
  cpu: number
  mem: number
  disk: number
}
const METRIC_BASE: Record<string, NodeMetric> = {
  'master-01': { cpu: 38, mem: 47, disk: 52 },
  'node-01': { cpu: 41, mem: 56, disk: 66 },
  'node-02': { cpu: 79, mem: 63, disk: 58 },
  'node-03': { cpu: 46, mem: 59, disk: 82 },
  'edge-01': { cpu: 12, mem: 24, disk: 38 },
}
const metrics = ref<Record<string, NodeMetric>>({})

function computeMetrics(): void {
  const out: Record<string, NodeMetric> = {}
  for (const sv of servers.value) {
    const b = METRIC_BASE[sv.name] ?? { cpu: 30, mem: 40, disk: 50 }
    const jitter = sv.status === 'online' ? Math.round((Math.random() - 0.5) * 6) : 0
    out[sv.id] = {
      cpu: Math.max(1, Math.min(99, b.cpu + jitter)),
      mem: Math.max(1, Math.min(99, b.mem + jitter)),
      disk: Math.max(1, Math.min(99, b.disk + jitter)),
    }
  }
  metrics.value = out
}
function refresh(): void {
  computeMetrics()
  ElMessage.success('指标已刷新（Prometheus 采集，15s 周期）')
}
function goAlarm(): void {
  router.push('/dep/alarm')
}
function goLog(): void {
  router.push('/dep/log')
}

/* ---- 统计条 ---- */
const onlineSv = computed(() => servers.value.filter((s) => s.status === 'online'))
const runComps = computed(() => comps.value.filter((c) => c.status === 'running'))
const avgCpu = computed(() => {
  const list = onlineSv.value
  if (!list.length) return 0
  return Math.round(list.reduce((s, sv) => s + (metrics.value[sv.id]?.cpu ?? 0), 0) / list.length)
})
const avgMem = computed(() => {
  const list = onlineSv.value
  if (!list.length) return 0
  return Math.round(list.reduce((s, sv) => s + (metrics.value[sv.id]?.mem ?? 0), 0) / list.length)
})
const diskAlarms = computed(
  () => onlineSv.value.filter((s) => (metrics.value[s.id]?.disk ?? 0) >= 80).length,
)

/* ---- 组件监控卡片指标条颜色 ---- */
function diskClsOf(id: string): string {
  const m = metrics.value[id]
  if (!m) return ''
  return m.disk >= 80 ? 'red' : m.disk >= 60 ? 'orange' : ''
}

/* ---- 主机资源明细行视图模型 ---- */
interface HostRow {
  sv: Server
  m: NodeMetric | null
  comps: string[]
}
const hostRows = computed<HostRow[]>(() =>
  servers.value.map((sv) => ({
    sv,
    m: sv.status === 'online' ? metrics.value[sv.id] ?? null : null,
    comps: runComps.value.filter((c) => c.nodes.join(',').includes(sv.ip)).map((c) => c.name),
  })),
)

/* ---- 服务运行清单（内置运行时 + 组件引用，对齐原型 svcDefs） ---- */
interface SvcDef {
  n: string
  r: string
  inst?: string
  ver?: string
  ref?: string
  builtin?: boolean
}
const SVC_DEFS: SvcDef[] = [
  { n: '平台核心服务', r: '运行时 · API / 引擎服务', inst: '2 实例', ver: 'v2.3.0', builtin: true },
  { n: '调度中心 DolphinScheduler', r: '运行时 · 工作流调度', inst: '1M + 3W', ver: 'v3.2.0', builtin: true },
  { n: '数据开发 IDE', r: '运行时 · 在线开发', inst: '2 实例', ver: 'v2.3.0', builtin: true },
  { n: 'Apache Doris', r: 'OLAP 引擎', ref: 'CP01' },
  { n: 'Flink', r: '流计算引擎', ref: 'CP03' },
  { n: 'Kafka', r: '消息队列', ref: 'CP02' },
  { n: 'ZooKeeper', r: '协调服务', ref: 'CP04' },
  { n: 'Redis', r: '缓存', ref: 'CP05' },
  { n: 'Prometheus + Grafana', r: '监控告警', ref: 'CP06' },
  { n: 'RocketMQ', r: '消息队列 · 国产备选', ref: 'CP07' },
  { n: 'HDFS + Hive', r: '离线数仓（规划）', ref: 'CP08' },
]
const svcRows = computed(() =>
  SVC_DEFS.map((s) => {
    const c = s.ref ? comps.value.find((x) => x.id === s.ref) ?? null : null
    const run = s.builtin ? true : !!(c && c.status === 'running')
    return {
      n: s.n,
      r: s.r,
      run,
      inst: run ? s.inst ?? (c ? `${c.nodes.length} 实例` : '—') : '—',
      ver: run ? s.ver ?? (c ? `v${c.version}` : '—') : '—',
    }
  }),
)

/* ---- 集群 CPU/内存 8 小时趋势（静态样例，对齐原型 Charts.line 数据） ---- */
const TREND = {
  labels: ['15:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00', '22:00'],
  cpu: [42, 45, 44, 49, 53, 58, 55, 51],
  mem: [55, 56, 57, 57, 60, 62, 61, 60],
}
function polyPoints(data: number[]): string {
  const x0 = 36
  const x1 = 368
  const y = (v: number) => 186 - v * 1.7
  return data
    .map((v, i) => `${(x0 + (i * (x1 - x0)) / (data.length - 1)).toFixed(1)},${y(v).toFixed(1)}`)
    .join(' ')
}

/* ---- 主机详情弹窗 ---- */
const detailVisible = ref(false)
const detailSv = ref<Server | null>(null)
const detailMetric = computed(() => (detailSv.value ? metrics.value[detailSv.value.id] ?? null : null))
const detailComps = computed(() => {
  const sv = detailSv.value
  if (!sv) return []
  return runComps.value.filter((c) => c.nodes.join(',').includes(sv.ip))
})
const detailTasks = computed(() => {
  const sv = detailSv.value
  if (!sv || sv.status !== 'online') return 0
  const last = Number(sv.ip.split('.')[3])
  return detailComps.value.length * 2 + (Number.isFinite(last) ? last % 9 : 0)
})
const detailAlarms = computed(() => {
  const sv = detailSv.value
  if (!sv) return []
  const names = new Set(detailComps.value.map((c) => c.name))
  return alarms.value.filter((a) => a.desc.includes(sv.ip) || names.has(a.comp)).slice(0, 3)
})
function openDetail(sv: Server): void {
  detailSv.value = sv
  detailVisible.value = true
}
const RING_R = 30
function ringDash(v: number): string {
  const c = 2 * Math.PI * RING_R
  return `${((v / 100) * c).toFixed(1)} ${c.toFixed(1)}`
}
function ringColor(kind: 'cpu' | 'mem' | 'disk', v: number): string {
  if (kind === 'disk') return v >= 80 ? '#e5484d' : v >= 60 ? '#d97706' : '#16a34a'
  if (kind === 'cpu') return v >= 75 ? '#d97706' : '#1668dc'
  return v >= 85 ? '#d97706' : '#7c3aed'
}

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
</script>

<template>
  <div class="page">
    <!-- 页头 + 顶部工具栏 -->
    <div class="page-head">
      <div>
        <div class="ph-title">集群监控</div>
        <div class="ph-desc">组件 / 主机资源水位监控（Prometheus 采集，15s 周期）；集群运行拓扑图见下方「集群拓扑（实时）」区块（原独立拓扑页已并入本页）</div>
      </div>
      <div class="ph-btns">
        <button class="op-btn" style="padding:7px 14px" @click="refresh">刷新</button>
        <button class="tb-new" @click="goAlarm">告警管理</button>
      </div>
    </div>

    <!-- 顶部统计条 -->
    <div class="stat-grid5">
      <div class="stat-card">
        <span class="type-icon" style="background:#475569">▤</span>
        <div><div class="stat-num">{{ servers.length }}</div><div class="stat-label">主机节点</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:var(--success)">✓</span>
        <div><div class="stat-num">{{ onlineSv.length }}/{{ servers.length }}</div><div class="stat-label">节点在线</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#1668dc">⚙</span>
        <div><div class="stat-num">{{ runComps.length }}/{{ comps.length }}</div><div class="stat-label">组件运行中</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#7c3aed">◔</span>
        <div><div class="stat-num">{{ avgCpu }}% / {{ avgMem }}%</div><div class="stat-label">CPU / 内存均值</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:var(--danger)">⚑</span>
        <div><div class="stat-num">{{ diskAlarms }}</div><div class="stat-label">磁盘告警节点（≥80%）</div></div>
      </div>
    </div>

    <!-- I7 F55 实时注册节点状态（/monitor/nodes 30s 轮询） -->
    <div class="card real-bar">
      <span class="real-title">实时注册节点</span>
      <span class="pill info">Master {{ realStat.onlineOf(realStat.master) }}/{{ realStat.master.length }}</span>
      <span class="pill off">Worker {{ realStat.onlineOf(realStat.worker) }}/{{ realStat.worker.length }}</span>
      <span class="pill warn">SSH {{ realStat.onlineOf(realStat.ssh) }}/{{ realStat.ssh.length }}</span>
      <span class="spacer" />
      <span v-for="n in realNodes" :key="n.module + ':' + n.node"
            class="mono node-chip" :class="{ 'node-off': n.heartbeat !== 'online' }"
            :title="`${moduleLabel(n.module)} · ${n.heartbeat}`">
        {{ n.node }}
      </span>
    </div>

    <!-- 集群拓扑工作台（图为主视角） -->
    <div class="topo-sec">
      <div class="topo-head">
        <div class="sec-title" style="margin-bottom:0">集群拓扑（实时）</div>
        <div class="topo-btns">
          <button class="op-btn" @click="refresh">刷新指标</button>
          <button class="op-btn" @click="detailOpen = !detailOpen">{{ detailOpen ? '收起明细' : '展开明细' }}</button>
        </div>
      </div>
      <div class="topo-wrap">
        <GraphWorkbench :profile="topoProfile" doc-id="topo_prod" />
      </div>
    </div>

    <!-- 资源明细（折叠区，v-show 保留组件状态） -->
    <div v-show="detailOpen">
      <div class="sec-title detail-cap">资源明细</div>
      <!-- 左：组件监控卡片 右：趋势 + 服务清单 -->
      <div class="monitor-grid">
      <div class="card sec" style="margin-bottom:0">
        <div class="sec-title">组件监控卡片</div>
        <div class="grid1">
          <div v-for="c in runComps" :key="c.id" class="cp-card">
            <div class="cp-head">
              <span class="type-icon sm" style="background:#0891b2">{{ c.name.slice(0, 2).toUpperCase() }}</span>
              <div style="flex:1">
                <b class="cp-name">{{ c.name }}</b>
                <div class="cell-sub">v{{ c.version }} · {{ c.role }} · 连续运行 {{ c.upDays }} 天</div>
              </div>
              <span class="pill" :class="c.health === '健康' ? 'ok' : 'warn'">{{ c.health }}</span>
            </div>
            <div class="cp-metrics">
              <div class="cp-m"><b>{{ c.cpu }}%</b><span>CPU</span></div>
              <div class="cp-m"><b>{{ c.mem }}%</b><span>内存</span></div>
              <div class="cp-m"><b>{{ c.qps ? c.qps : '—' }}</b><span>QPS</span></div>
              <div class="cp-m"><b>{{ c.nodes.length }}</b><span>实例</span></div>
            </div>
            <div class="cp-nodes">
              <span v-for="n in c.nodes" :key="n" class="mono node-chip">{{ n }}</span>
            </div>
          </div>
        </div>
        <div v-if="runComps.length === 0" class="empty">暂无运行中组件，请前往部署中心安装</div>
      </div>

      <div>
        <div class="card sec" style="margin-bottom:14px">
          <div class="sec-title">集群 CPU / 内存 8 小时趋势</div>
          <div class="legend">
            <span><i class="lg" style="background:#1668dc" />CPU 均值 %</span>
            <span><i class="lg" style="background:#7c3aed" />内存均值 %</span>
          </div>
          <svg viewBox="0 0 386 200" class="trend">
            <line x1="36" y1="186" x2="368" y2="186" stroke="var(--border)" />
            <line x1="36" y1="101" x2="368" y2="101" stroke="var(--border)" stroke-dasharray="3 4" />
            <line x1="36" y1="16" x2="368" y2="16" stroke="var(--border)" stroke-dasharray="3 4" />
            <text x="28" y="189" class="t-txt">0</text>
            <text x="24" y="104" class="t-txt">50</text>
            <text x="20" y="19" class="t-txt">100</text>
            <text v-for="(l, i) in TREND.labels" :key="l" :x="36 + i * ((368 - 36) / (TREND.labels.length - 1))" y="198" class="t-txt" text-anchor="middle">{{ l }}</text>
            <polyline :points="polyPoints(TREND.mem)" fill="none" stroke="#7c3aed" stroke-width="2" />
            <polyline :points="polyPoints(TREND.cpu)" fill="none" stroke="#1668dc" stroke-width="2" />
          </svg>
        </div>
        <div class="card sec" style="margin-bottom:0">
          <div class="sec-title">服务运行清单</div>
          <div class="svc-row head">
            <span style="flex:1">服务 / 组件</span><span style="width:56px">状态</span><span style="width:62px;text-align:right">实例</span><span style="width:66px;text-align:right">版本</span>
          </div>
          <div v-for="s in svcRows" :key="s.n" class="svc-row">
            <span style="flex:1"><b>{{ s.n }}</b><span class="cell-sub"> · {{ s.r }}</span></span>
            <span style="width:56px"><span class="pill" :class="s.run ? 'ok' : 'off'" style="font-size:10.5px">{{ s.run ? '运行中' : '未部署' }}</span></span>
            <span class="mono" style="width:62px;text-align:right;color:var(--text-2)">{{ s.inst }}</span>
            <span class="mono" style="width:66px;text-align:right;color:var(--text-2)">{{ s.ver }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 主机资源明细 -->
    <div class="card sec">
      <div class="sec-title">主机资源明细</div>
      <table class="tbl">
        <thead>
          <tr>
            <th>主机</th><th>规格</th><th>系统</th><th>承载组件</th><th>资源使用</th><th>状态</th><th style="width:120px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in hostRows" :key="r.sv.id">
            <td>
              <b>{{ r.sv.name }}</b>
              <div class="cell-sub mono">{{ r.sv.ip }} · {{ r.sv.role }}</div>
            </td>
            <td>{{ r.sv.cpu }} / {{ r.sv.mem }} / {{ r.sv.disk }}</td>
            <td>{{ r.sv.os }}</td>
            <td>
              <span v-if="r.comps.length" style="font-size:11.5px">{{ r.comps.join('、') }}</span>
              <span v-else style="color:var(--text-3)">—</span>
            </td>
            <td>
              <template v-if="r.m">
                <div class="mini-bar"><div class="bar" :class="diskClsOf(r.sv.id)" :style="{ width: r.m.disk + '%' }" /></div>
                <div class="cell-sub">CPU {{ r.m.cpu }}% · MEM {{ r.m.mem }}% · DISK {{ r.m.disk }}%</div>
              </template>
              <span v-else style="color:var(--text-3)">离线</span>
            </td>
            <td>
              <span class="st" :class="stCls(r.sv.status === 'online' ? 'online' : 'offline')">
                <span class="dot" />{{ stLabel(r.sv.status === 'online' ? 'online' : 'offline') }}
              </span>
            </td>
            <td>
              <button class="op-btn primary" @click="openDetail(r.sv)">详情</button>
              <button class="op-btn" @click="goLog">日志</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="hostRows.length === 0" class="empty">暂无主机节点数据</div>
    </div>
    </div>

    <!-- 主机详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detailSv ? `节点详情 - ${detailSv.name}（${detailSv.ip}）` : '节点详情'" width="560px">
      <div v-if="detailSv && detailMetric">
        <div v-if="detailSv.status !== 'online'" class="banner warn">
          <span class="b-ico">⚠</span><span>节点离线（最后心跳 2026-09-11 18:02），以下为最后采集快照。</span>
        </div>
        <div class="rings">
          <svg viewBox="0 0 76 76" class="ring">
            <circle cx="38" cy="38" :r="RING_R" class="ring-bg" />
            <circle cx="38" cy="38" :r="RING_R" class="ring-fg" :stroke="ringColor('cpu', detailMetric.cpu)" :stroke-dasharray="ringDash(detailMetric.cpu)" />
            <text x="38" y="37" class="ring-num">{{ detailMetric.cpu }}%</text>
            <text x="38" y="51" class="ring-label">CPU</text>
          </svg>
          <svg viewBox="0 0 76 76" class="ring">
            <circle cx="38" cy="38" :r="RING_R" class="ring-bg" />
            <circle cx="38" cy="38" :r="RING_R" class="ring-fg" :stroke="ringColor('mem', detailMetric.mem)" :stroke-dasharray="ringDash(detailMetric.mem)" />
            <text x="38" y="37" class="ring-num">{{ detailMetric.mem }}%</text>
            <text x="38" y="51" class="ring-label">内存</text>
          </svg>
          <svg viewBox="0 0 76 76" class="ring">
            <circle cx="38" cy="38" :r="RING_R" class="ring-bg" />
            <circle cx="38" cy="38" :r="RING_R" class="ring-fg" :stroke="ringColor('disk', detailMetric.disk)" :stroke-dasharray="ringDash(detailMetric.disk)" />
            <text x="38" y="37" class="ring-num">{{ detailMetric.disk }}%</text>
            <text x="38" y="51" class="ring-label">磁盘</text>
          </svg>
        </div>
        <div class="d-grid">
          <div>节点 IP：<span class="mono">{{ detailSv.ip }}</span></div>
          <div>角色：<b>{{ detailSv.role }}</b></div>
          <div>规格：{{ detailSv.cpu }} / {{ detailSv.mem }} / {{ detailSv.disk }}</div>
          <div>操作系统：{{ detailSv.os }}</div>
          <div>状态：{{ detailSv.status === 'online' ? '在线' : '离线' }}</div>
          <div>运行任务数：<b>{{ detailTasks }}</b> 个</div>
        </div>
        <div class="d-cap">承载组件（{{ detailComps.length }}）</div>
        <div v-if="detailComps.length">
          <div v-for="c in detailComps" :key="c.id" class="d-line">
            <span class="d-dot" />
            <b>{{ c.name }}</b>
            <span class="cell-sub" style="margin-left:6px">v{{ c.version }} · CPU {{ c.cpu }}% / MEM {{ c.mem }}%</span>
            <span class="pill" :class="c.health === '健康' ? 'ok' : 'warn'" style="margin-left:auto">{{ c.health }}</span>
          </div>
        </div>
        <div v-else class="cell-sub" style="margin-bottom:8px">无运行组件</div>
        <div class="d-cap" style="margin-top:10px">最近节点相关告警</div>
        <div v-if="detailAlarms.length">
          <div v-for="a in detailAlarms" :key="a.id" class="d-line" :class="a.status === 'pending' ? 'err' : 'ok'">
            <span class="d-ico">{{ a.level === 'err' ? '✕' : a.level === 'warn' ? '⚠' : 'ℹ' }}</span>
            <b>{{ a.title }}</b>
            <span class="cell-sub" style="margin-left:auto">{{ a.time }}</span>
          </div>
        </div>
        <div v-else class="cell-sub">近 7 日无相关告警</div>
      </div>
      <template #footer>
        <button class="op-btn" style="margin-right:8px" @click="detailVisible = false">关闭</button>
        <button class="tb-new" @click="detailVisible = false; goLog()">查看节点日志</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ---- I7 F55 实时注册节点横幅 ---- */
.real-bar{display:flex;align-items:center;gap:8px;padding:10px 14px;margin-bottom:14px;flex-wrap:wrap}
.real-bar .spacer{flex:1}
.real-title{font-weight:700;font-size:13px}
.node-chip.node-off{opacity:.45;text-decoration:line-through}
/* ---- 页头 / 统计 ---- */
.page-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:14px}
.ph-title{font-size:17px;font-weight:700}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:3px}
.ph-btns{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.stat-grid5{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:11px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:12px 14px}
.type-icon{width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;flex-shrink:0}
.type-icon.sm{width:28px;height:28px;font-size:10px;border-radius:7px}
.stat-num{font-size:18px;font-weight:700;line-height:1.25}
.stat-label{font-size:11px;color:var(--text-3)}
/* ---- 区块 ---- */
.topo-sec{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:12px 14px;margin-bottom:14px}
.topo-head{display:flex;align-items:center;margin-bottom:10px}
.topo-btns{margin-left:auto;display:flex;gap:8px}
.topo-wrap{height:560px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.detail-cap{margin-bottom:10px}
.monitor-grid{display:grid;grid-template-columns:62fr 38fr;gap:14px;align-items:start;margin-bottom:14px}
.sec{padding:15px;margin-bottom:14px}
.sec-title{font-weight:700;font-size:13.5px;margin-bottom:10px}
.grid1{display:grid;grid-template-columns:1fr;gap:11px}
.cp-card{border:1px solid var(--border);border-radius:9px;padding:11px 13px}
.cp-head{display:flex;align-items:center;gap:9px;margin-bottom:9px}
.cp-name{font-size:12.5px}
.cp-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:9px}
.cp-m{border:1px solid var(--border);border-radius:var(--radius);padding:6px 8px;text-align:center}
.cp-m b{display:block;font-size:14px;color:var(--primary)}
.cp-m span{font-size:10.5px;color:var(--text-3)}
.cp-nodes{display:flex;flex-wrap:wrap}
.node-chip{display:inline-block;padding:2px 8px;margin:0 6px 4px 0;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11px;background:#f8fafc}
/* ---- 趋势图 / 服务清单 ---- */
.legend{display:flex;gap:16px;font-size:11.5px;color:var(--text-2);margin-bottom:4px}
.lg{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}
.trend{width:100%;height:auto;display:block}
.t-txt{font-size:9px;fill:var(--text-3)}
.svc-row{display:flex;align-items:center;gap:8px;padding:6px 2px;border-bottom:1px dashed var(--border);font-size:12px}
.svc-row.head{color:var(--text-3);font-size:11px;border-bottom:1px solid var(--border);padding-bottom:7px}
/* ---- 主机表 ---- */
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.cell-sub{font-size:11px;color:var(--text-3)}
.mini-bar{height:6px;border-radius:4px;background:var(--bg);overflow:hidden;width:140px;margin-bottom:3px}
.mini-bar .bar{height:100%;border-radius:4px;background:var(--success)}
.mini-bar .bar.orange{background:var(--warn)}
.mini-bar .bar.red{background:var(--danger)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
/* ---- 详情弹窗 ---- */
.banner{display:flex;gap:8px;align-items:flex-start;border-radius:var(--radius);padding:9px 12px;font-size:12.5px;margin-bottom:12px}
.banner.warn{background:var(--warn-bg);color:var(--warn)}
.b-ico{font-weight:700}
.rings{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;justify-items:center;margin-bottom:14px}
.ring{width:92px;height:92px}
.ring-bg{fill:none;stroke:var(--bg);stroke-width:7}
.ring-fg{fill:none;stroke-width:7;stroke-linecap:round;transform:rotate(-90deg);transform-origin:38px 38px}
.ring-num{font-size:13px;font-weight:700;fill:var(--text);text-anchor:middle}
.ring-label{font-size:9px;fill:var(--text-3);text-anchor:middle}
.d-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px 20px;font-size:12.5px;margin-bottom:13px}
.d-cap{font-size:12px;color:var(--text-2);margin-bottom:6px}
.d-line{display:flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:6px;font-size:12.5px}
.d-line.err{border-color:rgba(229,72,77,.3);background:var(--danger-bg)}
.d-line.ok{border-color:rgba(22,163,74,.25);background:var(--success-bg)}
.d-dot{width:8px;height:8px;border-radius:2px;background:var(--cyan);flex-shrink:0}
.d-ico{font-weight:700}
.d-line.err .d-ico{color:var(--danger)}
.d-line.ok .d-ico{color:var(--success)}
</style>
