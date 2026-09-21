<script setup lang="ts">
/**
 * 流作业指标卡浮窗：TPS / 延迟 / Watermark / Checkpoint（mock 周期微抖动）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useGraphStore } from '../../../stores/graph'

const store = useGraphStore()

interface SeedMetrics { tps: number; latency: string; watermark: string; ckInterval: string; ckMode: string; ckRate: string }

const base = computed<SeedMetrics>(() => {
  const doc = store.doc
  const n = doc?.nodes.find((x) => x.type === 's_kafka')
  return (n?.data.metrics as SeedMetrics | undefined) ?? {
    tps: 1240, latency: '380ms', watermark: '延迟 4s', ckInterval: '60s', ckMode: 'Exactly-Once', ckRate: '99.8%',
  }
})

const tps = ref(base.value.tps)
let timer = 0
onMounted(() => {
  timer = window.setInterval(() => {
    tps.value = Math.max(0, Math.round(base.value.tps * (0.9 + Math.random() * 0.2)))
  }, 2000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div style="padding:12px 14px;font-size:12px">
    <div class="m-grid">
      <div class="m-card"><b style="color:var(--primary)">{{ tps.toLocaleString() }}</b><span>当前 TPS</span></div>
      <div class="m-card"><b>{{ base.latency }}</b><span>端到端延迟</span></div>
      <div class="m-card"><b style="color:var(--warning)">{{ base.watermark }}</b><span>Watermark</span></div>
    </div>
    <div class="m-rows">
      <div class="m-row"><span>Checkpoint 间隔</span><b class="mono">{{ base.ckInterval }}</b></div>
      <div class="m-row"><span>语义保障</span><b class="mono">{{ base.ckMode }}</b></div>
      <div class="m-row"><span>最近成功率</span><b class="mono" style="color:var(--success)">{{ base.ckRate }}</b></div>
      <div class="m-row"><span>反压状态</span><b style="color:var(--success)">Normal（无反压）</b></div>
    </div>
    <div class="m-tip">指标由运行服务异步推送（mock 定时抖动模拟 WebSocket 语义）</div>
  </div>
</template>

<style scoped>
.m-grid{display:flex;gap:10px;margin-bottom:10px}
.m-card{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:9px 10px;text-align:center}
.m-card b{display:block;font-size:17px}
.m-card span{font-size:10.5px;color:var(--text-3)}
.m-rows{display:flex;flex-direction:column;gap:4px}
.m-row{display:flex;justify-content:space-between;padding:5px 9px;background:var(--bg);border-radius:var(--radius-sm);font-size:11.5px;color:var(--text-2)}
.m-tip{margin-top:9px;font-size:10.5px;color:var(--text-3)}
</style>
