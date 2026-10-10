<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../../../stores/run'
import { getSseSource, flagsVersion } from '../../../services/featureFlags'

const run = useRunStore()

/* Task 18（§5.1）日志 SSE 化：sseSource=pubsub 时节点事件由 runStore（唯一持连方）经
 * applyNodeEvent 实时写入 logs（错误行即日志行），本面板只消费不自行开连接（§7.2）；
 * polling（默认）时 logs 仅来自既有轮询/总线通道，行为与 SSE 化之前完全一致。 */
const sourceText = computed(() => {
  flagsVersion() // 订阅开关翻转（运行时可改）即时反映
  return getSseSource() === 'pubsub' ? 'SSE 推送（pubsub）' : '轮询/总线（polling）'
})

function fmt(ts: number) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<template>
  <div class="log-panel">
    <div v-if="run.logs.length === 0" style="padding:16px;text-align:center;color:var(--text-3)">
      暂无运行日志。点击「试运行」提交执行（提交即返回，状态异步推送）。
    </div>
    <div v-for="(l, i) in run.logs" :key="run.runId + i" class="log-line" :class="l.cls">
      <span class="t">{{ fmt(l.ts) }}</span> {{ l.text }}
    </div>
    <div class="log-src">日志推送源：{{ sourceText }}</div>
  </div>
</template>

<style scoped>
.log-src{margin-top:8px;padding:6px 10px;border-top:1px dashed var(--border);font-size:10.5px;color:var(--text-3)}
</style>
