<script setup lang="ts">
import { useRunStore } from '../../../stores/run'

const run = useRunStore()

function fmt(ts: number) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<template>
  <div>
    <div v-if="run.logs.length === 0" style="padding:16px;text-align:center;color:var(--text-3)">
      暂无运行日志。点击「试运行」提交执行（提交即返回，状态异步推送）。
    </div>
    <div v-for="(l, i) in run.logs" :key="run.runId + i" class="log-line" :class="l.cls">
      <span class="t">{{ fmt(l.ts) }}</span> {{ l.text }}
    </div>
  </div>
</template>
