<script setup lang="ts">
import { EDGE_DATA_TYPE_VISUALS } from './edgeData'

const entries = Object.entries(EDGE_DATA_TYPE_VISUALS)
</script>

<template>
  <div class="edge-legend">
    <p>连线颜色表示上游输出的数据类型。</p>
    <div v-for="([type, visual]) in entries" :key="type" class="legend-row">
      <span class="legend-line" :style="{ background: visual.color }" />
      <span class="legend-name">{{ visual.label }}</span>
      <code>{{ type }}</code>
    </div>
  </div>
</template>

<style scoped>
.edge-legend{padding:12px 14px;font-size:12px;color:var(--text-2)}
.edge-legend p{margin:0 0 10px;color:var(--text-3)}
.legend-row{height:30px;display:grid;grid-template-columns:48px 1fr 72px;align-items:center;gap:10px;border-top:1px solid var(--border)}
.legend-line{height:3px;border-radius:2px}
.legend-name{font-weight:600;color:var(--text-1)}
.legend-row code{font:11px var(--mono,monospace);color:var(--text-3)}
</style>

