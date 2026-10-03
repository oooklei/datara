<script setup lang="ts">
/** 真实集群监控：ZK 在线性 + Redis 时效指标 + SSH 注册状态。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import GraphWorkbench from '../../graph/workbench/GraphWorkbench.vue'
import { topoProfile } from '../../graph/profiles'
import type { GraphDocument, GEdge, GNode } from '../../graph/model'
import { fetchMonitorNodes, type MonitorNodeRow } from '../../services/graphApi'

const nodes = ref<MonitorNodeRow[]>([])
const zkAvailable = ref(true)
const generatedAt = ref('')
const loading = ref(false)
const loadError = ref('')
let refreshTimer: number | null = null

/* 拓扑/明细上下分栏拖拽 */
const MIN_TOPOLOGY = 160
const MIN_TABLE = 180
const HANDLE_SPACE = 22 // 手柄高度 + 上下间距

const splitArea = ref<HTMLElement | null>(null)
const topologyHeight = ref(360)
const resizing = ref(false)
let onDragMove: ((ev: MouseEvent) => void) | null = null
let onDragEnd: (() => void) | null = null

function startResize(event: MouseEvent) {
  const area = splitArea.value
  if (!area || resizing.value) return
  event.preventDefault()
  resizing.value = true
  const startY = event.clientY
  const startHeight = topologyHeight.value
  const maxTopology = Math.max(MIN_TOPOLOGY + 120, area.clientHeight - MIN_TABLE - HANDLE_SPACE)
  onDragMove = (ev: MouseEvent) => {
    topologyHeight.value = Math.min(Math.max(startHeight + ev.clientY - startY, MIN_TOPOLOGY), maxTopology)
  }
  onDragEnd = () => {
    window.removeEventListener('mousemove', onDragMove!)
    window.removeEventListener('mouseup', onDragEnd!)
    onDragMove = null
    onDragEnd = null
    resizing.value = false
    document.body.classList.remove('row-resizing')
  }
  document.body.classList.add('row-resizing')
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function scheduleRefresh() {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  refreshTimer = window.setTimeout(refresh, 30_000)
}

async function refresh() {
  if (loading.value) return
  loading.value = true
  try {
    const result = await fetchMonitorNodes()
    nodes.value = result.nodes
    zkAvailable.value = result.zkAvailable
    generatedAt.value = result.generatedAt
    loadError.value = ''
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
    scheduleRefresh()
  }
}

onMounted(refresh)
onBeforeUnmount(() => {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  onDragEnd?.()
})

const online = computed(() => nodes.value.filter((node) => node.heartbeat === 'online').length)
const stale = computed(() => nodes.value.filter((node) => node.metricState === 'stale').length)
const offline = computed(() => nodes.value.filter((node) => node.heartbeat === 'offline').length)

function average(field: 'cpu' | 'mem' | 'disk'): string {
  const values = nodes.value.map((node) => node[field]).filter((value): value is number => value !== null)
  if (!values.length) return '-'
  return `${(values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)}%`
}

function nodeType(module: MonitorNodeRow['module']): string {
  return module === 'master' ? 'ds_master' : module === 'worker' ? 'ds_worker' : 'app'
}

function health(row: MonitorNodeRow): string {
  if (row.heartbeat === 'online' && row.metricState !== 'stale') return 'healthy'
  if (row.heartbeat === 'unknown' || row.metricState === 'stale') return 'warn'
  return 'fail'
}

const topology = computed<GraphDocument>(() => {
  const graphNodes: GNode[] = nodes.value.map((row, index) => ({
    id: `runtime-${row.module}-${row.node}`,
    type: nodeType(row.module),
    position: { x: 80 + (index % 4) * 220, y: 80 + Math.floor(index / 4) * 140 },
    lane: 'runtime',
    data: {
      name: row.node,
      comp: row.module,
      addr: row.node,
      health: health(row),
      cpu: row.cpu,
      mem: row.mem,
      disk: row.disk,
    },
  }))
  const masters = graphNodes.filter((node) => node.data.comp === 'master')
  const targets = graphNodes.filter((node) => node.data.comp !== 'master')
  const edges: GEdge[] = masters.flatMap((master) => targets.map((target) => ({
    id: `edge-${master.id}-${target.id}`,
    source: master.id,
    target: target.id,
    kind: 'flow' as const,
    label: target.data.comp === 'worker' ? '调度/状态' : 'SSH 路由',
  })))
  return {
    id: 'runtime-topology',
    name: '实时运行拓扑',
    version: 1,
    meta: { profile: 'topo', updatedAt: generatedAt.value },
    nodes: graphNodes,
    edges,
  }
})

function stateLabel(row: MonitorNodeRow): string {
  if (row.heartbeat === 'unknown') return '注册中心未知'
  if (row.heartbeat === 'offline') return '离线'
  if (row.metricState === 'stale') return '在线·指标过期'
  return '在线'
}
</script>

<template>
  <div class="page monitor-page">
    <div class="page-head">
      <div>
        <div class="ph-title">集群监控</div>
        <div class="ph-desc">真实注册节点与资源指标；在线性来自 ZooKeeper，资源指标来自 Redis 心跳上报。</div>
      </div>
      <button class="tb-new" :disabled="loading" @click="refresh">{{ loading ? '刷新中…' : '刷新' }}</button>
    </div>

    <div v-if="!zkAvailable" class="status-banner warn">ZooKeeper 当前不可用，master/worker 状态降级为 unknown；保留最近指标供排障。</div>
    <div v-if="loadError" class="status-banner fail">刷新失败：{{ loadError }}。页面保留上次成功数据。</div>

    <div class="stats">
      <div class="stat"><b>{{ nodes.length }}</b><span>已知节点</span></div>
      <div class="stat"><b>{{ online }}</b><span>在线</span></div>
      <div class="stat"><b>{{ offline }}</b><span>离线</span></div>
      <div class="stat"><b>{{ stale }}</b><span>指标过期</span></div>
      <div class="stat"><b>{{ average('cpu') }} / {{ average('mem') }}</b><span>CPU / 内存均值</span></div>
    </div>

    <div ref="splitArea" class="split-area" :class="{ resizing }">
      <div class="card topology-card" :style="{ flexBasis: `${topologyHeight}px` }">
        <div class="section-head"><b>实时运行拓扑</b><span>采集时间 {{ generatedAt || '-' }}</span></div>
        <div class="card-body">
          <div v-if="nodes.length" class="topology"><GraphWorkbench :profile="topoProfile" doc-id="runtime-topology" :doc="topology" /></div>
          <div v-else class="empty">暂无已注册节点</div>
        </div>
      </div>

      <div class="split-handle" title="上下拖动调整高度" @mousedown="startResize"><span class="split-grip"></span></div>

      <div class="card table-card">
        <div class="section-head"><b>节点明细</b><span>指标 TTL 90 秒</span></div>
        <div class="card-body">
          <table class="node-table">
            <thead><tr><th>角色</th><th>节点</th><th>状态</th><th>CPU</th><th>内存</th><th>磁盘</th><th>最后上报</th><th>标签</th></tr></thead>
            <tbody>
              <tr v-for="row in nodes" :key="`${row.module}:${row.node}`">
                <td>{{ row.module }}</td><td class="mono">{{ row.node }}</td>
                <td><span class="pill" :class="health(row)">{{ stateLabel(row) }}</span></td>
                <td>{{ row.cpu === null ? '-' : `${row.cpu}%` }}</td>
                <td>{{ row.mem === null ? '-' : `${row.mem}%` }}</td>
                <td>{{ row.disk === null ? '-' : `${row.disk}%` }}</td>
                <td class="mono">{{ row.lastSeen || '-' }}</td><td>{{ row.tags.join('、') || '-' }}</td>
              </tr>
              <tr v-if="!nodes.length"><td colspan="8" class="empty">暂无节点数据</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.monitor-page{display:flex;flex-direction:column;gap:14px;min-height:0}
.page-head{display:flex;align-items:center;justify-content:space-between}
.ph-title{font-size:20px;font-weight:700}
.ph-desc{margin-top:4px;color:var(--text-3);font-size:12px}
.tb-new{border:0;border-radius:var(--radius-sm);padding:8px 16px;background:var(--primary);color:#fff;cursor:pointer}
.tb-new:disabled{opacity:.6;cursor:wait}
.status-banner{padding:9px 12px;border-radius:var(--radius-sm);font-size:12px}
.status-banner.warn{background:var(--warn-bg);color:var(--warn)}
.status-banner.fail{background:var(--danger-bg);color:var(--danger)}
.stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.stat{display:flex;flex-direction:column;gap:3px;padding:14px;background:#fff;border:1px solid var(--border);border-radius:var(--radius)}
.stat b{font-size:20px}
.stat span,.section-head span{font-size:11px;color:var(--text-3)}
.card{background:#fff;border:1px solid var(--border);border-radius:var(--radius)}
.section-head{display:flex;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--border)}

/* 拓扑 / 明细 上下分栏 */
.split-area{flex:1;min-height:0;display:flex;flex-direction:column;gap:6px}
.topology-card{flex:0 0 auto;min-height:160px;display:flex;flex-direction:column}
.table-card{flex:1 1 0;min-height:180px;display:flex;flex-direction:column}
.card-body{flex:1;min-height:0;overflow:auto}
.topology{height:100%;min-height:0}
.split-handle{flex:none;height:10px;border-radius:var(--radius-sm);cursor:row-resize;display:flex;align-items:center;justify-content:center;background:var(--bg);border:1px solid var(--border);transition:background .15s,border-color .15s}
.split-handle:hover,.split-area.resizing .split-handle{background:var(--primary-light);border-color:var(--primary)}
.split-grip{width:34px;height:3px;border-radius:2px;background:var(--border-strong)}
.split-handle:hover .split-grip,.split-area.resizing .split-grip{background:var(--primary)}

.node-table{width:100%;border-collapse:collapse;font-size:12px}
.node-table th,.node-table td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--border)}
.node-table th{background:var(--bg);color:var(--text-2);position:sticky;top:0;z-index:1}
.pill{display:inline-flex;padding:2px 7px;border-radius:999px;background:var(--bg)}
.pill.healthy{background:var(--success-bg);color:var(--success)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.fail{background:var(--danger-bg);color:var(--danger)}
.empty{text-align:center;color:var(--text-3);padding:28px}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
@media(max-width:1000px){.stats{grid-template-columns:repeat(2,1fr)}.table-card{overflow:auto}}
</style>

<style>
/* 拖拽进行中：全局禁用文本选中，保持抓手光标 */
body.row-resizing{cursor:row-resize !important;user-select:none}
</style>
