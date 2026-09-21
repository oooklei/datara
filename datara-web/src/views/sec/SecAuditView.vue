<script setup lang="ts">
/**
 * M15 数据安全 · 访问审计
 * 记录所有数据访问（谁/何时/查了什么/多少行/允许或拒绝），左筛选面板（用户/结果）+ 关键字搜索。
 */
import { ref, computed, onMounted } from 'vue'
import { dataStore } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { AccessLog } from '../../services/types'

const logs = ref<AccessLog[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ user: '', result: '' })

onMounted(async () => {
  logs.value = [...((await dataStore.list<AccessLog>('accessLogs')) ?? [])].sort((a, b) => b.ts.localeCompare(a.ts))
})

const facets = computed<Facet[]>(() => [
  { key: 'user', label: '访问人', options: [...new Set(logs.value.map(l => l.user))].map(u => ({ v: u, t: u })) },
  { key: 'result', label: '结果', options: [{ v: '允许', t: '允许' }, { v: '拒绝', t: '拒绝' }] },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return logs.value.filter((l) => {
    if (filters.value.user && l.user !== filters.value.user) return false
    if (filters.value.result && l.result !== filters.value.result) return false
    if (!kw) return true
    return [l.user, l.action, l.target, l.reason ?? ''].join(' ').toLowerCase().includes(kw)
  })
})

const denied = computed(() => filtered.value.filter((l) => l.result === '拒绝').length)
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索目标表/原因"
      :result-count="filtered.length"
      :total-count="logs.length"
    />
    <div class="card" style="flex:1;min-width:0;padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">访问审计日志</span>
        <span class="pill info">允许 {{ filtered.length - denied }}</span>
        <span class="pill err">拒绝 {{ denied }}</span>
        <span class="spacer" />
        <span style="color:var(--text-3);font-size:12px">记录所有数据访问：谁、什么时间、查了什么、查了多少</span>
      </div>
      <table class="tbl">
        <thead><tr><th>时间</th><th>访问人</th><th>操作</th><th>目标对象</th><th>行数</th><th>结果</th><th>判定原因</th></tr></thead>
        <tbody>
          <tr v-for="l in filtered" :key="l.id">
            <td class="mono" style="font-size:11.5px;color:var(--text-3)">{{ l.ts }}</td>
            <td><b>{{ l.user }}</b></td>
            <td><span class="pill info">{{ l.action }}</span></td>
            <td class="mono" style="font-size:12px">{{ l.target }}</td>
            <td style="color:var(--text-2)">{{ l.rows.toLocaleString() }}</td>
            <td><span class="pill" :class="l.result === '允许' ? 'ok' : 'err'">{{ l.result }}</span></td>
            <td style="color:var(--text-2)">{{ l.reason ?? '-' }}</td>
          </tr>
          <tr v-if="!filtered.length"><td colspan="7" class="empty">暂无审计记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
/* ---- 区块标题（渐变竖条，与全站统一） ---- */
.sec-head{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px}
.sec-head::before{content:'';width:3px;height:14px;border-radius:2px;background:linear-gradient(180deg,var(--primary),var(--purple))}
.empty{text-align:center;color:var(--text-3);padding:24px}
</style>
