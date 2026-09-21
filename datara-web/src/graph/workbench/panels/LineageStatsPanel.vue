<script setup lang="ts">
/**
 * 血缘统计浮窗：分层节点分布 / 跨层流 / 最大链路深度（从 store 文档实时计算）。
 * I5 F25：real 模式追加「运行时采集」全局统计行（/lineage/stats）；mock 模式静默跳过。
 */
import { computed, onMounted, ref } from 'vue'
import { adjacency } from '../../../graph/model'
import { useGraphStore } from '../../../stores/graph'
import { isMock } from '../../../services'
import { lineageStats } from '../../../services/lineageApi'
import type { LineageStats } from '../../../services/lineageApi'

const store = useGraphStore()

/** 运行时采集统计（real 模式拉取一次；失败静默，浮窗仍显示文档计算值） */
const apiStats = ref<LineageStats | null>(null)
onMounted(async () => {
  if (isMock) return
  try {
    apiStats.value = await lineageStats()
  } catch { /* 静默 */ }
})

const stats = computed(() => {
  const doc = store.doc
  if (!doc) return null
  const LAYERS = ['ODS', 'DIM', 'DWD', 'DWS', 'ADS']
  const byLayer = LAYERS.map((l) => ({
    layer: l,
    cnt: doc.nodes.filter((n) => String(n.data.layer) === l).length,
  })).filter((x) => x.cnt > 0)
  const adj = adjacency(doc)
  // 最大链路深度（记忆化 DFS）
  const depth = new Map<string, number>()
  const walk = (id: string): number => {
    if (depth.has(id)) return depth.get(id)!
    depth.set(id, 0)
    const d = (adj.get(id) ?? []).reduce((m, next) => Math.max(m, walk(next) + 1), 0)
    depth.set(id, d)
    return d
  }
  doc.nodes.forEach((n) => walk(n.id))
  const crossLayer = doc.edges.filter((e) => {
    const s = doc.nodes.find((n) => n.id === e.source)
    const t = doc.nodes.find((n) => n.id === e.target)
    return s && t && s.data.layer !== t.data.layer
  }).length
  return {
    byLayer,
    edges: doc.edges.length,
    crossLayer,
    maxDepth: Math.max(0, ...depth.values()),
  }
})
</script>

<template>
  <div v-if="stats" style="padding:12px 14px;font-size:12px">
    <div v-if="apiStats" class="l-api">
      <div class="l-api-title">运行时采集（真实血缘）</div>
      <div class="l-api-row"><span>表级边</span><b>{{ apiStats.edgeCount }}</b></div>
      <div class="l-api-row"><span>字段映射</span><b>{{ apiStats.fieldCount }}</b></div>
      <div class="l-api-row"><span>覆盖表</span><b>{{ apiStats.tableCount }}</b></div>
      <div class="l-api-row"><span>覆盖工作流</span><b>{{ apiStats.wfCount }}</b></div>
      <div v-if="apiStats.lastTime" class="l-api-row"><span>最近采集</span><b class="l-time mono">{{ apiStats.lastTime }}</b></div>
    </div>
    <div class="l-stats">
      <div class="l-stat"><b>{{ stats.byLayer.reduce((s, x) => s + x.cnt, 0) }}</b><span>血缘资产</span></div>
      <div class="l-stat"><b>{{ stats.edges }}</b><span>血缘关系</span></div>
      <div class="l-stat"><b>{{ stats.crossLayer }}</b><span>跨层流动</span></div>
      <div class="l-stat"><b>{{ stats.maxDepth }}</b><span>最大链路深度</span></div>
    </div>
    <div class="l-layers">
      <div v-for="x in stats.byLayer" :key="x.layer" class="l-layer">
        <span class="l-name">{{ x.layer }}</span>
        <div class="l-bar"><i :style="{ width: `${(x.cnt / Math.max(...stats.byLayer.map((y) => y.cnt))) * 100}%` }" /></div>
        <b>{{ x.cnt }}</b>
      </div>
    </div>
    <div class="l-tip">点击画布节点可在右侧查看上游/下游血缘明细；结构检查用于发现环与孤岛。</div>
  </div>
</template>

<style scoped>
.l-api{margin-bottom:10px;border:1px solid var(--border);border-radius:var(--radius);padding:8px 10px}
.l-api-title{font-size:10.5px;color:var(--text-3);margin-bottom:4px;font-weight:600}
.l-api-row{display:flex;justify-content:space-between;gap:8px;font-size:11.5px;padding:2px 0;color:var(--text-2)}
.l-api-row b{color:var(--text)}
.l-time{font-size:10.5px;font-weight:400}
.l-stats{display:flex;gap:8px;margin-bottom:10px}
.l-stat{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px;text-align:center}
.l-stat b{display:block;font-size:16px;color:var(--primary)}
.l-stat span{font-size:10px;color:var(--text-3)}
.l-layers{display:flex;flex-direction:column;gap:5px}
.l-layer{display:flex;align-items:center;gap:8px;font-size:11.5px}
.l-name{width:36px;color:var(--text-2);font-weight:600}
.l-bar{flex:1;height:8px;background:var(--bg);border-radius:4px;overflow:hidden}
.l-bar i{display:block;height:100%;background:linear-gradient(90deg,#1668dc,#7c3aed);border-radius:4px}
.l-tip{margin-top:10px;font-size:10.5px;color:var(--text-3);line-height:1.6}
</style>
