<script setup lang="ts">
/**
 * M07 专项质量报告（/qc/report-dag）—— 三级报告体系之「专项报告（DAG工作流级）」
 * 聚合 DAG 工作流涉及的全部资产表（nodesDetail.outTable）的质量检查结果：
 * 工作流列表（左侧筛选）→ 选中后展示 汇总卡 + 表明细（规则/异常）+ Quality Gate 判定记录；
 * 可「生成专项报告」写入 qcReports（type=专项），在总体报告中可查。
 * 数据：workflows / qcRules / qcExceptions / metaTables / qcReports（写入）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { WorkflowMeta, QcRule, QcException, MetaTable } from '../../services/types'

const router = useRouter()

const wfs = ref<WorkflowMeta[]>([])
const rules = ref<QcRule[]>([])
const exceptions = ref<QcException[]>([])
const tables = ref<MetaTable[]>([])

onMounted(async () => {
  const [w, r, e, t] = await Promise.all([
    dataStore.list<WorkflowMeta>('workflows'),
    dataStore.list<QcRule>('qcRules'),
    dataStore.list<QcException>('qcExceptions'),
    dataStore.list<MetaTable>('metaTables'),
  ])
  wfs.value = [...(w ?? [])]
  rules.value = [...(r ?? [])]
  exceptions.value = [...(e ?? [])]
  tables.value = [...(t ?? [])]
  if (wfs.value.length > 0) selected.value = wfs.value[0].id
})

/* ---- 左侧搜索筛选（约定：主窗口为列表的页面左侧必有筛选面板） ---- */
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '', lastResult: '' })
const facets = computed<Facet[]>(() => [
  { key: 'status', label: '上线状态', options: [{ v: 'online', t: '已上线' }, { v: 'offline', t: '已下线' }] },
  { key: 'lastResult', label: '最近结果', options: [{ v: 'success', t: '成功' }, { v: 'failed', t: '失败' }] },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return wfs.value.filter((w) => {
    if (filters.value.status && w.status !== filters.value.status) return false
    if (filters.value.lastResult && w.lastResult !== filters.value.lastResult) return false
    if (!kw) return true
    return [w.id, w.name, w.desc, w.owner].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 选中工作流 ---- */
const selected = ref('')
const wf = computed(() => wfs.value.find((w) => w.id === selected.value) ?? null)

/* 涉及资产表（产出表 ≠ '-'） */
function tablesOf(w: WorkflowMeta): string[] {
  return [...new Set(w.nodesDetail.map((n) => n.outTable).filter((t) => t && t !== '-'))]
}

function tableMeta(name: string): MetaTable | undefined {
  return tables.value.find((t) => t.name === name)
}
function rulesOf(table: string): QcRule[] {
  return rules.value.filter((r) => r.table === table && r.status === 'enabled')
}
function pendingOf(table: string): number {
  return exceptions.value.filter((e) => e.table === table && e.status === 'pending').reduce((s, e) => s + e.cnt, 0)
}

interface TableStat {
  name: string
  layer: string
  domain: string
  rules: number
  strongFail: number
  weakFail: number
  pendingCnt: number
  gate: 'pass' | 'fail'
  score: number
}

/* 表级聚合纯函数：列表行（per-workflow）与选中明细共用，保证 Gate/评分全页一致 */
function tableStatsOf(w: WorkflowMeta): TableStat[] {
  return tablesOf(w).map((name) => {
    const rs = rulesOf(name)
    const strongFail = rs.filter((r) => r.level === '强规则' && r.lastResult === 'fail').length
    const weakFail = rs.filter((r) => r.level === '弱规则' && r.lastResult === 'fail').length
    const pendingCnt = pendingOf(name)
    const gate: 'pass' | 'fail' = strongFail > 0 || pendingCnt > 0 ? 'fail' : 'pass'
    const score = Math.max(60, 100 - strongFail * 8 - weakFail * 3 - Math.min(20, Math.floor(pendingCnt / 10) * 2))
    const meta = tableMeta(name)
    return { name, layer: meta?.layer ?? '-', domain: meta?.domain ?? '-', rules: rs.length, strongFail, weakFail, pendingCnt, gate, score }
  })
}

const tableStats = computed<TableStat[]>(() => (wf.value ? tableStatsOf(wf.value) : []))

/* 列表行 Gate/评分：按工作流一次性聚合（computed map，避免模板每行重复计算） */
const wfStatsMap = computed<Record<string, { gate: 'pass' | 'fail'; score: number }>>(() => {
  const map: Record<string, { gate: 'pass' | 'fail'; score: number }> = {}
  for (const w of wfs.value) {
    const ts = tableStatsOf(w)
    map[w.id] = {
      gate: ts.some((t) => t.gate === 'fail') ? 'fail' : 'pass',
      score: ts.length ? Math.round(ts.reduce((s, t) => s + t.score, 0) / ts.length) : 100,
    }
  }
  return map
})
function gateOf(w: WorkflowMeta): 'pass' | 'fail' {
  return wfStatsMap.value[w.id]?.gate ?? 'pass'
}
function scoreOf(w: WorkflowMeta): number {
  return wfStatsMap.value[w.id]?.score ?? 100
}

const summary = computed(() => {
  const ts = tableStats.value
  const strongFail = ts.reduce((s, t) => s + t.strongFail, 0)
  const weakFail = ts.reduce((s, t) => s + t.weakFail, 0)
  const pendingCnt = ts.reduce((s, t) => s + t.pendingCnt, 0)
  const gateFail = ts.some((t) => t.gate === 'fail')
  const rulesCnt = ts.reduce((s, t) => s + t.rules, 0)
  const score = ts.length ? Math.round(ts.reduce((s, t) => s + t.score, 0) / ts.length) : 100
  return { tables: ts.length, rulesCnt, strongFail, weakFail, pendingCnt, gateFail, score }
})

/* ---- Quality Gate 判定记录（按节点产出表聚合，闸门规则 = 强规则失败数 = 0 且无待处理异常） ---- */
interface GateRecord {
  node: string
  table: string
  ruleDesc: string
  result: 'pass' | 'fail'
  policy: string
  at: string
}
const gateRecords = computed<GateRecord[]>(() => {
  const w = wf.value
  if (!w) return []
  return w.nodesDetail
    .filter((n) => n.outTable && n.outTable !== '-')
    .map((n) => {
      const stat = tableStats.value.find((t) => t.name === n.outTable)
      return {
        node: `${n.name}（${n.type}）`,
        table: n.outTable,
        ruleDesc: '强规则失败数 = 0 且无待处理异常',
        result: (stat?.gate ?? 'pass') as 'pass' | 'fail',
        policy: stat && stat.strongFail > 0 ? '阻断：跳过下游节点并即时告警' : '放行：继续执行下游节点',
        at: w.lastRun,
      }
    })
})

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

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* ---- 生成专项报告（写入 qcReports，总体报告可查） ---- */
async function genSpecial() {
  const w = wf.value
  if (!w) return
  const s = summary.value
  const id = `QR-${today().replace(/-/g, '')}-SP${w.id.replace(/\D/g, '')}`
  await dataStore.save('qcReports', {
    id,
    name: `专项质量报告 - ${w.name}`,
    type: '专项',
    period: today(),
    score: s.score,
    problems: s.strongFail + s.weakFail + (s.pendingCnt > 0 ? 1 : 0),
    fixed: Math.max(0, s.pendingCnt > 2 ? 2 : 0),
    status: 'published',
  })
  ElMessage.success(`专项报告已生成：${id}（可在总体报告中查阅）`)
}

function goDetailTable(name: string) {
  router.push({ path: '/qc/report-table', query: { table: name } })
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索工作流/描述/负责人"
      :result-count="filtered.length"
      :total-count="wfs.length"
    />
    <div style="flex:1;min-width:0">
      <!-- 页头 -->
      <div class="card page-head">
        <div>
          <div class="ph-title">专项质量报告（DAG工作流级）</div>
          <div class="ph-desc">按工作流聚合其涉及的全部资产表质量结果 + Quality Gate 判定记录；与总体/细项报告互通</div>
        </div>
        <div class="ph-acts">
          <button class="tb-new" :disabled="!wf" @click="genSpecial">+ 生成专项报告</button>
          <button class="op-btn" @click="router.push('/qc/report')">总体报告</button>
          <button class="op-btn" @click="router.push('/qc/report-table')">细项报告</button>
        </div>
      </div>

      <!-- 工作流列表 -->
      <div class="card panel">
        <div class="tbl-toolbar">
          <span class="sec-head">工作流列表</span>
          <span class="pill info">{{ filtered.length }} / {{ wfs.length }}</span>
          <span class="spacer" />
        </div>
        <table class="tbl">
          <thead>
            <tr><th>工作流</th><th>调度</th><th>节点</th><th>涉及表</th><th>最近结果</th><th>Gate</th><th>评分</th><th style="width:90px">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="w in filtered" :key="w.id" :class="{ on: selected === w.id }" @click="selected = w.id">
              <td>
                <a @click.stop="selected = w.id"><b>{{ w.name }}</b></a>
                <div style="font-size:11px;color:var(--text-3)">{{ w.id }} · {{ w.owner }}</div>
              </td>
              <td class="mono" style="font-size:11px">{{ w.cron }}</td>
              <td>{{ w.nodes }}</td>
              <td>{{ tablesOf(w).length }}</td>
              <td><span class="st" :class="stCls(w.lastResult)"><span class="dot" />{{ stLabel(w.lastResult) }}</span></td>
              <td><span class="st" :class="gateOf(w) === 'fail' ? 'st-red' : 'st-green'"><span class="dot" />{{ gateOf(w) === 'fail' ? '未通过' : '通过' }}</span></td>
              <td><b :style="{ color: scoreColor(scoreOf(w)) }">{{ scoreOf(w) }}</b></td>
              <td><button class="op-btn primary" @click.stop="selected = w.id">查看报告</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">未找到匹配的工作流，请调整筛选条件</div>
      </div>

      <!-- 专项报告明细 -->
      <template v-if="wf">
        <div class="stat-grid">
          <div class="card stat-card">
            <span class="sc-icon" style="background:#1668dc">▤</span>
            <div><div class="stat-num">{{ summary.tables }}</div><div class="stat-label">涉及资产表</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" style="background:#7c3aed">⌇</span>
            <div><div class="stat-num">{{ summary.rulesCnt }}</div><div class="stat-label">绑定规则（启用）</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" style="background:#e5484d">⚑</span>
            <div><div class="stat-num">{{ summary.strongFail }}</div><div class="stat-label">强规则失败</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" style="background:#d97706">◉</span>
            <div><div class="stat-num">{{ summary.pendingCnt }}</div><div class="stat-label">待处理异常行</div></div>
          </div>
          <div class="card stat-card">
            <span class="sc-icon" :style="{ background: summary.gateFail ? '#e5484d' : '#16a34a' }">{{ summary.gateFail ? '✗' : '✓' }}</span>
            <div><div class="stat-num" :style="{ color: scoreColor(summary.score) }">{{ summary.score }}</div><div class="stat-label">专项评分 · Gate{{ summary.gateFail ? '未通过' : '通过' }}</div></div>
          </div>
        </div>

        <div class="card panel">
          <div class="tbl-toolbar">
            <span class="sec-head">涉及表明细 — {{ wf.name }}</span>
            <span class="pill info">{{ wf.desc }}</span>
            <span class="spacer" />
          </div>
          <table class="tbl">
            <thead>
              <tr><th>表名</th><th>分层</th><th>业务域</th><th>规则数</th><th>强规则失败</th><th>弱规则失败</th><th>待处理异常</th><th>Gate</th><th>评分</th><th style="width:150px">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in tableStats" :key="t.name">
                <td><a @click="goDetailTable(t.name)"><span class="mono">{{ t.name }}</span></a></td>
                <td><span class="pill info">{{ t.layer }}</span></td>
                <td>{{ t.domain }}</td>
                <td>{{ t.rules }}</td>
                <td :style="{ color: t.strongFail ? 'var(--danger)' : 'var(--text-2)' }">{{ t.strongFail }}</td>
                <td :style="{ color: t.weakFail ? 'var(--warn)' : 'var(--text-2)' }">{{ t.weakFail }}</td>
                <td :style="{ color: t.pendingCnt ? 'var(--warn)' : 'var(--text-2)' }">{{ t.pendingCnt }}</td>
                <td><span class="st" :class="t.gate === 'fail' ? 'st-red' : 'st-green'"><span class="dot" />{{ t.gate === 'fail' ? '未通过' : '通过' }}</span></td>
                <td><b :style="{ color: scoreColor(t.score) }">{{ t.score }}</b></td>
                <td>
                  <button class="op-btn primary" @click="goDetailTable(t.name)">细项报告</button>
                  <button class="op-btn" @click="router.push('/qc/exception')">异常</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card panel">
          <div class="tbl-toolbar">
            <span class="sec-head">Quality Gate 判定记录</span>
            <span class="pill purple">闸门规则：强规则失败数 = 0 且无待处理异常</span>
            <span class="spacer" />
          </div>
          <table class="tbl">
            <thead>
              <tr><th>节点</th><th>产出表</th><th>闸门规则</th><th>判定结果</th><th>策略</th><th>判定时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="(g, i) in gateRecords" :key="i">
                <td>{{ g.node }}</td>
                <td><span class="mono" style="font-size:11.5px">{{ g.table }}</span></td>
                <td style="font-size:11.5px">{{ g.ruleDesc }}</td>
                <td><span class="st" :class="g.result === 'fail' ? 'st-red' : 'st-green'"><span class="dot" />{{ g.result === 'fail' ? '未通过' : '通过' }}</span></td>
                <td :style="{ fontSize: '11.5px', color: g.result === 'fail' ? 'var(--danger)' : 'var(--text-2)' }">{{ g.policy }}</td>
                <td class="mono" style="font-size:11px">{{ g.at }}</td>
              </tr>
            </tbody>
          </table>
          <div class="lock-tip">运行时下游节点可引用上游部分结果数据并按 Gate 判定决定是否继续执行（同周期/同批次依赖条件在 DAG 依赖页配置）。</div>
        </div>
      </template>
    </div>
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
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tbody tr:hover{background:var(--bg)}
.tbl tbody tr.on{background:var(--primary-light)}
.lock-tip{background:var(--warn-bg);color:var(--warn);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;margin-top:10px}
.empty{padding:24px;text-align:center;color:var(--text-3);font-size:12.5px}
.stat-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:12px}
.stat-card{padding:12px 14px;display:flex;align-items:center;gap:10px}
.stat-num{font-size:20px;font-weight:700;line-height:1.2}
.stat-label{font-size:11px;color:var(--text-3);margin-top:2px}
.sc-icon{width:30px;height:30px;border-radius:var(--radius);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:14px;flex:none}
.mono{font-family:ui-monospace,Consolas,monospace}
a{cursor:pointer;color:var(--primary)}
</style>
