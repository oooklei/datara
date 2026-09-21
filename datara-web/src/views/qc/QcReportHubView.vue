<script setup lang="ts">
/**
 * 质量报告 Hub（三级报告合并入口，F56a 同壳单入口）—— 权威路由 /qc/report，
 * 页签走 query.tab 切换；旧路径 /qc/report-dag|table redirect 保书签。
 * query 原样透传：资产地图 goScore 直达 /qc/report-table?table=xxx → redirect 后 table 参数不丢；
 * 报告页内互跳均走路由，切 Tab 时其余 query 原样保留。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import QcReportView from './QcReportView.vue'
import QcReportDagView from './QcReportDagView.vue'
import QcReportTableView from './QcReportTableView.vue'

const route = useRoute()
type TabKey = 'total' | 'dag' | 'table'
const tabs: { k: TabKey; label: string }[] = [
  { k: 'total', label: '总体报告（系统级）' },
  { k: 'dag', label: '专项报告（DAG工作流）' },
  { k: 'table', label: '细项报告（指定表）' },
]
const tab = computed<TabKey>(() => {
  const t = String(route.query.tab ?? 'total')
  return (tabs.some((x) => x.k === t) ? t : 'total') as TabKey
})
</script>

<template>
  <div class="hub">
    <div class="hub-tabs">
      <router-link
        v-for="t in tabs" :key="t.k"
        class="hub-tab" :class="{ on: tab === t.k }"
        :to="{ query: { ...route.query, tab: t.k } }"
      >{{ t.label }}</router-link>
    </div>
    <div class="hub-body">
      <QcReportView v-if="tab === 'total'" />
      <QcReportDagView v-else-if="tab === 'dag'" />
      <QcReportTableView v-else />
    </div>
  </div>
</template>

<style scoped>
.hub{display:flex;flex-direction:column;height:100%}
.hub-tabs{display:flex;align-items:center;gap:2px;padding:0 14px;background:#fff;border-bottom:1px solid var(--border);flex-shrink:0}
.hub-tab{padding:11px 16px;font-size:13px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;text-decoration:none;transition:color var(--dur-base) var(--ease),border-color var(--dur-base) var(--ease)}
.hub-tab:hover{color:var(--primary)}
.hub-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.hub-body{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column}
</style>
