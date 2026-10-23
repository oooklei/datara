<template>
  <main class="monitor-page" aria-label="集群监控">
    <header class="monitor-head">
      <div>
        <h1>集群监控</h1>
        <p>master / worker / ssh 三类节点的心跳与指标快照。指标由节点上报聚合，非实时值。</p>
      </div>
      <span class="zk-badge" :data-zk="snapshot ? String(snapshot.zkAvailable) : undefined">
        ZK：{{ snapshot ? (snapshot.zkAvailable ? '可用' : '不可用') : '—' }}
      </span>
      <span class="generated" data-generated>生成时间：{{ snapshot?.generatedAt || '—' }}</span>
      <button type="button" data-refresh @click="reload">刷新</button>
    </header>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时表格须保留 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="busy" role="status">正在加载…</p>
    <p v-else-if="!snapshot && !error" data-empty>暂无监控数据</p>
    <p v-else-if="snapshot && snapshot.nodes.length === 0 && !error" data-empty>暂无节点上报</p>

    <table v-if="snapshot && snapshot.nodes.length > 0" data-node-list>
      <thead>
        <tr>
          <th>模块</th><th>节点</th><th>CPU</th><th>内存 %</th><th>内存 MB</th><th>磁盘</th>
          <th>心跳</th><th>指标态</th><th>最近上报</th><th>标签</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in snapshot.nodes" :key="`${row.module}:${row.node}`" :data-node="`${row.module}:${row.node}`">
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
      </tbody>
    </table>

    <p class="monitor-note" role="note" data-metric-note>
      口径：空指标如实显示 —；heartbeat=unknown 表示 ZK 不可用、无法判定在线状态；指标态 过期=上报时间超出 90s TTL，不支持=该模块（ssh）不上报指标。手动刷新，不做轮询。
    </p>
  </main>
</template>

<script setup lang="ts">
/**
 * 17.3 集群监控页组件段（IMPL-v4-16，不含路由/菜单壳，由 IMPL-v4-17 收口）。
 *
 * 契约面：`createMonitorContract().fetchMonitorNodes()`（B3 monitorApi，REGISTRY #13 GREEN）。
 * 数据红线：
 *  - 仅经契约工厂取数，禁直连 fetch/axios；
 *  - 空指标如实显示 —，heartbeat=unknown / metricState=stale|unsupported 给可辨识文案，不虚构实时性；
 *  - 手动刷新，不做高频轮询。
 */
import { onMounted, ref } from 'vue'
import { createMonitorContract, type MonitorHeartbeat, type MonitorMetricState, type MonitorSnapshot } from '../../services/rebuild/monitorApi'

const monitor = createMonitorContract()

const snapshot = ref<MonitorSnapshot | null>(null)
const busy = ref(false)
const error = ref('')

const MODULE_LABEL: Record<string, string> = { master: 'master', worker: 'worker', ssh: 'ssh' }
const moduleLabel = (m: string): string => MODULE_LABEL[m] ?? m

/** 心跳：unknown 须可辨识（ZK 不可用、无法判定），不虚构在线状态；后端 ssh 行的心跳串如实透出。 */
const heartbeatLabel = (h: MonitorHeartbeat): string => {
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

const percent = (v: number | null): string => (v === null || v === undefined ? '—' : `${v}%`)
const memMb = (used: number | null, total: number | null): string =>
  used === null && total === null ? '—' : `${used ?? '—'} / ${total ?? '—'}`

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 非 0 包络码须随错误信息透出（monitorApi 经 preserveEnvelopeCode 保码）。 */
const errorText = (e: unknown): string => {
  const code = (e as { code?: number | string } | null)?.code
  return code !== undefined && code !== 0 ? `加载失败（code ${code}）：${message(e)}` : message(e)
}

async function reload(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    snapshot.value = await monitor.fetchMonitorNodes()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.monitor-page{max-width:1180px;margin:auto;padding:32px 24px;color:#172033}
.monitor-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.monitor-head h1{margin:0}
.monitor-head p{margin:4px 0 0;color:#64748b;flex-basis:100%}
.zk-badge{padding:4px 10px;border-radius:999px;background:#e2e8f0;font-size:13px}
.zk-badge[data-zk='true']{background:#dcfce7}
.zk-badge[data-zk='false']{background:#fee2e2}
.generated{color:#64748b;font-size:13px;margin-left:auto}
button{cursor:pointer;padding:7px 12px}
table{width:100%;border-collapse:collapse;background:#fff;margin-top:8px}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}
td[data-heartbeat='unknown']{color:#b45309}
td[data-metric-state='stale']{color:#b45309}
td[data-metric-state='unsupported']{color:#64748b}
.monitor-note{margin-top:16px;color:#475569;font-size:13px}
</style>
