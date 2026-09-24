<script setup lang="ts">
/**
 * I11 页面组件（C24）看板浮窗：流任务 API 通道数据 → 实时看板。
 * - 数据接入与 StreamDataPage 同骨架：docId 定位流任务 → SSE 推送（断线回退 3s 轮询）；
 * - 渲染按行字段特征自适应（union 混合 schema 天然分流，一套逻辑支撑三模板）：
 *   窗口行（含 win_start）按窗口分桶 → 最新窗口渲染指标卡/分布，历史窗口渲染趋势曲线；
 *   事件行（如 IoT 告警透传，无 win_start）单独列出；
 * - preset 仅影响标题文案，ecommerce/IoT/visit 三场景与自定义共用本组件。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { GNode, GraphDocument } from '../../model'
import { isMock, listStreamJobs, pollStreamData, startStreamJob, stopStreamJob, streamSseUrl } from '../../../services'
import type { StreamDataPage, StreamJobRow } from '../../../services'

echarts.use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ node: GNode; doc: GraphDocument }>()

type Row = Record<string, unknown>

const job = ref<StreamJobRow | null>(null)
const rows = ref<Row[]>([])
const fields = ref<string[]>([])
const mode = ref<'sse' | 'poll' | 'off'>('off')
const loadErr = ref('')
const acting = ref(false)
let es: EventSource | null = null
let timer = 0
let lineChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null
const lineEl = ref<HTMLDivElement | null>(null)
const pieEl = ref<HTMLDivElement | null>(null)

const PRESET_LABEL: Record<string, string> = {
  ecommerce: '电商实时大盘', iot: 'IoT 设备监控', visit: '站点访问分析', custom: '自定义看板',
}
const presetLabel = computed(() => PRESET_LABEL[String(props.node.data.preset ?? 'custom')] ?? '自定义看板')

/* ---------- 通用工具 ---------- */
const numOf = (v: unknown): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
const gmvOf = (r: Row): number => numOf(r.amt_total ?? r.gmv)
const round2 = (v: number): number => Math.round(v * 100) / 100
const fmtTime = (ws: number): string => {
  const d = new Date(ws * 1000)
  const p = (x: number): string => String(x).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
const num = (v: unknown): string => numOf(v).toLocaleString()

/* ---------- 行特征分流（union 混合 schema 自适应） ---------- */
const winRows = computed(() => rows.value.filter((r) => r.win_start !== undefined))
const alertRows = computed(() => rows.value.filter((r) => r.event === 'alert'))

/** 按 win_start 分桶（升序）：[0]=历史窗口… [last]=最新窗口 */
const buckets = computed(() => {
  const m = new Map<number, Row[]>()
  winRows.value.forEach((r) => {
    const ws = Number(r.win_start)
    if (!m.has(ws)) m.set(ws, [])
    m.get(ws)!.push(r)
  })
  return [...m.entries()].sort((a, b) => a[0] - b[0])
})
const latest = computed<Row[]>(() => buckets.value.at(-1)?.[1] ?? [])

/* ---------- 指标卡（按当前窗口行特征生成） ---------- */
const cards = computed(() => {
  const list: { label: string; value: string; accent?: boolean }[] = []
  const cur = latest.value
  const gmv = cur.reduce((s, r) => s + gmvOf(r), 0)
  const ordCnt = cur.reduce((s, r) => s + numOf(r.ord_cnt), 0)
  const uv = cur.reduce((s, r) => s + numOf(r.uv), 0)
  const pv = cur.reduce((s, r) => s + numOf(r.page_pv ?? r.pv), 0)
  if (gmv > 0 || ordCnt > 0 || pv > 0) {
    list.push({ label: 'GMV（当前窗口）', value: gmv.toLocaleString(undefined, { maximumFractionDigits: 2 }), accent: true })
    if (ordCnt > 0) list.push({ label: '订单数', value: String(ordCnt) })
    if (uv > 0) list.push({ label: 'UV', value: String(uv) })
    if (pv > 0) list.push({ label: 'PV', value: String(pv) })
  }
  const iot = cur.filter((r) => r.temp_avg !== undefined)
  if (iot.length) {
    list.push({ label: '平均温度', value: round2(iot.reduce((s, r) => s + numOf(r.temp_avg), 0) / iot.length).toFixed(1), accent: true })
    list.push({ label: '设备数', value: String(new Set(iot.map((r) => String(r.device))).size) })
  }
  if (alertRows.value.length) {
    list.push({ label: '告警（累计）', value: String(alertRows.value.length), accent: true })
  }
  if (!list.length) {
    list.push({ label: '速率（条/秒）', value: num(job.value?.metrics?.ratePerSec) })
    list.push({ label: '累计输出', value: num(job.value?.metrics?.totalOut) })
  }
  return list
})

/* ---------- 趋势曲线（历史窗口时序，存在的维度才出 series） ---------- */
const lineSeries = computed(() => {
  const xs: string[] = []
  const gmv: number[] = []
  const pv: number[] = []
  const temp: number[] = []
  buckets.value.forEach(([, rs]) => {
    xs.push(fmtTime(Number(rs[0]?.win_start)))
    gmv.push(round2(rs.reduce((s, r) => s + gmvOf(r), 0)))
    pv.push(rs.reduce((s, r) => s + numOf(r.page_pv ?? r.pv), 0))
    const iot = rs.filter((r) => r.temp_avg !== undefined)
    temp.push(iot.length ? round2(iot.reduce((s, r) => s + numOf(r.temp_avg), 0) / iot.length) : Number.NaN)
  })
  const series: { name: string; type: 'line'; smooth: boolean; data: number[] }[] = []
  if (gmv.some((v) => v > 0)) series.push({ name: 'GMV', type: 'line', smooth: true, data: gmv })
  if (pv.some((v) => v > 0)) series.push({ name: 'PV', type: 'line', smooth: true, data: pv })
  if (temp.some((v) => !Number.isNaN(v))) series.push({ name: '平均温度', type: 'line', smooth: true, data: temp })
  return { xs, series }
})

/* ---------- 分布饼图：优先 page 分布（visit），退化 goods 排行（点击/加购合并热度） ---------- */
const pieData = computed(() => {
  const cur = latest.value
  const pageRows = cur.filter((r) => r.page_pv !== undefined)
  if (pageRows.length) {
    return pageRows.map((r) => ({ name: String(r.page ?? '?'), value: numOf(r.page_pv) }))
  }
  const goods = new Map<string, number>()
  cur.forEach((r) => {
    if (r.goods_id === undefined) return
    const v = numOf(r.click_cnt) + numOf(r.cart_cnt)
    if (v > 0) goods.set(String(r.goods_id), (goods.get(String(r.goods_id)) ?? 0) + v)
  })
  return [...goods.entries()].map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value).slice(0, 8)
})

/* ---------- 明细表列 ---------- */
const tableFields = computed<string[]>(() => {
  if (fields.value.length) return fields.value
  const set = new Set<string>()
  rows.value.slice(0, 20).forEach((r) => Object.keys(r).forEach((k) => set.add(k)))
  return [...set]
})

/* ---------- 数据接入（StreamDataPage 同骨架） ---------- */
function stCls(s: string): string {
  return s === 'running' ? 'ok' : s === 'failed' ? 'err' : ['starting', 'reconnecting'].includes(s) ? 'info' : 'off'
}
function stLabel(s: string): string {
  return ({
    starting: '启动中', running: '运行中', reconnecting: '重连中', stopped: '已停止', failed: '失败',
  } as Record<string, string>)[s] ?? (s || '未启动')
}
function applyPage(p: StreamDataPage): void {
  if (p.fields?.length) fields.value = p.fields
  rows.value = p.rows
  if (p.metrics) job.value = job.value ? { ...job.value, metrics: p.metrics, status: p.metrics.status || job.value.status } : job.value
}

function openSse(id: number): void {
  es?.close()
  mode.value = 'sse'
  es = new EventSource(streamSseUrl(id))
  es.onmessage = (ev) => {
    try { applyPage(JSON.parse(ev.data) as StreamDataPage) } catch { /* 忽略坏帧 */ }
  }
  es.onerror = () => {
    es?.close()
    es = null
    mode.value = 'poll'
    timer = window.setInterval(refreshPoll, 3000)
  }
}

async function refreshPoll(): Promise<void> {
  if (!job.value) return
  try {
    applyPage(await pollStreamData(job.value.id, 600))
    loadErr.value = ''
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  }
}

async function refreshJob(): Promise<void> {
  const list = await listStreamJobs({ docId: props.doc.id, pageSize: 1 })
  job.value = list[0] ?? null
  if (job.value && mode.value === 'off') {
    if (['running', 'reconnecting'].includes(job.value.status)) openSse(job.value.id)
    else mode.value = 'poll'
  }
}

async function act(kind: 'start' | 'stop'): Promise<void> {
  acting.value = true
  try {
    if (kind === 'start') {
      const r = await startStreamJob(props.doc.id)
      ElMessage.success(`流任务已${r.restarted ? '重启' : '启动'}（${r.name}）`)
      await refreshJob()
    } else if (job.value) {
      await stopStreamJob(job.value.id)
      ElMessage.success('流任务已停止')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    acting.value = false
  }
}

/* ---------- 图表渲染 ---------- */
function renderCharts(): void {
  const { xs, series } = lineSeries.value
  if (lineEl.value && xs.length && series.length) {
    lineChart ??= echarts.init(lineEl.value)
    lineChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { top: 0, right: 0, itemWidth: 12, textStyle: { fontSize: 10 } },
      grid: { left: 46, right: 12, top: 26, bottom: 22 },
      xAxis: { type: 'category', data: xs, axisLabel: { fontSize: 9 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 9 } },
      series,
    }, { notMerge: true })
  }
  const pie = pieData.value
  if (pieEl.value && pie.length) {
    pieChart ??= echarts.init(pieEl.value)
    pieChart.setOption({
      tooltip: {},
      legend: { orient: 'vertical', right: 0, top: 'middle', itemWidth: 10, textStyle: { fontSize: 10 } },
      series: [{ type: 'pie', radius: ['35%', '68%'], center: ['38%', '50%'], data: pie, label: { show: false } }],
    }, { notMerge: true })
  }
}

watch(rows, () => nextTick(renderCharts))

onMounted(async () => {
  if (isMock) return
  try {
    await refreshJob()
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  }
  if (mode.value === 'poll') timer = window.setInterval(refreshPoll, 3000)
})
onBeforeUnmount(() => {
  es?.close()
  es = null
  window.clearInterval(timer)
  lineChart?.dispose()
  pieChart?.dispose()
  lineChart = null
  pieChart = null
})
</script>

<template>
  <div class="bdp">
    <div class="bdp-head">
      <span class="pill info">{{ presetLabel }}</span>
      <span v-if="job" class="pill" :class="stCls(job.status)">{{ stLabel(job.status) }}</span>
      <span v-if="mode !== 'off'" class="pill">{{ mode === 'sse' ? 'SSE 推送' : '轮询 3s' }}</span>
      <span class="bdp-spacer" />
      <el-button size="small" type="primary" :disabled="acting || isMock" @click="act('start')">启动 / 重启</el-button>
      <el-button size="small" :disabled="acting || !job || ['stopped', 'failed'].includes(job.status)" @click="act('stop')">停止</el-button>
    </div>

    <div v-if="isMock" class="bdp-empty">mock 模式无流引擎数据源。</div>
    <div v-else-if="!job" class="bdp-empty">
      本画布尚未注册流任务。<br />
      <span style="font-size:11px">保存画布后点「试运行」启动常驻流任务，本页即实时看板（数据来自 API 输出通道）。</span>
    </div>
    <template v-else>
      <div v-if="loadErr" class="bdp-empty err">{{ loadErr }}</div>

      <div class="bdp-cards">
        <div v-for="c in cards" :key="c.label" class="m-card">
          <b :style="c.accent ? 'color:var(--primary)' : ''">{{ c.value }}</b>
          <span>{{ c.label }}</span>
        </div>
      </div>

      <div class="bdp-charts">
        <div class="chart-box" :style="{ flex: pieData.length ? '2' : '1' }">
          <div class="chart-title">窗口趋势</div>
          <div v-show="lineSeries.series.length" ref="lineEl" class="chart-canvas" />
          <div v-if="!lineSeries.series.length" class="bdp-empty">暂无窗口数据（等待窗口触发…）</div>
        </div>
        <div v-if="pieData.length" class="chart-box">
          <div class="chart-title">{{ latest.some((r) => r.page_pv !== undefined) ? '页面访问分布' : '商品热度排行' }}</div>
          <div ref="pieEl" class="chart-canvas" />
        </div>
      </div>

      <div v-if="alertRows.length" class="bdp-alerts">
        <div class="chart-title">实时告警（{{ alertRows.length }}）</div>
        <div class="alert-list">
          <div v-for="(a, i) in [...alertRows].reverse().slice(0, 12)" :key="i" class="alert-item">
            <span class="mono">{{ a.ts ? fmtTime(Number(a.ts)) : '-' }}</span>
            <span>{{ a.device ?? '?' }}</span>
            <span class="alert-type">{{ a.type ?? '' }}</span>
          </div>
        </div>
      </div>

      <div class="bdp-table">
        <div class="chart-title">明细数据（Last-{{ rows.length }}）</div>
        <div class="tbl-wrap">
          <table class="tbl">
            <thead>
              <tr><th v-for="c in tableFields" :key="c">{{ c }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in [...rows].reverse().slice(0, 30)" :key="i">
                <td v-for="c in tableFields" :key="c" class="mono">{{ r[c] === undefined ? '' : typeof r[c] === 'object' ? JSON.stringify(r[c]) : String(r[c]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bdp{padding:10px 12px;display:flex;flex-direction:column;height:100%;gap:8px;overflow:auto}
.bdp-head{display:flex;align-items:center;gap:8px;flex-shrink:0}
.bdp-spacer{flex:1}
.bdp-empty{text-align:center;color:var(--text-3);font-size:12px;padding:18px 8px;line-height:1.9}
.bdp-empty.err{color:var(--danger)}
.bdp-cards{display:flex;gap:8px;flex-shrink:0;flex-wrap:wrap}
.m-card{flex:1;min-width:96px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px 6px;text-align:center}
.m-card b{display:block;font-size:16px}
.m-card span{font-size:10px;color:var(--text-3)}
.bdp-charts{display:flex;gap:8px;flex-shrink:0;min-height:180px}
.chart-box{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 8px;display:flex;flex-direction:column;min-width:0}
.chart-title{font-size:11px;color:var(--text-2);margin-bottom:2px;flex-shrink:0}
.chart-canvas{flex:1;min-height:140px;width:100%}
.bdp-alerts{flex-shrink:0}
.alert-list{display:flex;flex-direction:column;gap:2px;max-height:110px;overflow:auto}
.alert-item{display:flex;gap:10px;font-size:11px;padding:2px 6px;background:var(--bg);border:1px solid var(--border);border-radius:4px}
.alert-type{color:var(--danger);font-weight:600}
.bdp-table{flex-shrink:0}
.tbl-wrap{max-height:150px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm)}
.tbl{width:100%;border-collapse:collapse;font-size:11px}
.tbl th{position:sticky;top:0;background:var(--bg);text-align:left;padding:4px 6px;border-bottom:1px solid var(--border)}
.tbl td{padding:3px 6px;border-bottom:1px solid var(--border);white-space:nowrap}
.mono{font-family:var(--font-mono,monospace)}
</style>
