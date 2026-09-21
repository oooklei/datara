<script setup lang="ts">
/**
 * M07 细项质量报告（/qc/report-table）—— 三级报告体系之「细项报告（表级）」
 * 指定表视角：全表检索（左侧筛选）→ 选中表展示 汇总卡 + 规则绑定明细 + 异常记录（抽样 drawer）；
 * 支持 route.query.table 直达（专项报告「细项报告」/ 资产地图「质量分」入口）；
 * 「生成细项报告」写入 qcReports（type=细项），在总体报告中可查。
 * 数据：metaTables / qcRules / qcExceptions / qcReports（写入）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { MetaTable, QcRule, QcException, QcReport } from '../../services/types'

const route = useRoute()
const router = useRouter()

const tables = ref<MetaTable[]>([])
const rules = ref<QcRule[]>([])
const exceptions = ref<QcException[]>([])
const reports = ref<QcReport[]>([])

const keyword = ref('')
const filters = ref<Record<string, string>>({ layer: '', domain: '' })
const selected = ref('')

onMounted(async () => {
  const [t, r, e, rp] = await Promise.all([
    dataStore.list<MetaTable>('metaTables'),
    dataStore.list<QcRule>('qcRules'),
    dataStore.list<QcException>('qcExceptions'),
    dataStore.list<QcReport>('qcReports'),
  ])
  tables.value = [...(t ?? [])]
  rules.value = [...(r ?? [])]
  exceptions.value = [...(e ?? [])]
  reports.value = [...(rp ?? [])]
  /* query.table 直达：预置关键字并选中该表（来源：专项报告/资产地图入口） */
  const q = route.query.table
  const name = Array.isArray(q) ? q[0] : q
  if (name) {
    keyword.value = name
    const hit = tables.value.find((x) => x.name === name)
    if (hit) selected.value = hit.id
  } else if (tables.value.length > 0) {
    selected.value = tables.value[0].id
  }
})

/* ---- 左侧搜索筛选 ---- */
const facets = computed<Facet[]>(() => [
  { key: 'layer', label: '数仓分层', options: [...new Set(tables.value.map((t) => t.layer))].map((v) => ({ v, t: v })) },
  { key: 'domain', label: '业务域', options: [...new Set(tables.value.map((t) => t.domain))].map((v) => ({ v, t: v })) },
])
const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return tables.value.filter((t) => {
    if (filters.value.layer && t.layer !== filters.value.layer) return false
    if (filters.value.domain && t.domain !== filters.value.domain) return false
    if (!kw) return true
    return [t.id, t.name, t.desc, t.owner].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 选中表明细 ---- */
const table = computed(() => tables.value.find((t) => t.id === selected.value) ?? null)
const tableRules = computed(() => (table.value ? rules.value.filter((r) => r.table === table.value!.name) : []))
const tableExceptions = computed(() => (table.value ? exceptions.value.filter((e) => e.table === table.value!.name) : []))

function rulesEnabledOf(name: string): QcRule[] {
  return rules.value.filter((r) => r.table === name && r.status === 'enabled')
}
function pendingCntOf(name: string): number {
  return exceptions.value.filter((e) => e.table === name && e.status === 'pending').reduce((s, e) => s + e.cnt, 0)
}
function scoreOfName(name: string): { gate: 'pass' | 'fail'; score: number } {
  const rs = rulesEnabledOf(name)
  const strongFail = rs.filter((r) => r.level === '强规则' && r.lastResult === 'fail').length
  const weakFail = rs.filter((r) => r.level === '弱规则' && r.lastResult === 'fail').length
  const pending = pendingCntOf(name)
  return {
    gate: strongFail > 0 || pending > 0 ? 'fail' : 'pass',
    score: Math.max(60, 100 - strongFail * 8 - weakFail * 3 - Math.min(20, Math.floor(pending / 10) * 2)),
  }
}

/* 列表行 Gate/评分：一次性聚合（computed map，避免模板每行重复计算） */
const tblStatsMap = computed<Record<string, { gate: 'pass' | 'fail'; score: number }>>(() => {
  const map: Record<string, { gate: 'pass' | 'fail'; score: number }> = {}
  for (const t of tables.value) map[t.id] = scoreOfName(t.name)
  return map
})
function gateOf(t: MetaTable): 'pass' | 'fail' {
  return tblStatsMap.value[t.id]?.gate ?? 'pass'
}
function scoreOf(t: MetaTable): number {
  return tblStatsMap.value[t.id]?.score ?? 100
}

const stats = computed(() => {
  const name = table.value?.name ?? ''
  const rs = rulesEnabledOf(name)
  const all = tableRules.value
  const strongFail = rs.filter((r) => r.level === '强规则' && r.lastResult === 'fail').length
  const weakFail = rs.filter((r) => r.level === '弱规则' && r.lastResult === 'fail').length
  const pending = pendingCntOf(name)
  const g = scoreOfName(name)
  return { rules: rs.length, total: all.length, strongFail, weakFail, pending, gate: g.gate, score: g.score }
})

/* ---- 抽样 drawer ---- */
const sampleVisible = ref(false)
const sampleTarget = ref<QcException | null>(null)
const sampleKeys = computed(() =>
  sampleTarget.value?.sample?.length ? Object.keys(sampleTarget.value.sample[0]) : [],
)
function openSample(e: QcException) {
  sampleTarget.value = e
  sampleVisible.value = true
}

/* ---- 状态徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function scoreColor(score: number): string {
  return score >= 95 ? 'var(--success)' : score >= 90 ? 'var(--warn)' : 'var(--danger)'
}
function resultCls(r: string): string {
  return r === 'fail' ? 'st-red' : r === 'pass' ? 'st-green' : 'st-gray'
}
function resultLabel(r: string): string {
  return r === 'fail' ? '失败' : r === 'pass' ? '通过' : r === 'pending' ? '待核查' : r
}

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* ---- 生成细项报告（写入 qcReports，总体报告可查） ---- */
async function genDetail() {
  const t = table.value
  if (!t) return
  const s = stats.value
  const id = `QR-${today().replace(/-/g, '')}-TB${t.id.replace(/\D/g, '')}`
  await dataStore.save('qcReports', {
    id,
    name: `细项质量报告 - ${t.name}`,
    type: '细项',
    period: today(),
    score: s.score,
    problems: s.strongFail + s.weakFail + (s.pending > 0 ? 1 : 0),
    fixed: 0,
    status: 'published',
  })
  reports.value = [...((await dataStore.list<QcReport>('qcReports')) ?? [])]
  ElMessage.success(`细项报告已生成：${id}（可在总体报告中查阅）`)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索表名/描述/负责人"
      :result-count="filtered.length"
      :total-count="tables.length"
    />
    <div style="flex:1;min-width:0">
      <!-- 页头 -->
      <div class="card page-head">
        <div>
          <div class="ph-title">细项质量报告（表级）</div>
          <div class="ph-desc">指定表的质量结果：规则绑定明细 + 异常记录（可抽样）+ 表级评分；与总体/专项报告互通</div>
        </div>
        <div class="ph-acts">
          <button class="tb-new" :disabled="!table" @click="genDetail">+ 生成细项报告</button>
          <button class="op-btn" @click="router.push('/qc/report')">总体报告</button>
          <button class="op-btn" @click="router.push('/qc/report-dag')">专项报告</button>
        </div>
      </div>

      <!-- 资产表列表 -->
      <div class="card panel">
        <div class="tbl-toolbar">
          <span class="sec-head">资产表列表</span>
          <span class="pill info">{{ filtered.length }} / {{ tables.length }}</span>
          <span class="spacer" />
        </div>
        <table class="tbl">
          <thead>
            <tr><th>表名</th><th>分层</th><th>业务域</th><th>行数</th><th>负责人</th><th>Gate</th><th>评分</th><th style="width:90px">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in filtered" :key="t.id" :class="{ on: selected === t.id }" @click="selected = t.id">
              <td><a @click.stop="selected = t.id"><span class="mono"><b>{{ t.name }}</b></span></a></td>
              <td><span class="pill info">{{ t.layer }}</span></td>
              <td>{{ t.domain }}</td>
              <td>{{ t.rows }}</td>
              <td style="color:var(--text-2)">{{ t.owner }}</td>
              <td><span class="st" :class="gateOf(t) === 'fail' ? 'st-red' : 'st-green'"><span class="dot" />{{ gateOf(t) === 'fail' ? '未通过' : '通过' }}</span></td>
              <td><b :style="{ color: scoreColor(scoreOf(t)) }">{{ scoreOf(t) }}</b></td>
              <td><button class="op-btn primary" @click.stop="selected = t.id">查看报告</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">未找到匹配的资产表，请调整筛选条件</div>
      </div>

      <!-- 细项报告明细 -->
      <template v-if="table">
        <div class="stat-grid">
          <div class="card stat-card">
            <span class="sc-icon" style="background:#1668dc">▤</span>
            <div><div class="stat-num">{{ stats.total }}</div><div class="stat-label">绑定规则（{{ stats.rules }} 启用）</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" style="background:#e5484d">⚑</span>
            <div><div class="stat-num">{{ stats.strongFail }}</div><div class="stat-label">强规则失败</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" style="background:#d97706">◈</span>
            <div><div class="stat-num">{{ stats.weakFail }}</div><div class="stat-label">弱规则失败</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" style="background:#7c3aed">◉</span>
            <div><div class="stat-num">{{ stats.pending }}</div><div class="stat-label">待处理异常行</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" :style="{ background: stats.gate === 'fail' ? '#e5484d' : '#16a34a' }">{{ stats.gate === 'fail' ? '✗' : '✓' }}</span>
            <div><div class="stat-num" :style="{ color: scoreColor(stats.score) }">{{ stats.score }}</div><div class="stat-label">表级评分 · Gate{{ stats.gate === 'fail' ? '未通过' : '通过' }}</div></div>
          </div>
        </div>

        <div class="card panel">
          <div class="tbl-toolbar">
            <span class="sec-head">规则绑定明细 — {{ table.name }}</span>
            <span class="pill info">{{ table.desc }}</span>
            <span class="spacer" />
          </div>
          <table class="tbl">
            <thead>
              <tr><th>规则</th><th>字段</th><th>维度</th><th>类型</th><th>级别</th><th>阈值</th><th>状态</th><th>最近结果</th><th style="width:70px">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in tableRules" :key="r.id">
                <td>
                  <b>{{ r.name }}</b>
                  <span v-if="r.builtin" class="pill purple" style="margin-left:5px">预制</span>
                  <div class="mono" style="font-size:11px;color:var(--text-3)">{{ r.id }}</div>
                </td>
                <td class="mono" style="font-size:11.5px">{{ r.field }}</td>
                <td>{{ r.dim }}</td>
                <td style="font-size:11.5px;color:var(--text-2)">{{ r.type }}</td>
                <td><span class="pill" :class="r.level === '强规则' ? 'warn' : 'info'">{{ r.level }}</span></td>
                <td class="mono" style="font-size:11px">{{ r.threshold }}</td>
                <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
                <td><span class="st" :class="resultCls(r.lastResult)"><span class="dot" />{{ resultLabel(r.lastResult) }}</span></td>
                <td><button v-if="tableExceptions.some((e) => e.ruleId === r.id)" class="op-btn" @click="openSample(tableExceptions.find((e) => e.ruleId === r.id)!)">抽样</button></td>
              </tr>
            </tbody>
          </table>
          <div v-if="tableRules.length === 0" class="empty">该表未绑定质量规则</div>
        </div>

        <div class="card panel">
          <div class="tbl-toolbar">
            <span class="sec-head">异常记录</span>
            <span class="pill info">{{ tableExceptions.length }} 条</span>
            <span class="spacer" />
          </div>
          <table class="tbl">
            <thead>
              <tr><th>异常单</th><th>规则</th><th>字段</th><th>异常行数</th><th>数据日期</th><th>状态</th><th style="width:80px">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in tableExceptions" :key="e.id">
                <td><span class="mono" style="font-size:11.5px">{{ e.id }}</span></td>
                <td>{{ e.ruleName }}</td>
                <td class="mono" style="font-size:11.5px">{{ e.field }}</td>
                <td :style="{ color: e.cnt ? 'var(--warn)' : 'var(--text-2)' }"><b>{{ e.cnt }}</b></td>
                <td class="mono" style="font-size:11px">{{ e.dt }}</td>
                <td><span class="st" :class="stCls(e.status)"><span class="dot" />{{ stLabel(e.status) }}</span></td>
                <td><button class="op-btn primary" @click="openSample(e)">抽样</button></td>
              </tr>
            </tbody>
          </table>
          <div v-if="tableExceptions.length === 0" class="empty">该表暂无异常记录</div>
        </div>
      </template>
    </div>

    <!-- 抽样数据 drawer -->
    <el-drawer v-model="sampleVisible" :title="sampleTarget ? `异常抽样 — ${sampleTarget.ruleName}` : '异常抽样'" size="560px">
      <template v-if="sampleTarget">
        <div class="desc-grid">
          <div class="d-row"><span class="d-k">异常单</span><span class="mono">{{ sampleTarget.id }}</span></div>
          <div class="d-row"><span class="d-k">表 / 字段</span><span class="mono">{{ sampleTarget.table }}.{{ sampleTarget.field }}</span></div>
          <div class="d-row"><span class="d-k">异常行数</span><span><b style="color:var(--warn)">{{ sampleTarget.cnt }}</b></span></div>
          <div class="d-row"><span class="d-k">数据日期</span><span class="mono">{{ sampleTarget.dt }}</span></div>
        </div>
        <div class="sec-title">抽样数据（前 {{ sampleTarget.sample.length }} 行）</div>
        <div v-if="sampleKeys.length" class="sample-wrap">
          <table class="tbl sample">
            <thead>
              <tr><th v-for="k in sampleKeys" :key="k">{{ k }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in sampleTarget.sample" :key="i">
                <td v-for="k in sampleKeys" :key="k" class="mono">{{ row[k] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">无抽样数据</div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page-head{padding:14px 16px;display:flex;align-items:flex-start;gap:10px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.ph-acts{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.panel{padding:14px 16px;margin-top:12px}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.tbl-toolbar .spacer{flex:1}
.pill{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500}
.pill.info{background:var(--info-bg);color:var(--info)}
.pill.purple{background:#f1eaff;color:var(--purple)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tbody tr:hover{background:var(--bg)}
.tbl tbody tr.on{background:var(--primary-light)}
.empty{padding:24px;text-align:center;color:var(--text-3);font-size:12.5px}
.stat-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:12px}
.stat-card{padding:12px 14px;display:flex;align-items:center;gap:10px}
.stat-num{font-size:20px;font-weight:700;line-height:1.2}
.stat-label{font-size:11px;color:var(--text-3);margin-top:2px}
.sc-icon{width:30px;height:30px;border-radius:var(--radius);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:14px;flex:none}
.mono{font-family:ui-monospace,Consolas,monospace}
a{cursor:pointer;color:var(--primary)}
.desc-grid{display:flex;flex-direction:column;margin-bottom:10px}
.d-row{display:flex;gap:12px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:12.5px}
.d-k{width:88px;color:var(--text-3);flex-shrink:0}
.sec-title{font-weight:700;font-size:13px;margin:14px 0 8px;color:var(--text)}
.sample-wrap{overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm);max-height:60vh}
.sample th{background:var(--bg);position:sticky;top:0}
.sample td{white-space:nowrap;font-size:11.5px}
</style>
