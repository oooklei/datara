<template>
  <section class="workbench" aria-label="项目工作台">
    <header class="wb-head">
      <h1>项目工作台</h1>
      <p class="wb-sub">快捷导航与统计指标总览</p>
    </header>

    <nav class="wb-nav" aria-label="快捷导航" data-workbench-nav>
      <button
        v-for="seg in PROJECT_MENU_SECTIONS"
        :key="seg.key"
        type="button"
        class="nav-item"
        :data-nav="seg.key"
        @click="nav(seg.key)"
      >
        {{ seg.label }}
      </button>
    </nav>

    <h2 class="wb-section-title">运行统计（近 7 天）</h2>
    <p v-if="loading" class="state state-loading" role="status" data-loading>统计加载中…</p>
    <p v-else-if="error" class="state state-error" role="alert" data-metrics-error>{{ error }}</p>
    <p v-else-if="stats.length === 0" class="state state-empty" data-empty>
      暂无运行统计数据：项目近 7 天内没有工作流运行记录
    </p>
    <table v-else class="stat-table" data-metrics-table>
      <thead>
        <tr>
          <th>运行日期</th>
          <th>成功</th>
          <th>失败</th>
          <th>跳过</th>
          <th>重试</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in stats" :key="row.runDate" :data-metric-row="row.runDate">
          <td>{{ row.runDate }}</td>
          <td>{{ row.successCount }}</td>
          <td>{{ row.failureCount }}</td>
          <td>{{ row.skippedCount }}</td>
          <td>{{ row.retryCount }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
/**
 * L3-06 项目工作台页（A 组工作台承载，权威设计 §3.3 A 组行 + PRE §四-1 口径）：
 * 全局工作台 = 项目列表页（L3-02 HomeView 已承载全局总览）；本件 = 项目工作台，
 * 承载剩余两语义：① metrics 域统计指标呈现（真实查询→展示闭环）② 快捷导航（PRE §3.2 七段）。
 * metrics 数据源 createMetricsContract（R7 GREEN 收编件，零修改）：queryWorkflowResultStats
 * 按 runDate 逐行呈现四计数（成功/失败/跳过/重试），不聚合（A7 Step 1 口径：FE 不加工推导）。
 * TimeWindowQuery 默认近 7 天窗 + offset 0 / limit 50（B2 缺口 #4 开放点，FE 取值候定稿）。
 * 快捷导航 push `/p/:projectId/<seg>`：路由注册 L3-03 已落地（s251）。
 * 本件为可挂载视图组件（props projectId，路由 props 注入）。
 * 七段段名 L3-03 定稿：提升为 navigation/projectMenu.ts PROJECT_MENU_SECTIONS（s251 派令
 * NAV 段名定稿权落点），本件与 AppShell 项目模式侧栏同源消费（DOM data-nav 锚零变化）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createMetricsContract } from '../services/rebuild/metricsApi'
import type { TimeWindowQuery, WorkflowResultStatRow } from '../services/rebuild/metricsApi'
import { PROJECT_MENU_SECTIONS } from '../navigation/projectMenu'

const props = defineProps<{ projectId: number }>()

const router = useRouter()
const loading = ref(true)
const error = ref('')
const stats = ref<WorkflowResultStatRow[]>([])

function defaultWindow(): TimeWindowQuery {
  const to = new Date()
  const from = new Date(to.getTime() - 7 * 24 * 60 * 60 * 1000)
  return { from: from.toISOString(), to: to.toISOString(), offset: 0, limit: 50 }
}

async function loadStats(): Promise<void> {
  error.value = ''
  try {
    stats.value = await createMetricsContract().queryWorkflowResultStats(props.projectId, defaultWindow())
  } catch (err) {
    error.value = err instanceof Error ? err.message : '统计数据加载失败'
  }
}

function nav(seg: string): void {
  router.push(`/p/${props.projectId}/${seg}`)
}

onMounted(async () => {
  loading.value = true
  await loadStats()
  loading.value = false
})
</script>

<style scoped>
.workbench {
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 24px;
}

.wb-head {
  margin-bottom: 20px;
}

.wb-head h1 {
  margin: 0 0 8px;
  font-size: 28px;
}

.wb-sub {
  margin: 0;
  color: var(--text-secondary, #64748b);
}

.wb-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 32px;
}

.nav-item {
  padding: 10px 18px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  background: var(--bg-surface, #fff);
  cursor: pointer;
  font-size: 14px;
}

.nav-item:hover {
  border-color: var(--primary-color, #2563eb);
}

.wb-section-title {
  margin: 0 0 12px;
  font-size: 18px;
}

.state {
  padding: 32px 0;
  text-align: center;
  color: var(--text-secondary, #64748b);
}

.state-error {
  color: #dc2626;
}

.stat-table {
  width: 100%;
  border-collapse: collapse;
}

.stat-table th,
.stat-table td {
  border: 1px solid var(--border-color, #e2e8f0);
  padding: 8px 12px;
  text-align: left;
}

.stat-table th {
  background: var(--bg-subtle, #f8fafc);
}
</style>
