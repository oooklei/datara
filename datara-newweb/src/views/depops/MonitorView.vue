<template>
  <main class="pg" aria-label="集群监控">
    <header class="pg-head">
      <h1 class="sec-head">集群监控</h1>
      <p class="pg-desc">master / worker / ssh 三类节点的心跳与指标快照。指标由节点上报聚合，非实时值。</p>
    </header>

    <div class="toolbar">
      <span class="pill" :class="snapshot && snapshot.zkAvailable ? 'ok' : 'err'" :data-zk="snapshot ? String(snapshot.zkAvailable) : undefined">
        ZK：{{ snapshot ? (snapshot.zkAvailable ? '可用' : '不可用') : '—' }}
      </span>
      <span class="spacer"></span>
      <span class="hint" data-generated>生成时间：{{ snapshot?.generatedAt || '—' }}</span>
      <button type="button" class="op-btn" data-refresh :disabled="busy" @click="reload">刷新</button>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时表格须保留 -->
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="busy" @click="reload">重试</button>
    </div>

    <div v-if="busy" class="panel" role="status" aria-live="polite">
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

    <div v-else-if="snapshot && snapshot.nodes.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">节点指标</span>
        <span class="pill info">{{ snapshot.nodes.length }}</span>
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
    </div>

    <p class="lock-tip" role="note" data-metric-note>
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
 *
 * 样式范式：复用全局设计系统（`.pg`/`.pg-head`/`.panel`/`.tbl`/`.tbl-toolbar`/`.pill`/`.lock-tip`
 *   + `var(--*)` 令牌），与旧前端 datara-web 监控页的 `.card.panel` + `.tbl-toolbar` + `table.tbl` 范式对齐。
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
/* 仅保留语义化状态着色；版式/令牌一律走全局设计系统（.pg/.tbl/.pill/.lock-tip） */
td[data-heartbeat='unknown'] { color: var(--warn); }
td[data-metric-state='stale'] { color: var(--warn); }
td[data-metric-state='unsupported'] { color: var(--text-3); }
</style>
