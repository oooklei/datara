<script setup lang="ts">
/**
 * M10i 指标看板（/ind/board）
 * 对齐 prototype/assets/pages/m10-standard.js L738-764：
 * 核心指标趋势卡（今日/日环比/近8日均/较8日前 + 折线 + 指标切换）、
 * 渠道拆解环形图（CSS conic-gradient）、指标健康度卡片（前 3 个指标）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dataStore } from '../../services/mock/dataStore'
import type { Indicator } from '../../services/types'

const router = useRouter()

const indicators = ref<Indicator[]>([])
const activeIdx = ref(0)

const cur = computed<Indicator | null>(() => indicators.value[activeIdx.value] ?? null)

async function reload() {
  indicators.value = [...((await dataStore.list<Indicator>('indicators')) ?? [])]
}

onMounted(reload)

/* ---- 趋势统计 ---- */
const todayVal = computed(() => {
  const t = cur.value?.trend ?? []
  return t.length ? t[t.length - 1] : 0
})
const dayOverDay = computed(() => {
  const t = cur.value?.trend ?? []
  if (t.length < 2 || !t[t.length - 2]) return '0.0'
  return (((t[t.length - 1] - t[t.length - 2]) / t[t.length - 2]) * 100).toFixed(1)
})
const avg8 = computed(() => {
  const t = cur.value?.trend ?? []
  if (!t.length) return 0
  return Math.round(t.reduce((a, b) => a + b, 0) / t.length)
})
const vs8d = computed(() => {
  const t = cur.value?.trend ?? []
  if (t.length < 2 || !t[0]) return '0.0'
  return ((t[t.length - 1] / t[0]) * 100 - 100).toFixed(1)
})

/* ---- 折线图（SVG，8 个趋势点） ---- */
const W = 560
const H = 160
const PAD = 12
const linePts = computed(() => {
  const t = cur.value?.trend ?? []
  if (t.length < 2) return []
  const min = Math.min(...t)
  const max = Math.max(...t)
  const span = max - min || 1
  return t.map((v, i) => ({
    x: PAD + (i * (W - PAD * 2)) / (t.length - 1),
    y: PAD + (1 - (v - min) / span) * (H - PAD * 2),
    v,
  }))
})
const polyline = computed(() => linePts.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))

/* ---- 指标切换按钮（对齐原型：支付金额 / 支付用户数 / 近7天支付金额） ---- */
const switchItems = computed(() =>
  [0, 2, 1]
    .filter((i) => indicators.value[i])
    .map((i) => ({ i, label: indicators.value[i].name })),
)

/* ---- 渠道拆解（对齐原型静态演示数据） ---- */
const donutItems = [
  { name: '支付宝', value: 528210, color: '#1668dc' },
  { name: '微信支付', value: 451870, color: '#16a34a' },
  { name: '银联', value: 122400, color: '#d97706' },
  { name: '银行卡', value: 68900, color: '#7c3aed' },
]
const donutTotal = donutItems.reduce((s, it) => s + it.value, 0)
const donutStyle = computed(() => {
  let acc = 0
  const segs = donutItems.map((it) => {
    const from = (acc / donutTotal) * 360
    acc += it.value
    const to = (acc / donutTotal) * 360
    return `${it.color} ${from.toFixed(2)}deg ${to.toFixed(2)}deg`
  })
  return { background: `conic-gradient(${segs.join(',')})` }
})
const donutCenter = computed(() => `${Math.round(donutTotal / 10000)}万`)
</script>

<template>
  <div class="page">
    <div class="board-grid">
      <!-- 左：核心指标趋势 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="sec-head">
            核心指标趋势{{ cur ? `（${cur.name} · 单位 ${cur.unit}）` : '' }}
          </span>
        </div>
        <template v-if="cur">
          <div class="mini-row">
            <div class="mini-stat">
              <div class="mini-num">{{ todayVal }}</div>
              <div class="mini-label">今日 {{ cur.unit }}</div>
            </div>
            <div class="mini-stat">
              <div class="mini-num" :style="{ color: Number(dayOverDay) >= 0 ? 'var(--success)' : 'var(--danger)' }">
                {{ Number(dayOverDay) >= 0 ? '+' : '' }}{{ dayOverDay }}%
              </div>
              <div class="mini-label">日环比</div>
            </div>
            <div class="mini-stat">
              <div class="mini-num">{{ avg8 }}</div>
              <div class="mini-label">近8日均</div>
            </div>
            <div class="mini-stat">
              <div class="mini-num" :style="{ color: Number(vs8d) >= 0 ? 'var(--success)' : 'var(--danger)' }">
                {{ Number(vs8d) >= 0 ? '+' : '' }}{{ vs8d }}%
              </div>
              <div class="mini-label">较8日前</div>
            </div>
          </div>

          <svg :viewBox="`0 0 ${W} ${H}`" class="trend-svg" preserveAspectRatio="none">
            <polyline :points="polyline" fill="none" stroke="#1668dc" stroke-width="2" />
            <circle v-for="(p, i) in linePts" :key="i" :cx="p.x" :cy="p.y" r="3" fill="#1668dc" />
          </svg>

          <div class="switch-row">
            <button
              v-for="it in switchItems"
              :key="it.i"
              class="op-btn"
              :class="{ 'op-btn--on': activeIdx === it.i }"
              @click="activeIdx = it.i"
            >{{ it.label }}</button>
          </div>
        </template>
        <div v-else class="empty">暂无指标数据</div>
      </div>

      <!-- 右：渠道拆解 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="sec-head">渠道拆解（支付金额占比）</span>
        </div>
        <div class="donut-wrap">
          <div class="donut" :style="donutStyle">
            <div class="donut-center">
              <b>{{ donutCenter }}</b>
              <span>昨日支付金额</span>
            </div>
          </div>
          <div class="legend">
            <div v-for="it in donutItems" :key="it.name" class="legend-line">
              <span class="dot" :style="{ background: it.color }" />
              <span>{{ it.name }}</span>
              <span class="legend-val mono">{{ it.value.toLocaleString() }}</span>
            </div>
          </div>
        </div>
        <div class="hint">数据来源 dws_pay_summary_daily dt=2026-09-11，与指标「支付金额」技术口径一致（不含退款）。</div>
      </div>
    </div>

    <!-- 指标健康度 -->
    <div class="card" style="padding:16px;margin-top:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">指标健康度</span>
        <span class="spacer" />
        <button class="op-btn" @click="router.push('/ind/consistency')">一致性检查</button>
      </div>
      <div class="health-row">
        <div v-for="m in indicators.slice(0, 3)" :key="m.id" class="health-card">
          <span class="type-icon" style="background:#16a34a">✦</span>
          <div>
            <b style="font-size:12.5px">{{ m.name }}</b>
            <div style="font-size:11px;color:var(--text-3)">产出正常 · 口径一致 · 负责人 {{ m.owner }}</div>
          </div>
        </div>
      </div>
      <div v-if="indicators.length === 0" class="empty">暂无指标数据</div>
    </div>
  </div>
</template>

<style scoped>
.board-grid{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;align-items:start}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.tbl-toolbar .spacer{flex:1}
.mini-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
.mini-stat{background:var(--bg);border-radius:var(--radius);padding:10px 12px}
.mini-num{font-size:19px;font-weight:700}
.mini-label{font-size:11px;color:var(--text-3);margin-top:2px}
.trend-svg{width:100%;height:160px;display:block}
.switch-row{display:flex;gap:8px;margin-top:10px}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.op-btn--on{background:var(--primary-light);color:var(--primary);border-color:rgba(22,104,220,.4)}
.donut-wrap{display:flex;gap:16px;align-items:center}
.donut{width:150px;height:150px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.donut-center{width:96px;height:96px;border-radius:50%;background:var(--card);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px}
.donut-center b{font-size:17px}
.donut-center span{font-size:10px;color:var(--text-3)}
.legend{flex:1;display:flex;flex-direction:column;gap:7px}
.legend-line{display:flex;align-items:center;gap:7px;font-size:12px}
.legend-line .dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.legend-val{margin-left:auto;color:var(--text-2);font-size:11.5px}
.hint{font-size:11.5px;color:var(--text-3);margin-top:12px;line-height:1.6}
.health-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.health-card{display:flex;align-items:center;gap:10px;background:var(--bg);border-radius:var(--radius);padding:12px 14px}
.type-icon{width:32px;height:32px;border-radius:var(--radius);display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;flex-shrink:0}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
</style>
