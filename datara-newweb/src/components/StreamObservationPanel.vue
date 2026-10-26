<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  createStreamContract,
  type StreamCheckpointRow,
  type StreamObservation,
  type StreamRecoveryEventRow,
} from '../services/rebuild/streamApi'

const props = defineProps<{ jobId?: string; projectId?: number; workflowId?: number; workflowName?: string }>()
const api = createStreamContract(props.projectId)
const jobId = ref(props.jobId ?? '')
const count = ref(10)
const loading = ref(false)
const error = ref('')
const detailWarning = ref('')
const observation = ref<StreamObservation | null>(null)
const checkpoints = ref<StreamCheckpointRow[]>([])
const recoveryEvents = ref<StreamRecoveryEventRow[]>([])
const produced = ref(0)
const fuseKey = ref('id')
const fuseStreams = ref('{"orders":[{"id":1,"amount":10}],"customers":[{"id":1,"name":"Ada"}]}')
const fused = ref(0)
const aggregateKey = ref('partition')
const aggregateValue = ref('value')
const aggregateWindow = ref(10)
let observationSeq = 0

watch(() => [props.projectId, props.jobId] as const, ([, value]) => {
  observationSeq += 1
  // Project/workflow navigation can reuse this component; never retain the
  // previous job id when the parent scope changes.
  jobId.value = value ?? ''
  observation.value = null
  checkpoints.value = []
  recoveryEvents.value = []
  produced.value = 0
  fused.value = 0
  error.value = ''
  detailWarning.value = ''
  loading.value = false
})

async function produce() {
  if (!jobId.value.trim()) return
  const requested = Math.max(1, Math.min(10000, Math.trunc(Number(count.value) || 1)))
  count.value = requested
  loading.value = true
  error.value = ''
  detailWarning.value = ''
  try {
    const result = await api.produceStreamEvents(jobId.value.trim(), {
      count: count.value,
      payload: { kind: 'sample', amount: 1 },
      aggregate: { keyField: aggregateKey.value.trim() || 'partition', valueField: aggregateValue.value.trim() || 'value', windowSize: Math.max(1, Math.min(10000, Math.trunc(Number(aggregateWindow.value) || 1))) },
    })
    produced.value += result.produced
    await refresh()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '生产失败' }
  finally { loading.value = false }
}

async function provisionLiveObservation() {
  const workflowId = Number(props.workflowId)
  if (!Number.isSafeInteger(props.projectId) || Number(props.projectId) <= 0 || !Number.isSafeInteger(workflowId) || workflowId <= 0) {
    error.value = '请先保存流处理工作流再创建实时观摩'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const active = await api.provisionStreamJob({
      projectId: Number(props.projectId),
      workflowId,
      name: `${props.workflowName?.trim() || `workflow-${workflowId}`}-live`,
      mqTopic: `datara.workflow.${workflowId}`,
      runtimeConfig: {
        mode: 'fixed_rate',
        rows_per_sec: Math.max(1, Math.min(1000, Math.trunc(Number(count.value) || 1))),
        columns: ['id', 'event_time', 'value'],
      },
    })
    jobId.value = active.jobId
    await produce()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '创建实时流观摩失败'
  } finally {
    loading.value = false
  }
}

async function fuse() {
  if (!jobId.value.trim() || !fuseKey.value.trim()) return
  let streams: Record<string, Array<Record<string, unknown>>>
  try {
    const parsed: unknown = JSON.parse(fuseStreams.value)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('streams 必须是对象')
    streams = parsed as Record<string, Array<Record<string, unknown>>>
    if (!Object.values(streams).every(Array.isArray)) throw new Error('每个流必须是数组')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '融合输入格式错误'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api.fuseStreamEvents(jobId.value.trim(), fuseKey.value.trim(), streams)
    fused.value = result.fused
    await refresh()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '流融合失败' }
  finally { loading.value = false }
}

async function refresh() {
  if (!jobId.value.trim()) return
  const seq = ++observationSeq
  const requestedJobId = jobId.value.trim()
  loading.value = true
  error.value = ''
  try {
    const window = { from: new Date(Date.now() - 3600000).toISOString(), to: new Date().toISOString(), limit: 100, offset: 0 }
    const [observationOutcome, checkpointOutcome, recoveryOutcome] = await Promise.allSettled([
      api.queryStreamObservation(window, requestedJobId),
      api.listStreamCheckpoints(window, requestedJobId),
      api.listStreamRecoveryEvents(window, requestedJobId),
    ])
    if (seq !== observationSeq) return
    if (observationOutcome.status === 'rejected') throw observationOutcome.reason
    observation.value = observationOutcome.value
    checkpoints.value = checkpointOutcome.status === 'fulfilled' ? checkpointOutcome.value : []
    recoveryEvents.value = recoveryOutcome.status === 'fulfilled' ? recoveryOutcome.value : []
    detailWarning.value = [checkpointOutcome, recoveryOutcome]
      .filter((outcome): outcome is PromiseRejectedResult => outcome.status === 'rejected')
      .map((outcome) => outcome.reason instanceof Error ? outcome.reason.message : String(outcome.reason))
      .join('；')
  } catch (cause) {
    if (seq !== observationSeq) return
    // Refresh is a user-visible operation; avoid an unhandled rejection and
    // keep the last observation on screen while exposing the failure.
    error.value = cause instanceof Error ? cause.message : '流观摩刷新失败'
  } finally {
    if (seq === observationSeq) loading.value = false
  }
}
</script>

<template>
  <section class="stream-observation" data-stream-observation>
    <header><strong>流处理观摩</strong><button type="button" :disabled="loading" @click="refresh">刷新</button></header>
    <div class="stream-controls">
      <button v-if="workflowId" type="button" :disabled="loading" data-stream-provision @click="provisionLiveObservation">创建并启动实时观摩</button>
      <label>Job ID<input v-model="jobId" data-stream-job-id /></label>
      <label>生产条数<input v-model.number="count" type="number" min="1" max="10000" /></label>
      <button type="button" :disabled="loading || !jobId" data-stream-produce @click="produce">生产事件</button>
    </div>
    <div class="stream-aggregate" data-stream-aggregate>
      <label>聚合键<input v-model="aggregateKey" data-stream-aggregate-key /></label>
      <label>聚合值<input v-model="aggregateValue" data-stream-aggregate-value /></label>
      <label>窗口<input v-model.number="aggregateWindow" type="number" min="1" data-stream-aggregate-window /></label>
    </div>
    <div class="stream-fuse" data-stream-fuse>
      <label>融合键<input v-model="fuseKey" data-stream-fuse-key /></label>
      <label>流数据 JSON<textarea v-model="fuseStreams" rows="2" data-stream-fuse-streams /></label>
      <button type="button" :disabled="loading || !jobId" data-stream-fuse-submit @click="fuse">融合流</button>
      <span>最近融合 {{ fused }}</span>
    </div>
    <p v-if="error" class="error" data-stream-error>{{ error }}</p>
    <p v-if="detailWarning" class="warning" data-stream-detail-warning>部分观测明细暂不可用：{{ detailWarning }}</p>
    <div v-if="observation" class="stream-observation-grid" data-stream-metrics>
      <article class="stream-metric-panel" data-stream-metric-panel="rate">
        <h4>实时速率</h4>
        <span data-stream-metric>生产速率 {{ observation.produceRate.value }}</span>
        <span data-stream-metric>消费速率 {{ observation.consumeRate.value }}</span>
        <span data-stream-metric>处理速率 {{ observation.processRate.value }}</span>
        <small>本次生产 {{ produced }}</small>
      </article>
      <article class="stream-metric-panel" data-stream-metric-panel="volume">
        <h4>处理水位</h4>
        <span data-stream-metric>输入 {{ observation.inputCount.value }}</span>
        <span data-stream-metric>输出 {{ observation.outputCount.value }}</span>
        <span data-stream-metric>重复 {{ observation.duplicateCount.value }}</span>
        <span data-stream-metric>积压 {{ observation.lag.value }}</span>
      </article>
      <article class="stream-metric-panel" data-stream-metric-panel="offset">
        <h4>位点与窗口</h4>
        <span data-stream-metric>当前偏移 {{ observation.offset.current.value }}</span>
        <span data-stream-metric>提交偏移 {{ observation.offset.committed.value }}</span>
        <span data-stream-metric>窗口结果 {{ observation.windowResults.length }}</span>
      </article>
      <article class="stream-metric-panel" data-stream-metric-panel="result">
        <h4>处理结果</h4>
        <span data-stream-metric>成功 {{ observation.counters.success.value }}</span>
        <span data-stream-metric>失败 {{ observation.counters.failure.value }}</span>
        <span data-stream-metric>跳过 {{ observation.counters.skipped.value }}</span>
      </article>
    </div>
    <div v-if="observation" class="stream-detail-grid" data-stream-details>
      <section class="stream-detail" data-stream-window-results>
        <h4>窗口处理结果</h4>
        <p v-if="!observation.windowResults.length">暂无窗口结果</p>
        <table v-else><thead><tr><th>窗口</th><th>时间</th><th>输入 → 输出</th><th>状态</th></tr></thead><tbody>
          <tr v-for="row in observation.windowResults" :key="row.windowKey"><td>{{ row.windowKey }}</td><td>{{ row.windowStart }} – {{ row.windowEnd }}</td><td>{{ row.recordsIn.value }} → {{ row.recordsOut.value }}</td><td>{{ row.status }}</td></tr>
        </tbody></table>
      </section>
      <section class="stream-detail" data-stream-checkpoints>
        <h4>检查点</h4>
        <p v-if="!checkpoints.length">暂无检查点</p>
        <table v-else><thead><tr><th>分区</th><th>当前 / 已提交</th><th>时间</th></tr></thead><tbody>
          <tr v-for="row in checkpoints" :key="`${row.jobId}:${row.partition}`"><td>{{ row.partition }}</td><td>{{ row.currentOffset.value }} / {{ row.committedOffset.value }}</td><td>{{ row.checkpointedAt }}</td></tr>
        </tbody></table>
      </section>
      <section class="stream-detail" data-stream-error-samples>
        <h4>错误样本</h4>
        <p v-if="!observation.errorSamples.length">暂无错误样本</p>
        <table v-else><thead><tr><th>流向</th><th>样本</th><th>时间</th></tr></thead><tbody>
          <tr v-for="(row, index) in observation.errorSamples" :key="`${row.jobId}:${row.capturedAt}:${index}`"><td>{{ row.flow }}</td><td><code>{{ row.sample }}</code></td><td>{{ row.capturedAt }}</td></tr>
        </tbody></table>
      </section>
      <section class="stream-detail" data-stream-recovery-events>
        <h4>恢复事件</h4>
        <p v-if="!recoveryEvents.length">暂无恢复事件</p>
        <table v-else><thead><tr><th>类型</th><th>详情</th><th>时间</th></tr></thead><tbody>
          <tr v-for="row in recoveryEvents" :key="row.eventId"><td>{{ row.kind }}</td><td>{{ row.detail }}</td><td>{{ row.occurredAt }}</td></tr>
        </tbody></table>
      </section>
    </div>
  </section>
</template>

<style scoped>
.stream-observation{padding:10px 14px;border-top:1px solid var(--border-color,#e2e8f0);background:#f8fafc;display:grid;gap:8px}.stream-observation header,.stream-controls,.stream-aggregate,.stream-fuse{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stream-observation label{display:flex;align-items:center;gap:5px;font-size:12px}.stream-observation input{width:110px;padding:5px}.stream-fuse textarea{width:320px;min-height:34px;font:11px monospace}.stream-fuse span{padding:4px 8px;background:#fff;border:1px solid #dbe3ef;border-radius:5px;font-size:12px}.stream-observation-grid,.stream-detail-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.stream-metric-panel,.stream-detail{padding:9px;background:#fff;border:1px solid #dbe3ef;border-radius:7px}.stream-metric-panel{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.stream-metric-panel h4{grid-column:1/-1;margin:0;color:#334155;font-size:12px}.stream-metric-panel span,.stream-metric-panel small{padding:4px 6px;border-radius:4px;background:#f8fafc;font-size:12px;white-space:nowrap}.stream-metric-panel small{grid-column:1/-1;color:#64748b}.stream-detail{min-width:0;overflow:auto}.stream-detail h4{margin:0 0 7px;color:#334155;font-size:12px}.stream-detail p{margin:0;color:#94a3b8;font-size:12px}.stream-detail table{width:100%;border-collapse:collapse;font-size:11px;white-space:nowrap}.stream-detail th,.stream-detail td{padding:4px 5px;text-align:left;border-bottom:1px solid #edf2f7}.stream-detail code{font-size:10px}.error,.warning{margin:0}.error{color:#b91c1c}.warning{color:#a16207;font-size:12px}@media(max-width:1100px){.stream-observation-grid,.stream-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.stream-observation-grid,.stream-detail-grid{grid-template-columns:1fr}}
</style>
