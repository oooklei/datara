<template>
  <section class="dashboard" aria-label="项目工作台">
    <header class="dashboard-hero">
      <div>
        <div class="eyebrow"><span>PROJECT {{ projectId }}</span><i></i><i></i><i></i></div>
        <h1>项目工作台</h1>
        <p>从运行管线到治理资产，实时掌握项目健康度并直达处置入口。</p>
      </div>
      <button type="button" class="refresh" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新数据' }}</button>
    </header>

    <div v-if="loading && !model" class="loading-grid" role="status" data-dashboard-loading>
      <span v-for="index in 12" :key="index"></span>
    </div>
    <div v-else-if="error && !model" class="dashboard-error" role="alert" data-dashboard-error>
      <strong>工作台数据加载失败</strong><p>{{ error }}</p>
      <button type="button" data-dashboard-retry @click="load">重新加载</button>
    </div>

    <template v-else-if="model">
      <p v-if="model.partialFailures.length" class="partial-warning" data-partial-warning>
        部分数据暂不可用：{{ model.partialFailures.join('、') }}。其余区域仍可正常使用。
      </p>

      <section class="band" aria-labelledby="pipeline-title">
        <header class="band-head"><h2 id="pipeline-title">核心管线</h2><span>工作流与运行态</span></header>
        <div class="kpi-grid pipeline-grid">
          <button v-for="item in pipelineKpis" :key="item.key" type="button" class="kpi-card" :class="item.tone" data-pipeline-kpi :data-kpi-route="item.route" @click="go(item.route)">
            <span class="kpi-label">{{ item.label }}</span><b>{{ item.value }}</b><small>{{ item.detail }}</small>
          </button>
        </div>
      </section>

      <section class="band" aria-labelledby="governance-title">
        <header class="band-head"><h2 id="governance-title">数据治理</h2><span>资产与质量语义</span></header>
        <div class="kpi-grid governance-grid">
          <button v-for="item in governanceKpis" :key="item.key" type="button" class="kpi-card compact" :class="item.tone" data-governance-kpi :data-kpi-route="item.route" @click="go(item.route)">
            <span class="kpi-label">{{ item.label }}</span><b>{{ item.value }}</b><small>{{ item.detail }}</small>
          </button>
        </div>
      </section>

      <section class="chart-grid" aria-label="项目运行图表">
        <article class="panel trend-panel"><header><h2>近 7 天运行趋势</h2><span>成功 / 失败</span></header><div ref="trendChart" class="chart" data-dashboard-chart></div></article>
        <article class="panel"><header><h2>工作流类型分布</h2><span>编排结构</span></header><div ref="typeChart" class="chart" data-dashboard-chart></div></article>
        <article class="panel"><header><h2>运行状态分布</h2><span>结果统计</span></header><div ref="statusChart" class="chart" data-dashboard-chart></div></article>
      </section>

      <section class="panel recent-panel">
        <header><h2>最近运行实例</h2><button type="button" data-run-monitor @click="go('dag?tab=runs')">进入运行监控 →</button></header>
        <div v-if="!model.recentRuns.length" class="empty">近 7 天暂无运行实例</div>
        <div v-else class="table-wrap">
          <table>
            <thead><tr><th>工作流</th><th>类型</th><th>状态</th><th>成功/失败</th><th>开始时间</th></tr></thead>
            <tbody>
              <tr v-for="run in model.recentRuns" :key="run.id" data-recent-run tabindex="0" @click="openRun(run.id)" @keydown.enter="openRun(run.id)">
                <td><strong>{{ run.dag_name || `工作流 #${run.workflow_id}` }}</strong></td>
                <td>{{ run.instance_type }}</td>
                <td><span class="status-pill" :class="statusTone(run.status)">{{ statusText(run.status) }}</span></td>
                <td>{{ run.success_count }} / {{ run.failure_count }}</td>
                <td>{{ formatTime(run.started_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { loadProjectDashboard, type ProjectDashboardModel } from '../services/rebuild/projectDashboard'

const props = defineProps<{ projectId: number }>()
const router = useRouter()
const loading = ref(true)
const error = ref('')
const model = ref<ProjectDashboardModel | null>(null)
const trendChart = ref<HTMLElement | null>(null)
const typeChart = ref<HTMLElement | null>(null)
const statusChart = ref<HTMLElement | null>(null)
const charts: echarts.ECharts[] = []

const pipelineKpis = computed(() => {
  const current = model.value!
  const total = current.workflowTypes.normal + current.workflowTypes.sync + current.workflowTypes.stream
  return [
    { key: 'workflows', label: '工作流总数', value: total, detail: `普通 ${current.workflowTypes.normal} · 同步 ${current.workflowTypes.sync} · 流 ${current.workflowTypes.stream}`, route: 'dag', tone: '' },
    { key: 'success', label: '近 7 天成功', value: current.runTotals.success, detail: '已处理成功记录', route: 'dag?tab=runs&status=SUCCEEDED', tone: 'success' },
    { key: 'failure', label: '近 7 天失败', value: current.runTotals.failure, detail: '点击进入失败实例', route: 'dag?tab=runs&status=FAILED', tone: current.runTotals.failure ? 'danger' : '' },
    { key: 'running', label: '运行中实例', value: current.runTotals.running, detail: '包含实时流任务', route: 'dag?tab=runs&status=RUNNING', tone: 'primary' },
    { key: 'skipped', label: '跳过记录', value: current.runTotals.skipped, detail: '近 7 天累计', route: 'dag?tab=runs', tone: '' },
    { key: 'retry', label: '重试记录', value: current.runTotals.retry, detail: '近 7 天累计', route: 'dag?tab=runs', tone: 'warning' },
  ]
})

const governanceKpis = computed(() => {
  const current = model.value!.governance
  return [
    { key: 'datasources', label: '数据源', value: current.datasources, detail: '连接与元数据', route: 'ds/list', tone: 'primary' },
    { key: 'resources', label: '资源', value: current.resources, detail: 'SQL / Python / Shell', route: 'resources', tone: '' },
    { key: 'rules', label: '质量规则', value: current.qualityRules, detail: '项目规则总数', route: 'qc/rule', tone: '' },
    { key: 'exceptions', label: '未处置异常', value: current.openExceptions, detail: '待核查与处置', route: 'qc/exception', tone: current.openExceptions ? 'warning' : '' },
    { key: 'assets', label: '数据资产', value: current.assets, detail: '目录收录资产', route: 'meta/catalog', tone: '' },
    { key: 'standards', label: '数据标准', value: current.standards, detail: '已定义标准', route: 'std/element', tone: '' },
    { key: 'metrics', label: '指标目录', value: current.metrics, detail: '业务指标', route: 'ind/list', tone: '' },
  ]
})

function go(suffix: string): void { void router.push(`/p/${props.projectId}/${suffix}`) }
function openRun(id: number): void { go(`dag?tab=runs&runId=${id}`) }
function formatTime(value: string): string { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
function statusText(status: string): string {
  return ({ SUCCESS: '成功', FAILED: '失败', RUNNING: '运行中', SKIPPED: '跳过' } as Record<string, string>)[status.toUpperCase()] ?? status
}
function statusTone(status: string): string { return status.toLowerCase() }

function renderCharts(): void {
  charts.splice(0).forEach((chart) => chart.dispose())
  if (!model.value || !trendChart.value || !typeChart.value || !statusChart.value) return
  const dark = document.documentElement.dataset.theme === 'dark'
  const text = dark ? '#b3c0d4' : '#5b6478'
  const grid = dark ? '#27364a' : '#e7eaf0'
  const common = { textStyle: { color: text }, animationDuration: 420 }
  const trend = echarts.init(trendChart.value)
  trend.setOption({ ...common, tooltip: { trigger: 'axis' }, legend: { data: ['成功', '失败'], textStyle: { color: text } }, grid: { left: 42, right: 18, top: 42, bottom: 30 }, xAxis: { type: 'category', data: model.value.dailyStats.map((row) => row.runDate.slice(5)), axisLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: grid } } }, series: [{ name: '成功', type: 'line', smooth: true, data: model.value.dailyStats.map((row) => row.successCount), itemStyle: { color: '#16a34a' }, areaStyle: { color: 'rgba(22,163,74,.09)' } }, { name: '失败', type: 'line', smooth: true, data: model.value.dailyStats.map((row) => row.failureCount), itemStyle: { color: '#e5484d' } }] })
  const types = echarts.init(typeChart.value)
  types.setOption({ ...common, tooltip: { trigger: 'item' }, legend: { bottom: 4, textStyle: { color: text } }, series: [{ type: 'pie', radius: ['38%', '66%'], center: ['50%', '44%'], data: [{ name: '普通', value: model.value.workflowTypes.normal }, { name: '同步', value: model.value.workflowTypes.sync }, { name: '流处理', value: model.value.workflowTypes.stream }], color: ['#1668dc', '#0891b2', '#7c3aed'] }] })
  const status = echarts.init(statusChart.value)
  status.setOption({ ...common, tooltip: { trigger: 'axis' }, grid: { left: 44, right: 15, top: 25, bottom: 30 }, xAxis: { type: 'category', data: ['成功', '失败', '跳过', '重试'], axisLine: { lineStyle: { color: grid } } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: grid } } }, series: [{ type: 'bar', barMaxWidth: 30, data: [model.value.runTotals.success, model.value.runTotals.failure, model.value.runTotals.skipped, model.value.runTotals.retry], itemStyle: { color: (params: { dataIndex: number }) => ['#1668dc', '#e5484d', '#8c94a6', '#d97706'][params.dataIndex], borderRadius: [4, 4, 0, 0] } }] })
  charts.push(trend, types, status)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    model.value = await loadProjectDashboard(props.projectId)
    await nextTick()
    renderCharts()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目工作台加载失败'
  } finally { loading.value = false }
}

function resizeCharts(): void { charts.forEach((chart) => chart.resize()) }
onMounted(() => { void load(); window.addEventListener('resize', resizeCharts) })
onBeforeUnmount(() => { window.removeEventListener('resize', resizeCharts); charts.splice(0).forEach((chart) => chart.dispose()) })
</script>

<style scoped>
.dashboard{min-height:100%;padding:18px;background:var(--bg)}
.dashboard-hero{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px}.dashboard-hero h1{margin:2px 0 1px;font-size:24px;letter-spacing:-.6px}.dashboard-hero p{color:var(--text-3)}.eyebrow{display:flex;align-items:center;gap:5px;color:var(--primary);font-size:10px;font-weight:800;letter-spacing:1.2px}.eyebrow i{width:7px;height:7px;background:var(--primary)}.eyebrow i:nth-child(3){border-radius:50%;background:var(--purple)}.eyebrow i:nth-child(4){clip-path:polygon(50% 0,100% 100%,0 100%);background:var(--cyan)}
.refresh,.dashboard-error button{border:1px solid var(--border-strong);border-radius:7px;background:var(--card);color:var(--text-2);padding:7px 13px;cursor:pointer}.refresh:hover{border-color:var(--primary);color:var(--primary)}
.band{margin-bottom:14px}.band-head{display:flex;align-items:baseline;gap:14px;margin:0 0 8px 2px}.band-head h2,.panel h2{font-size:14px}.band-head h2::before,.panel header h2::before{content:'';display:inline-block;width:3px;height:14px;margin-right:8px;border-radius:2px;background:linear-gradient(var(--primary),var(--purple));vertical-align:-2px}.band-head span,.panel header span{font-size:11px;color:var(--text-3)}
.kpi-grid{display:grid;gap:10px}.pipeline-grid{grid-template-columns:repeat(6,minmax(0,1fr))}.governance-grid{grid-template-columns:repeat(7,minmax(0,1fr))}.kpi-card{min-width:0;padding:12px 13px;text-align:left;border:1px solid var(--border);border-radius:9px;background:var(--card);box-shadow:var(--shadow);cursor:pointer;position:relative;overflow:hidden}.kpi-card::before{content:'';position:absolute;inset:0 auto 0 0;width:3px;background:transparent}.kpi-card:hover{transform:translateY(-1px);border-color:var(--primary);box-shadow:var(--shadow-md)}.kpi-card b{display:block;margin:2px 0;font-size:23px;line-height:1.2}.kpi-card small,.kpi-label{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-3);font-size:10.5px}.kpi-label{font-size:11.5px}.kpi-card.primary::before{background:var(--primary)}.kpi-card.success::before{background:var(--success)}.kpi-card.danger::before{background:var(--danger)}.kpi-card.warning::before{background:var(--warn)}.kpi-card.compact b{font-size:21px}
.chart-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin:14px 0}.panel{border:1px solid var(--border);border-radius:9px;background:var(--card);box-shadow:var(--shadow)}.panel>header{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid var(--border)}.chart{height:250px}
.recent-panel>header{justify-content:space-between}.recent-panel>header button{border:0;background:none;color:var(--primary);cursor:pointer}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:9px 14px;text-align:left;border-bottom:1px solid var(--border);font-size:12px}th{background:var(--bg);color:var(--text-2)}tbody tr{cursor:pointer}tbody tr:hover{background:var(--primary-light)}.status-pill{padding:2px 8px;border-radius:11px;background:var(--bg-deep);color:var(--text-2);font-size:10px}.status-pill.success{background:var(--success-bg);color:var(--success)}.status-pill.failed{background:var(--danger-bg);color:var(--danger)}.status-pill.running{background:var(--info-bg);color:var(--info)}
.partial-warning,.dashboard-error{margin-bottom:12px;padding:10px 12px;border:1px solid color-mix(in srgb,var(--warn) 35%,var(--border));border-radius:8px;background:var(--warn-bg);color:var(--warn)}.dashboard-error{display:grid;place-items:start;gap:8px;color:var(--danger);background:var(--danger-bg)}.empty{padding:36px;text-align:center;color:var(--text-3)}.loading-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.loading-grid span{height:88px;border-radius:9px;background:linear-gradient(100deg,var(--card) 20%,var(--bg-deep) 45%,var(--card) 70%);background-size:300% 100%;animation:pulse 1.2s infinite}@keyframes pulse{to{background-position:-150% 0}}
@media(max-width:1180px){.pipeline-grid{grid-template-columns:repeat(3,1fr)}.governance-grid{grid-template-columns:repeat(4,1fr)}.chart-grid{grid-template-columns:1fr 1fr}.trend-panel{grid-column:1/-1}}
@media(max-width:767px){.dashboard{padding:12px}.dashboard-hero{gap:12px}.dashboard-hero h1{font-size:20px}.dashboard-hero p{display:none}.pipeline-grid,.governance-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.chart-grid{grid-template-columns:1fr}.trend-panel{grid-column:auto}.chart{height:220px}.kpi-card b{font-size:20px}.table-wrap{max-width:100%}}
</style>
