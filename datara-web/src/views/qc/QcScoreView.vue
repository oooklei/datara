<script setup lang="ts">
/**
 * M07 质量评分卡（/qc/score）
 * 原型对齐：prototype/assets/pages/m07-quality.js L7-34（#/qc/score）
 * 顶部统计卡（综合评分/待核查异常/生效规则/及时性）+ 分层趋势（SVG 折线，无新依赖）
 * + 六维得分环 + 异常明细表（核查 → /qc/exception）。本页只读，无写操作。
 * 数据：qcReports / qcExceptions / qcRules / qcScoreTrend / qcDimScore / qcDims。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { QcReport, QcException, QcRule, QcScoreTrend, QcDim, QcDimScore } from '../../services/types'

const router = useRouter()

const reports = ref<QcReport[]>([])
const exceptions = ref<QcException[]>([])
const rules = ref<QcRule[]>([])
const dims = ref<QcDim[]>([])
const dimScores = ref<QcDimScore[]>([])
const trend = ref<QcScoreTrend | null>(null)

onMounted(async () => {
  reports.value = [...((await dataStore.list<QcReport>('qcReports')) ?? [])]
  exceptions.value = [...((await dataStore.list<QcException>('qcExceptions')) ?? [])]
  rules.value = [...((await dataStore.list<QcRule>('qcRules')) ?? [])]
  dims.value = [...((await dataStore.list<QcDim>('qcDims')) ?? [])]
  dimScores.value = [...((await dataStore.list<QcDimScore>('qcDimScore')) ?? [])]
  trend.value = await dataStore.get<QcScoreTrend>('qcScoreTrend')
})

/* ---- 统计卡 ---- */
const lastReport = computed(() => reports.value[0] ?? null)
const pendingCnt = computed(() => exceptions.value.filter((e) => e.status === 'pending').length)
const enabledCnt = computed(() => rules.value.filter((r) => r.status === 'enabled').length)
const strongEnabledCnt = computed(
  () => rules.value.filter((r) => r.level === '强规则' && r.status === 'enabled').length,
)

/* ---- 分层趋势折线（SVG） ---- */
const SERIES = [
  { key: 'ods', name: 'ODS', color: '#0891b2' },
  { key: 'dwd', name: 'DWD', color: '#1668dc' },
  { key: 'dws', name: 'DWS', color: '#7c3aed' },
  { key: 'ads', name: 'ADS', color: '#16a34a' },
] as const

const CHART_W = 640
const CHART_H = 210
const PAD_L = 34
const PAD_T = 10
const PAD_B = 22
const V_MIN = 85
const V_MAX = 100
const GRID = [85, 90, 95, 100]

const chart = computed(() => {
  const t = trend.value
  if (!t) return null
  return { labels: t.labels, series: SERIES.map((s) => ({ name: s.name, color: s.color, data: t[s.key] })) }
})

function xAt(i: number, n: number): number {
  return PAD_L + (n <= 1 ? 0 : (i * (CHART_W - PAD_L - 10)) / (n - 1))
}
function yAt(v: number): number {
  return PAD_T + ((V_MAX - v) / (V_MAX - V_MIN)) * (CHART_H - PAD_T - PAD_B)
}
function polyPoints(data: number[], labels: string[]): string {
  return data.map((v, i) => `${xAt(i, labels.length).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
}

/* ---- 六维得分环 ---- */
function ringDash(score: number): string {
  const c = 2 * Math.PI * 24
  return `${((score / 100) * c).toFixed(1)} ${c.toFixed(1)}`
}
function ringColor(score: number): string {
  return score >= 95 ? '#16a34a' : score >= 90 ? '#1668dc' : '#d97706'
}
function dimGrade(score: number): string {
  return score >= 95 ? '优' : score >= 90 ? '良' : '待改进'
}
function dimIcon(name: string): string {
  return dims.value.find((d) => d.name === name)?.icon ?? '✓'
}

/* ---- 状态徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

function goException() {
  router.push('/qc/exception')
}
</script>

<template>
  <div class="page">
    <!-- 页头 + 顶部工具栏按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">质量评分卡</div>
        <div class="ph-desc">全库质量健康度总览：六维得分 · 分层趋势 · 问题分布，评分 = 100 - Σ(问题扣分)，弱规则半权计分</div>
      </div>
      <div class="ph-acts">
        <button class="tb-new" @click="router.push('/qc/task')">检查任务</button>
        <button class="op-btn" @click="router.push('/qc/report')">质量报告</button>
      </div>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid">
      <div class="card stat-card">
        <span class="sc-icon" style="background:#16a34a">✓</span>
        <div>
          <div class="stat-num">{{ lastReport?.score ?? '-' }}</div>
          <div class="stat-label">综合评分（{{ lastReport?.period ?? '-' }}）</div>
        </div>
      </div>
      <div class="card stat-card">
        <span class="sc-icon" style="background:#e5484d">⚑</span>
        <div>
          <div class="stat-num">{{ pendingCnt }}</div>
          <div class="stat-label">待核查异常</div>
        </div>
      </div>
      <div class="card stat-card">
        <span class="sc-icon" style="background:#1668dc">⌇</span>
        <div>
          <div class="stat-num">{{ enabledCnt }}</div>
          <div class="stat-label">生效规则（强 {{ strongEnabledCnt }}）</div>
        </div>
      </div>
      <div class="card stat-card">
        <span class="sc-icon" style="background:#d97706">⏱</span>
        <div>
          <div class="stat-num">100</div>
          <div class="stat-label">及时性得分（SLA达标）</div>
        </div>
      </div>
    </div>

    <!-- 趋势 + 六维 -->
    <div class="mid-grid">
      <div class="card panel">
        <div class="panel-title">分层质量评分趋势（近8日）</div>
        <svg v-if="chart" :viewBox="`0 0 ${CHART_W} ${CHART_H}`" class="trend-svg">
          <g v-for="g in GRID" :key="g">
            <line :x1="PAD_L" :x2="CHART_W - 10" :y1="yAt(g)" :y2="yAt(g)" stroke="var(--border)" stroke-width="1" />
            <text :x="PAD_L - 6" :y="yAt(g) + 3" text-anchor="end" font-size="10" fill="var(--text-3)">{{ g }}</text>
          </g>
          <text
            v-for="(lb, i) in chart.labels" :key="lb" :x="xAt(i, chart.labels.length)"
            :y="CHART_H - 6" text-anchor="middle" font-size="10" fill="var(--text-3)"
          >{{ lb }}</text>
          <polyline
            v-for="s in chart.series" :key="s.name" fill="none" :stroke="s.color" stroke-width="1.8"
            stroke-linejoin="round" :points="polyPoints(s.data, chart.labels)"
          />
        </svg>
        <div class="legend">
          <span v-for="s in SERIES" :key="s.name" class="lg-item">
            <i class="lg-dot" :style="{ background: s.color }" />{{ s.name }}
          </span>
        </div>
        <div class="lock-tip">DWD 层 09-11 降至 90 分：QC-R-012 支付金额范围检查失败（12 行异常），点击下方异常核查处理。</div>
      </div>

      <div class="card panel">
        <div class="panel-title">六维雷达得分</div>
        <div class="dim-grid">
          <div v-for="d in dimScores" :key="d.name" class="dim-item">
            <svg width="56" height="56" viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="24" fill="none" stroke="var(--border)" stroke-width="6" />
              <circle
                cx="28" cy="28" r="24" fill="none" :stroke="ringColor(d.score)" stroke-width="6"
                stroke-linecap="round" :stroke-dasharray="ringDash(d.score)" transform="rotate(-90 28 28)"
              />
              <text x="28" y="32" text-anchor="middle" font-size="13" font-weight="700" :fill="ringColor(d.score)">{{ d.score }}</text>
            </svg>
            <div>
              <b class="dim-name">{{ dimIcon(d.name) }} {{ d.name }}</b>
              <div class="dim-grade">{{ dimGrade(d.score) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 异常明细 -->
    <div class="card panel">
      <div class="panel-title">异常明细（待处理 {{ pendingCnt }}）</div>
      <table class="tbl">
        <thead>
          <tr>
            <th>异常单</th><th>规则</th><th>表</th><th>异常数</th><th>日期</th><th>状态</th><th style="width:80px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in exceptions" :key="e.id">
            <td><b class="mono" style="font-size:12px">{{ e.id }}</b></td>
            <td>{{ e.ruleName }}</td>
            <td><span class="mono" style="font-size:11.5px">{{ e.table }}</span></td>
            <td><b style="color:var(--danger)">{{ e.cnt }}</b></td>
            <td style="color:var(--text-2)">{{ e.dt }}</td>
            <td><span class="st" :class="stCls(e.status)"><span class="dot" />{{ stLabel(e.status) }}</span></td>
            <td><button class="op-btn primary" @click="goException">核查</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="exceptions.length === 0" class="empty">暂无异常记录，检核全部通过</div>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.ph-acts{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:12px;padding:13px 15px}
.sc-icon{width:34px;height:34px;border-radius:9px;color:#fff;font-size:15px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.stat-num{font-size:21px;font-weight:700;line-height:1.2}
.stat-label{font-size:11.5px;color:var(--text-3)}
.mid-grid{display:grid;grid-template-columns:1.6fr 1fr;gap:14px;align-items:flex-start;margin-bottom:14px}
.panel{padding:14px 16px}
.panel-title{font-weight:700;font-size:13px;margin-bottom:10px}
.trend-svg{width:100%;height:auto;display:block}
.legend{display:flex;gap:14px;margin-top:6px}
.lg-item{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--text-2)}
.lg-dot{width:8px;height:8px;border-radius:50%}
.dim-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.dim-item{display:flex;gap:10px;align-items:center;padding:9px 11px;border:1px solid var(--border);border-radius:9px}
.dim-name{font-size:12.5px}
.dim-grade{font-size:11px;color:var(--text-3)}
.lock-tip{margin-top:10px;border-left:3px solid var(--warn);background:var(--warn-bg);color:var(--warn);font-size:11.5px;padding:7px 10px;border-radius:0 7px 7px 0}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
</style>
