<script setup lang="ts">
import { ref, watch } from 'vue'
import { createStreamContract, type StreamObservation } from '../services/rebuild/streamApi'

const props = defineProps<{ jobId?: string }>()
const api = createStreamContract()
const jobId = ref(props.jobId ?? '')
const count = ref(10)
const loading = ref(false)
const error = ref('')
const observation = ref<StreamObservation | null>(null)
const produced = ref(0)
const fuseKey = ref('id')
const fuseStreams = ref('{"orders":[{"id":1,"amount":10}],"customers":[{"id":1,"name":"Ada"}]}')
const fused = ref(0)

watch(() => props.jobId, (value) => {
  // Project/workflow navigation can reuse this component; never retain the
  // previous job id when the parent scope changes.
  jobId.value = value ?? ''
  observation.value = null
  produced.value = 0
  fused.value = 0
  error.value = ''
})

async function produce() {
  if (!jobId.value.trim()) return
  const requested = Math.max(1, Math.min(10000, Math.trunc(Number(count.value) || 1)))
  count.value = requested
  loading.value = true
  error.value = ''
  try {
    const result = await api.produceStreamEvents(jobId.value.trim(), { count: count.value, payload: { kind: 'sample', amount: 1 } })
    produced.value += result.produced
    await refresh()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '生产失败' }
  finally { loading.value = false }
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
  loading.value = true
  error.value = ''
  try {
    observation.value = await api.queryStreamObservation({ from: new Date(Date.now() - 3600000).toISOString(), to: new Date().toISOString(), limit: 100, offset: 0 }, jobId.value.trim())
  } catch (cause) {
    // Refresh is a user-visible operation; avoid an unhandled rejection and
    // keep the last observation on screen while exposing the failure.
    error.value = cause instanceof Error ? cause.message : '流观摩刷新失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="stream-observation" data-stream-observation>
    <header><strong>流处理观摩</strong><button type="button" :disabled="loading" @click="refresh">刷新</button></header>
    <div class="stream-controls">
      <label>Job ID<input v-model="jobId" data-stream-job-id /></label>
      <label>生产条数<input v-model.number="count" type="number" min="1" max="10000" /></label>
      <button type="button" :disabled="loading || !jobId" data-stream-produce @click="produce">生产事件</button>
    </div>
    <div class="stream-fuse" data-stream-fuse>
      <label>融合键<input v-model="fuseKey" data-stream-fuse-key /></label>
      <label>流数据 JSON<textarea v-model="fuseStreams" rows="2" data-stream-fuse-streams /></label>
      <button type="button" :disabled="loading || !jobId" data-stream-fuse-submit @click="fuse">融合流</button>
      <span>最近融合 {{ fused }}</span>
    </div>
    <p v-if="error" class="error" data-stream-error>{{ error }}</p>
    <div v-if="observation" class="stream-metrics" data-stream-metrics>
      <span>本次生产 {{ produced }}</span>
      <span>输入 {{ observation.inputCount.value }}</span>
      <span>输出 {{ observation.outputCount.value }}</span>
      <span>成功 {{ observation.counters.success.value }}</span>
      <span>失败 {{ observation.counters.failure.value }}</span>
      <span>积压 {{ observation.lag.value }}</span>
    </div>
  </section>
</template>

<style scoped>
.stream-observation{padding:10px 14px;border-top:1px solid var(--border-color,#e2e8f0);background:#f8fafc;display:grid;gap:8px}.stream-observation header,.stream-controls,.stream-fuse,.stream-metrics{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stream-observation label{display:flex;align-items:center;gap:5px;font-size:12px}.stream-observation input{width:110px;padding:5px}.stream-fuse textarea{width:320px;min-height:34px;font:11px monospace}.stream-metrics span,.stream-fuse span{padding:4px 8px;background:#fff;border:1px solid #dbe3ef;border-radius:5px;font-size:12px}.error{color:#b91c1c;margin:0}
</style>
